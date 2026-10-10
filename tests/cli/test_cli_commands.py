"""End-to-end tests of aidus init / record / validate / rebuild."""
import io
import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from aidus.__main__ import main
from aidus import store

REPO = Path(__file__).resolve().parents[2]
SCHEMAS = {n: Draft202012Validator(json.loads((REPO / "schema" / f"{n}.schema.json").read_text(encoding="utf-8")))
           for n in ("event", "project", "usage")}
CC_PROJECT = REPO / "fixtures" / "claude_code" / "v2.1" / "projects" / "C--work-demo-app"
S1 = "11111111-1111-4111-8111-111111111111"
S2 = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "demo"
    root.mkdir()
    assert main(["init", "--path", str(root), "--name", "Demo App"]) == 0
    return root


def _events(root):
    lines = []
    for path in store.shard_paths(root):
        lines += [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    return lines


def test_init_creates_valid_layout_and_is_idempotent(project):
    base = project / ".ai-usage"
    proj = json.loads((base / "project.json").read_text(encoding="utf-8"))
    SCHEMAS["project"].validate(proj)
    SCHEMAS["usage"].validate(json.loads((base / "usage.json").read_text(encoding="utf-8")))
    assert proj["project_id"].startswith("demo-app-")
    assert "merge=union" in (base / ".gitattributes").read_text(encoding="utf-8")

    assert main(["init", "--path", str(project), "--name", "Other"]) == 0
    again = json.loads((base / "project.json").read_text(encoding="utf-8"))
    assert again["project_id"] == proj["project_id"]  # identity never overwritten
    assert (project / ".gitignore").read_text(encoding="utf-8").count(".ai-usage/imports/*") == 1


def test_record_is_deduplicated_idempotent_and_valid(project, capsys):
    transcript = CC_PROJECT / f"{S1}.jsonl"
    assert main(["record", "--from", "claude-code", "--transcript", str(transcript), "--project", str(project)]) == 0
    err = capsys.readouterr().err
    assert "recorded 5 new event(s)" in err and "msg_A07: iterations_gt_1" in err

    events = _events(project)
    assert sorted(e["usage_id"] for e in events) == [
        "claude-code:msg_A01", "claude-code:msg_A02", "claude-code:msg_A03",
        "claude-code:msg_A06", "claude-code:msg_C01"]
    for e in events:
        SCHEMAS["event"].validate(e)
    assert next(e for e in events if e["usage_id"] == "claude-code:msg_A02")["output_tokens"] == 444
    assert next(e for e in events if e["usage_id"] == "claude-code:msg_C01")["subagent"] is True

    main(["record", "--from", "claude-code", "--transcript", str(transcript), "--project", str(project)])
    assert len(_events(project)) == 5  # re-recording adds nothing

    main(["record", "--from", "claude-code", "--transcript", str(CC_PROJECT / f"{S2}.jsonl"),
          "--project", str(project)])
    assert len(_events(project)) == 6  # only msg_B01; the copied msg_A01 is skipped
    assert main(["validate", "--path", str(project)]) == 0


def test_record_writes_correction_for_more_complete_usage(project, tmp_path):
    lines = (CC_PROJECT / f"{S1}.jsonl").read_text(encoding="utf-8").splitlines()
    partial = [l for l in lines if '"msg_A02"' in l]
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(partial[0] + "\n", encoding="utf-8")
    main(["record", "--from", "claude-code", "--transcript", str(transcript), "--project", str(project)])
    transcript.write_text("\n".join(partial) + "\n", encoding="utf-8")
    main(["record", "--from", "claude-code", "--transcript", str(transcript), "--project", str(project)])

    assert len(_events(project)) == 2  # original + correction line
    events, problems, _ = store.read_shards(store.shard_paths(project))
    assert not problems
    assert events["claude-code:msg_A02"]["output_tokens"] == 444
    assert main(["validate", "--path", str(project)]) == 0


def test_validate_reports_problems(project, capsys):
    main(["record", "--from", "claude-code", "--transcript", str(CC_PROJECT / f"{S1}.jsonl"),
          "--project", str(project)])
    shard = store.shard_paths(project)[0]
    good = json.loads(shard.read_text(encoding="utf-8").splitlines()[0])

    leaked = dict(good, usage_id="claude-code:msg_LEAK", notes="sk-FAKEFAKEFAKEFAKEFAKEFAKE0000")
    moved = dict(good, usage_id="claude-code:msg_MOVED", timestamp="2026-09-30T23:00:00Z",
                 recorded_at="2026-09-30T23:00:01Z")
    with open(shard, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(leaked) + "\n" + json.dumps(moved) + "\n")
    wrong_writer = shard.with_name("zzzzzzzz9999.jsonl")
    shutil.copy(shard, wrong_writer)

    capsys.readouterr()
    assert main(["validate", "--path", str(project)]) == 1
    err = capsys.readouterr().err
    assert "credential_pattern" in err
    assert "wrong month folder" in err
    assert "writer_id differs from the file name" in err


def test_rebuild_rolls_up_per_month_provider_model(project):
    for s in (S1, S2):
        main(["record", "--from", "claude-code", "--transcript", str(CC_PROJECT / f"{s}.jsonl"),
              "--project", str(project)])
    assert main(["rebuild", "--path", str(project)]) == 0
    usage = json.loads((project / ".ai-usage" / "usage.json").read_text(encoding="utf-8"))
    SCHEMAS["usage"].validate(usage)
    records = {r["usage_id"]: r for r in usage["records"]}
    sonnet = records["rollup:2026-10:anthropic:claude-sonnet-5"]
    # A01 3+200, A02 5+300, A03 2+0, C01 4+400, B01 7+1500 (unsplit write)
    assert (sonnet["input_tokens"], sonnet["cached_input_tokens"], sonnet["output_tokens"]) == (2421, 5700, 734)
    assert sonnet["reasoning_tokens"] is None  # msg_B01 did not report thinking tokens
    assert sonnet["total_tokens"] == 8855
    opus = records["rollup:2026-10:anthropic:claude-opus-5-5"]
    assert (opus["input_tokens"], opus["cached_input_tokens"], opus["output_tokens"],
            opus["reasoning_tokens"], opus["total_tokens"]) == (10, 5000, 900, 300, 5910)
    assert sonnet["cost_status"] == "unknown" and sonnet["estimated_cost"] is None


def test_hook_mode_records_and_fails_open(project, monkeypatch, isolated_state, tmp_path):
    payload = {"session_id": S1, "transcript_path": str(CC_PROJECT / f"{S1}.jsonl"),
               "cwd": str(project), "hook_event_name": "Stop"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert main(["record", "--from", "claude-code-hook"]) == 0
    assert len(_events(project)) == 5

    outside = tmp_path / "not-a-project"
    outside.mkdir()
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(dict(payload, cwd=str(outside)))))
    assert main(["record", "--from", "claude-code-hook"]) == 0

    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert main(["record", "--from", "claude-code-hook"]) == 0
    assert "record failed" in (isolated_state / "aidus.log").read_text(encoding="utf-8")


def test_hook_mode_skips_a_session_without_a_transcript_quietly(project, monkeypatch, isolated_state, tmp_path):
    payload = {"session_id": S1, "transcript_path": str(tmp_path / "never-written.jsonl"),
               "cwd": str(project), "hook_event_name": "SessionEnd"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert main(["record", "--from", "claude-code-hook"]) == 0
    assert _events(project) == [] and not (isolated_state / "aidus.log").exists()  # not an error
