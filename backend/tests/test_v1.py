from fastapi.testclient import TestClient

from app import main
from app.storage import Store
from app.memory import MemoryService
from app.orchestrator import run_review
from app.schemas import ReviewRequest
from app.tools import ToolDraft


def test_admin_provisioning_and_project_isolation(tmp_path, monkeypatch):
    store = Store(f"sqlite:///{tmp_path / 'v1.sqlite3'}")
    store.create_user("admin", "admin-password-123", True)
    store.create_user("member", "member-password-123")
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main.queue, "client", lambda: type("Queue", (), {"ping": lambda self: True})())
    client = TestClient(main.app)
    assert client.get("/api/ready").json() == {"status": "ready"}
    client.post("/api/login", json={"username": "member", "password": "member-password-123"})
    assert client.post("/api/admin/users", json={"username": "new", "password": "new-password-123"}).status_code == 403
    own = client.post("/api/projects", json={"name": "own"}).json()
    assert client.post("/api/projects", json={"name": "   "}).status_code == 422
    assert [item["id"] for item in client.get("/api/projects").json()] == [own["id"]]
    client.post("/api/logout")
    assert client.get("/api/projects").status_code == 401
    client.post("/api/login", json={"username": "admin", "password": "admin-password-123"})
    assert client.get("/api/projects").json() == []
    assert client.post("/api/admin/users", json={"username": "new", "password": "new-password-123"}).status_code == 201


def test_password_hash_and_failed_job(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'v1.sqlite3'}")
    user_id = store.create_user("tester", "tester-password-123")
    assert store.authenticate("tester", "incorrect-password") is None
    token, _, _ = store.authenticate("tester", "tester-password-123")
    assert store.session_user(token)["id"] == user_id
    project = store.create_project(user_id, "P")
    job_id = store.create_job(user_id, project["id"], "x.py", "print(1)", "v1-1")
    assert store.claim(job_id)
    store.fail(job_id, "internal error")
    assert store.job(job_id, user_id)["status"] == "failed"
    assert store.job(job_id, "someone-else") is None


def test_saved_source_is_available_only_to_its_owner(tmp_path, monkeypatch):
    store = Store(f"sqlite:///{tmp_path / 'source.sqlite3'}")
    owner = store.create_user("owner", "owner-password-123")
    store.create_user("other", "other-password-123")
    project = store.create_project(owner, "P")
    job_id = store.create_job(owner, project["id"], "sample.py", "print(1)", "v1-1")
    monkeypatch.setattr(main, "store", store)
    client = TestClient(main.app)
    path = f"/api/jobs/{job_id}/source"
    assert client.get(path).status_code == 401
    client.post("/api/login", json={"username": "owner", "password": "owner-password-123"})
    assert client.get(path).json()["source"] == "print(1)"
    client.post("/api/logout")
    client.post("/api/login", json={"username": "other", "password": "other-password-123"})
    assert client.get(path).status_code == 404


def test_three_memory_layers_remain_project_private(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'v1.sqlite3'}")
    alice = store.create_user("alice", "alice-password-123")
    bob = store.create_user("bob", "bob-password-123")
    project = store.create_project(alice, "private")
    task = store.create_job(alice, project["id"], "x.py", "print(1)", "v1-1")
    service = MemoryService(store)
    for layer in ("task", "project", "experience"):
        service.remember(alice, project["id"], layer, "example", "test",
                         task if layer == "task" else None)
        assert len(service.recall(alice, project["id"], layer,
                                  task if layer == "task" else None)) == 1
    import pytest
    with pytest.raises(PermissionError):
        service.recall(bob, project["id"], "experience")


def test_cancelled_queued_job_cannot_be_claimed(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'cancel.sqlite3'}")
    user_id = store.create_user("owner", "owner-password-123")
    project = store.create_project(user_id, "P")
    job_id = store.create_job(user_id, project["id"], "a.py", "print(1)", "v1-1")
    assert not store.cancel_queued(job_id, "other-user")
    assert store.cancel_queued(job_id, user_id)
    assert not store.claim(job_id)
    assert store.job(job_id, user_id)["status"] == "cancelled"


def test_targeted_recheck_stops_when_tool_adds_evidence(monkeypatch):
    calls = 0
    def tool_results(source):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [], ["Python AST"], ["Ruff 未安装"]
        return [ToolDraft("LOG-001", "边界", "说明", 1, "S2", "Ruff",
                          "原始工具证据", "检查边界")], ["Python AST", "Ruff"], []
    monkeypatch.setattr("app.review.tools.run_tools", tool_results)
    monkeypatch.setattr("app.orchestrator.tools.run_tools", tool_results)
    monkeypatch.setattr("app.review.llm.review_source", lambda source: ([{
        "rule_id": "LOG-001", "title": "边界", "explanation": "检查边界", "line": 1,
        "code_quote": "print(1)", "severity": "S2", "suggestion": "修正边界",
    }], None))
    events, rounds = [], []
    report = run_review(ReviewRequest(source="print(1)"),
                        lambda kind, detail: events.append(kind), rounds.append)
    assert calls == 2
    assert rounds == [0, 1]
    assert report.findings[0].evidence_level == "medium"
    assert report.findings[0].disposition == "suggested"
    assert "rechecked" in events


def test_scanner_and_architect_have_separate_model_outputs(monkeypatch):
    monkeypatch.setattr("app.review.tools.run_tools", lambda source: ([], ["Python AST"], []))
    monkeypatch.setattr("app.review.llm.review_source", lambda source: ([{
        "rule_id": "LOG-001", "title": "边界", "explanation": "检查边界", "line": 1,
        "code_quote": "print(1)", "severity": "S2", "suggestion": "修正边界",
    }], None))
    monkeypatch.setattr("app.orchestrator.llm.architect_review", lambda source, findings: ([{
        "finding_id": findings[0]["finding_id"], "assessment": "unknown",
        "reason": "没有可见的调用条件",
    }], None))
    events = []
    report = run_review(ReviewRequest(source="print(1)"),
                        lambda kind, detail: events.append(kind), lambda _: None)
    assert events.index("specialist") < events.index("architect") < events.index("reviewed")
    assert any(item.source == "Architect" for item in report.findings[0].evidence)
    assert report.findings[0].disposition == "uncertain"


def test_recovered_review_keeps_persisted_round_budget(monkeypatch):
    monkeypatch.setattr("app.review.tools.run_tools",
                        lambda source: ([], ["Python AST"], ["Ruff 未安装"]))
    monkeypatch.setattr("app.review.llm.review_source", lambda source: ([{
        "rule_id": "LOG-001", "title": "边界", "explanation": "检查边界", "line": 1,
        "code_quote": "print(1)", "severity": "S2", "suggestion": "修正边界",
    }], None))
    monkeypatch.setattr("app.orchestrator.llm.architect_review", lambda source, findings: ([], None))
    rounds = []
    report = run_review(ReviewRequest(source="print(1)"),
                        lambda *_: None, rounds.append, initial_round=4)
    assert report.findings[0].disposition == "uncertain"
    assert rounds == [4, 5]
