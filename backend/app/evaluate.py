"""Reproducible offline calibration for the built-in dynamic-execution rule."""

import json
from pathlib import Path

from .tools import _ast_review

CASES_PATH = Path(__file__).resolve().parent.parent / "evaluation" / "cases.json"


def evaluate() -> dict:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    true_positive = false_positive = false_negative = 0
    failures = []
    for case in cases:
        drafts, gap = _ast_review(case["source"])
        if gap:
            failures.append({"id": case["id"], "error": gap})
            continue
        actual = {
            (draft.line, draft.severity, draft.trigger_path is not None)
            for draft in drafts if draft.rule_id == "SEC-DYNAMIC-EXEC"
        }
        expected = {
            (item["line"], item["severity"], item["triggered"])
            for item in case["expected"]
        }
        true_positive += len(actual & expected)
        false_positive += len(actual - expected)
        false_negative += len(expected - actual)
        if actual != expected:
            failures.append({
                "id": case["id"],
                "expected": sorted(expected),
                "actual": sorted(actual),
            })
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive else 1.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative else 1.0
    )
    return {
        "cases": len(cases),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "failures": failures,
        "scope": "SEC-DYNAMIC-EXEC curated synthetic cases only",
    }


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["failures"] else 0)
