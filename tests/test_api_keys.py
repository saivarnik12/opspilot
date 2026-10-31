from tests.conftest import make_user


def _create(client, auth, name="prod-1"):
    return client.post("/api/v1/api-keys", json={"name": name}, headers=auth)


def test_create_key_shown_once(client, auth):
    r = _create(client, auth)
    assert r.status_code == 201
    body = r.json()
    assert body["key"].startswith("op_")
    listed = client.get("/api/v1/api-keys", headers=auth).json()
    assert len(listed) == 1
    assert "key" not in listed[0]
    assert listed[0]["prefix"] == body["key"][:11]


def test_api_key_can_ingest_and_read(client, auth):
    key = _create(client, auth).json()["key"]
    kh = {"X-API-Key": key}
    r = client.post("/api/v1/logs", json={"source": "agent", "level": "WARNING", "message": "disk 91%"}, headers=kh)
    assert r.status_code == 201
    # same data visible to the owner via JWT
    assert client.get("/api/v1/logs", headers=auth).json()[0]["message"] == "disk 91%"
    assert client.get("/api/v1/logs/stats", headers=kh).json()["total"] == 1


def test_invalid_api_key_rejected(client):
    r = client.get("/api/v1/logs", headers={"X-API-Key": "op_not-a-real-key"})
    assert r.status_code == 401


def test_revoked_key_stops_working(client, auth):
    created = _create(client, auth).json()
    kh = {"X-API-Key": created["key"]}
    assert client.get("/api/v1/logs", headers=kh).status_code == 200
    assert client.delete(f"/api/v1/api-keys/{created['id']}", headers=auth).status_code == 204
    assert client.get("/api/v1/logs", headers=kh).status_code == 401
    assert client.get("/api/v1/api-keys", headers=auth).json()[0]["revoked"] is True


def test_api_key_cannot_manage_keys(client, auth):
    key = _create(client, auth).json()["key"]
    r = client.post("/api/v1/api-keys", json={"name": "evil"}, headers={"X-API-Key": key})
    assert r.status_code == 401


def test_cannot_revoke_someone_elses_key(client, auth):
    created = _create(client, auth).json()
    bob = make_user(client, "bob@example.com")
    assert client.delete(f"/api/v1/api-keys/{created['id']}", headers=bob).status_code == 404
    assert client.get("/api/v1/api-keys", headers=bob).json() == []
