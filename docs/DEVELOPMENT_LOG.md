# Development Log

## 2026-10-08 — Repository created, AIDUS 1.1 draft

- **Context:** the spec was split out of the private AI Dev Monitor project so that other tools can adopt the format. It is licensed Apache-2.0.
- **Implementation:**
  - draft spec
  - JSON Schemas
  - synthetic conformance fixtures, built from generator scripts
  - a reference reader
  - pytest suite
  - CI on Windows and Linux.
- **Evidence behind the Claude Code rules:** an analysis of real local transcripts (Claude Code 2.1.252–2.1.270) that read only key names and numeric usage fields. No real data is included here. The fixtures recreate the observed patterns synthetically:
  - duplicate lines
  - partial streaming usage
  - history copied across files
  - subagent files
  - synthetic and API-error lines.
- **Tests:** 29 passed locally on Windows. A mutation check showed that breaking the dedup or reasoning rule makes the suite fail.
- **Next:** the `aidus` CLI (`init`, `record`, `validate`, `rebuild`).

## 2026-10-08 — aidus CLI 0.1.0 (FEAT-001)

- **Implementation:** a zero-dependency package in `cli/` with these commands:
  - `init`
  - `record` (Claude Code transcript or hook stdin; idempotent; correction lines; fails open in hook mode)
  - `validate` (schema, cross-field, privacy and layout rules)
  - `rebuild`.
- **Decision:** the CLI has its own validator because it must have no dependencies. Tests require it to agree with `schema/event.schema.json` on every fixture line and on 33 mutations.
- **Spec clarification (§5):** the per-event cache-write part counts non-null buckets. Otherwise Anthropic events, whose unsplit `cache_write_tokens` is null, would make every rollup null.
- **Tests:**
  - 116 passed locally.
  - Mutation check: breaking the dedup tie rule or the unknown-field rule fails 5 tests.
  - Smoke test on a real local Claude Code transcript, in a scratch folder: 91 events, re-run idempotent, `validate` clean, no content or paths in the output. No real data was committed.
