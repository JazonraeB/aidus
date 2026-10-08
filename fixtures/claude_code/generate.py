"""Generate the synthetic Claude Code transcript fixtures.

All ids, paths and text are invented. The line shapes mirror what Claude Code
2.1.25x-2.1.27x writes, so readers can be tested against spec/AIDUS.md
Appendix B. Run from the repository root:

    python fixtures/claude_code/generate.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent / "v2.1" / "projects" / "C--work-demo-app"
S1 = "11111111-1111-4111-8111-111111111111"
S2 = "22222222-2222-4222-8222-222222222222"
CWD = "C:\\work\\demo-app"
BRANCH = "feat/FEAT-001-login"


def usage(inp, read, out, *, w5m=0, w1h=0, thinking=0, speed="standard",
          web_search=0, split=True, details=True, iterations=1):
    u = {
        "input_tokens": inp,
        "cache_creation_input_tokens": w5m + w1h,
        "cache_read_input_tokens": read,
        "output_tokens": out,
        "service_tier": "standard",
        "inference_geo": "not_available",
    }
    if split:
        u["cache_creation"] = {"ephemeral_5m_input_tokens": w5m, "ephemeral_1h_input_tokens": w1h}
    if details:
        u["output_tokens_details"] = {"thinking_tokens": thinking}
        u["server_tool_use"] = {"web_search_requests": web_search, "web_fetch_requests": 0}
        u["speed"] = speed
        u["iterations"] = [{"type": "message", "input_tokens": inp, "output_tokens": out,
                            "cache_read_input_tokens": read,
                            "cache_creation_input_tokens": w5m + w1h}] * iterations
    return u


def assistant(msg_id, req_id, ts, u, *, session=S1, model="claude-sonnet-5", stop="tool_use",
              version="2.1.270", sidechain=False, agent_id=None, api_error=None):
    line = {
        "parentUuid": None, "isSidechain": sidechain, "userType": "external", "cwd": CWD,
        "sessionId": session, "version": version, "gitBranch": BRANCH, "type": "assistant",
        "requestId": req_id, "timestamp": ts,
        "uuid": f"uuid-{msg_id}-{ts}",
        "message": {
            "id": msg_id, "type": "message", "role": "assistant", "model": model,
            "content": [{"type": "text", "text": "REDACTED-ASSISTANT-TEXT"}],
            "stop_reason": stop, "stop_sequence": None, "usage": u,
        },
    }
    if agent_id:
        line["agentId"] = agent_id
    if api_error is not None:
        line["isApiErrorMessage"] = api_error
    return line


def user(ts, session=S1):
    return {"type": "user", "cwd": CWD, "sessionId": session, "version": "2.1.270", "gitBranch": BRANCH,
            "timestamp": ts, "message": {"role": "user", "content": "REDACTED-PROMPT"}}


a01 = assistant("msg_A01", "req_A01", "2026-10-01T09:00:01.000Z", usage(3, 1000, 50, w1h=200, thinking=20))
s1 = [
    user("2026-10-01T09:00:00.000Z"),
    a01,
    a01,                                                                                   # identical duplicate
    assistant("msg_A02", "req_A02", "2026-10-01T09:00:05.000Z", usage(5, 1200, 2, w1h=300), stop=None),
    assistant("msg_A02", "req_A02", "2026-10-01T09:00:05.100Z", usage(5, 1200, 2, w1h=300), stop=None),
    assistant("msg_A02", "req_A02", "2026-10-01T09:00:09.000Z", usage(5, 1200, 444, w1h=300, thinking=100)),
    assistant("msg_A03", "req_A03a", "2026-10-01T09:01:00.000Z", usage(2, 1500, 100)),
    assistant("msg_A03", "req_A03b", "2026-10-01T09:01:00.200Z", usage(2, 1500, 100)),     # other requestId, same usage
    assistant("msg_SYN1", "req_SYN1", "2026-10-01T09:02:00.000Z", usage(0, 0, 0), model="<synthetic>"),
    assistant("msg_ERR1", "req_ERR1", "2026-10-01T09:03:00.000Z", usage(0, 0, 0), api_error=True),
    assistant("msg_A06", "req_A06", "2026-10-01T09:04:00.000Z",
              usage(10, 5000, 900, thinking=300, speed="fast", web_search=2), model="claude-opus-5-5"),
    assistant("msg_A07", "req_A07", "2026-10-01T09:05:00.000Z", usage(1, 100, 10, iterations=2)),
    {"type": "file-history-snapshot", "messageId": "uuid-x", "snapshot": {"trackedFileBackups": {}}},
]
s2 = [
    a01,                                                                                   # copied by a resumed session
    user("2026-10-02T10:00:00.000Z", session=S2),
    assistant("msg_B01", "req_B01", "2026-10-02T10:00:01.000Z",
              usage(7, 0, 80, w1h=1500, split=False, details=False), session=S2, version="2.1.263"),
]
sub = [
    assistant("msg_C01", "req_C01", "2026-10-01T09:06:00.000Z", usage(4, 2000, 60, w5m=400),
              sidechain=True, agent_id="aaaa1111"),
    assistant("msg_C01", "req_C01", "2026-10-01T09:06:00.000Z", usage(4, 2000, 60, w5m=400),
              sidechain=True, agent_id="aaaa1111"),
]


def write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(json.dumps(line, separators=(",", ":")) + "\n")


write(ROOT / f"{S1}.jsonl", s1)
write(ROOT / f"{S2}.jsonl", s2)
write(ROOT / S1 / "subagents" / "agent-aaaa1111.jsonl", sub)
print("written under", ROOT)
