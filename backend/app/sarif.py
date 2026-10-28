"""Export a saved CodeSentinel report as SARIF 2.1.0."""

import hashlib
import json
from urllib.parse import quote


def _source_files(job: dict, saved: dict) -> dict[str, str]:
    if job["filename"] == "project.codesentinel-bundle":
        return {item["path"]: item["source"] for item in json.loads(saved["source"])["files"]}
    return {job["filename"]: saved["source"]}


def to_sarif(job: dict, saved: dict) -> dict:
    report = job["report"]
    if not report:
        raise ValueError("审查报告尚未完成")
    sources = _source_files(job, saved)
    rules: dict[str, dict] = {}
    results = []
    for finding in report["findings"]:
        rule_id = finding["rule_id"]
        rules.setdefault(rule_id, {"id": rule_id,
            "shortDescription": {"text": finding["title"][:255]}})
        path = finding.get("filename") or report["filename"]
        line = finding["line"]
        source_lines = sources.get(path, "").splitlines()
        line_text = source_lines[line - 1].strip() if 1 <= line <= len(source_lines) else ""
        occurrence = sum(1 for item in source_lines[:line] if item.strip() == line_text)
        fingerprint = hashlib.sha256(line_text.encode("utf-8")).hexdigest()[:32]
        results.append({
            "ruleId": rule_id,
            "level": "error" if finding["severity"] in {"S0", "S1"} else
                     "warning" if finding["severity"] == "S2" else "note",
            "message": {"text": finding["explanation"] + " 建议：" + finding["suggestion"]},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": quote(path, safe="/-._~")},
                "region": {"startLine": line},
            }}],
            "partialFingerprints": {"primaryLocationLineHash": f"{fingerprint}:{occurrence}"},
            "properties": {"evidenceLevel": finding["evidence_level"],
                           "disposition": finding["disposition"]},
        })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "CodeSentinel",
                                "version": report.get("build_version") or "1.0.0",
                                "rules": list(rules.values())}},
            "results": results,
            "properties": {"coverageGaps": report["coverage"]["gaps"]},
        }],
    }
