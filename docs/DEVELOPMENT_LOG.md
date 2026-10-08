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
