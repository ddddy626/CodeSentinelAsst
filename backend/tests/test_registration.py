from fastapi.testclient import TestClient

from app import main
from app.storage import Store


def test_public_registration_creates_only_ordinary_user_and_allows_login(tmp_path, monkeypatch):
    store = Store(f"sqlite:///{tmp_path / 'registration.sqlite3'}")
    monkeypatch.setattr(main, "store", store)
    client = TestClient(main.app)

    created = client.post("/api/register", json={"username": " new_user ", "password": "long-password-123"})
    assert created.status_code == 201
    assert created.json()["username"] == "new_user"
    assert created.json()["is_admin"] is False
    assert "password" not in created.json()
    assert client.post("/api/register", json={"username": "new_user", "password": "long-password-123"}).status_code == 409
    assert client.post("/api/register", json={"username": "  ", "password": "long-password-123"}).status_code == 422
    assert client.post("/api/register", json={"username": "another", "password": "short"}).status_code == 422
    assert client.post("/api/register", json={"username": "another", "password": "long-password-123", "is_admin": True}).status_code == 422

    assert client.post("/api/login", json={"username": "new_user", "password": "long-password-123"}).status_code == 200
    assert client.get("/api/me").json()["is_admin"] is False
    assert client.post("/api/projects", json={"name": "首次审查"}).status_code == 201
    assert client.post("/api/admin/users", json={"username": "elevated", "password": "long-password-456"}).status_code == 403
