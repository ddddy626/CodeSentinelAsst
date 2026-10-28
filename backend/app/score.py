"""Transparent, deterministic estimate for a completed review."""

WEIGHTS = {"S0": 40, "S1": 20, "S2": 8, "S3": 3}
VERSION = "severity-v1"


def calculate_score(report: dict, feedback: dict[str, str] | None = None) -> dict:
    feedback = feedback or {}
    deducted = counted = pending = 0
    for finding in report.get("findings", []):
        response = feedback.get(finding.get("id", ""))
        if response == "false_positive":
            continue
        if response != "confirmed" and (
            finding.get("disposition") == "uncertain" or
            finding.get("evidence_level") == "weak"
        ):
            pending += 1
            continue
        deducted += WEIGHTS.get(finding.get("severity"), 0)
        counted += 1
    return {
        "value": max(0, 100 - deducted),
        "deduction": min(100, deducted),
        "counted_findings": counted,
        "pending_findings": pending,
        "version": VERSION,
    }
