# Changelog

All notable changes are documented here. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The spec uses [semantic versioning](https://semver.org/).

## [Unreleased] — 1.1.0-draft

### Added
- AIDUS 1.1 draft spec:
  - append-only event shards
  - disjoint token buckets
  - price modifiers
  - the `calculated` cost status, with a 1.0 compatibility mapping
  - `usage.json` as a derived 1.0-format summary
  - deduplication and writer rules
  - privacy rules
  - provider mappings (Anthropic, OpenAI)
  - Claude Code reading rules.
- JSON Schemas for events, `project.json` and `usage.json`.
- Conformance fixtures (9 valid and 13 invalid event cases, plus synthetic Claude Code transcripts), with a reference reader and tests.
- CI on Windows and Linux, which also checks that fixtures are regenerated reproducibly.
- `aidus` CLI 0.1.0 (zero dependencies, Python 3.10+):
  - `init`
  - `record --from claude-code` and `record --from claude-code-hook` (fail-open)
  - `validate`
  - `rebuild`
- CLI tests:
  - the hand-written validator must agree with the JSON Schema on every fixture line and on 33 targeted mutations
  - end-to-end tests of every command.
- Spec §5: clarified how cache writes are summed into `usage.json`.
- `aidus` 0.2.0: `session start|end`, a `trailers` command and `init --hooks`. The prepare-commit-msg hook adds `AI-Session` / `Feature` trailers, never overwrites a foreign hook, and always fails open. Tests run against real git commits.
- Claude Code reader keeps only allowlisted fields of each transcript line: bounded memory for very large transcripts (250 MB+), and content is never retained.
- Release workflow: when a tag is pushed, it builds, runs `twine check` and publishes to PyPI.
  - It uses Trusted Publishing, so no API tokens are stored.
  - The `pypi` environment requires the owner's approval.
  - The wheel includes the license.
- `aidus` 0.2.1, fixes found in daily use:
  - `record --from claude-code-hook` no longer refreshes the session heartbeat on `SessionEnd`. That hook runs alongside `session end`, so the refresh could re-create the session just removed and leave a ghost that claimed commits for two hours.
  - A session that closed before writing a transcript is skipped quietly, not logged as "record failed".
  - The `Feature:` trailer is now added on a repository's first commit too (the branch is read with `git symbolic-ref`, which works before the first commit).
- `aidus` 0.2.2: the Claude Code reader no longer fails on a transcript line that is valid JSON but not a record (`null`, a number, a list), on a message id that is not text, on an `iterations` field that is not a list, or on a token count that is not a number. Found by fuzzing in the reference reader app. One such line used to stop the whole read.
