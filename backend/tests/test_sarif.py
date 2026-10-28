import hashlib
import json

from fastapi.testclient import TestClient

from app import main
from app.config import RULE_VERSION
from app.schemas import Coverage, Finding, ReviewReport
from app.storage import Store


def test_sarif_export_has_project_locations_and_owner_boundary(tmp_path, monkeypatch):
    store = Store(f"sqlite:///{tmp_path / 'sarif.sqlite3'}")
    owner = store.create_user("owner", "owner-password-123")
    store.create_user("other", "other-password-123")
    project = store.create_project(owner, "P")
    source = json.dumps({"files": [
        {"path": "src/应用.java", "source": "class App {}", "language": "java"},
        {"path": "application.properties", "source": "password=demo", "language": "properties"},
    ]}, ensure_ascii=False)
    job_id = store.create_job(owner, project["id"], "project.codesentinel-bundle", source, RULE_VERSION)
    finding = Finding(id="f-1", rule_id="R-1", title="测试规则", explanation="发现配置问题",
                      filename="application.properties", line=1, severity="S2",
                      evidence_level="medium", disposition="suggested", evidence=[],
                      suggestion="检查配置")
    report = ReviewReport(id="r-1", task_id=job_id, filename="项目审查", language="project",
                          created_at="2026-10-23T00:00:00+00:00", decision="comment",
                          findings=[finding], coverage=Coverage(gaps=["跨文件未验证"]),
                          rule_version=RULE_VERSION,
                          source_hash=hashlib.sha256(source.encode()).hexdigest())
    store.finish(job_id, report)
    monkeypatch.setattr(main, "store", store)
    client = TestClient(main.app)
    assert client.get(f"/api/jobs/{job_id}/sarif").status_code == 401
    client.post("/api/login", json={"username": "owner", "password": "owner-password-123"})
    pending = store.create_job(owner, project["id"], "pending.py", "print(1)", RULE_VERSION)
    assert client.get(f"/api/jobs/{pending}/sarif").status_code == 409
    response = client.get(f"/api/jobs/{job_id}/sarif")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    sarif = response.json()
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["rules"][0]["id"] == "R-1"
    assert run["results"][0]["locations"][0]["physicalLocation"] == {
        "artifactLocation": {"uri": "application.properties"}, "region": {"startLine": 1}}
    assert run["results"][0]["partialFingerprints"]["primaryLocationLineHash"]
    assert run["properties"]["coverageGaps"] == ["跨文件未验证"]
    client.post("/api/logout")
    client.post("/api/login", json={"username": "other", "password": "other-password-123"})
    assert client.get(f"/api/jobs/{job_id}/sarif").status_code == 404
