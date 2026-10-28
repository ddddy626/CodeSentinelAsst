from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main
from app.memory import MemoryStore
from app.review import create_review
from app.schemas import ReviewRequest


def test_dynamic_execution_is_located_and_not_marked_confirmed(monkeypatch):
    monkeypatch.setattr(
        "app.review.tools.run_tools",
        lambda source: ([__import__("app.tools", fromlist=["ToolDraft"]).ToolDraft(
            "SEC-DYNAMIC-EXEC", "动态执行", "检查输入来源", 2, "S1",
            "ast", "第 2 行调用 eval()", "避免动态执行",
        )], ["Python AST"], []),
    )
    monkeypatch.setattr("app.review.llm.review_source", lambda source: ([], "LLM 未配置"))
    report = create_review(ReviewRequest(filename="sample.py", source="x = 1\ny = eval(x)\n"))
    assert report.findings[0].line == 2
    assert report.findings[0].evidence_level == "medium"
    assert report.findings[0].disposition == "suggested"
    assert report.decision == "comment"


def test_llm_only_issue_is_uncertain(monkeypatch):
    monkeypatch.setattr("app.review.tools.run_tools", lambda source: ([], ["Python AST"], []))
    monkeypatch.setattr(
        "app.review.llm.review_source",
        lambda source: ([{
            "rule_id": "LOG-001", "title": "边界问题",
            "explanation": "需要检查调用条件", "line": 1,
            "code_quote": "print('hello')",
            "severity": "S1", "suggestion": "补充验证",
        }], None),
    )
    report = create_review(ReviewRequest(source="print('hello')"))
    assert report.findings[0].disposition == "uncertain"
    assert report.findings[0].evidence_level == "weak"
    assert report.findings[0].verification.status == "located"
    assert report.decision == "comment"


def test_forged_source_quote_is_rejected(monkeypatch):
    monkeypatch.setattr("app.review.tools.run_tools", lambda source: ([], ["Python AST"], []))
    monkeypatch.setattr(
        "app.review.llm.review_source",
        lambda source: ([{
            "rule_id": "SEC-001", "title": "注入",
            "explanation": "声称存在动态执行", "line": 1,
            "code_quote": "eval(user_input)",
            "severity": "S1", "suggestion": "验证输入",
        }], None),
    )
    report = create_review(ReviewRequest(source="print('safe')"))
    assert report.findings == []
    assert any("定位校验失败" in gap for gap in report.coverage.gaps)
    assert report.decision == "comment"


def test_line_number_must_be_an_integer(monkeypatch):
    monkeypatch.setattr("app.review.tools.run_tools", lambda source: ([], ["Python AST"], []))
    monkeypatch.setattr(
        "app.review.llm.review_source",
        lambda source: ([{
            "rule_id": "LOG-001", "title": "问题",
            "explanation": "错误的行号类型", "line": 1.7,
            "code_quote": "print(1)",
            "severity": "S2", "suggestion": "检查",
        }], None),
    )
    report = create_review(ReviewRequest(source="print(1)"))
    assert report.findings == []
    assert any("定位校验失败" in gap for gap in report.coverage.gaps)


def test_matching_tool_and_model_findings_are_combined(monkeypatch):
    from app.tools import ToolDraft

    monkeypatch.setattr(
        "app.review.tools.run_tools",
        lambda source: ([ToolDraft(
            "SEC-DYNAMIC-EXEC", "动态执行", "检查输入来源", 1, "S1",
            "ast", "第 1 行调用 eval()", "避免动态执行", "input() → eval()",
        )], ["Python AST"], []),
    )
    monkeypatch.setattr(
        "app.review.llm.review_source",
        lambda source: ([{
            "rule_id": "SEC-DYNAMIC-EXEC", "title": "动态执行",
            "explanation": "输入可能进入 eval", "line": 1,
            "code_quote": "eval(input())",
            "severity": "S1", "suggestion": "避免 eval",
        }], None),
    )
    report = create_review(ReviewRequest(source="x = eval(input())"))
    assert len(report.findings) == 1
    assert report.findings[0].verification.status == "corroborated"
    assert {e.origin for e in report.findings[0].evidence} == {"source", "tool", "llm"}
    assert report.findings[0].evidence_level == "strong"
    assert report.findings[0].disposition == "must_fix"
    assert report.decision == "request_changes"


def test_same_rule_and_line_keeps_both_tool_evidence(monkeypatch):
    from app.tools import ToolDraft
    drafts = [ToolDraft("RULE-1", "issue", "explain", 1, "S2", name,
                        f"raw output from {name}", "check") for name in ("Ruff", "Bandit")]
    monkeypatch.setattr("app.review.tools.run_tools", lambda source: (drafts, ["Ruff", "Bandit"], []))
    monkeypatch.setattr("app.review.llm.review_source", lambda source: ([], "LLM 未配置"))
    report = create_review(ReviewRequest(source="print(1)"))
    assert len(report.findings) == 1
    assert {item.source for item in report.findings[0].evidence} == {"Ruff", "Bandit"}


def test_invalid_input_rejected():
    with pytest.raises(HTTPException):
        create_review(ReviewRequest(filename="a.txt", source="print(1)"))


def test_history_round_trip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.review.tools.run_tools", lambda source: ([], ["Python AST"], []))
    monkeypatch.setattr("app.review.llm.review_source", lambda source: ([], "LLM 未配置"))
    report = create_review(ReviewRequest(source="print(1)"))
    store = MemoryStore(tmp_path / "history.sqlite3")
    store.save(report)
    assert store.get(report.id) == report
    assert store.recent()[0].id == report.id


def test_api_submit_and_fetch(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.review.tools.run_tools", lambda source: ([], ["Python AST"], []))
    monkeypatch.setattr("app.review.llm.review_source", lambda source: ([], "LLM 未配置"))
    from app.storage import Store
    from app.worker import run_once
    store = Store(f"sqlite:///{tmp_path / 'api.sqlite3'}")
    store.create_user("alice", "secure-password-123")
    store.create_user("bob", "secure-password-456")
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main.queue, "client", lambda: type("Queue", (), {"ping": lambda self: True})())
    monkeypatch.setattr(main.queue, "publish", lambda job_id: None)
    client = TestClient(main.app)
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/login", json={"username": "alice", "password": "wrong"}).status_code == 401
    assert client.post("/api/login", json={"username": "alice", "password": "secure-password-123"}).status_code == 200
    project = client.post("/api/projects", json={"name": "Alice project"}).json()
    created = client.post("/api/jobs", json={
        "project_id": project["id"], "filename": "sample.py", "source": "print('ok')\n",
    })
    assert created.status_code == 202
    review_id = created.json()["id"]
    assert "source" not in created.json()
    assert run_once(store, review_id)
    fetched = client.get(f"/api/jobs/{review_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "completed"
    assert fetched.json()["report"]["filename"] == "sample.py"
    assert [row["kind"] for row in client.get(f"/api/jobs/{review_id}/events").json()] == [
        "queued", "running", "planned", "specialist", "reviewed", "completed",
    ]
    assert not run_once(store, review_id)
    assert client.post("/api/login", json={"username": "bob", "password": "secure-password-456"}).status_code == 200
    assert client.get(f"/api/jobs/{review_id}").status_code == 404
    assert client.get(f"/api/jobs/{review_id}/events").status_code == 404
    assert client.get(f"/api/projects/{project['id']}/jobs").status_code == 404
