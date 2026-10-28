"""Bounded multi-file review using the existing per-file review workflow."""

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from .config import BUILD_VERSION, LLM_MODEL, RULE_VERSION
from .orchestrator import run_review
from .review import validate_source
from .schemas import Coverage, ProjectBundle, ReviewReport, ReviewRequest


def validate_bundle(bundle: ProjectBundle) -> None:
    seen: set[str] = set()
    total_bytes = 0
    for file in bundle.files:
        path = file.path
        parts = path.split("/")
        if (path != path.strip() or "\\" in path or ":" in path or
                any(part in {"", ".", ".."} for part in parts) or
                any(ord(char) < 32 for char in path)):
            raise HTTPException(status_code=422, detail=f"项目文件路径无效：{path}")
        key = path.casefold()
        if key in seen:
            raise HTTPException(status_code=422, detail=f"项目文件路径重复：{path}")
        seen.add(key)
        total_bytes += len(file.source.encode("utf-8"))
        validate_source(ReviewRequest(filename=parts[-1], source=file.source,
                                      language=file.language))
    if total_bytes > 300_000:
        raise HTTPException(status_code=413, detail="项目文件总大小超过 300 KB 上限")


def run_project_review(bundle: ProjectBundle, saved_source: str, emit, save_round,
                       task_id: str) -> ReviewReport:
    validate_bundle(bundle)
    findings = []
    completed = []
    gaps = ["项目文件已逐个审查；跨文件调用关系与运行时行为尚未验证"]
    references = []
    for index, file in enumerate(bundle.files, 1):
        emit("file_started", f"正在审查第 {index}/{len(bundle.files)} 个文件：{file.path}")
        report = run_review(
            ReviewRequest(filename=file.path.rsplit("/", 1)[-1],
                          source=file.source, language=file.language),
            emit, save_round, task_id=task_id,
        )
        for finding in report.findings:
            finding.filename = file.path
            findings.append(finding)
        completed.extend(f"{file.path}：{item}" for item in report.coverage.completed)
        gaps.extend(f"{file.path}：{item}" for item in report.coverage.gaps)
        references.extend(report.knowledge_refs)
    decision = ("request_changes" if any(item.disposition == "must_fix" for item in findings)
                else "comment" if findings or gaps else "pass")
    return ReviewReport(
        id=uuid4().hex, task_id=task_id, filename="项目审查", language="project",
        created_at=datetime.now(timezone.utc).isoformat(), decision=decision,
        findings=findings, coverage=Coverage(completed=completed, gaps=gaps),
        knowledge_refs=list({item.id: item for item in references}.values()),
        source_hash=hashlib.sha256(saved_source.encode("utf-8")).hexdigest(),
        rule_version=RULE_VERSION, model_version=LLM_MODEL or None,
        build_version=BUILD_VERSION,
    )
