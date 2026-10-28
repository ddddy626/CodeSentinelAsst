from fastapi import HTTPException

from fastapi.testclient import TestClient

from app import llm, main, tools, worker
from app.context import select_context
from app.review import create_review, validate_source
from app.schemas import ReviewRequest
from app.storage import Store


def test_language_and_extension_must_agree():
    validate_source(ReviewRequest(filename="sample.js", source="const x = 1;", language="javascript"))
    validate_source(ReviewRequest(filename="sample.tsx", source="const x: number = 1;", language="typescript"))
    try:
        validate_source(ReviewRequest(filename="sample.py", source="const x = 1;", language="javascript"))
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("Mismatched extension was accepted")


def test_web_context_keeps_original_lines_without_python_parser():
    source = "const first = 1;\n" + "\n".join(f"const value{i} = {i};" for i in range(80)) + "\neval(userInput);\n"
    line = len(source.splitlines())
    context = select_context(source, {line}, max_chars=280, language="javascript")
    assert f"{line}: eval(userInput);" in context.text
    assert context.omitted_ranges


def test_web_review_uses_semgrep_and_preserves_language(monkeypatch):
    called = []
    def scan(command, path):
        called.append(command[0])
        return {"results": [{"check_id": "rules.codesentinel.web.dynamic-eval",
                             "start": {"line": 1},
                             "extra": {"message": "动态执行", "severity": "WARNING"}}]}, None
    monkeypatch.setattr(tools, "_run_json_tool", scan)
    monkeypatch.setattr(llm, "review_source", lambda source: ([], None))
    report = create_review(ReviewRequest(filename="sample.ts", source="eval(userInput);", language="typescript"))
    assert called == ["semgrep"]
    assert report.language == "typescript"
    assert report.findings[0].rule_id.endswith("dynamic-eval")
    assert report.findings[0].disposition == "suggested"
    assert "Python AST" not in report.coverage.completed


def test_javascript_job_survives_api_and_worker(tmp_path, monkeypatch):
    store = Store(f"sqlite:///{tmp_path / 'web.sqlite3'}")
    store.create_user("reviewer", "reviewer-password-123")
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main.queue, "client", lambda: type("Queue", (), {"ping": lambda self: True})())
    monkeypatch.setattr(main.queue, "publish", lambda job_id: None)
    monkeypatch.setattr(llm, "review_source", lambda source: ([], "LLM 未配置"))
    client = TestClient(main.app)
    assert client.post("/api/login", json={"username": "reviewer", "password": "reviewer-password-123"}).status_code == 200
    project = client.post("/api/projects", json={"name": "Web"}).json()
    response = client.post("/api/jobs", json={"project_id": project["id"],
        "filename": "sample.js", "source": "eval(userInput);", "language": "javascript"})
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert client.get(f"/api/jobs/{job_id}/source").json()["source"] == "eval(userInput);"
    assert worker.run_once(store, job_id)
    saved = client.get(f"/api/jobs/{job_id}").json()
    assert saved["status"] == "completed"
    assert saved["report"]["language"] == "javascript"
    assert any(item["rule_id"].endswith("dynamic-eval") for item in saved["report"]["findings"])
