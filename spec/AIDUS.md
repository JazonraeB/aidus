# AIDUS — AI Development Usage Specification

- **Version:** 1.1.0-draft
- **Status:** Draft
- **License:** Apache-2.0
- **Editor:** Rae ([@JazonraeB](https://github.com/JazonraeB))

AIDUS defines the `.ai-usage/` folder that a software repository uses to record the AI usage behind its development. Usage means tokens, models, sessions and cost, never content.

AIDUS is **local-first** and **provider-neutral**, and it is safe to commit. A project never needs any AIDUS tool installed to build or run.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are to be read as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174).

---

## 1. Design goals

1. **Real numbers only.** Token counts come from tools: agent hooks, agent logs, provider APIs. They never come from a language model describing its own usage. Unknown values are `null`, never guessed.
2. **Merge-safe.** Many developers and agents can commit usage to the same repository without merge conflicts or corrupted history.
3. **Priced once.** Token buckets are disjoint, so summing and pricing them never counts a token twice.
4. **Honest cost.** Every cost says where it came from. Calculated or estimated cost is never presented as billing.
5. **Metadata, not content.** No prompts, code, conversations, file contents or credentials.
6. **Backward compatible.** A reader that only knows AIDUS 1.0 (one `usage.json` file) still finds valid data.

## 2. Directory layout

```text
.ai-usage/
├── project.json                    # REQUIRED  identity and settings          (commit)
├── usage.json                      # REQUIRED  derived summary, v1.0 format    (commit)
├── events/                         # v1.1      append-only event shards        (commit)
│   └── YYYY-MM/
│       └── <writer_id>.jsonl
├── sessions/                       # OPTIONAL  session rollups                 (review before commit)
│   └── YYYY-MM-DD.json
├── imports/                        # OPTIONAL  raw provider exports            (MUST be gitignored)
├── .gitattributes                  # v1.1      merge rules (§8)
└── README.md                       # REQUIRED  human explanation
```

- `YYYY-MM` is the **UTC** month of each event's `timestamp`.
- A v1.0 repository contains only `project.json`, `usage.json`, `sessions/`, `imports/` and `README.md`. It is a valid AIDUS 1.1 repository with no events.

## 3. `project.json`

`project.json` identifies the project. The schema is [`schema/project.schema.json`](../schema/project.schema.json).

| Field | Req. | Rules |
| --- | --- | --- |
| `schema_version` | MUST | `"1.0"` or `"1.1"` |
| `project_id` | MUST | Stable for the project's lifetime. Lowercase letters, digits and `-`, 8–128 chars. MUST NOT be derived from a secret |
| `project_name` | MUST | Human-readable name |
| `description` | SHOULD | Short description |
| `repository` | SHOULD | `{provider, url, branch}`. `url` MUST NOT contain credentials (no `user:pass@`) |
| `team` | MAY | Team name |
| `environment` | MAY | e.g. `development` |
| `created_at` | SHOULD | RFC 3339 timestamp |
| `monitoring` | SHOULD | `{enabled: bool, format: "json"}` |

## 4. Event records (`events/**/*.jsonl`)

Each line is one JSON object describing **one billable model response**, encoded as UTF-8 and terminated by `\n`. The schema is [`schema/event.schema.json`](../schema/event.schema.json).

### 4.1 Identity and provenance

| Field | Req. | Rules |
| --- | --- | --- |
| `schema_version` | MUST | `"1.1"` |
| `usage_id` | MUST | Stable and unique per billable response (§6) |
| `project_id` | MUST | Equals `project.json` `project_id` |
| `timestamp` | MUST | RFC 3339 with an offset. The time of the model response. MUST NOT be more than 5 minutes in the future when written |
| `recorded_at` | MUST | RFC 3339. The time the line was written |
| `writer_id` | MUST | The shard's writer (§7). MUST equal the file name stem |
| `source` | MUST | One of `coding-agent`, `provider-api`, `provider-billing`, `local-log`, `manual-import`, `ide-integration`, `cli-integration` |
| `provider` | MUST | Lowercase, e.g. `anthropic`, `openai` |
| `model` | MUST | The provider's model id, as reported |
| `agent` / `agent_version` | SHOULD | The tool that made the call, e.g. `claude-code` / `2.1.270`. This is different from `provider` |
| `session_id` | SHOULD | The agent's session id |
| `subagent` | MAY | `true` if a subagent made the call |

### 4.2 Token buckets (disjoint)

Every bucket is a non-negative integer or `null` (unknown). **The buckets do not overlap.** Each input token is counted in exactly one input bucket.

| Bucket | Meaning |
| --- | --- |
| `input_tokens` | Input tokens that were neither read from nor written to a cache |
| `cache_read_tokens` | Input tokens served from a cache |
| `cache_write_5m_tokens` | Input tokens written to a cache with a ~5-minute lifetime |
| `cache_write_1h_tokens` | Input tokens written to a cache with a ~1-hour lifetime |
| `cache_write_tokens` | Cache writes whose lifetime is unknown or not split by the provider. MUST be `null` when either split bucket is non-null |
| `output_tokens` | **All** output tokens, including reasoning/thinking tokens |
| `reasoning_tokens` | **Informational.** The part of `output_tokens` spent on reasoning. MUST be ≤ `output_tokens`. MUST NOT be priced or added to totals |

`total_tokens` is OPTIONAL. If present, it MUST equal the sum of the non-null buckets **excluding** `reasoning_tokens`.

Writers MUST convert each provider's native shape into these buckets. Appendix A gives the mappings for common providers.

### 4.3 Price modifiers

Some fields change the price without changing the token counts. Writers SHOULD record them when the source reports them, because readers need them to price correctly.

| Field | Type | Example |
| --- | --- | --- |
| `speed` | string \| null | `"standard"`, `"fast"` |
| `inference_geo` | string \| null | `"us"`, `"not_available"` |
| `service_tier` | string \| null | `"standard"`, `"priority"`, `"batch"` |
| `batch` | bool \| null | `true` for batch API requests |
| `server_tool_requests` | object \| null | `{"web_search": 2, "web_fetch": 0}`. Counts of per-request-priced server tools |

A reader that prices events MUST treat an event whose modifier value it has no price rule for as **unknown cost**. It MUST NOT silently apply the base price.

### 4.4 Context and outcome links

| Field | Rules |
| --- | --- |
| `branch` | Git branch at the time of the call |
| `commit` | Commit SHA, if known when written |
| `feature_id` | `FEAT-` followed by digits, from the project's feature registry |
| `developer` | `null`, or a **keyed hash**: `hmac-sha256:` followed by 64 hex chars. Names and emails MUST NOT be written by default (§9) |
| `notes` | ≤ 200 chars. MUST NOT contain prompt, code or conversation text |

### 4.5 Cost (optional)

Writers SHOULD omit cost and let readers price events from a versioned catalog. If a writer does include cost:

```json
"cost": {
  "amount_micros": 1234,
  "currency": "USD",
  "cost_status": "calculated",
  "pricing_source": "provider-pricing",
  "pricing_version": "2026-10"
}
```

- `amount_micros` is an integer in millionths of the currency unit.
- `cost_status` is one of the following. When sources overlap, the highest wins.
  1. `authoritative`: reported by a provider billing or usage API.
  2. `calculated`: tokens from a trusted tool record × a published price.
  3. `estimated`: tokens from a partial or self-reported source × a price.
  4. `unknown`: not enough information. `amount_micros` MUST be `null`.
- **Compatibility:** AIDUS 1.0 has no `calculated` status. A reader or writer emitting the 1.0 format MUST map `calculated` → `estimated`.
- Any status other than `authoritative` MUST NOT be presented as billed cost.

### 4.6 Extensions

Fields beginning with `x-` are extensions. They MUST follow §9. Readers MAY ignore them. All other fields not defined by this version are invalid for writers of this version.

## 5. `usage.json` (derived summary)

`usage.json` keeps the **AIDUS 1.0 format**, so 1.0 readers keep working. In v1.1 it is **derived**: it is rebuilt from `events/` and never edited by hand. The schema is [`schema/usage.schema.json`](../schema/usage.schema.json).

- The file contains one rollup record per `(UTC month, provider, model)`:
  - `usage_id`: `rollup:<YYYY-MM>:<provider>:<model>`.
  - `timestamp`: the first instant of the month (UTC).
  - `source`: `"cli-integration"`.
- Token mapping into the 1.0 fields:

  | 1.0 field | Value |
  | --- | --- |
  | `input_tokens` | `input + cache_write_5m + cache_write_1h + cache_write` |
  | `cached_input_tokens` | `cache_read` |
  | `output_tokens` | `output` |
  | `reasoning_tokens` | `reasoning` |
  | `total_tokens` | `input_tokens + cached_input_tokens + output_tokens` |

  For each event, the cache-write part is the sum of its non-null cache-write buckets, or `null` if all three are `null`. A rollup field is `null` if any contributing event's value for it is `null`, because unknown stays unknown.
- `estimated_cost` is `null` and `cost_status` is `"unknown"`, unless the rebuilding tool prices the events. In that case it MUST use `"estimated"` (the 1.0 mapping in §4.5).
- `notes`: `"AIDUS 1.1 rollup of <n> events"`.
- **Merge conflicts:** because the file is derived, a conflict is resolved by rebuilding it (`aidus rebuild`), never by hand-merging. Tools SHOULD NOT rebuild it on every event. Rebuilding on demand or before a release keeps conflicts rare.

## 6. `usage_id` and deduplication

- A writer that has the provider's response id MUST use `<agent>:<response id>`, e.g. `claude-code:msg_01AbC…`.
- Otherwise it MUST use `h:` + the lowercase hex SHA-256 of the UTF-8 JSON array `[source, session_id, timestamp, model, input_tokens, cache_read_tokens, cache_write_5m_tokens, cache_write_1h_tokens, cache_write_tokens, output_tokens]`. The array is serialized with no whitespace, and `null` is kept as `null`.
- **Readers MUST deduplicate by `usage_id` across all shards and months.**
  - Lines with the same `usage_id` and identical buckets and modifiers are one event.
  - If they differ, the line with the latest `recorded_at` wins.
  - If `recorded_at` is equal, the reader MUST quarantine the conflict and report it.

## 7. Writers and shards

1. `writer_id` is a random id: lowercase letters and digits, 8–32 chars. It is created once per **developer × machine × tool**, stored **outside** the repository, and reused.
2. A writer appends only to `events/<YYYY-MM>/<writer_id>.jsonl`. It MUST NOT modify or delete existing lines (corrections are new lines, §6), and MUST NOT write to another writer's shard.
3. Each line is written with **one** append call that contains the complete line, including `\n`. Lines MUST be ≤ 64 KiB.
4. Readers MUST ignore a final line that has no trailing `\n` (a crash mid-write). They MUST NOT quarantine it unless it is still incomplete when a later line has been appended after it.
5. Writers MUST NOT invent values. A field the tool doesn't report is `null` or omitted.

## 8. Git integration

`.ai-usage/.gitattributes` SHOULD contain:

```gitattributes
events/** text eol=lf merge=union
usage.json text eol=lf linguist-generated=true
project.json text eol=lf
```

- `merge=union` makes concurrent appends merge without conflicts, because lines are independent.
- The repository `.gitignore` MUST exclude `.ai-usage/imports/`.

**Commit trailers (RECOMMENDED).** Tools that link sessions to commits SHOULD add trailers in a `prepare-commit-msg` hook, not `post-commit`. A `post-commit` hook would need to amend the commit. Use `git interpret-trailers --if-exists addIfDifferent`:

```text
AI-Session: <session_id>
Feature: FEAT-012
```

Hooks MUST fail open. A failure prints a warning and never blocks the commit.

## 9. Privacy and security

AIDUS files are meant to be committed, possibly to public repositories. Writers and validators MUST enforce the following.

- **Never written:** prompts, completions, conversation text, source code, file contents, file paths outside the repository, environment variables, API keys, tokens, passwords, cookies, private keys.
- **Credential-shaped strings are invalid anywhere in a file.** Validators MUST reject any string value matching common credential patterns, including at least:
  - `sk-` followed by 20+ chars
  - `AKIA` followed by 16 uppercase letters or digits
  - `gh[pousr]_` followed by 20+ chars
  - `-----BEGIN … PRIVATE KEY-----`
  - JWT-shaped `eyJ<...>.eyJ<...>.<...>`
- **Developer identity** is either omitted or written as `hmac-sha256:<hex>`, keyed with a secret that is stored outside the repository. A plain hash of an email is guessable and MUST NOT be used.
- `sessions/` and `imports/` may hold more detail. `imports/` MUST be gitignored, and `sessions/` SHOULD be reviewed before committing.

## 10. Versioning and compatibility

- The spec uses semantic versioning. Each line and file carries its own `schema_version` (`MAJOR.MINOR`).
- Readers MUST reject a **major** version they don't know, and MUST ignore unknown fields in a **higher minor** version of a major they know.
- Readers MUST accept AIDUS 1.0 `usage.json` files.

## 11. Conformance

- **Writer:** produces files that validate against `schema/` and meet §4.2 (disjoint buckets, `reasoning_tokens ≤ output_tokens`, `total_tokens` rule), §6, §7 and §9.
- **Reader:** meets §5, §6, §7.4 and §10. It quarantines invalid lines **with a reason** and never silently drops them.
- The conformance suite is in [`fixtures/`](../fixtures/). A tool MAY claim "AIDUS 1.1 conformant" only if it produces the expected outcome for every fixture.

---

## Appendix A — Provider mappings (normative)

### A.1 Anthropic Messages API (`usage`)

Anthropic's fields are already disjoint.

| AIDUS | Anthropic |
| --- | --- |
| `input_tokens` | `input_tokens`. This is the uncached remainder only |
| `cache_read_tokens` | `cache_read_input_tokens` |
| `cache_write_5m_tokens` | `cache_creation.ephemeral_5m_input_tokens` |
| `cache_write_1h_tokens` | `cache_creation.ephemeral_1h_input_tokens` |
| `cache_write_tokens` | `cache_creation_input_tokens`, **only** if the `cache_creation` split is absent |
| `output_tokens` | `output_tokens`. Includes thinking |
| `reasoning_tokens` | `output_tokens_details.thinking_tokens`, if present |
| `speed`, `inference_geo`, `service_tier` | Same-named fields |
| `server_tool_requests` | `server_tool_use.web_search_requests` → `web_search`, `web_fetch_requests` → `web_fetch` |

### A.2 OpenAI (Chat Completions / Responses)

OpenAI's input count **includes** cached tokens, so they must be subtracted.

| AIDUS | OpenAI |
| --- | --- |
| `input_tokens` | `prompt_tokens` (or `input_tokens`) − `cached_tokens` − cache-write tokens, if reported |
| `cache_read_tokens` | `prompt_tokens_details.cached_tokens` (or `input_tokens_details.cached_tokens`) |
| `cache_write_tokens` | Cache-write tokens, if reported. Otherwise `null` |
| `output_tokens` | `completion_tokens` (or `output_tokens`). Includes reasoning |
| `reasoning_tokens` | `completion_tokens_details.reasoning_tokens` (or `output_tokens_details.reasoning_tokens`) |

## Appendix B — Reading Claude Code transcripts (informative)

Claude Code stores session transcripts as JSONL under `~/.claude/projects/<encoded-path>/`. Analysis of versions 2.1.252–2.1.270 found the following, and a reader SHOULD follow these rules:

1. **Recurse into subagent files** (`<session>/subagents/*.jsonl`). Subagent calls are real usage.
2. **Use only** `type: "assistant"` lines that have `message.usage`. **Skip** `message.model == "<synthetic>"` and lines with `isApiErrorMessage: true`.
3. **One response is logged on several lines** (about 72% of responses in the sample). Earlier lines may carry partial streaming counts. Deduplicate by `message.id` **across all files**, because resumed sessions copy earlier history into new files. Keep the line with the highest `output_tokens`. On a tie, keep the line with the earliest `timestamp`, then the first by file path in sorted order. Identical lines copied into another file are the same event.
4. **Map the project from the line's `cwd` field**, not from the encoded folder name, which is lossy. `sessionId`, `gitBranch`, `version`, `isSidechain` and `agentId` give the session, branch, agent version and subagent flag.
5. If `usage.iterations` has more than one entry, quarantine the line until the meaning is confirmed.
6. Never copy `message.content`, tool inputs or outputs, prompts, titles or summaries.
7. Transcripts are deleted after the `cleanupPeriodDays` setting (default 30). Collect them more often than that.

The fixtures in [`fixtures/claude_code/`](../fixtures/claude_code/) encode these rules.
