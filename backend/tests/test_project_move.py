from fastapi.testclient import TestClient

from app import main
from app.storage import Store


def test_move_completed_review_between_owned_projects(tmp_path, monkeypatch):
    store = Store(f"sqlite:///{tmp_path / 'move.sqlite3'}")
    owner = store.create_user("owner", "owner-password-123")
    other = store.create_user("other", "other-password-123")
    source = store.create_project(owner, "原项目")
    target = store.create_project(owner, "目标项目")
    foreign = store.create_project(other, "别人的项目")
    job_id = store.create_job(owner, source["id"], "sample.py", "print(1)", "v1")
    store.save_memory(owner, source["id"], "task", "test memory", "test", job_id, "verified")
    with store.connection() as conn:
        store._run(conn, "UPDATE jobs SET status='completed' WHERE id=?", (job_id,))
    monkeypatch.setattr(main, "store", store)
    client = TestClient(main.app)
    client.post("/api/login", json={"username": "owner", "password": "owner-password-123"})

    listing = client.get("/api/jobs")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert client.post(f"/api/jobs/{job_id}/move", json={"project_id": foreign["id"]}).status_code == 404
    moved = client.post(f"/api/jobs/{job_id}/move", json={"project_id": target["id"]})
    assert moved.status_code == 200
    assert moved.json()["project_id"] == target["id"]
    assert client.get(f"/api/projects/{source['id']}/jobs").json() == []
    assert len(client.get(f"/api/projects/{target['id']}/jobs").json()) == 1
    assert store.memories(owner, target["id"], "task", job_id)[0]["content"] == "test memory"

    client.post("/api/logout")
    client.post("/api/login", json={"username": "other", "password": "other-password-123"})
    assert client.post(f"/api/jobs/{job_id}/move", json={"project_id": foreign["id"]}).status_code == 404


def test_running_review_cannot_move(tmp_path, monkeypatch):
    store = Store(f"sqlite:///{tmp_path / 'running.sqlite3'}")
    owner = store.create_user("owner", "owner-password-123")
    source = store.create_project(owner, "原项目")
    target = store.create_project(owner, "目标项目")
    job_id = store.create_job(owner, source["id"], "sample.py", "print(1)", "v1")
    monkeypatch.setattr(main, "store", store)
    client = TestClient(main.app)
    client.post("/api/login", json={"username": "owner", "password": "owner-password-123"})
    response = client.post(f"/api/jobs/{job_id}/move", json={"project_id": target["id"]})
    assert response.status_code == 409
    assert store.job(job_id, owner)["project_id"] == source["id"]
