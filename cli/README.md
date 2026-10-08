# aidus CLI

`aidus` is a zero-dependency writer and validator for [AIDUS](https://github.com/JazonraeB/aidus/blob/main/spec/AIDUS.md) files. It needs Python 3.10+ and no third-party packages.

```bash
pip install "git+https://github.com/JazonraeB/aidus#subdirectory=cli"   # until it is published on PyPI
```

| Command | Purpose |
| --- | --- |
| `aidus init [--path DIR] [--name NAME]` | Create `.ai-usage/`. An existing `project.json` is never overwritten |
| `aidus record --from claude-code --transcript FILE` | Append events from a Claude Code transcript and its subagent transcripts |
| `aidus record --from claude-code-hook` | The same, reading the Claude Code hook payload from stdin. **Always exits 0.** Errors go to the state-dir log |
| `aidus validate [--path DIR]` | Check `.ai-usage/` against the spec and print `file:line: reason`. Exits 1 on problems. Use it as a pre-commit check |
| `aidus rebuild [--path DIR]` | Regenerate `usage.json` from `events/` (spec §5). Run it instead of hand-merging a conflict |
| `aidus init --hooks` | Also install a `prepare-commit-msg` hook that adds `AI-Session:` and `Feature:` trailers (spec §8). An existing hook that isn't aidus's is never overwritten |
| `aidus session start\|end` | Track an agent session, outside the repository, so commits made during it get its trailer. `--from claude-code-hook` reads the hook payload and never fails |
| `aidus trailers MSGFILE` | What the hook runs. It adds trailers with `git interpret-trailers --if-exists addIfDifferent` and always exits 0 |

## Recording Claude Code automatically

Add this to the project's `.claude/settings.json`, merging it with any existing `"hooks"`:

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "aidus session start --from claude-code-hook" }] }],
    "Stop": [{ "hooks": [{ "type": "command", "command": "aidus record --from claude-code-hook" }] }],
    "SessionEnd": [{ "hooks": [
      { "type": "command", "command": "aidus record --from claude-code-hook" },
      { "type": "command", "command": "aidus session end --from claude-code-hook" }
    ] }]
  }
}
```

Recording is idempotent. Re-reading a transcript adds only new responses, plus a correction line when a response's usage grew (spec §6).

## Where state lives

The writer id (spec §7) and the error log live **outside** the repository:

| OS | State directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%\aidus` |
| macOS | `~/Library/Application Support/aidus` |
| Linux | `$XDG_STATE_HOME/aidus` |

Set `AIDUS_STATE_DIR` to override it.

## How commit trailers work

1. `SessionStart` runs `aidus session start`. Every `Stop` (via `aidus record`) refreshes a heartbeat file in the state directory. Nothing is written into the repository.
2. On `git commit`, the hook adds `AI-Session: <id>` for each session with a heartbeat in the last 2 hours. If the branch name contains `FEAT-n`, it also adds `Feature: FEAT-n`.
3. `SessionEnd` runs `aidus session end`.

The hook runs before the commit is created, so nothing is amended. `--no-verify` doesn't skip it. If anything fails, the commit goes ahead without trailers.

## Not yet implemented

- Readers for agents other than Claude Code.
