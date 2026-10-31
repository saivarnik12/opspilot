"""Deterministic error-pattern detection: redact, normalize, fingerprint, group."""
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

_REDACTIONS = [
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer <redacted>"),
    (re.compile(r"\bop_[A-Za-z0-9_-]{20,}"), "<api-key>"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "<api-key>"),
    (re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+"), r"\1=<redacted>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
]

_NORMALIZATIONS = [
    (re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b"), "<uuid>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<hex>"),
    (re.compile(r"\b[0-9a-fA-F]{16,}\b"), "<hex>"),
    (re.compile(r"(?<![A-Za-z_<])\d+(?:\.\d+)?"), "<n>"),
]

MAX_EXAMPLES = 5
MAX_EXAMPLE_CHARS = 500


def redact(text: str) -> str:
    """Strip obvious secrets/PII before text is stored in examples or sent to an LLM."""
    for rx, repl in _REDACTIONS:
        text = rx.sub(repl, text)
    return text


def normalize(message: str) -> str:
    """Turn a log line into a stable template so similar errors group together."""
    text = redact(message)
    for rx, repl in _NORMALIZATIONS:
        text = rx.sub(repl, text)
    return " ".join(text.lower().split())[:300]


def fingerprint(template: str) -> str:
    return hashlib.sha256(template.encode()).hexdigest()[:16]


@dataclass
class Pattern:
    fingerprint: str
    template: str
    count: int = 0
    levels: dict[str, int] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    examples: list[str] = field(default_factory=list)


def build_patterns(rows, min_count: int = 1) -> list[Pattern]:
    """Group log rows (anything with .message/.level/.source/.timestamp) by fingerprint."""
    groups: dict[str, Pattern] = {}
    for row in rows:
        template = normalize(row.message)
        fp = fingerprint(template)
        p = groups.get(fp)
        if p is None:
            p = groups[fp] = Pattern(fingerprint=fp, template=template)
        p.count += 1
        p.levels[row.level] = p.levels.get(row.level, 0) + 1
        if row.source not in p.sources:
            p.sources.append(row.source)
        if p.first_seen is None or row.timestamp < p.first_seen:
            p.first_seen = row.timestamp
        if p.last_seen is None or row.timestamp > p.last_seen:
            p.last_seen = row.timestamp
        example = redact(row.message)[:MAX_EXAMPLE_CHARS]
        if len(p.examples) < MAX_EXAMPLES and example not in p.examples:
            p.examples.append(example)
    result = [p for p in groups.values() if p.count >= min_count]
    return sorted(result, key=lambda p: (-p.count, p.fingerprint))


def heuristic_severity(p: Pattern) -> str:
    if p.levels.get("CRITICAL"):
        return "critical"
    if p.count >= 20:
        return "high"
    if p.count >= 5:
        return "medium"
    return "low"
