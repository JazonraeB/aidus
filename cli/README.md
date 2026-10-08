# aidus CLI (planned)

The `aidus` CLI is a zero-dependency Python tool that writes and validates AIDUS files. It will be published to PyPI as `aidus`.

| Command | Purpose |
| --- | --- |
| `aidus init [--hooks]` | Create `.ai-usage/`. Optionally install the `prepare-commit-msg` trailer hook and agent hook examples |
| `aidus record` | Append one event, using usage data read from an agent hook or transcript, never typed by hand |
| `aidus validate` | Check files against the schemas and the spec's cross-field and privacy rules. Suitable for a pre-commit check |
| `aidus rebuild` | Regenerate `usage.json` from `events/` (spec §5) |
| `aidus session start/stop` | Track active agent sessions outside the repo, for commit trailers (spec §8) |

The CLI must pass the conformance suite in [`../fixtures/`](../fixtures/).
