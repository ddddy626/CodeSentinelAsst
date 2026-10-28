"""Verify candidate locations and corroborate them against independent tool output."""

from uuid import uuid4

from . import config
from .schemas import Evidence, Finding, Verification


def verify_llm_drafts(
    source: str, drafts: list[dict], tool_findings: list[Finding]
) -> tuple[list[Finding], int]:
    lines = source.splitlines()
    by_rule_line = {(item.rule_id, item.line): item for item in tool_findings}
    accepted: list[Finding] = []
    rejected = 0
    seen: set[tuple[str, int]] = set()

    for draft in drafts:
        try:
            line = draft["line"]
            if type(line) is not int:
                raise ValueError("line must be an integer")
            severity = str(draft["severity"]).upper()
            rule_id = str(draft["rule_id"]).strip()[:80]
            title = str(draft["title"]).strip()[:120]
            explanation = str(draft["explanation"]).strip()[:1200]
            suggestion = str(draft["suggestion"]).strip()[:1000]
            quote = draft["code_quote"]
            if not isinstance(quote, str):
                raise ValueError("code quote must be a string")
            quote = quote.strip()
            if (
                not 1 <= line <= len(lines)
                or severity not in {"S0", "S1", "S2", "S3"}
                or not rule_id or not title or not explanation or not suggestion
                or not 1 <= len(quote) <= 160
                or quote not in lines[line - 1]
            ):
                raise ValueError("invalid finding or source quote")
        except (KeyError, TypeError, ValueError):
            rejected += 1
            continue

        key = (rule_id, line)
        if key in seen:
            continue
        seen.add(key)
        source_evidence = Evidence(
            origin="source", source=f"第 {line} 行", detail=quote,
        )
        model_evidence = Evidence(
            origin="llm", source=config.LLM_MODEL or "LLM",
            detail="模型对该代码片段的推断；触发条件仍需核查",
        )
        tool_match = by_rule_line.get((rule_id, line))
        if tool_match:
            tool_match.evidence.extend([source_evidence, model_evidence])
            tool_match.verification = Verification(
                status="corroborated",
                reason="同一规则和行号有工具报告及源码片段支持；实际危害仍需人工判断。",
            )
            continue

        accepted.append(Finding(
            id=uuid4().hex,
            rule_id=rule_id,
            title=title,
            explanation=explanation,
            line=line,
            severity=severity,
            evidence_level="weak",
            disposition="uncertain",
            evidence=[source_evidence, model_evidence],
            suggestion=suggestion,
            verification=Verification(
                status="located",
                reason="源码片段与行号一致，但没有独立工具证据支持该缺陷。",
            ),
        ))
    return accepted, rejected
