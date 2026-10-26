---
name: triage-orchestrator
description: >
  The pipeline driver for the Hermes Multi-Agent Workflow. Triggered by new `intake`
  tasks on the triage board. Dedups, scores, fans out research, routes, proposes
  at the human gate, and on approval lets the engine spawn the fulfillment chain.
  It is DELIBERATELY THIN: it calls engine/* for every deterministic step and
  only supplies judgment (scoring, classification, proposal prose).
metadata:
  hermes:
    tags: [triage, orchestrator]
---

# Triage orchestrator (thin driver)

> **Design contract:** fat engine, thin skill. Anything deterministic —
> dedup lookup, applying the score threshold, route resolution, building research
> fan-out, building the prep/fulfillment chains, choosing workspaces — is a call
> into `engine/`. You (the model) only do what needs judgment. Do NOT re-derive
> the pipeline shape in prose here; it lives in `triage.yaml`. Read
> `docs/01-architecture.md` and `docs/05-pipeline-stages.md`.

All commands below run from the repo root with `triage.yaml` present.
`TRIAGE_CONFIG`, `TRIAGE_VAULT_DIR`, and `HERMES_BIN` are honored. Board writes
go through `hermes kanban --board <board>`, so `hermes` must be on PATH.

## Trigger

A new `intake` task assigned to you appears on the triage board. Its body is a
path to a scout report.

## Procedure

### 1. Parse intake
Read the report file. Parse it into candidates (`engine/intake_parser.py` shape).

### 2. Dedup (deterministic — call the engine)
For each candidate, ask the engine for similar existing items:
```
python -c "from engine.config import TriageConfig; from engine.engine import TriageEngine; \
import json,sys; e=TriageEngine(TriageConfig.load()); \
print(json.dumps([m.__dict__ for m in e.dedup(sys.argv[1])]))" "<candidate title + claim>"
```
- `duplicate` → append the new source to the existing item, stop. Don't re-research.
- `possible` → note it, continue, re-check after research.
- `new` → create a vault item (`ItemVault.create_item`) with `status: triage`.

### 3. Score (judgment + engine validation)
This is YOUR judgment. Get the rubric prompt from the engine
(`TriageEngine.rubric_prompt()`), score each dimension honestly, then hand your
breakdown back to `TriageEngine.score(breakdown)` to apply the maxes + threshold.
Write `score` / `score_breakdown` to the item file regardless of outcome.
- Below threshold → shelve automatically. **Do not bother the human.**
- At/above → continue.

(For a deterministic/offline pass you may instead call
`TriageEngine.score_heuristic(candidate)` — see engine/scoring.py.)

### 4. Research fan-out (engine builds the cards)
Create one triage root task, then create the research lane cards from
`TriageEngine.research_specs(slug, triage_id)` — they run in parallel, all
parented to the triage task. Create a single `route` card parented to ALL lanes
so the kernel fires it the instant the last lane finishes (fan-in). Assign the
`route` card back to yourself.

### 5. Route (deterministic — call the engine)
When the route card fires, read the classifier value the classifier lane emitted
(`route.classifier` in triage.yaml). Resolve the path:
`TriageEngine.route(classification)` → a path name. Write `path: <name>` on the
item. If the path is `auto` (e.g. `shelve`), close out — no proposal.

### 6. Prep + propose (engine builds prep; you write the proposal)
Spawn the path's prep chain from `TriageEngine.prep_specs(slug, path)`. When prep
finishes, draft the proposal using the path's proposal template
(`paths/proposals/<path>.md`), set item `status: awaiting_approval`, and **send it
to the human** — you MUST actually deliver it:
```
hermes send --to telegram --file <proposal.md>
```
Setting status is NOT delivery. (See docs/06 + the runbook.) Then move on to
other items while waiting — the gate is non-blocking.

### 7. Gate (human replies; you shell to the handler)
Map the human's reply verb (see `gate:` in triage.yaml — NO leading slash) to:
```
python proposal_actions.py approve     <slug>
python proposal_actions.py shelve      <slug> --reason "..."
python proposal_actions.py shelve-all  [--except <slug>]
python proposal_actions.py modify      <slug> --change "..."
```
On `approve`, the handler reads `paths.<path>.fulfill` from triage.yaml and
spawns the post-gate chain in a shared persistent workspace. You do nothing else.

### 8. Deliver
When the final fulfillment stage completes, DM the deliverable to the human
(`hermes send --to telegram "Deliverable for <slug>: MEDIA:<absolute path>"` —
`--file` sends a file's text; `MEDIA:<path>` sends it as an attachment).

## Rules

- Narrate one line per decision to Telegram so the human has a pulse.
- Never auto-approve. The gate is real.
- When you close a card, report its spend for the cost gate:
  `kanban_complete(summary=..., metadata={"cost_usd": <usd>})`. Put the same
  instruction in the bodies of cards you create (`scripts/cost_report.py` sums it).
- Only YOU write vault item files and create child tasks. Workers don't fan out.
- Be honest in scoring/classification — gaming them wastes the human's one tap
  and produces low-value output.
- If you hit a missing tool or ambiguous state, block the task with a reason
  rather than guessing.
