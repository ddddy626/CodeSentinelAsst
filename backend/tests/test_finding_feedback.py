import hashlib

from fastapi.testclient import TestClient

from app import main
from app.config import RULE_VERSION
from app.schemas import Coverage, Finding, ReviewReport
from app.storage import Store


def test_finding_feedback_persists_and_is_owner_only(tmp_path, monkeypatch):
    store = Store(f"sqlite:///{tmp_path / 'feedback.sqlite3'}")
    owner = store.create_user("owner", "owner-password-123")
    store.create_user("other", "other-password-123")
    project = store.create_project(owner, "P")
    source = "eval(input())"
    job_id = store.create_job(owner, project["id"], "a.py", source, RULE_VERSION)
    finding = Finding(id="finding-1", rule_id="SEC-DYNAMIC-EXEC", title="动态执行",
                      explanation="需要检查输入", line=1, severity="S1",
                      evidence_level="strong", disposition="must_fix", evidence=[],
                      suggestion="移除动态执行")
    report = ReviewReport(id="report-1", task_id=job_id, filename="a.py",
                          created_at="2026-10-23T00:00:00+00:00", decision="request_changes",
                          findings=[finding], coverage=Coverage(), rule_version=RULE_VERSION,
                          source_hash=hashlib.sha256(source.encode()).hexdigest())
    store.finish(job_id, report)
    monkeypatch.setattr(main, "store", store)
    client = TestClient(main.app)
    client.post("/api/login", json={"username": "owner", "password": "owner-password-123"})
    path = f"/api/jobs/{job_id}/findings/{finding.id}/feedback"
    saved = client.post(path, json={"status": "false_positive", "note": "已核查输入"})
    assert saved.status_code == 200
    assert client.get(f"/api/jobs/{job_id}/feedback").json()[0]["note"] == "已核查输入"
    assert client.post(path, json={"status": "confirmed", "note": "复核后确认"}).status_code == 200
    feedback = client.get(f"/api/jobs/{job_id}/feedback").json()
    assert len(feedback) == 1 and feedback[0]["status"] == "confirmed"
    assert client.post(path, json={"status": "invalid"}).status_code == 422
    assert client.post(f"/api/jobs/{job_id}/findings/missing/feedback",
                       json={"status": "confirmed"}).status_code == 404
    client.post("/api/logout")
    client.post("/api/login", json={"username": "other", "password": "other-password-123"})
    assert client.get(f"/api/jobs/{job_id}/feedback").status_code == 404
    assert client.post(path, json={"status": "confirmed"}).status_code == 404
