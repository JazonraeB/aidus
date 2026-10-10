"""Session tracking and commit trailers (spec §8), against real git repositories."""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from aidus import git_link
from aidus.__main__ import main

REPO = Path(__file__).resolve().parents[2]


def git(root, *args, env=None):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True, env=env)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "dev@example.com")
    git(root, "config", "user.name", "Dev")
    git(root, "config", "commit.gpgsign", "false")
    (root / "a.txt").write_text("a", encoding="utf-8")
    git(root, "add", "a.txt")
    git(root, "commit", "-q", "-m", "initial")
    return root


def test_sessions_start_refresh_go_stale_and_end(repo):
    git_link.touch_session(repo, "s1")
    git_link.touch_session(repo, "s2")
    assert git_link.active_sessions(repo) == ["s1", "s2"]
    later = git_link.timeutil.format_utc(git_link.timeutil.parse(git_link.timeutil.now()) + git_link.STALE_AFTER * 2)
    assert git_link.active_sessions(repo, later) == []  # silent sessions stop claiming commits
    git_link.end_session(repo, "s1")
    assert git_link.active_sessions(repo) == ["s2"]
    assert git_link.touch_session(repo, "../escape") is None  # ids can't name paths


def test_trailers_added_once_with_feature_from_branch(repo, tmp_path):
    git(repo, "checkout", "-q", "-b", "feat/FEAT-012-auth")
    git_link.touch_session(repo, "sess-1")
    msg = tmp_path / "MSG"
    msg.write_text("feat: login form\n", encoding="utf-8")
    assert git_link.add_trailers(msg, repo) == ["AI-Session: sess-1", "Feature: FEAT-012"]
    git_link.add_trailers(msg, repo)  # amend / rebase run the hook again
    text = msg.read_text(encoding="utf-8")
    assert text.count("AI-Session: sess-1") == 1 and text.count("Feature: FEAT-012") == 1


def test_no_session_no_feature_leaves_message_alone(repo, tmp_path):
    msg = tmp_path / "MSG"
    msg.write_text("chore: tidy\n", encoding="utf-8")
    assert git_link.add_trailers(msg, repo) == []
    assert msg.read_text(encoding="utf-8") == "chore: tidy\n"


def test_installed_hook_adds_trailers_to_a_real_commit(repo):
    assert git_link.install_hook(repo).startswith("installed")
    git_link.touch_session(repo, "sess-9")
    (repo / "b.txt").write_text("b", encoding="utf-8")
    git(repo, "add", "b.txt")
    env = dict(os.environ, PYTHONPATH=str(REPO / "cli" / "src"))
    git(repo, "commit", "-q", "--no-verify", "-m", "feat: b", env=env)  # --no-verify skips commit-msg, not this hook
    body = git(repo, "log", "-1", "--format=%B").stdout
    assert "AI-Session: sess-9" in body


def test_hook_fails_open_when_aidus_is_missing(repo):
    git_link.install_hook(repo, python=sys.executable)
    (repo / "c.txt").write_text("c", encoding="utf-8")
    git(repo, "add", "c.txt")
    env = dict(os.environ, PYTHONPATH="")  # aidus not importable: the commit must still succeed
    git(repo, "commit", "-q", "-m", "chore: c", env=env)
    assert git(repo, "log", "-1", "--format=%s").stdout.strip() == "chore: c"


def test_install_never_overwrites_a_foreign_hook(repo):
    hook = repo / ".git" / "hooks" / "prepare-commit-msg"
    hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    assert git_link.install_hook(repo).startswith("skipped")
    assert hook.read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"


def test_session_commands_from_claude_code_hook(repo, monkeypatch):
    payload = {"session_id": "abc-123", "cwd": str(repo / "sub"), "hook_event_name": "SessionStart"}
    (repo / "sub").mkdir()
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert main(["session", "start", "--from", "claude-code-hook"]) == 0
    assert git_link.active_sessions(repo) == ["abc-123"]
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert main(["session", "end", "--from", "claude-code-hook"]) == 0
    assert git_link.active_sessions(repo) == []
    monkeypatch.setattr("sys.stdin", io.StringIO("garbage"))
    assert main(["session", "start", "--from", "claude-code-hook"]) == 0  # never fails


def test_init_with_hooks(repo):
    assert main(["init", "--path", str(repo), "--hooks"]) == 0
    assert git_link.HOOK_MARKER in (repo / ".git" / "hooks" / "prepare-commit-msg").read_text(encoding="utf-8")


def test_feature_trailer_on_the_first_commit_of_a_repository(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    git(root, "init", "-q", "-b", "feat/FEAT-7-export")  # no commit yet: HEAD is unborn
    assert git_link.feature_from_branch(root) == "FEAT-7"
    assert git_link.feature_from_branch(tmp_path) is None  # not a repository


def test_record_at_session_end_does_not_revive_the_session(repo, monkeypatch):
    payload = {"session_id": "abc-123", "cwd": str(repo), "hook_event_name": "Stop"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert main(["record", "--from", "claude-code-hook"]) == 0  # a working session: heartbeat
    assert git_link.active_sessions(repo) == ["abc-123"]

    # SessionEnd runs `record` and `session end` side by side; record may run last.
    ending = dict(payload, hook_event_name="SessionEnd")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(ending)))
    assert main(["session", "end", "--from", "claude-code-hook"]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(ending)))
    assert main(["record", "--from", "claude-code-hook"]) == 0
    assert git_link.active_sessions(repo) == []
