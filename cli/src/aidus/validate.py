"""Validation of AIDUS records without third-party libraries.

Mirrors schema/*.schema.json (the conformance tests check that both agree on
every fixture line) and adds the cross-field and privacy rules of spec §4.2,
§4.1 and §9 that JSON Schema cannot express.
"""
import json
import re
from datetime import timedelta

from . import timeutil

PRICED_BUCKETS = ("input_tokens", "cache_read_tokens", "cache_write_5m_tokens",
                  "cache_write_1h_tokens", "cache_write_tokens", "output_tokens")
TOKEN_FIELDS = PRICED_BUCKETS + ("reasoning_tokens", "total_tokens")
SOURCES = {"coding-agent", "provider-api", "provider-billing", "local-log",
           "manual-import", "ide-integration", "cli-integration"}
COST_STATUSES = {"authoritative", "calculated", "estimated", "unknown"}
REQUIRED = ("schema_version", "usage_id", "project_id", "timestamp", "recorded_at",
            "writer_id", "source", "provider", "model")

PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{6,126}[a-z0-9]$")
WRITER_ID = re.compile(r"^[a-z0-9]{8,32}$")
USAGE_ID = re.compile(r"^[A-Za-z0-9._-]+:[A-Za-z0-9._:-]+$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
DATETIME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$")
TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
FEATURE = re.compile(r"^FEAT-[0-9]+$")
DEVELOPER = re.compile(r"^hmac-sha256:[0-9a-f]{64}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
EXTENSION = re.compile(r"^x-[a-z0-9-]+$")
VERSION = re.compile(r"^(\d+)\.(\d+)$")
URL_WITH_CREDENTIALS = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^/@]+@")

CREDENTIAL_PATTERNS = [re.compile(p) for p in (
    r"sk-[A-Za-z0-9_-]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+",
)]
FUTURE_TOLERANCE = timedelta(minutes=5)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _nullable_str(v, pattern=None, maxlen=None):
    if v is None:
        return True
    if not isinstance(v, str) or (maxlen is not None and len(v) > maxlen):
        return False
    return pattern is None or bool(pattern.fullmatch(v))


def _str(v, pattern=None, minlen=0, maxlen=None):
    return isinstance(v, str) and len(v) >= minlen and _nullable_str(v, pattern, maxlen)


def _tokens(v):
    return v is None or (_is_int(v) and v >= 0)


def _cost(v):
    if v is None:
        return True
    if not isinstance(v, dict) or set(v) - {"amount_micros", "currency", "cost_status",
                                            "pricing_source", "pricing_version"}:
        return False
    if not {"amount_micros", "currency", "cost_status"} <= set(v):
        return False
    amount = v["amount_micros"]
    if not (amount is None or (_is_int(amount) and amount >= 0)):
        return False
    if not _str(v["currency"], CURRENCY) or v["cost_status"] not in COST_STATUSES:
        return False
    if v["cost_status"] == "unknown" and amount is not None:
        return False
    return (_nullable_str(v.get("pricing_source"), maxlen=64)
            and _nullable_str(v.get("pricing_version"), maxlen=32))


def _server_tools(v):
    if v is None:
        return True
    return isinstance(v, dict) and all(
        isinstance(k, str) and TOOL_NAME.fullmatch(k) and _is_int(n) and n >= 0 for k, n in v.items())


FIELD_CHECKS = {
    "schema_version": lambda v: v == "1.1",
    "usage_id": lambda v: _str(v, USAGE_ID, 3, 256),
    "project_id": lambda v: _str(v, PROJECT_ID),
    "timestamp": lambda v: _str(v, DATETIME),
    "recorded_at": lambda v: _str(v, DATETIME),
    "writer_id": lambda v: _str(v, WRITER_ID),
    "source": lambda v: v in SOURCES,
    "provider": lambda v: _str(v, SLUG),
    "model": lambda v: _str(v, None, 1, 128),
    "agent": lambda v: _nullable_str(v, SLUG),
    "agent_version": lambda v: _nullable_str(v, maxlen=64),
    "session_id": lambda v: _nullable_str(v, maxlen=128),
    "subagent": lambda v: v is None or isinstance(v, bool),
    "speed": lambda v: _nullable_str(v, maxlen=32),
    "inference_geo": lambda v: _nullable_str(v, maxlen=32),
    "service_tier": lambda v: _nullable_str(v, maxlen=32),
    "batch": lambda v: v is None or isinstance(v, bool),
    "server_tool_requests": _server_tools,
    "branch": lambda v: _nullable_str(v, maxlen=255),
    "commit": lambda v: _nullable_str(v, COMMIT),
    "feature_id": lambda v: _nullable_str(v, FEATURE),
    "developer": lambda v: _nullable_str(v, DEVELOPER),
    "notes": lambda v: _nullable_str(v, maxlen=200),
    "cost": _cost,
    **{name: _tokens for name in TOKEN_FIELDS},
}


def strings_in(value):
    """Every string (keys included) inside a JSON value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from strings_in(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings_in(v)


def has_credential(value):
    return any(p.search(s) for s in strings_in(value) for p in CREDENTIAL_PATTERNS)


def schema_ok(event):
    """True if the event satisfies schema/event.schema.json."""
    if not isinstance(event, dict) or not all(k in event for k in REQUIRED):
        return False
    for key, value in event.items():
        check = FIELD_CHECKS.get(key)
        if check is None:
            if not EXTENSION.fullmatch(key):
                return False
        elif not check(value):
            return False
    return True


def check_event(obj):
    """Validate a parsed event line. Returns (event, None) or (None, reason code)."""
    if not isinstance(obj, dict):
        return None, "schema"
    m = VERSION.fullmatch(str(obj.get("schema_version", "")))
    if not m:
        return None, "schema"
    major, minor = int(m.group(1)), int(m.group(2))
    if major != 1:
        return None, "unsupported_major"
    if minor > 1:  # §10: ignore unknown fields of a higher minor version
        obj = {k: v for k, v in obj.items() if k in FIELD_CHECKS or EXTENSION.fullmatch(k)}
        obj["schema_version"] = "1.1"
    if has_credential(obj):
        return None, "credential_pattern"
    if not schema_ok(obj):
        return None, "schema"
    out, reasoning = obj.get("output_tokens"), obj.get("reasoning_tokens")
    if out is not None and reasoning is not None and reasoning > out:
        return None, "reasoning_exceeds_output"
    if obj.get("cache_write_tokens") is not None and (
            obj.get("cache_write_5m_tokens") is not None or obj.get("cache_write_1h_tokens") is not None):
        return None, "cache_write_overlap"
    if obj.get("total_tokens") is not None and \
            obj["total_tokens"] != sum(obj.get(b) or 0 for b in PRICED_BUCKETS):
        return None, "total_mismatch"
    try:
        late = timeutil.parse(obj["timestamp"]) > timeutil.parse(obj["recorded_at"]) + FUTURE_TOLERANCE
    except ValueError:  # matches the pattern but is not a real date, e.g. month 13
        return None, "schema"
    if late:
        return None, "timestamp_after_recorded_at"
    return obj, None


def check_line(raw):
    """Validate one raw JSONL line. Returns (event, None) or (None, reason code)."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None, "invalid_json"
    return check_event(obj)


def check_project(obj):
    """Problems with a project.json object (spec §3), as a list of messages."""
    problems = []
    if not isinstance(obj, dict):
        return ["project.json is not a JSON object"]
    if obj.get("schema_version") not in ("1.0", "1.1"):
        problems.append("schema_version must be '1.0' or '1.1'")
    if not _str(obj.get("project_id"), PROJECT_ID):
        problems.append("project_id is missing or malformed")
    if not _str(obj.get("project_name"), None, 1, 200):
        problems.append("project_name is missing")
    url = (obj.get("repository") or {}).get("url") if isinstance(obj.get("repository"), dict) else None
    if isinstance(url, str) and URL_WITH_CREDENTIALS.match(url):
        problems.append("repository.url contains credentials")
    if has_credential(obj):
        problems.append("credential-shaped string found")
    return problems


def check_usage(obj, project_id=None):
    """Problems with a usage.json object (1.0 format, spec §5), as a list of messages."""
    if not isinstance(obj, dict):
        return ["usage.json is not a JSON object"]
    problems = []
    if obj.get("schema_version") != "1.0":
        problems.append("usage.json schema_version must be '1.0'")
    if project_id is not None and obj.get("project_id") != project_id:
        problems.append("usage.json project_id differs from project.json")
    records = obj.get("records")
    if not isinstance(records, list):
        return problems + ["records must be a list"]
    for i, rec in enumerate(records):
        if not isinstance(rec, dict) or not all(
                isinstance(rec.get(k), str) for k in ("usage_id", "timestamp", "provider", "model", "source")):
            problems.append(f"records[{i}] is missing required fields")
            continue
        for k in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens"):
            if not _tokens(rec.get(k)):
                problems.append(f"records[{i}].{k} must be a non-negative integer or null")
    if has_credential(obj):
        problems.append("credential-shaped string found")
    return problems
