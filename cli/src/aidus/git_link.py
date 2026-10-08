"""Link AI sessions to commits with trailers (spec §8, monitor ADR-0007).

* Active agent sessions are tracked OUTSIDE the repository, per repo:
  <state_dir>/active/<repo-id>/<session_id>.json
* A `prepare-commit-msg` hook adds `AI-Session: <id>` for each fresh session and
  `Feature: FEAT-n` when the branch name carries one. It runs before the commit
  exists (no amend), is not skipped by --no-verify, and always fails open.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from . import store, timeutil

STALE_AFTER = timedelta(hours=2)  # a session silent this long no longer claims new commits
FEATURE = re.compile(r"FEAT-\d+", re.IGNORECASE)
HOOK_MARKER = "# aidus: AI-Session / Feature trailers"


def git_root(start):
    """Nearest folder at or above `start` that holds a .git directory or file (worktrees)."""
    here = Path(start).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _repo_id(root):
    return hashlib.sha256(os.path.normcase(str(Path(root).resolve())).encode()).hexdigest()[:16]


def _sessions_dir(root):
    return store.state_dir() / "active" / _repo_id(root)


def touch_session(root, session_id, agent="claude-code"):
    """Start a session, or refresh its heartbeat."""
    if not session_id or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", session_id):
        return None
    path = _sessions_dir(root) / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    now = timeutil.now()
    try:
        state = store.load_json(path)
    except (OSError, ValueError):
        state = {"session_id": session_id, "agent": agent, "started_at": now}
    state["heartbeat_at"] = now
    store.write_json_atomic(path, state)
    return path


def end_session(root, session_id):
    path = _sessions_dir(root) / f"{session_id}.json"
    if path.exists():
        path.unlink()


def active_sessions(root, now=None):
    """Session ids with a heartbeat newer than STALE_AFTER, oldest first."""
    now = timeutil.parse(now) if isinstance(now, str) else (now or timeutil.parse(timeutil.now()))
    folder = _sessions_dir(root)
    found = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            state = store.load_json(path)
            beat = timeutil.parse(state["heartbeat_at"])
        except (OSError, ValueError, KeyError):
            continue
        if now - beat <= STALE_AFTER:
            found.append((state.get("started_at", ""), state["session_id"]))
    return [sid for _, sid in sorted(found)]


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10)


def feature_from_branch(root):
    result = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    m = FEATURE.search(result.stdout or "") if result.returncode == 0 else None
    return m.group(0).upper() if m else None


def add_trailers(message_file, root, now=None):
    """Add AI-Session / Feature trailers to a commit message file. Returns the trailers added."""
    trailers = [f"AI-Session: {sid}" for sid in active_sessions(root, now)]
    feature = feature_from_branch(root)
    if feature:
        trailers.append(f"Feature: {feature}")
    if not trailers:
        return []
    args = ["interpret-trailers", "--in-place", "--if-exists", "addIfDifferent"]
    for trailer in trailers:
        args += ["--trailer", trailer]
    result = _git(root, *args, str(message_file))
    return trailers if result.returncode == 0 else []


def hook_script(python=None):
    python = python or sys.executable
    return (f"#!/bin/sh\n{HOOK_MARKER} (installed by `aidus init --hooks`; fails open)\n"
            f"\"{Path(python).as_posix()}\" -m aidus trailers \"$1\" \"$2\" >/dev/null 2>&1 || true\n")


def install_hook(root, python=None):
    """Install .git/hooks/prepare-commit-msg. Never overwrites a hook that isn't ours."""
    git_dir = Path(root) / ".git"
    if not git_dir.is_dir():
        return "skipped: not a regular git checkout"
    hook = git_dir / "hooks" / "prepare-commit-msg"
    if hook.exists() and HOOK_MARKER not in hook.read_text(encoding="utf-8", errors="replace"):
        return f"skipped: {hook} exists and is not an aidus hook; add the aidus line to it by hand"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(hook_script(python), encoding="utf-8", newline="\n")
    try:
        hook.chmod(0o755)
    except OSError:
        pass
    return f"installed {hook}"
