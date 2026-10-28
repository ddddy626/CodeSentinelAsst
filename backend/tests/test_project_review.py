from fastapi.testclient import TestClient

from app import main, worker
from app.storage import Store


def test_multi_file_job_keeps_locations_and_is_private(tmp_path, monkeypatch):
    store = Store(f"sqlite:///{tmp_path / 'project.sqlite3'}")
    store.create_user("owner", "owner-password-123")
    store.create_user("other", "other-password-123")
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main.queue, "client", lambda: type("Queue", (), {"ping": lambda self: True})())
    monkeypatch.setattr(main.queue, "publish", lambda job_id: None)
    monkeypatch.setattr("app.review.llm.review_source", lambda source: ([], "LLM 未配置"))
    client = TestClient(main.app)
    client.post("/api/login", json={"username": "owner", "password": "owner-password-123"})
    project = client.post("/api/projects", json={"name": "Spring"}).json()
    files = [
        {"path": "src/main/java/App.java", "source": "class App {}", "language": "java"},
        {"path": "src/main/resources/application.properties",
         "source": "spring.datasource.password=example\n", "language": "properties"},
    ]
    response = client.post("/api/project-reviews", json={"project_id": project["id"], "files": files})
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert worker.run_once(store, job_id)
    report = client.get(f"/api/jobs/{job_id}").json()["report"]
    assert report["language"] == "project"
    assert any(item["filename"] == files[1]["path"] and item["line"] == 1
               for item in report["findings"])
    assert "跨文件" in report["coverage"]["gaps"][0]
    client.post("/api/logout")
    client.post("/api/login", json={"username": "other", "password": "other-password-123"})
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert client.get(f"/api/jobs/{job_id}/source").status_code == 404


def test_project_paths_and_size_are_bounded(tmp_path, monkeypatch):
    store = Store(f"sqlite:///{tmp_path / 'paths.sqlite3'}")
    store.create_user("owner", "owner-password-123")
    monkeypatch.setattr(main, "store", store)
    client = TestClient(main.app)
    client.post("/api/login", json={"username": "owner", "password": "owner-password-123"})
    project = client.post("/api/projects", json={"name": "P"}).json()
    good = {"path": "a.py", "source": "print(1)", "language": "python"}
    for path in ("../a.py", "/a.py", "src\\a.py", "src/./a.py", "C:a.py"):
        response = client.post("/api/project-reviews", json={"project_id": project["id"],
            "files": [{**good, "path": path}, good]})
        assert response.status_code == 422
    duplicate = client.post("/api/project-reviews", json={"project_id": project["id"],
        "files": [good, {**good, "path": "A.py"}]})
    assert duplicate.status_code == 422
