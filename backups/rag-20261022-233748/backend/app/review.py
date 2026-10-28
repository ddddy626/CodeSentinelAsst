"""Single-file review orchestration and conservative finding adjudication."""

import ast
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from pydantic import ValidationError

from . import config, llm, tools, verifier
from .context import select_context
from .schemas import (Coverage, Evidence, Finding, ModelCandidate, ReviewReport,
                      ReviewRequest, ScanResult, ToolCandidate, Verification, FILE_LANGUAGES,
                      language_for_filename)


def validate_source(payload: ReviewRequest) -> None:
    if language_for_filename(payload.filename) != payload.language:
        raise HTTPException(status_code=422, detail="文件后缀与所选语言不一致；支持的后缀：" + "、".join(FILE_LANGUAGES))
    if len(payload.filename) > 255 or "/" in payload.filename or "\\" in payload.filename or "\x00" in payload.filename:
        raise HTTPException(status_code=422, detail="文件名无效或超过 255 个字符")
    if not payload.source.strip():
        raise HTTPException(status_code=422, detail="源码不能为空")
    if len(payload.source.encode("utf-8")) > config.MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="源码超过 100 KB 上限")
    if len(payload.source.splitlines()) > config.MAX_SOURCE_LINES:
        raise HTTPException(status_code=413, detail="源码超过 2000 行上限")
    if payload.language == "python":
        try:
            ast.parse(payload.source)
        except SyntaxError as exc:
            raise HTTPException(status_code=422,
                detail=f"Python 语法错误：第 {exc.lineno or '?'} 行") from exc
    if payload.language == "xml":
        try:
            ET.fromstring(payload.source)
        except ET.ParseError as exc:
            raise HTTPException(status_code=422,
                detail=f"XML 格式错误：第 {exc.position[0]} 行") from exc


def run_language_tools(payload: ReviewRequest):
    return (tools.run_tools(payload.source) if payload.language == "python"
            else tools.run_tools(payload.source, payload.language))


def scan_source(payload: ReviewRequest, context_budget: int = 12_000,
                task_id: str | None = None) -> ScanResult:
    validate_source(payload)
    raw_tools, completed, gaps = run_language_tools(payload)
    tool_drafts = []
    for item in raw_tools:
        try:
            tool_drafts.append(ToolCandidate.model_validate(asdict(item)))
        except (ValidationError, TypeError):
            gaps.append("工具候选结构校验失败")
    context = select_context(payload.source, {item.line for item in tool_drafts},
                             max_chars=context_budget, language=payload.language)
    if len(payload.source) > 20_000 or len(payload.source.splitlines()) > 800:
        gaps.append("源码超过建议规模（20000 字符或 800 行）；仍执行全量静态检查，模型上下文可能不完整")
    if context.omitted_ranges:
        gaps.append(f"模型上下文省略原始行范围：{list(context.omitted_ranges)}")
    model_input = (context.text if payload.language == "python" else
                   f"Language: {payload.language}\nOriginal source lines follow:\n{context.text}")
    raw_llm, llm_gap = llm.review_source(model_input)
    llm_drafts = []
    for item in raw_llm:
        try:
            llm_drafts.append(ModelCandidate.model_validate(item))
        except ValidationError:
            gaps.append("LLM 候选结构或源码定位校验失败")
    if llm_gap:
        gaps.append(llm_gap)
    else:
        completed.append("LLM 语义审查")
    return ScanResult(source_hash=context.source_hash, filename=payload.filename,
        language=payload.language,
        task_id=task_id, rule_version=config.RULE_VERSION,
        tool_drafts=tool_drafts, model_drafts=llm_drafts, completed=completed,
        gaps=gaps, context_ranges=list(context.ranges),
        omitted_ranges=list(context.omitted_ranges),
        original_chars=context.original_chars, selected_chars=context.selected_chars)


def adjudicate(payload: ReviewRequest, scan: ScanResult) -> ReviewReport:
    if (scan.source_hash != select_context(payload.source, language=payload.language).source_hash
        or scan.filename != payload.filename or scan.language != payload.language):
        raise ValueError("扫描结果与提交源码版本不一致")
    line_count = len(payload.source.splitlines())
    findings = []
    direct_input_sinks: set[int] = set()
    if payload.language == "python":
        try:
            tree = ast.parse(payload.source)
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in {"eval", "exec"} and node.args
                    and isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Name)
                    and node.args[0].func.id == "input"):
                    direct_input_sinks.add(node.lineno)
        except SyntaxError:
            pass
    seen: dict[tuple[str, int], Finding] = {}
    invalid_tool_count = 0
    for draft in scan.tool_drafts:
        if not 1 <= draft.line <= line_count:
            invalid_tool_count += 1
            continue
        key = (draft.rule_id, draft.line)
        if key in seen:
            seen[key].evidence.append(Evidence(origin="tool", source=draft.tool,
                                               detail=draft.evidence))
            continue
        direct = (draft.tool == "ast" and draft.rule_id == "SEC-DYNAMIC-EXEC"
                  and draft.line in direct_input_sinks and draft.trigger_path is not None)
        finding = Finding(
            id=uuid4().hex,
            rule_id=draft.rule_id,
            title=draft.title,
            explanation=draft.explanation,
            line=draft.line,
            severity=draft.severity,
            evidence_level="strong" if direct else "medium",
            disposition="must_fix" if direct else "suggested",
            evidence=[Evidence(
                origin="tool", source=draft.tool, detail=draft.evidence,
            )],
            suggestion=draft.suggestion,
            trigger_path=draft.trigger_path,
            verification=Verification(
                status="corroborated" if direct else "tool_reported",
                reason=(
                    "同一表达式中 input() 直接进入 eval()/exec()；源码证据充分，仍未执行代码。"
                    if direct else
                    "文件内发现受控输入到该调用的静态可能路径；未执行代码，仍需核查实际可达性。"
                    if draft.trigger_path else
                    "工具报告了该位置；实际触发条件和危害仍需核查。"
                ),
            ),
        )
        findings.append(finding)
        seen[key] = finding
    verified_llm, rejected = verifier.verify_llm_drafts(
        payload.source, [item.model_dump() for item in scan.model_drafts], findings,
    )
    findings.extend(verified_llm)
    gaps = list(scan.gaps)
    if invalid_tool_count:
        gaps.append(f"工具有 {invalid_tool_count} 项候选因行号超出源码范围而未展示")
    if rejected:
        gaps.append(f"LLM 有 {rejected} 项候选因结构或源码定位校验失败而未展示")
    findings.sort(key=lambda item: (item.line, item.rule_id))

    # A partially covered review must never claim an unconditional pass.
    decision = "request_changes" if any(
        item.disposition == "must_fix" for item in findings
    ) else "comment" if findings or gaps else "pass"
    return ReviewReport(
        id=uuid4().hex,
        task_id=scan.task_id,
        filename=payload.filename,
        language=payload.language,
        created_at=datetime.now(timezone.utc).isoformat(),
        decision=decision,
        findings=findings,
        coverage=Coverage(completed=scan.completed, gaps=gaps),
        source_hash=scan.source_hash,
        model_version=config.LLM_MODEL or None,
        context_ranges=scan.context_ranges,
        omitted_ranges=scan.omitted_ranges,
        context_chars=scan.selected_chars,
        build_version=config.BUILD_VERSION,
        rule_version=config.RULE_VERSION,
    )


def create_review(payload: ReviewRequest) -> ReviewReport:
    return adjudicate(payload, scan_source(payload))
