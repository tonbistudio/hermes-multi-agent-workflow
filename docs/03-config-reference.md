# 03 — Config reference (`triage.yaml`)

Every key in `triage.yaml`. The typed view is `engine/config.py`; the validator is
`TriageConfig.validate()` (run via `python -m cli.triage validate`).

## Top level

| Key | Type | Meaning |
|---|---|---|
| `name` | str | Pipeline slug, for logs. |
| `board` | str | Kanban board slug, passed as `hermes kanban --board <board>`. Create it with `hermes kanban boards create <board>`; Hermes resolves where it lives on disk. |
| `workspace_root` | path | Base for the item vault and per-item persistent workspaces. |
| `cost_gate_usd` | number | Soft per-item LLM budget. Over before gate → pause+notify; over after approval → notify+continue. |

## `sources:` — the scouts

List of detectors. Each runs a scout skill on a profile, on a cron.

| Key | Meaning |
|---|---|
| `id` | Short id (used in report filenames + the intake task title). |
| `profile` | Hermes profile the scout runs under (binds the model). |
| `skill` | Scout skill name installed on that profile (copy of the scout template). |
| `schedule` | Cron expression. Registered under the scout's own profile (`hermes -p <profile> cron create`); the host gateway runs every profile's crons (see runbook). |
| `query` | The domain prompt — what to look for. Pasted into the scout skill. |

## `item_schema.fields:`

The structured fields a scout emits per candidate. `title`, `claim`, `sources` are
required by the engine; the rest feed your rubric/router. Keep this in sync with
the scout report format and `engine/intake_parser.py`.

## `dedup:`

| Key | Meaning |
|---|---|
| `method` | `token-cosine` (default, no deps) or `embedding` (wire it up yourself). |
| `duplicate_threshold` | ≥ → treat as a duplicate of an existing item. |
| `possible_threshold` | ≥ → flag as a possible duplicate, continue. |

Token-cosine runs colder than embedding cosine; defaults (0.62/0.40) suit it. For
embeddings, raise toward ~0.85/0.65.

## `rubric:`

| Key | Meaning |
|---|---|
| `threshold` | Advance if total score ≥ this. Must be ≤ sum of dimension maxes (validated). |
| `dimensions[]` | `{key, max, hint}`. `key` is the score field; `max` its ceiling; `hint` guides the orchestrator. |

LLM mode (recommended) adapts to ANY dimensions. The deterministic heuristic in
`scoring.py` only understands the reference keys — see docs/04 if you change them.

## `research_lanes:`

| Key | Meaning |
|---|---|
| `role` | Role the lanes run under (mapped via `roles:`). |
| `lanes[]` | Parallel lane task titles. All must finish before route fires. |
| `classifier_lane` | Which lane emits the value the router reads. Must be one of `lanes`. |

## `route:`

| Key | Meaning |
|---|---|
| `classifier` | Dotted reference to the classifier output, e.g. `<lane>.<field>`. Documentation for the orchestrator; the engine matches on the value string. |
| `map` | `{classification_value: path_name}`. Every target must be a key under `paths:` (validated). |

## `paths:`

A map of path name → definition. A path is one outcome of routing.

| Key | Meaning |
|---|---|
| `prep[]` | Stages BEFORE the gate. Each `{stage, role}`. Chained sequentially. |
| `propose.role` | Who drafts + sends the proposal (usually `orchestrator`). |
| `propose.template` | Markdown proposal template under `paths/proposals/`. |
| `fulfill[]` | Stages AFTER approval. Each `{stage, role}`. Run in a shared persistent workspace. |
| `workspace_subdir` | Bucket under `workspace_root` for this path's per-item dirs (e.g. `builds`). Defaults to the path name. |
| `scope_rails` | Markdown file (under `paths/rails/`) inlined into each worker's task body — hard limits. |
| `deliverable_spec` | Markdown file (under `paths/specs/`) inlined into workers — output format. |
| `auto` | `true` → terminal path, no work (e.g. `shelve`). |

`stage` is the task-title prefix and the conventional name workers key off. `role`
is mapped to a profile.

## `roles:`

Map abstract role → real Hermes profile. Every role used anywhere (research,
prep, fulfill, propose) must appear here (validated). This indirection lets you
rename/merge profiles without touching paths.

## `gate:`

| Key | Meaning |
|---|---|
| `channel` | Where proposals go (e.g. `telegram`). |
| `approve` / `shelve` / `modify` | Reply verbs the orchestrator maps to `proposal_actions.py` subcommands. **No leading slash** on Telegram. |

## Validation guarantees

`validate()` fails (with actionable messages) if: a route target isn't a defined
path; a role is used but undefined; the threshold exceeds the max possible total;
or the classifier lane isn't in `lanes`. It *warns* (non-fatal) if a referenced
template file is missing.
