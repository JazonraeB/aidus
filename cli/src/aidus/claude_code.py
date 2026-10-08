"""Read usage from Claude Code transcripts (spec Appendix A.1 and B).

Only allowlisted fields are copied. Message content, tool inputs/outputs,
prompts, titles and summaries are never read past the parsed line.
"""
import json
from pathlib import Path

AGENT = "claude-code"
# The only line fields any reader needs (Appendix B rule 4). Everything else, including
# message content, tool inputs/outputs and prompts, is dropped as soon as a line is parsed.
KEPT_LINE_FIELDS = ("type", "timestamp", "cwd", "sessionId", "version", "gitBranch", "isSidechain", "agentId")
KEPT_MESSAGE_FIELDS = ("id", "model", "usage")


def _trim(line):
    """Allowlisted copy of a transcript line: bounded memory, and content never retained."""
    kept = {k: line[k] for k in KEPT_LINE_FIELDS if k in line}
    kept["message"] = {k: line["message"][k] for k in KEPT_MESSAGE_FIELDS if k in line["message"]}
    return kept


def transcript_files(transcript):
    """The transcript plus its subagent transcripts (<dir>/<session>/subagents/*.jsonl)."""
    transcript = Path(transcript)
    sub = transcript.parent / transcript.stem / "subagents"
    return [transcript] + (sorted(sub.glob("*.jsonl")) if sub.is_dir() else [])


def read_lines(files):
    """Pick one line per response (Appendix B rules 2, 3, 5).

    Returns (best line by message id, quarantined {message id: reason}, skipped ids).
    """
    best, quarantined, skipped = {}, {}, set()
    for path in sorted(files, key=lambda p: Path(p).as_posix()):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                try:
                    line = json.loads(raw)
                except json.JSONDecodeError:
                    continue  # an incomplete line from a session still being written
                msg = line.get("message") if isinstance(line, dict) else None
                if line.get("type") != "assistant" or not isinstance(msg, dict) \
                        or not isinstance(msg.get("usage"), dict) or not msg.get("id"):
                    continue
                if msg.get("model") == "<synthetic>" or line.get("isApiErrorMessage"):
                    skipped.add(msg["id"])
                    continue
                if len(msg["usage"].get("iterations") or []) > 1:
                    quarantined[msg["id"]] = "iterations_gt_1"
                    continue
                current = best.get(msg["id"])
                if current is None or _better(line, current):
                    best[msg["id"]] = _trim(line)
    for message_id in quarantined:
        best.pop(message_id, None)
    return best, quarantined, skipped


def _better(line, current):
    out = line["message"]["usage"].get("output_tokens") or 0
    cur = current["message"]["usage"].get("output_tokens") or 0
    return out > cur or (out == cur and str(line.get("timestamp")) < str(current.get("timestamp")))


def to_event(line, *, project_id, writer_id, recorded_at):
    """Map one transcript line to an AIDUS 1.1 event (Appendix A.1)."""
    msg = line["message"]
    u = msg["usage"]
    split = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else None
    details = u.get("output_tokens_details") if isinstance(u.get("output_tokens_details"), dict) else None
    stu = u.get("server_tool_use") if isinstance(u.get("server_tool_use"), dict) else None
    return {
        "schema_version": "1.1",
        "usage_id": f"{AGENT}:{msg['id']}",
        "project_id": project_id,
        "timestamp": line["timestamp"],
        "recorded_at": recorded_at,
        "writer_id": writer_id,
        "source": "local-log",
        "provider": "anthropic",
        "model": msg["model"],
        "agent": AGENT,
        "agent_version": line.get("version"),
        "session_id": line.get("sessionId"),
        "subagent": bool(line.get("isSidechain")),
        "input_tokens": u.get("input_tokens"),
        "cache_read_tokens": u.get("cache_read_input_tokens"),
        "cache_write_5m_tokens": split.get("ephemeral_5m_input_tokens") if split else None,
        "cache_write_1h_tokens": split.get("ephemeral_1h_input_tokens") if split else None,
        "cache_write_tokens": None if split else u.get("cache_creation_input_tokens"),
        "output_tokens": u.get("output_tokens"),
        "reasoning_tokens": details.get("thinking_tokens") if details else None,
        "speed": u.get("speed"),
        "inference_geo": u.get("inference_geo"),
        "service_tier": u.get("service_tier"),
        "server_tool_requests": ({"web_search": stu.get("web_search_requests", 0),
                                  "web_fetch": stu.get("web_fetch_requests", 0)} if stu else None),
        "branch": line.get("gitBranch") or None,
    }
