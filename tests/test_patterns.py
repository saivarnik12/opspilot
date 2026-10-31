from types import SimpleNamespace
from datetime import datetime, timezone

from app.analysis.patterns import build_patterns, fingerprint, heuristic_severity, normalize, redact


def row(msg, level="ERROR", source="api", ts=None):
    return SimpleNamespace(message=msg, level=level, source=source, timestamp=ts or datetime.now(timezone.utc))


def test_similar_messages_share_a_fingerprint():
    a = normalize("Timeout after 30s connecting to 10.0.0.5:5432 (req 123)")
    b = normalize("Timeout after 45s connecting to 10.0.0.9:5432 (req 998)")
    assert a == b == "timeout after <n>s connecting to <ip> (req <n>)"
    assert fingerprint(a) == fingerprint(b)


def test_uuid_and_hex_normalized():
    t = normalize("job 3f2b8c1e-1111-2222-3333-444455556666 failed at 0xdeadbeef")
    assert t == "job <uuid> failed at <hex>"


def test_different_errors_get_different_fingerprints():
    assert fingerprint(normalize("disk full")) != fingerprint(normalize("connection refused"))


def test_redaction_removes_secrets():
    text = "login failed for bob@example.com password=hunter2 Bearer abc.def.ghi key op_" + "A" * 30
    out = redact(text)
    for secret in ("bob@example.com", "hunter2", "abc.def.ghi", "A" * 30):
        assert secret not in out


def test_build_patterns_groups_and_orders():
    rows = [row("Timeout after 5s"), row("Timeout after 9s", source="worker"), row("disk full")]
    patterns = build_patterns(rows)
    assert [p.count for p in patterns] == [2, 1]
    assert patterns[0].sources == ["api", "worker"]
    assert patterns[0].levels == {"ERROR": 2}
    assert len(patterns[0].examples) == 2


def test_min_count_filters():
    rows = [row("Timeout after 5s"), row("Timeout after 9s"), row("disk full")]
    assert len(build_patterns(rows, min_count=2)) == 1


def test_severity_heuristic():
    base = build_patterns([row("x")])[0]
    assert heuristic_severity(base) == "low"
    base.count = 5
    assert heuristic_severity(base) == "medium"
    base.count = 20
    assert heuristic_severity(base) == "high"
    base.levels["CRITICAL"] = 1
    assert heuristic_severity(base) == "critical"
