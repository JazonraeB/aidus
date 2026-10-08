"""Minimal reference reader for AIDUS 1.1 event shards (spec/AIDUS.md §4-§10).

Used by the conformance tests; deliberately small and dependency-light
(jsonschema only). It is not the `aidus` CLI.
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
EVENT_SCHEMA = json.loads((SCHEMA_DIR / "event.schema.json").read_text(encoding="utf-8"))
EVENT_VALIDATOR = Draft202012Validator(EVENT_SCHEMA)
KNOWN_FIELDS = set(EVENT_SCHEMA["properties"])
PRICED_BUCKETS = ("input_tokens", "cache_read_tokens", "cache_write_5m_tokens",
                  "cache_write_1h_tokens", "cache_write_tokens", "output_tokens")
CREDENTIAL_PATTERNS = [re.compile(p) for p in (
    r"sk-[A-Za-z0-9_-]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+",
)]
FUTURE_TOLERANCE = timedelta(minutes=5)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def check_line(raw):
    """Return (event, None) if the line is acceptable, else (None, reason)."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None, "invalid_json"
    if not isinstance(obj, dict):
        return None, "schema"
    version = str(obj.get("schema_version", ""))
    m = re.fullmatch(r"(\d+)\.(\d+)", version)
    if not m:
        return None, "schema"
    major, minor = int(m.group(1)), int(m.group(2))
    if major != 1:
        return None, "unsupported_major"
    if minor > 1:  # §10: ignore unknown fields of a higher minor version
        obj = {k: v for k, v in obj.items() if k in KNOWN_FIELDS or k.startswith("x-")}
        obj["schema_version"] = "1.1"
    if any(p.search(s) for s in _strings(obj) for p in CREDENTIAL_PATTERNS):
        return None, "credential_pattern"
    if next(EVENT_VALIDATOR.iter_errors(obj), None) is not None:
        return None, "schema"
    out, reasoning = obj.get("output_tokens"), obj.get("reasoning_tokens")
    if out is not None and reasoning is not None and reasoning > out:
        return None, "reasoning_exceeds_output"
    if obj.get("cache_write_tokens") is not None and (
            obj.get("cache_write_5m_tokens") is not None or obj.get("cache_write_1h_tokens") is not None):
        return None, "cache_write_overlap"
    if obj.get("total_tokens") is not None:
        if obj["total_tokens"] != sum(obj.get(b) or 0 for b in PRICED_BUCKETS):
            return None, "total_mismatch"
    if _parse_time(obj["timestamp"]) > _parse_time(obj["recorded_at"]) + FUTURE_TOLERANCE:
        return None, "timestamp_after_recorded_at"
    return obj, None


def read_shards(paths):
    """Read shard files; return (events by usage_id, list of quarantine reasons)."""
    quarantine, by_id = [], {}
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        lines = text.split("\n")
        complete = lines[:-1]  # §7.4: the part after the last "\n" is incomplete (or empty)
        for raw in complete:
            if not raw.strip():
                continue
            event, reason = check_line(raw)
            if reason:
                quarantine.append(reason)
            else:
                by_id.setdefault(event["usage_id"], []).append(event)

    events = {}
    for usage_id, candidates in by_id.items():
        material = {json.dumps({k: v for k, v in c.items() if k != "recorded_at"}, sort_keys=True)
                    for c in candidates}
        latest = max(c["recorded_at"] for c in candidates)
        at_latest = [c for c in candidates if c["recorded_at"] == latest]
        latest_material = {json.dumps({k: v for k, v in c.items() if k != "recorded_at"}, sort_keys=True)
                           for c in at_latest}
        if len(material) > 1 and len(latest_material) > 1:
            quarantine.append("duplicate_conflict")  # §6
            continue
        events[usage_id] = at_latest[0]
    return events, quarantine
