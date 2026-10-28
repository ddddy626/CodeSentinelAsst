import hashlib

from app.schemas import Coverage, Finding, ReviewReport
from app.score import calculate_score
from app.storage import Store


def test_score_separates_uncertain_findings_and_reacts_to_feedback(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'score.sqlite3'}")
    owner = store.create_user("owner", "owner-password-123")
    project = store.create_project(owner, "Example")
    source = "eval(input())"
    job_id = store.create_job(owner, project["id"], "example.py", source, "v1-5")
    confirmed = Finding(id="one", rule_id="EXEC", title="Dynamic execution",
                        explanation="Input reaches eval", line=1, severity="S1",
                        evidence_level="medium", disposition="suggested", evidence=[],
                        suggestion="Remove eval")
    uncertain = Finding(id="two", rule_id="CHECK", title="Check input",
                        explanation="Unclear", line=1, severity="S2",
                        evidence_level="weak", disposition="uncertain", evidence=[],
                        suggestion="Inspect")
    report = ReviewReport(id="report", task_id=job_id, filename="example.py",
                          created_at="2026-10-26T00:00:00+00:00", decision="request_changes",
                          findings=[confirmed, uncertain], coverage=Coverage(),
                          rule_version="v1-5", source_hash=hashlib.sha256(source.encode()).hexdigest())
    store.finish(job_id, report)
    assert store.job(job_id, owner)["score"]["value"] == 80
    assert store.job(job_id, owner)["score"]["pending_findings"] == 1
    store.save_finding_feedback(owner, job_id, "one", "false_positive", "reviewed")
    assert store.job(job_id, owner)["score"]["value"] == 100
    store.save_finding_feedback(owner, job_id, "two", "confirmed", "reviewed")
    assert store.job(job_id, owner)["score"]["value"] == 92
    assert store.job(job_id, owner)["score"]["pending_findings"] == 0
    assert store.job(job_id, "another-user") is None


def test_score_has_zero_floor():
    findings = [{"id": str(i), "severity": "S0", "evidence_level": "strong",
                 "disposition": "must_fix"} for i in range(4)]
    assert calculate_score({"findings": findings})["value"] == 0
