"""Reproducible A/B/C/D comparison on a labeled JSON fixture.

No model configuration means model groups are skipped, never inferred.
The bundled 12 cases cover only the dynamic-execution rule.
"""

import argparse
import hashlib
import importlib.metadata
import json
import time
from pathlib import Path

from . import config
from .orchestrator import run_review
from .review import adjudicate, scan_source
from .schemas import ReviewRequest
from .tools import run_tools

DEFAULT_CASES = Path(__file__).resolve().parent.parent / "evaluation" / "cases.json"


def version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def score(cases: list[dict], predictions: list[set[int]]) -> dict:
    tp = fp = fn = 0
    for case, actual in zip(cases, predictions):
        expected = {item["line"] for item in case["expected"]}
        tp += len(actual & expected)
        fp += len(actual - expected)
        fn += len(expected - actual)
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None}


def evaluate(cases_path: Path = DEFAULT_CASES, with_model: bool = False,
             context_budget: int = 12_000) -> dict:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if not all(case.get("origin") == "curated synthetic" for case in cases):
        dataset_kind = "custom; verify annotation provenance"
    else:
        dataset_kind = "curated synthetic"
    model_ready = bool(config.LLM_API_URL and config.LLM_API_KEY and config.LLM_MODEL)
    prompt_dir = Path(__file__).parent / "prompts"
    results = {}
    for label in ("A_static", "B_scanner", "C_two_roles", "D_ast_context"):
        if label != "A_static" and not (with_model and model_ready):
            results[label] = {"status": "skipped", "reason": "requires --with-model and configured LLM"}
            continue
        predictions = []
        durations = []
        input_chars = []
        omitted = 0
        raw_reports = {}
        gaps_by_case = {}
        for case in cases:
            payload = ReviewRequest(filename=f"{case['id']}.py", source=case["source"])
            started = time.perf_counter()
            if label == "A_static":
                drafts, completed, gaps = run_tools(case["source"])
                lines = {item.line for item in drafts if item.rule_id == "SEC-DYNAMIC-EXEC"}
                raw_reports[case["id"]] = {"tool_drafts": [vars(item) for item in drafts],
                                            "completed": completed, "gaps": gaps}
            elif label == "B_scanner":
                scan = scan_source(payload, context_budget=len(case["source"]) + 1)
                report = adjudicate(payload, scan)
                lines = {item.line for item in report.findings if item.rule_id == "SEC-DYNAMIC-EXEC"}
                input_chars.append(scan.selected_chars)
                raw_reports[case["id"]] = {"scan": scan.model_dump(), "report": report.model_dump()}
                gaps_by_case[case["id"]] = report.coverage.gaps
            else:
                budget = len(case["source"]) + 1 if label == "C_two_roles" else context_budget
                report = run_review(payload, lambda *_: None, lambda *_: None,
                                    context_budget=budget)
                lines = {item.line for item in report.findings if item.rule_id == "SEC-DYNAMIC-EXEC"}
                input_chars.append(report.context_chars or 0)
                omitted += len(report.omitted_ranges)
                raw_reports[case["id"]] = report.model_dump()
                gaps_by_case[case["id"]] = report.coverage.gaps
            predictions.append(lines)
            durations.append(time.perf_counter() - started)
        model_failures = sum(any("LLM 输出不可用" in gap or "架构师模型输出不可用" in gap
                                 for gap in gaps) for gaps in gaps_by_case.values())
        results[label] = {"status": "partial" if model_failures else "measured",
                          "model_failure_cases": model_failures, **score(cases, predictions),
                          "elapsed_seconds": round(sum(durations), 3),
                          "selected_source_chars": sum(input_chars) if input_chars else None,
                          "omitted_ranges": omitted,
                          "predictions": {case["id"]: sorted(lines)
                                          for case, lines in zip(cases, predictions)},
                          "coverage_gaps": gaps_by_case, "raw_reports": raw_reports}
    try:
        dataset_name = str(cases_path.resolve().relative_to(Path(__file__).resolve().parent.parent))
    except ValueError:
        dataset_name = str(cases_path)
    return {"dataset": dataset_name, "dataset_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
            "dataset_kind": dataset_kind, "cases": len(cases),
            "matching": "SEC-DYNAMIC-EXEC, exact original line; one TP per defect instance",
            "model": config.LLM_MODEL if with_model and model_ready else None,
            "rule_version": config.RULE_VERSION,
            "scanner_prompt_sha256": hashlib.sha256((prompt_dir / "review.md").read_bytes()).hexdigest(),
            "architect_prompt_sha256": hashlib.sha256((prompt_dir / "architect.md").read_bytes()).hexdigest(),
            "package_versions": {name: version(name) for name in ("langgraph", "ruff", "bandit", "semgrep")},
            "context_budget_chars": context_budget, "results": results,
            "limits": "Only the provided labeled cases and dynamic-execution rule are scored; no online accuracy claim."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--with-model", action="store_true")
    parser.add_argument("--context-budget", type=int, default=12_000)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = evaluate(args.dataset, args.with_model, args.context_budget)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    if args.out:
        summary = {"dataset": result["dataset"], "cases": result["cases"],
                   "results": {name: {key: value.get(key) for key in
                               ("status", "tp", "fp", "fn", "precision", "recall",
                                "selected_source_chars", "elapsed_seconds")}
                               for name, value in result["results"].items()}}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(rendered)


if __name__ == "__main__":
    main()
