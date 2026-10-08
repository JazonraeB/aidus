"""Minimal reference reader for Claude Code transcripts (spec/AIDUS.md Appendix B).

Copies only allowlisted fields; message content is never read past `usage`.
"""
import json
from pathlib import Path

AGENT = "claude-code"


def _map(line):
    msg, u = line["message"], line["message"]["usage"]
    split = u.get("cache_creation")
    details = u.get("output_tokens_details")
    stu = u.get("server_tool_use")
    return {
        "usage_id": f"{AGENT}:{msg['id']}",
        "cwd": line.get("cwd"),
        "session_id": line.get("sessionId"),
        "timestamp": line.get("timestamp"),
        "provider": "anthropic",
        "model": msg.get("model"),
        "agent": AGENT,
        "agent_version": line.get("version"),
        "branch": line.get("gitBranch"),
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
    }


def read_projects(root):
    """Return (events sorted by usage_id, quarantined [(message_id, reason)], skipped message ids)."""
    root = Path(root)
    files = sorted(root.rglob("*.jsonl"), key=lambda p: p.relative_to(root).as_posix())
    best, quarantined, skipped = {}, {}, set()
    for path in files:
        with path.open(encoding="utf-8") as fh:
            for raw in fh:
                line = json.loads(raw)
                msg = line.get("message")
                if line.get("type") != "assistant" or not isinstance(msg, dict) or "usage" not in msg:
                    continue
                if msg.get("model") == "<synthetic>" or line.get("isApiErrorMessage"):
                    skipped.add(msg["id"])
                    continue
                if len(msg["usage"].get("iterations") or []) > 1:
                    quarantined[msg["id"]] = "iterations_gt_1"
                    continue
                cur = best.get(msg["id"])
                out = msg["usage"].get("output_tokens") or 0
                if cur is None:
                    best[msg["id"]] = line
                    continue
                cur_out = cur["message"]["usage"].get("output_tokens") or 0
                if out > cur_out or (out == cur_out and line["timestamp"] < cur["timestamp"]):
                    best[msg["id"]] = line
    events = sorted((_map(l) for l in best.values()), key=lambda e: e["usage_id"])
    return events, sorted(quarantined.items()), sorted(skipped)
