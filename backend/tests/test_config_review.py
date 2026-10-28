import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import llm, main, worker
from app.review import validate_source
from app.schemas import ReviewRequest, language_for_filename
from app.storage import Store
from app.tools import run_tools


@pytest.mark.parametrize(("filename", "language"), [
    ("schema.sql", "sql"), ("pom.xml", "xml"),
    ("application.yml", "yaml"), ("application.yaml", "yaml"),
    ("application.properties", "properties"),
])
def test_config_file_language_mapping(filename, language):
    assert language_for_filename(filename) == language
    source = "<project/>" if language == "xml" else "x"
    validate_source(ReviewRequest(filename=filename, source=source, language=language))


def test_sql_rule_ignores_comments_and_literals():
    source = "-- DELETE FROM users;\nSELECT 'DELETE FROM users;';\n/* UPDATE users SET name='x'; */\nDELETE FROM users;\n"
    drafts, completed, gaps = run_tools(source, "sql")
    assert [(item.line, item.rule_id) for item in drafts] == [(4, "codesentinel.sql.unbounded-write")]
    assert completed and gaps


def test_spring_config_rules_hide_secret_values():
    yaml_source = "spring:\n  datasource:\n    password: visible-only-in-source\nmanagement:\n  endpoints:\n    web:\n      exposure:\n        include: '*'\n"
    drafts, _, _ = run_tools(yaml_source, "yaml")
    assert {item.rule_id for item in drafts} == {
        "codesentinel.config.plaintext-secret", "codesentinel.spring.actuator-exposure"}
    assert all("visible-only-in-source" not in item.evidence for item in drafts)
    properties = "spring.datasource.password=${DB_PASSWORD}\nmanagement.endpoints.web.exposure.include=*\n"
    drafts, _, _ = run_tools(properties, "properties")
    assert [item.rule_id for item in drafts] == ["codesentinel.spring.actuator-exposure"]


def test_xml_syntax_and_password_rule():
    with pytest.raises(HTTPException) as caught:
        validate_source(ReviewRequest(filename="pom.xml", source="<project>", language="xml"))
    assert caught.value.status_code == 422
    source = "<project><password>plain-value</password></project>"
    validate_source(ReviewRequest(filename="pom.xml", source=source, language="xml"))
    drafts, _, _ = run_tools(source, "xml")
    assert drafts[0].rule_id == "codesentinel.xml.password"
    assert "plain-value" not in drafts[0].evidence


def test_spring_java_cors_rule():
    source = 'import org.springframework.web.bind.annotation.CrossOrigin; class Sample { @CrossOrigin(origins = "*") void handler() {} }'
    drafts, completed, gaps = run_tools(source, "java")
    assert "Semgrep" in completed
    assert not gaps
    assert any(item.rule_id.endswith("spring-wildcard-cors") for item in drafts)


def test_sql_job_survives_api_and_worker(tmp_path, monkeypatch):
    store = Store(f"sqlite:///{tmp_path / 'sql.sqlite3'}")
    store.create_user("reviewer", "reviewer-password-123")
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main.queue, "client", lambda: type("Queue", (), {"ping": lambda self: True})())
    monkeypatch.setattr(main.queue, "publish", lambda job_id: None)
    monkeypatch.setattr(llm, "review_source", lambda source: ([], "LLM 未配置"))
    client = TestClient(main.app)
    assert client.post("/api/login", json={"username": "reviewer", "password": "reviewer-password-123"}).status_code == 200
    project = client.post("/api/projects", json={"name": "Spring"}).json()
    response = client.post("/api/jobs", json={"project_id": project["id"],
        "filename": "schema.sql", "source": "DELETE FROM users;", "language": "sql"})
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert worker.run_once(store, job_id)
    saved = client.get(f"/api/jobs/{job_id}").json()
    assert saved["status"] == "completed"
    assert saved["report"]["language"] == "sql"
    assert saved["report"]["findings"][0]["rule_id"] == "codesentinel.sql.unbounded-write"
