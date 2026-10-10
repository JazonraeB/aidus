"""The aidus commands: init, record, validate, rebuild."""
import json
import re
import sys
import traceback
import uuid
from datetime import timedelta
from pathlib import Path

from . import claude_code, git_link, store, timeutil, validate

GITATTRIBUTES = """events/** text eol=lf merge=union
usage.json text eol=lf linguist-generated=true
project.json text eol=lf
"""
GITIGNORE_LINES = (".ai-usage/imports/*", "!.ai-usage/imports/.gitkeep")
README = """# .ai-usage

AI usage telemetry for this project in the AIDUS 1.1 format
(https://github.com/JazonraeB/aidus/blob/main/spec/AIDUS.md).

- `project.json`: project identity. Never change `project_id`.
- `usage.json`: derived summary. Regenerate with `aidus rebuild`, never edit by hand.
  On a merge conflict, run `aidus rebuild` instead of merging.
- `events/YYYY-MM/<writer_id>.jsonl`: append-only usage events written by tools.
- `sessions/`: optional session rollups. Review before committing.
- `imports/`: raw provider exports. Gitignored.

Metadata only: no prompts, code, conversations or credentials.
Check before committing with `aidus validate`.
"""
CLAUDE_CODE_HOOK = {
    "hooks": {
        "SessionStart": [{"hooks": [{"type": "command", "command": "aidus session start --from claude-code-hook"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "aidus record --from claude-code-hook"}]}],
        "SessionEnd": [{"hooks": [{"type": "command", "command": "aidus record --from claude-code-hook"},
                                  {"type": "command", "command": "aidus session end --from claude-code-hook"}]}],
    }
}
COMPARED_FIELDS = validate.TOKEN_FIELDS + ("speed", "inference_geo", "service_tier", "server_tool_requests", "model")


def _err(msg):
    print(f"aidus: {msg}", file=sys.stderr)


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "project")[:40].strip("-") or "project"


# --- init -------------------------------------------------------------------------

