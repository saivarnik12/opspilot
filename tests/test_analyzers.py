import json
from types import SimpleNamespace

from app.analysis.analyzers import SYSTEM_PROMPT, ClaudeAnalyzer, RuleBasedAnalyzer
from app.analysis.patterns import build_patterns
from tests.test_patterns import row


def pattern(*msgs, level="ERROR"):
    return build_patterns([row(m, level=level) for m in msgs])[0]


def test_rules_detect_known_signatures():
    cases = {
        "upstream timed out after 30s": "Timeouts",
        "java.lang.OutOfMemoryError: out of memory": "Memory exhaustion",
        "write failed: no space left on device": "Disk full",
        "connect ECONNREFUSED 10.0.0.4:5432": "refusing connections",
        "x509 certificate has expired": "TLS",
    }
    for msg, expected in cases.items():
        r = RuleBasedAnalyzer().analyze(pattern(msg))
        assert expected.lower() in r.title.lower(), (msg, r.title)
        assert r.source == "rules" and len(r.recommended_fixes) >= 2


def test_rules_generic_fallback():
    r = RuleBasedAnalyzer().analyze(pattern("something weird happened"))
    assert r.title.startswith("Recurring error")


class FakeClient:
    def __init__(self, text=None, exc=None):
        self.text, self.exc, self.calls = text, exc, []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])


GOOD = {
    "title": "DB connection pool exhausted",
    "severity": "HIGH",
    "summary": "Requests fail waiting for connections.",
    "root_cause": "Pool too small for current traffic.",
    "recommended_fixes": ["Increase pool size", "Find leaked connections"],
}


def test_claude_success_parses_json():
    client = FakeClient(json.dumps(GOOD))
    r = ClaudeAnalyzer("k", "m1", client=client).analyze(pattern("pool exhausted"))
    assert r.source == "claude" and r.model == "m1"
    assert r.severity == "high"  # normalized to lowercase
    assert r.recommended_fixes[0] == "Increase pool size"


def test_claude_handles_markdown_fenced_json():
    client = FakeClient("```json\n" + json.dumps(GOOD) + "\n```")
    assert ClaudeAnalyzer("k", "m", client=client).analyze(pattern("x")).source == "claude"


def test_claude_bad_output_falls_back_to_rules():
    r = ClaudeAnalyzer("k", "m", client=FakeClient("sorry, no idea")).analyze(pattern("disk full"))
    assert r.source == "rules"


def test_claude_invalid_schema_falls_back():
    bad = dict(GOOD, severity="catastrophic")
    r = ClaudeAnalyzer("k", "m", client=FakeClient(json.dumps(bad))).analyze(pattern("x"))
    assert r.source == "rules"


def test_claude_api_error_falls_back():
    r = ClaudeAnalyzer("k", "m", client=FakeClient(exc=RuntimeError("503"))).analyze(pattern("x"))
    assert r.source == "rules"


def test_prompt_is_redacted_and_marks_logs_untrusted():
    client = FakeClient(json.dumps(GOOD))
    p = pattern("auth failed for bob@example.com password=hunter2")
    ClaudeAnalyzer("k", "m", client=client).analyze(p)
    sent = client.calls[0]
    body = sent["messages"][0]["content"]
    assert "hunter2" not in body and "bob@example.com" not in body
    assert "<logs>" in body
    assert sent["system"] == SYSTEM_PROMPT and "untrusted" in SYSTEM_PROMPT
