# .ai-usage

This repository's own AI usage, recorded in the AIDUS 1.1 format ([spec](../spec/AIDUS.md)). It dogfoods the spec.

- `project.json` gives the project identity. `project_id` never changes.
- `usage.json` is a derived summary in the 1.0 format. Rebuild it; don't edit it by hand.
- `events/YYYY-MM/<writer_id>.jsonl` holds append-only usage events, written by tooling and never typed by hand or by an AI model.
- `sessions/` holds optional session rollups.
- `imports/` holds raw provider exports and is gitignored.

These files contain metadata only: no prompts, code, conversations or credentials.
