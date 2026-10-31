def _log(source="nginx-1", level="ERROR", message="upstream timed out"):
    return {"source": source, "level": level, "message": message}


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_ingest_single(client, auth):
    r = client.post("/api/v1/logs", json=_log(), headers=auth)
    assert r.status_code == 201
    assert r.json()["level"] == "ERROR"


def test_ingest_batch(client, auth):
    r = client.post("/api/v1/logs/batch", json={"logs": [_log(), _log(level="INFO")]}, headers=auth)
    assert r.status_code == 201
    assert r.json() == {"ingested": 2}


def test_invalid_level_rejected(client, auth):
    assert client.post("/api/v1/logs", json=_log(level="LOUD"), headers=auth).status_code == 422


def test_empty_batch_rejected(client, auth):
    assert client.post("/api/v1/logs/batch", json={"logs": []}, headers=auth).status_code == 422


def test_filter_by_level_and_source(client, auth):
    for s, lv in [("a", "ERROR"), ("b", "INFO"), ("a", "INFO")]:
        client.post("/api/v1/logs", json=_log(source=s, level=lv), headers=auth)
    assert len(client.get("/api/v1/logs", headers=auth).json()) == 3
    assert len(client.get("/api/v1/logs?level=INFO", headers=auth).json()) == 2
    assert len(client.get("/api/v1/logs?source=a&level=ERROR", headers=auth).json()) == 1


def test_pagination(client, auth):
    for i in range(5):
        client.post("/api/v1/logs", json=_log(message=f"m{i}"), headers=auth)
    r = client.get("/api/v1/logs?limit=2&offset=1", headers=auth)
    assert [x["message"] for x in r.json()] == ["m3", "m2"]


def test_stats(client, auth):
    client.post("/api/v1/logs", json=_log(source="a", level="ERROR"), headers=auth)
    client.post("/api/v1/logs", json=_log(source="a", level="INFO"), headers=auth)
    s = client.get("/api/v1/logs/stats", headers=auth).json()
    assert s["total"] == 2
    assert s["by_level"] == {"ERROR": 1, "INFO": 1}
    assert s["by_source"] == {"a": 2}
