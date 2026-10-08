"""Generate the AIDUS 1.1 event conformance fixtures (spec/AIDUS.md §4-§9).

Expected outcomes live in expected.json and are written by hand.
Run from the repository root:

    python fixtures/events/generate.py
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
BASE = {
    "schema_version": "1.1",
    "project_id": "demo-project-0001",
    "writer_id": "w1a2b3c4d5",
    "source": "coding-agent",
    "provider": "anthropic",
    "model": "claude-sonnet-5",
    "agent": "claude-code",
    "agent_version": "2.1.270",
    "session_id": "11111111-1111-4111-8111-111111111111",
    "timestamp": "2026-10-01T09:00:01Z",
    "recorded_at": "2026-10-01T09:00:02Z",
    "input_tokens": 3,
    "cache_read_tokens": 1000,
    "cache_write_5m_tokens": 0,
    "cache_write_1h_tokens": 200,
    "cache_write_tokens": None,
    "output_tokens": 50,
    "reasoning_tokens": 20,
}


def ev(usage_id, **over):
    e = dict(BASE, usage_id=usage_id)
    for k, v in over.items():
        if v is ...:
            e.pop(k, None)
        else:
            e[k] = v
    return e


def write(name, lines, *, tail=None):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(json.dumps(line, separators=(",", ":")) + "\n")
        if tail is not None:
            f.write(tail)  # deliberately no trailing newline


# --- valid -------------------------------------------------------------------
write("valid/anthropic-basic.jsonl", [
    ev("claude-code:msg_V01", total_tokens=1253),
    ev("claude-code:msg_V02", model="claude-opus-5-5", speed="fast", inference_geo="not_available",
       service_tier="standard", server_tool_requests={"web_search": 2, "web_fetch": 0},
       input_tokens=10, cache_read_tokens=5000, cache_write_1h_tokens=0, output_tokens=900,
       reasoning_tokens=300, branch="feat/FEAT-001-login", feature_id="FEAT-001",
       commit="0a1b2c3d", developer="hmac-sha256:" + "ab" * 32),
])
write("valid/openai-mapped.jsonl", [
    # prompt_tokens=1200 incl. cached_tokens=1000 -> input 200; completion=300 incl. reasoning=120
    ev("codex:resp_V03", provider="openai", model="gpt-6", agent="codex", agent_version="1.0.0",
       input_tokens=200, cache_read_tokens=1000, cache_write_5m_tokens=None, cache_write_1h_tokens=None,
       cache_write_tokens=None, output_tokens=300, reasoning_tokens=120, total_tokens=1500),
])
write("valid/duplicate-identical.jsonl", [ev("claude-code:msg_V04"), ev("claude-code:msg_V04")])
write("valid/correction-later-recorded.jsonl", [
    ev("claude-code:msg_V05", output_tokens=2, reasoning_tokens=0),
    ev("claude-code:msg_V05", output_tokens=444, reasoning_tokens=20, recorded_at="2026-10-01T09:05:00Z"),
])
write("valid/truncated-tail.jsonl", [ev("claude-code:msg_V06")],
      tail='{"schema_version":"1.1","usage_id":"claude-code:msg_V07","project_id":"demo-proj')
write("valid/extension-field.jsonl", [ev("claude-code:msg_V08", **{"x-team-cost-center": "cc-42"})])
write("valid/higher-minor.jsonl", [ev("claude-code:msg_V09", schema_version="1.2", future_field="ignored")])
write("valid/hash-usage-id.jsonl", [ev("h:" + "0" * 64, session_id=None)])
write("valid/unknown-cost.jsonl", [
    ev("claude-code:msg_V10", cost={"amount_micros": None, "currency": "USD", "cost_status": "unknown",
                                    "pricing_source": None, "pricing_version": None}),
])

# --- invalid (one case per file) ------------------------------------------------
write("invalid/negative-tokens.jsonl", [ev("claude-code:msg_X01", output_tokens=-5)])
write("invalid/missing-usage-id.jsonl", [{k: v for k, v in ev("x:y").items() if k != "usage_id"}])
write("invalid/unsupported-major.jsonl", [ev("claude-code:msg_X03", schema_version="2.0")])
write("invalid/reasoning-exceeds-output.jsonl", [ev("claude-code:msg_X04", output_tokens=50, reasoning_tokens=60)])
write("invalid/total-mismatch.jsonl", [ev("claude-code:msg_X05", total_tokens=1273)])  # added reasoning wrongly
write("invalid/cache-write-overlap.jsonl", [ev("claude-code:msg_X06", cache_write_tokens=200)])
write("invalid/timestamp-after-recorded.jsonl", [
    ev("claude-code:msg_X07", timestamp="2026-10-01T10:00:00Z", recorded_at="2026-10-01T09:00:00Z"),
])
write("invalid/credential-in-notes.jsonl", [ev("claude-code:msg_X08", notes="key sk-FAKEFAKEFAKEFAKEFAKEFAKE0000")])
write("invalid/developer-plaintext.jsonl", [ev("claude-code:msg_X09", developer="rae@example.com")])
write("invalid/unknown-field.jsonl", [ev("claude-code:msg_X10", prompt="REDACTED")])
write("invalid/unknown-cost-with-amount.jsonl", [
    ev("claude-code:msg_X11", cost={"amount_micros": 100, "currency": "USD", "cost_status": "unknown"}),
])
write("invalid/conflicting-duplicates.jsonl", [
    ev("claude-code:msg_X12", output_tokens=50),
    ev("claude-code:msg_X12", output_tokens=70),  # same recorded_at, different counts
])
write("invalid/not-json.jsonl", [], tail="this is not json\n")
print("written under", HERE)
