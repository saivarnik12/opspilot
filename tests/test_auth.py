from tests.conftest import make_user


def test_register_and_login(client):
    r = client.post("/api/v1/auth/register", json={"email": "Bob@Example.com", "password": "longenough1"})
    assert r.status_code == 201
    assert r.json()["email"] == "bob@example.com"
    assert "password" not in r.text
    login = client.post("/api/v1/auth/login", data={"username": "bob@example.com", "password": "longenough1"})
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"


def test_duplicate_email_rejected(client):
    body = {"email": "a@example.com", "password": "longenough1"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    assert client.post("/api/v1/auth/register", json=body).status_code == 409


def test_weak_password_and_bad_email_rejected(client):
    assert client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "short"}).status_code == 422
    assert client.post("/api/v1/auth/register", json={"email": "nope", "password": "longenough1"}).status_code == 422


def test_wrong_password_rejected(client):
    client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "longenough1"})
    r = client.post("/api/v1/auth/login", data={"username": "a@example.com", "password": "wrongwrong"})
    assert r.status_code == 401


def test_unknown_user_rejected(client):
    r = client.post("/api/v1/auth/login", data={"username": "ghost@example.com", "password": "whatever123"})
    assert r.status_code == 401


def test_me_requires_valid_token(client, auth):
    assert client.get("/api/v1/auth/me", headers=auth).json()["email"] == "alice@example.com"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_log_endpoints_are_protected(client):
    assert client.get("/api/v1/logs").status_code == 401
    assert client.get("/api/v1/logs/stats").status_code == 401
    r = client.post("/api/v1/logs", json={"source": "a", "level": "INFO", "message": "x"})
    assert r.status_code == 401


def test_expired_token_rejected(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)
    headers = make_user(client)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_users_cannot_see_each_others_logs(client):
    alice = make_user(client, "alice@example.com")
    bob = make_user(client, "bob@example.com")
    client.post("/api/v1/logs", json={"source": "a", "level": "ERROR", "message": "secret"}, headers=alice)
    assert client.get("/api/v1/logs", headers=bob).json() == []
    assert client.get("/api/v1/logs/stats", headers=bob).json()["total"] == 0
    assert len(client.get("/api/v1/logs", headers=alice).json()) == 1
