from datetime import datetime, timedelta, timezone

from tests.conftest import make_user


def post(client, headers, msg, level="INFO", source="api", ts=None):
    body = {"source": source, "level": level, "message": msg}
    if ts:
        body["timestamp"] = ts.isoformat()
    assert client.post("/api/v1/logs", json=body, headers=headers).status_code == 201


def test_total_count_header_and_search(client, auth):
    for i in range(7):
        post(client, auth, f"Payment failed for order {i}", level="ERROR")
    post(client, auth, "Health check ok")
    r = client.get("/api/v1/logs?limit=3", headers=auth)
    assert r.headers["X-Total-Count"] == "8" and len(r.json()) == 3
    r = client.get("/api/v1/logs?q=payment&limit=2&offset=2", headers=auth)
    assert r.headers["X-Total-Count"] == "7" and len(r.json()) == 2  # case-insensitive
    assert client.get("/api/v1/logs?q=nothing-matches", headers=auth).headers["X-Total-Count"] == "0"


def test_search_treats_wildcards_literally(client, auth):
    post(client, auth, "disk 100% full")
    post(client, auth, "disk 1000 full")
    r = client.get("/api/v1/logs", params={"q": "100%"}, headers=auth)
    assert [x["message"] for x in r.json()] == ["disk 100% full"]
    assert client.get("/api/v1/logs", params={"q": "_"}, headers=auth).json() == []


def test_total_count_is_per_user(client, auth):
    post(client, auth, "mine")
    bob = make_user(client, "bob@example.com")
    assert client.get("/api/v1/logs", headers=bob).headers["X-Total-Count"] == "0"


def test_timeseries_buckets_and_zero_fill(client, auth):
    now = datetime.now(timezone.utc)
    post(client, auth, "recent err", level="ERROR", ts=now - timedelta(minutes=5))
    post(client, auth, "recent crit", level="CRITICAL", ts=now - timedelta(minutes=5))
    post(client, auth, "recent info", ts=now - timedelta(minutes=5))
    post(client, auth, "older err", level="ERROR", ts=now - timedelta(hours=10))
    post(client, auth, "too old", level="ERROR", ts=now - timedelta(days=3))
    r = client.get("/api/v1/logs/timeseries?hours=24", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["hours"] == 24 and len(body["points"]) == 48 and body["bucket_seconds"] == 1800
    assert sum(p["total"] for p in body["points"]) == 4  # 3-day-old log excluded
    assert sum(p["errors"] for p in body["points"]) == 3  # ERROR + CRITICAL, not INFO
    assert body["points"][-1]["total"] == 3  # the recent ones land in the last bucket
    assert sum(1 for p in body["points"] if p["total"] == 0) == 46  # zero-filled
    wider = client.get("/api/v1/logs/timeseries?hours=96", headers=auth).json()
    assert sum(p["total"] for p in wider["points"]) == 5


def test_timeseries_validation_isolation_and_auth(client, auth):
    post(client, auth, "x", level="ERROR")
    assert client.get("/api/v1/logs/timeseries?hours=0", headers=auth).status_code == 422
    assert client.get("/api/v1/logs/timeseries?hours=500", headers=auth).status_code == 422
    bob = make_user(client, "bob@example.com")
    assert sum(p["total"] for p in client.get("/api/v1/logs/timeseries", headers=bob).json()["points"]) == 0
    assert client.get("/api/v1/logs/timeseries").status_code == 401


def test_dashboard_is_served(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/app/"
    page = client.get("/app/")
    assert page.status_code == 200 and "OpsPilot" in page.text
    assert "innerHTML" not in page.text  # guard: UI must never inject untrusted HTML
