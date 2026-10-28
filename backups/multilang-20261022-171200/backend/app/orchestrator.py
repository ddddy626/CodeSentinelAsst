"""LangGraph Planner -> Scanner -> Architect -> conditional recheck workflow.

The graph contains a review back edge, so it is a state graph, not a DAG.
Job/event persistence lives in Store; graph replay starts a job from its source.
"""

from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from . import llm, tools
from .context import select_context
from .review import adjudicate, scan_source, validate_source
from .schemas import (ArchitectAssessment, Evidence, ReviewReport, ReviewRequest,
                      ScanResult, ToolCandidate)

MAX_REVIEW_ROUNDS = 5


class ReviewState(TypedDict, total=False):
    payload: ReviewRequest
    scan: ScanResult
    report: ReviewReport
    round: int
    gained: bool


def build_graph(emit: Callable[[str, str], None],
                save_round: Callable[[int], None], context_budget: int = 12_000,
                task_id: str | None = None):
    def planner(state: ReviewState):
        validate_source(state["payload"])
        emit("planned", "Planner：已验证 Python 文件，选择静态工具与模型扫描员")
        return {"round": state["round"], "gained": True}

    def scanner(state: ReviewState):
        scan = scan_source(state["payload"], context_budget, task_id)
        emit("specialist", f"扫描器：工具候选 {len(scan.tool_drafts)} 项，模型候选 {len(scan.model_drafts)} 项；源码 SHA256 {scan.source_hash}")
        return {"scan": scan}

    def architect(state: ReviewState):
        report = adjudicate(state["payload"], state["scan"])
        if state["round"] > 0 and "report" in state:
            previous = {(item.rule_id, item.line): item for item in state["report"].findings}
            for finding in report.findings:
                old = previous.get((finding.rule_id, finding.line))
                if old:
                    finding.evidence.extend(e for e in old.evidence if e.source == "Architect")
        if "report" not in state and report.findings:
            context = select_context(state["payload"].source,
                {item.line for item in report.findings}, max_chars=context_budget)
            candidates = [{"finding_id": item.id, "rule_id": item.rule_id,
                           "line": item.line, "severity": item.severity,
                           "evidence": [e.detail[:500] for e in item.evidence]}
                          for item in report.findings[:12]]
            raw, gap = llm.architect_review(context.text, candidates)
            if gap:
                report.coverage.gaps.append(gap)
            accepted = 0
            by_id = {item.id: item for item in report.findings}
            for item in raw:
                try:
                    assessment = ArchitectAssessment.model_validate(item)
                except ValidationError:
                    report.coverage.gaps.append("架构师输出结构校验失败")
                    continue
                finding = by_id.get(assessment.finding_id)
                if finding:
                    assessment_label = {"supported": "支持", "disputed": "存疑", "unknown": "无法判断"}[assessment.assessment]
                    finding.evidence.append(Evidence(origin="llm", source="Architect",
                        detail=f"{assessment_label}：{assessment.reason}"))
                    accepted += 1
            emit("architect", f"架构师模型复核 {accepted} 项；模型意见不单独升级证据等级")
            if report.coverage.gaps and report.decision == "pass":
                report.decision = "comment"
        emit("reviewed", f"架构师复核：裁决 {len(report.findings)} 项发现；复审次数 {state['round']}")
        return {"report": report}

    def route(state: ReviewState):
        uncertain = any(item.disposition == "uncertain" for item in state["report"].findings)
        scanner_gap = any(name in gap for gap in state["scan"].gaps
                          for name in ("Ruff", "Bandit", "Semgrep"))
        if uncertain and scanner_gap and state["round"] < MAX_REVIEW_ROUNDS and state["gained"]:
            return "recheck"
        if uncertain:
            emit("uncertain", "证据不足的候选保留为待核验")
        return END

    def recheck(state: ReviewState):
        next_round = state["round"] + 1
        emit("recheck", f"Reviewer 请求第 {next_round} 次复审：重试失败的静态工具")
        try:
            raw, completed, gaps = tools.run_tools(state["payload"].source)
        except Exception as exc:
            raw, completed, gaps = [], [], [f"复审工具执行异常：{type(exc).__name__}"]
        previous = state["scan"]
        existing = {(item.rule_id, item.line) for item in previous.tool_drafts}
        new_drafts = []
        for item in raw:
            if (item.rule_id, item.line) in existing:
                continue
            try:
                new_drafts.append(ToolCandidate.model_validate(vars(item)))
            except (ValidationError, TypeError):
                gaps.append("复审工具候选结构校验失败")
        previous.tool_drafts.extend(new_drafts)
        previous.completed = list(dict.fromkeys(previous.completed + completed))
        previous.gaps = [gap for gap in previous.gaps
                         if not any(name in gap for name in ("Ruff", "Bandit", "Semgrep"))] + gaps
        save_round(next_round)
        emit("rechecked", f"第 {next_round} 次复审新增 {len(new_drafts)} 项工具候选")
        return {"scan": previous, "round": next_round, "gained": bool(new_drafts)}

    graph = StateGraph(ReviewState)
    graph.add_node("planner", planner)
    graph.add_node("scanner", scanner)
    graph.add_node("architect", architect)
    graph.add_node("recheck", recheck)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "scanner")
    graph.add_edge("scanner", "architect")
    graph.add_conditional_edges("architect", route, {"recheck": "recheck", END: END})
    graph.add_edge("recheck", "architect")
    return graph.compile()


def run_review(payload: ReviewRequest, emit: Callable[[str, str], None],
               save_round: Callable[[int], None],
               context_budget: int = 12_000,
               task_id: str | None = None,
               initial_round: int = 0) -> ReviewReport:
    if not 0 <= initial_round <= MAX_REVIEW_ROUNDS:
        raise ValueError("复审计数超出允许范围")
    save_round(initial_round)
    result = build_graph(emit, save_round, context_budget, task_id).invoke(
        {"payload": payload, "round": initial_round, "gained": True},
        config={"recursion_limit": 20},
    )
    return result["report"]
