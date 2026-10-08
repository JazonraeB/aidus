# aidus CLI

`aidus` is a zero-dependency writer and validator for [AIDUS](../spec/AIDUS.md) files. It needs Python 3.10+ and no third-party packages.

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

## Recording Claude Code automatically

Add this to the project's `.claude/settings.json`, merging it with any existing `"hooks"`:

```json
{
  "hooks": {
    "Stop": [{ "hooks": [{ "type": "command", "command": "aidus record --from claude-code-hook" }] }],
    "SessionEnd": [{ "hooks": [{ "type": "command", "command": "aidus record --from claude-code-hook" }] }]
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

## Not yet implemented

- Commit trailers (`prepare-commit-msg`, spec §8) and `aidus session start/stop`.
- Readers for agents other than Claude Code.
