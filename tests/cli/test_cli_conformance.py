"""The CLI must agree with the JSON Schemas and the conformance fixtures."""
import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from aidus import claude_code, store, validate

REPO = Path(__file__).resolve().parents[2]
EVENT_SCHEMA = Draft202012Validator(json.loads((REPO / "schema" / "event.schema.json").read_text(encoding="utf-8")))
EVENTS = REPO / "fixtures" / "events"
EXPECTED = json.loads((EVENTS / "expected.json").read_text(encoding="utf-8"))
CC = REPO / "fixtures" / "claude_code" / "v2.1"
CC_EXPECTED = json.loads((CC / "expected.json").read_text(encoding="utf-8"))

BASE = json.loads((EVENTS / "valid" / "anthropic-basic.jsonl").read_text(encoding="utf-8").splitlines()[1])
MUTATIONS = [
    ("usage_id", 5), ("usage_id", "no-colon"), ("usage_id", "a:b c"), ("project_id", "Bad_ID"),
    ("timestamp", "2026-10-01 09:00:00"), ("timestamp", "2026-10-01T09:00:00"), ("writer_id", "short"),
    ("source", "agent"), ("provider", "Anthropic"), ("model", ""), ("model", "m" * 129),
    ("agent", "Claude Code"), ("subagent", "yes"), ("input_tokens", 1.5), ("input_tokens", True),
    ("output_tokens", -1), ("server_tool_requests", {"Web": 1}), ("server_tool_requests", {"web": -1}),
    ("server_tool_requests", []), ("commit", "XYZ"), ("feature_id", "feat-1"), ("developer", "hmac-sha256:abc"),
    ("notes", "n" * 201), ("cost", {"amount_micros": 1, "currency": "usd", "cost_status": "estimated"}),
    ("cost", {"amount_micros": 1, "currency": "USD"}), ("cost", {"amount_micros": None, "currency": "USD",
                                                               "cost_status": "calculated", "extra": 1}),
    ("cost", {"amount_micros": 5, "currency": "USD", "cost_status": "calculated", "pricing_version": "2026-10"}),
    ("x-ok", 1), ("X-bad", 1), ("unknown", 1), ("batch", None), ("batch", 0), ("schema_version", "1.1.0"),
]


def _fixture_lines():
    for path in sorted(EVENTS.glob("*/*.jsonl")):
        for raw in path.read_text(encoding="utf-8").split("\n")[:-1]:
            try:
                yield path.name, json.loads(raw)
            except json.JSONDecodeError:
                pass


@pytest.mark.parametrize("name,obj", list(_fixture_lines()))
def test_validator_agrees_with_json_schema_on_fixtures(name, obj):
    assert validate.schema_ok(obj) == EVENT_SCHEMA.is_valid(obj)


@pytest.mark.parametrize("field,value", MUTATIONS, ids=[f"{f}={v!r}"[:40] for f, v in MUTATIONS])
def test_validator_agrees_with_json_schema_on_mutations(field, value):
    obj = copy.deepcopy(BASE)
    obj[field] = value
    assert validate.schema_ok(obj) == EVENT_SCHEMA.is_valid(obj)


def _cases():
    for group in ("valid", "invalid"):
        for name, expected in EXPECTED[group].items():
            yield pytest.param(EVENTS / group / name, expected, id=f"{group}/{name}")


@pytest.mark.parametrize("path,expected", list(_cases()))
def test_read_shards_matches_expected(path, expected):
    events, problems, _ = store.read_shards([path])
    assert sorted(events) == sorted(expected["events"])
    reasons = sorted(p.reason.split(" ")[0] for p in problems)
    assert reasons == sorted(expected["quarantine"])


def test_claude_code_reader_matches_expected():
    files = sorted((CC / "projects").rglob("*.jsonl"))
    best, quarantined, skipped = claude_code.read_lines(files)
    events = sorted((claude_code.to_event(line, project_id="demo-project-0001", writer_id="w1a2b3c4d5",
                                          recorded_at="2026-10-08T00:00:00Z") for line in best.values()),
                    key=lambda e: e["usage_id"])
    expected = sorted(CC_EXPECTED["events"], key=lambda e: e["usage_id"])
    assert [e["usage_id"] for e in events] == [e["usage_id"] for e in expected]
    for got, want in zip(events, expected):
        for key, value in want.items():
            if key != "cwd":  # project mapping only; never written to events
                assert got[key] == value, (got["usage_id"], key)
        assert EVENT_SCHEMA.is_valid(got)
    assert [{"message_id": m, "reason": r} for m, r in sorted(quarantined.items())] == CC_EXPECTED["quarantined"]
    assert sorted(skipped) == sorted(CC_EXPECTED["skipped"])
    dumped = json.dumps(events)
    assert all(s not in dumped for s in CC_EXPECTED["forbidden_substrings"])
    assert "cwd" not in dumped and "demo-app" not in dumped


def test_claude_code_reader_keeps_only_allowlisted_fields():
    best, _, _ = claude_code.read_lines(sorted((CC / "projects").rglob("*.jsonl")))
    for line in best.values():
        assert set(line) <= set(claude_code.KEPT_LINE_FIELDS) | {"message"}
        assert set(line["message"]) <= set(claude_code.KEPT_MESSAGE_FIELDS)
    assert "REDACTED" not in json.dumps(list(best.values()))
