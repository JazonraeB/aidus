import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import reference
import reference_claude_code

REPO = Path(__file__).resolve().parent.parent
SCHEMAS = sorted((REPO / "schema").glob("*.schema.json"))
EVENTS = REPO / "fixtures" / "events"
EVENTS_EXPECTED = json.loads((EVENTS / "expected.json").read_text(encoding="utf-8"))
CC = REPO / "fixtures" / "claude_code" / "v2.1"
CC_EXPECTED = json.loads((CC / "expected.json").read_text(encoding="utf-8"))


def _load(name):
    return json.loads((REPO / "schema" / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda p: p.name)
def test_schema_is_valid_json_schema(path):
    Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def _cases():
    for group in ("valid", "invalid"):
        for name, expected in EVENTS_EXPECTED[group].items():
            yield pytest.param(EVENTS / group / name, expected, id=f"{group}/{name}")


@pytest.mark.parametrize("path,expected", list(_cases()))
def test_event_fixture(path, expected):
    events, quarantine = reference.read_shards([path])
    assert sorted(events) == sorted(expected["events"])
    assert sorted(quarantine) == sorted(expected["quarantine"])
    for usage_id, out in expected.get("output_tokens", {}).items():
        assert events[usage_id]["output_tokens"] == out


def test_every_event_fixture_has_an_expectation():
    on_disk = {f"{p.parent.name}/{p.name}" for p in EVENTS.glob("*/*.jsonl")}
    listed = {f"{g}/{n}" for g in ("valid", "invalid") for n in EVENTS_EXPECTED[g]}
    assert on_disk == listed


def test_claude_code_transcripts():
    events, quarantined, skipped = reference_claude_code.read_projects(CC / "projects")
    assert events == sorted(CC_EXPECTED["events"], key=lambda e: e["usage_id"])
    assert [{"message_id": m, "reason": r} for m, r in quarantined] == CC_EXPECTED["quarantined"]
    assert skipped == sorted(CC_EXPECTED["skipped"])


def test_claude_code_output_contains_no_content():
    events, _, _ = reference_claude_code.read_projects(CC / "projects")
    dumped = json.dumps(events)
    for forbidden in CC_EXPECTED["forbidden_substrings"]:
        assert forbidden in (CC / "projects").joinpath(
            "C--work-demo-app", "11111111-1111-4111-8111-111111111111.jsonl").read_text(encoding="utf-8")
        assert forbidden not in dumped


def test_dogfood_ai_usage_files_validate():
    project = json.loads((REPO / ".ai-usage" / "project.json").read_text(encoding="utf-8"))
    usage = json.loads((REPO / ".ai-usage" / "usage.json").read_text(encoding="utf-8"))
    Draft202012Validator(_load("project.schema.json")).validate(project)
    Draft202012Validator(_load("usage.schema.json")).validate(usage)
    assert usage["project_id"] == project["project_id"]
