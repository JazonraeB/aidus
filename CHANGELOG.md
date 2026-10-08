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