def cmd_init(args):
    root = Path(args.path).resolve()
    base = root / store.AI_USAGE
    created = []
    for sub in ("events", "sessions", "imports"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    for keep in ("sessions/.gitkeep", "imports/.gitkeep"):
        if not (base / keep).exists():
            (base / keep).touch()

    project_path = base / "project.json"
    if project_path.exists():
        project = store.load_json(project_path)  # §21.3: never overwrite an existing identity
        print(f"kept existing {project_path.relative_to(root)} (project_id {project.get('project_id')})")
    else:
        name = args.name or root.name
        project = {
            "schema_version": "1.1",
            "project_id": f"{_slug(name)}-{uuid.uuid4().hex[:12]}",
            "project_name": name,
            "description": "",
            "repository": {"provider": "", "url": "", "branch": ""},
            "team": "",
            "environment": "development",
            "created_at": timeutil.now(),
            "monitoring": {"enabled": True, "format": "json"},
        }
        store.write_json_atomic(project_path, project)
        created.append(project_path)

    usage_path = base / "usage.json"
    if not usage_path.exists():
        store.write_json_atomic(usage_path, {"schema_version": "1.0", "project_id": project["project_id"],
                                             "updated_at": timeutil.now(), "records": []})
        created.append(usage_path)
    for rel, content in ((".gitattributes", GITATTRIBUTES), ("README.md", README)):
        path = base / rel
        if not path.exists():
            path.write_text(content, encoding="utf-8", newline="\n")
            created.append(path)

    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [line for line in GITIGNORE_LINES if line not in existing]
    if missing:
        with open(gitignore, "a", encoding="utf-8", newline="\n") as fh:
            if existing and existing[-1].strip():
                fh.write("\n")
            fh.write("# AIDUS raw provider exports\n" + "\n".join(missing) + "\n")
        created.append(gitignore)

    for path in created:
        print(f"wrote {path.relative_to(root)}")
    if getattr(args, "hooks", False):
        print(git_link.install_hook(root))
    print("\nTo record Claude Code usage automatically, add this to .claude/settings.json "
          "(merge with any existing \"hooks\"):\n")
    print(json.dumps(CLAUDE_CODE_HOOK, indent=2))
    print("\nBefore committing, run: aidus validate")
    return 0


# --- record -------------------------------------------------------------------------

def _same_usage(a, b):
    return all(a.get(k) == b.get(k) for k in COMPARED_FIELDS)


def record_claude_code(root, transcript):
    """Append new or corrected events from one transcript. Returns a summary dict."""
    project = store.load_json(root / store.AI_USAGE / "project.json")
    existing, _, _ = store.read_shards(store.shard_paths(root))
    wid = store.writer_id(claude_code.AGENT)
    best, quarantined, skipped = claude_code.read_lines(claude_code.transcript_files(transcript))

    recorded_at = timeutil.now()
    new, corrections, rejected = [], 0, []
    for line in sorted(best.values(), key=lambda l: str(l.get("timestamp"))):
        if not line.get("timestamp"):
            continue
        event = claude_code.to_event(line, project_id=project["project_id"], writer_id=wid,
                                     recorded_at=recorded_at)
        current = existing.get(event["usage_id"])
        if current is not None:
            if _same_usage(event, current) or \
                    (event.get("output_tokens") or 0) <= (current.get("output_tokens") or 0):
                continue
            # A later, more complete view of the same response: a correction line (§6).
            prev = timeutil.parse(current["recorded_at"])
            if timeutil.parse(event["recorded_at"]) <= prev:
                event["recorded_at"] = timeutil.format_utc(prev + timedelta(microseconds=1))
            corrections += 1
        checked, reason = validate.check_event(event)
        if reason:
            rejected.append((event["usage_id"], reason))
            continue
        new.append(checked)
    store.append_events(root, wid, new)
    return {"recorded": len(new) - corrections, "corrections": corrections,
            "quarantined": sorted(quarantined.items()), "rejected": rejected, "skipped": len(skipped)}


def _report(summary):
    print(f"aidus: recorded {summary['recorded']} new event(s), {summary['corrections']} correction(s)",
          file=sys.stderr)
    for message_id, reason in summary["quarantined"] + summary["rejected"]:
        _err(f"not recorded {message_id}: {reason}")


def cmd_record(args):
    if args.source == "claude-code-hook":
        # Fail open: a hook must never break the agent or the user's workflow (§8).
        try:
            payload = json.load(sys.stdin)
            repo = git_link.git_root(payload.get("cwd") or Path.cwd())
            # Not on SessionEnd: `session end` runs alongside this hook, and refreshing the heartbeat
            # there would re-create the session it just removed.
            if repo is not None and payload.get("hook_event_name") != "SessionEnd":
                git_link.touch_session(repo, payload.get("session_id"))
            root = store.find_root(payload.get("cwd") or Path.cwd())
            if root is None or not payload.get("transcript_path"):
                return 0
            transcript = Path(payload["transcript_path"])
            if not transcript.is_file():  # a session closed before it wrote anything: nothing to record
                return 0
            _report(record_claude_code(root, transcript))
        except Exception:  # noqa: BLE001 - logged, never raised into the agent
            log = store.state_dir() / "aidus.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(f"{timeutil.now()} record failed\n{traceback.format_exc()}\n")
        return 0

    if not args.transcript:
        _err("--transcript is required with --from claude-code")
        return 2
    root = store.find_root(args.project)
    if root is None:
        _err(f"no .ai-usage/project.json at or above {args.project}; run 'aidus init' first")
        return 2
    _report(record_claude_code(root, Path(args.transcript)))
    return 0


# --- validate -------------------------------------------------------------------------

def collect_problems(root):
    """All problems and warnings in a project's .ai-usage/ (spec §3-§9)."""
    base = root / store.AI_USAGE
    problems, warnings = [], []
    project_id = None
    try:
        project = store.load_json(base / "project.json")
        problems += [store.Problem(base / "project.json", p) for p in validate.check_project(project)]
        project_id = project.get("project_id") if isinstance(project, dict) else None
    except (OSError, ValueError) as exc:
        problems.append(store.Problem(base / "project.json", f"cannot read: {exc}"))
    try:
        usage = store.load_json(base / "usage.json")
        problems += [store.Problem(base / "usage.json", p) for p in validate.check_usage(usage, project_id)]
    except (OSError, ValueError) as exc:
        problems.append(store.Problem(base / "usage.json", f"cannot read: {exc}"))
    _, shard_problems, shard_warnings = store.read_shards(
        store.shard_paths(root), project_id=project_id, check_layout=True)
    problems += shard_problems
    warnings += shard_warnings
    for path in sorted((base / "sessions").glob("*.json")) if (base / "sessions").is_dir() else []:
        try:
            if validate.has_credential(store.load_json(path)):
                problems.append(store.Problem(path, "credential_pattern"))
        except (OSError, ValueError) as exc:
            problems.append(store.Problem(path, f"cannot read: {exc}"))
    gitignore = root / ".gitignore"
    if not (gitignore.exists() and ".ai-usage/imports/*" in gitignore.read_text(encoding="utf-8")):
        warnings.append(store.Problem(gitignore, "does not ignore .ai-usage/imports/ (§2)"))
    return problems, warnings


def cmd_validate(args):
    root = store.find_root(args.path)
    if root is None:
        _err(f"no .ai-usage/project.json at or above {args.path}")
        return 2
    problems, warnings = collect_problems(root)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for p in problems:
        print(f"error: {p}", file=sys.stderr)
    if problems:
        print(f"aidus: {len(problems)} problem(s) found", file=sys.stderr)
        return 1
    print("aidus: .ai-usage is valid")
    return 0


# --- rebuild -------------------------------------------------------------------------

def _sum(values):
    return None if any(v is None for v in values) else sum(values)


def _cache_writes(event):
    parts = [event.get(k) for k in ("cache_write_5m_tokens", "cache_write_1h_tokens", "cache_write_tokens")]
    known = [p for p in parts if p is not None]
    return sum(known) if known else None


def rollups(events):
    """usage.json records (1.0 format) from events (spec §5)."""
    groups = {}
    for e in events:
        key = (timeutil.utc_month(e["timestamp"]), e["provider"], e["model"])
        groups.setdefault(key, []).append(e)
    records = []
    for (month, provider, model), group in sorted(groups.items()):
        input_tokens = _sum([_sum([e.get("input_tokens"), _cache_writes(e)]) for e in group])
        cached = _sum([e.get("cache_read_tokens") for e in group])
        output = _sum([e.get("output_tokens") for e in group])
        records.append({
            "usage_id": f"rollup:{month}:{provider}:{model}",
            "timestamp": f"{month}-01T00:00:00Z",
            "provider": provider,
            "model": model,
            "source": "cli-integration",
            "session_id": None,
            "input_tokens": input_tokens,
            "output_tokens": output,
            "cached_input_tokens": cached,
            "reasoning_tokens": _sum([e.get("reasoning_tokens") for e in group]),
            "total_tokens": _sum([input_tokens, cached, output]),
            "estimated_cost": None,
            "currency": "USD",
            "cost_status": "unknown",
            "feature": None,
            "developer": None,
            "commit": None,
            "notes": f"AIDUS 1.1 rollup of {len(group)} events",
        })
    return records


def cmd_rebuild(args):
    root = store.find_root(args.path)
    if root is None:
        _err(f"no .ai-usage/project.json at or above {args.path}")
        return 2
    project = store.load_json(root / store.AI_USAGE / "project.json")
    events, problems, _ = store.read_shards(store.shard_paths(root), project_id=project["project_id"])
    for p in problems:
        _err(f"skipped invalid line {p}")
    usage = {"schema_version": "1.0", "project_id": project["project_id"],
             "updated_at": timeutil.now(), "records": rollups(events.values())}
    store.write_json_atomic(root / store.AI_USAGE / "usage.json", usage)
    print(f"aidus: rebuilt usage.json from {len(events)} event(s) into {len(usage['records'])} record(s)")
    return 1 if problems else 0


# --- session / trailers (spec §8) -----------------------------------------------------------------

def _log_failure(what):
    log = store.state_dir() / "aidus.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(f"{timeutil.now()} {what} failed\n{traceback.format_exc()}\n")


def cmd_session(args):
    """Track an agent session for commit trailers. Hook mode reads the payload from stdin and never fails."""
    try:
        if args.source == "claude-code-hook":
            payload = json.load(sys.stdin)
            cwd, session_id = payload.get("cwd") or Path.cwd(), payload.get("session_id")
        else:
            cwd, session_id = args.path, args.session_id
        repo = git_link.git_root(cwd)
        if repo is None or not session_id:
            return 0
        if args.action == "start":
            git_link.touch_session(repo, session_id)
        else:
            git_link.end_session(repo, session_id)
    except Exception:  # noqa: BLE001 - a hook must never break the agent
        _log_failure(f"session {args.action}")
    return 0


def cmd_trailers(args):
    """prepare-commit-msg hook: add AI-Session / Feature trailers. Always exits 0."""
    try:
        repo = git_link.git_root(Path.cwd())
        if repo is not None and args.message_file:
            git_link.add_trailers(Path(args.message_file), repo)
    except Exception:  # noqa: BLE001 - never block a commit
        _log_failure("trailers")
    return 0
