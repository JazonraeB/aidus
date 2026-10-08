"""Reading and writing .ai-usage/ (spec §2, §6, §7)."""
import json
import os
import secrets
import sys
from pathlib import Path

from . import timeutil, validate

AI_USAGE = ".ai-usage"
MAX_LINE_BYTES = 64 * 1024


class Problem:
    """A validation finding tied to a file (and optionally a line)."""

    def __init__(self, path, reason, line=None):
        self.path, self.reason, self.line = Path(path), reason, line

    def __str__(self):
        where = f"{self.path}:{self.line}" if self.line else str(self.path)
        return f"{where}: {self.reason}"

    def __repr__(self):
        return f"Problem({self})"


def find_root(start):
    """Nearest directory at or above `start` that contains .ai-usage/project.json."""
    here = Path(start).resolve()
    for candidate in (here, *here.parents):
        if (candidate / AI_USAGE / "project.json").is_file():
            return candidate
    return None


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json_atomic(path, obj):
    """Write JSON via a temp file + rename, so a crash never leaves a half-written file (§28)."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def shard_paths(root):
    events = Path(root) / AI_USAGE / "events"
    return sorted(events.glob("*/*.jsonl")) if events.is_dir() else []


def _material(event):
    return json.dumps({k: v for k, v in event.items() if k != "recorded_at"}, sort_keys=True)


def read_shards(paths, project_id=None, check_layout=False):
    """Read shard files and deduplicate by usage_id (spec §6, §7.4).

    Returns (events by usage_id, problems, warnings).
    """
    problems, warnings, by_id = [], [], {}
    for path in paths:
        path = Path(path)
        if check_layout and not validate.WRITER_ID.fullmatch(path.stem):
            problems.append(Problem(path, "file name is not a valid writer_id"))
        data = path.read_bytes()
        text = data.decode("utf-8", errors="replace")
        lines = text.split("\n")
        if lines[-1]:
            warnings.append(Problem(path, "ignoring incomplete last line (no trailing newline)", len(lines)))
        for lineno, raw in enumerate(lines[:-1], start=1):
            if not raw.strip():
                continue
            if len(raw.encode("utf-8")) > MAX_LINE_BYTES:
                problems.append(Problem(path, "line longer than 64 KiB", lineno))
                continue
            event, reason = validate.check_line(raw)
            if reason:
                problems.append(Problem(path, reason, lineno))
                continue
            if project_id is not None and event["project_id"] != project_id:
                problems.append(Problem(path, "project_id differs from project.json", lineno))
                continue
            if check_layout:
                if event["writer_id"] != path.stem:
                    problems.append(Problem(path, "writer_id differs from the file name", lineno))
                    continue
                if timeutil.utc_month(event["timestamp"]) != path.parent.name:
                    problems.append(Problem(path, "event is in the wrong month folder", lineno))
                    continue
            by_id.setdefault(event["usage_id"], []).append((event, path, lineno))

    events = {}
    for usage_id, candidates in by_id.items():
        latest_time = max(timeutil.parse(e["recorded_at"]) for e, _, _ in candidates)
        at_latest = [c for c in candidates if timeutil.parse(c[0]["recorded_at"]) == latest_time]
        if len({_material(e) for e, _, _ in at_latest}) > 1:
            _, path, lineno = at_latest[-1]
            problems.append(Problem(path, f"duplicate_conflict for {usage_id}", lineno))
            continue
        events[usage_id] = at_latest[0][0]
    return events, problems, warnings


def append_events(root, writer_id, events):
    """Append events to this writer's monthly shards, one write per line (spec §7)."""
    by_month = {}
    for event in events:
        by_month.setdefault(timeutil.utc_month(event["timestamp"]), []).append(event)
    written = []
    for month, batch in sorted(by_month.items()):
        path = Path(root) / AI_USAGE / "events" / month / f"{writer_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "ab") as fh:
            for event in batch:
                line = (json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
                if len(line) > MAX_LINE_BYTES:
                    raise ValueError(f"event {event['usage_id']} exceeds 64 KiB")
                fh.write(line)
                fh.flush()
        written.append(path)
    return written


def state_dir():
    """Per-user state directory, outside every repository (spec §7.1)."""
    override = os.environ.get("AIDUS_STATE_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "aidus"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "aidus"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "aidus"


def writer_id(tool):
    """Stable random writer id for this user x machine x tool, created on first use."""
    path = state_dir() / "writers.json"
    try:
        writers = load_json(path)
    except (FileNotFoundError, ValueError):
        writers = {}
    wid = writers.get(tool)
    if not (isinstance(wid, str) and validate.WRITER_ID.fullmatch(wid)):
        wid = secrets.token_hex(8)  # 16 lowercase hex chars
        writers[tool] = wid
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, writers)
    return wid
