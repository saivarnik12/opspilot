from datetime import datetime, timedelta, timezone

from app.analysis.analyzers import AnalysisResult, get_analyzer
from app.main import app
from tests.conftest import make_user


class StubAnalyzer:
    def __init__(self):
        self.calls = 0

    def analyze(self, pattern):
        self.calls += 1
        return AnalysisResult(
            title=f"Stub incident {self.calls}", severity="high", summary="s",
            root_cause="rc", recommended_fixes=["fix a", "fix b"], source="claude", model="stub",
        )


def post_log(client, headers, msg, level="ERROR", source="api", ts=None):
    body = {"source": source, "level": level, "message": msg}
    if ts:
        body["timestamp"] = ts.isoformat()
    assert client.post("/api/v1/logs", json=body, headers=headers).status_code == 201


def seed(client, auth):
    for i in range(3):
        post_log(client, auth, f"Timeout after {i + 5}s calling db {i}")
    post_log(client, auth, "disk full on /var", level="CRITICAL", source="worker")
    post_log(client, auth, "all good", level="INFO")


def test_patterns_group_errors_only(client, auth):
    seed(client, auth)
    r = client.get("/api/v1/incidents/patterns", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert [p["count"] for p in data] == [3, 1]  # INFO ignored
    assert data[0]["sources"] == ["api"]
    assert client.get("/api/v1/incidents/patterns?min_count=2", headers=auth).json()[0]["count"] == 3


def test_patterns_respect_time_window(client, auth):
    old = datetime.now(timezone.utc) - timedelta(days=3)
    post_log(client, auth, "ancient failure", ts=old)
    post_log(client, auth, "fresh failure")
    assert len(client.get("/api/v1/incidents/patterns?hours=24", headers=auth).json()) == 1
    assert len(client.get("/api/v1/incidents/patterns?hours=96", headers=auth).json()) == 2


def test_analyze_creates_then_refreshes_incident(client, auth):
    stub = StubAnalyzer()
    app.dependency_overrides[get_analyzer] = lambda: stub
    seed(client, auth)
    fp = client.get("/api/v1/incidents/patterns", headers=auth).json()[0]["fingerprint"]

    r1 = client.post("/api/v1/incidents/analyze", json={"fingerprint": fp}, headers=auth)
    assert r1.status_code == 201
    inc = r1.json()
    assert inc["status"] == "open" and inc["log_count"] == 3
    assert inc["analysis_source"] == "claude" and inc["recommended_fixes"] == ["fix a", "fix b"]

    r2 = client.post("/api/v1/incidents/analyze", json={"fingerprint": fp}, headers=auth)
    assert r2.status_code == 200 and r2.json()["id"] == inc["id"]
    assert r2.json()["title"] == "Stub incident 2"
    assert len(client.get("/api/v1/incidents", headers=auth).json()) == 1


def test_analyze_unknown_fingerprint_404(client, auth):
    r = client.post("/api/v1/incidents/analyze", json={"fingerprint": "deadbeefdeadbeef"}, headers=auth)
    assert r.status_code == 404


def test_default_analyzer_works_without_api_key(client, auth):
    post_log(client, auth, "write failed: no space left on device")
    fp = client.get("/api/v1/incidents/patterns", headers=auth).json()[0]["fingerprint"]
    r = client.post("/api/v1/incidents/analyze", json={"fingerprint": fp}, headers=auth)
    assert r.status_code == 201
    assert r.json()["analysis_source"] == "rules" and "Disk full" in r.json()["title"]


def test_resolve_and_filter(client, auth):
    app.dependency_overrides[get_analyzer] = lambda: StubAnalyzer()
    post_log(client, auth, "boom")
    fp = client.get("/api/v1/incidents/patterns", headers=auth).json()[0]["fingerprint"]
    iid = client.post("/api/v1/incidents/analyze", json={"fingerprint": fp}, headers=auth).json()["id"]
    assert client.patch(f"/api/v1/incidents/{iid}", json={"status": "resolved"}, headers=auth).json()["status"] == "resolved"
    assert client.get("/api/v1/incidents?status=open", headers=auth).json() == []
    assert len(client.get("/api/v1/incidents?status=resolved", headers=auth).json()) == 1
    assert client.patch(f"/api/v1/incidents/{iid}", json={"status": "bogus"}, headers=auth).status_code == 422
    # after resolving, re-analyzing the same pattern opens a NEW incident (regression tracking)
    again = client.post("/api/v1/incidents/analyze", json={"fingerprint": fp}, headers=auth)
    assert again.status_code == 201 and again.json()["id"] != iid


def test_incidents_are_private_and_protected(client, auth):
    app.dependency_overrides[get_analyzer] = lambda: StubAnalyzer()
    post_log(client, auth, "boom")
    fp = client.get("/api/v1/incidents/patterns", headers=auth).json()[0]["fingerprint"]
    iid = client.post("/api/v1/incidents/analyze", json={"fingerprint": fp}, headers=auth).json()["id"]
    bob = make_user(client, "bob@example.com")
    assert client.get(f"/api/v1/incidents/{iid}", headers=bob).status_code == 404
    assert client.patch(f"/api/v1/incidents/{iid}", json={"status": "resolved"}, headers=bob).status_code == 404
    assert client.get("/api/v1/incidents", headers=bob).json() == []
    assert client.post("/api/v1/incidents/analyze", json={"fingerprint": fp}, headers=bob).status_code == 404
    assert client.get("/api/v1/incidents").status_code == 401
    assert client.get("/api/v1/incidents/patterns").status_code == 401


def test_api_key_can_read_incidents(client, auth):
    key = client.post("/api/v1/api-keys", json={"name": "k"}, headers=auth).json()["key"]
    assert client.get("/api/v1/incidents/patterns", headers={"X-API-Key": key}).status_code == 200
