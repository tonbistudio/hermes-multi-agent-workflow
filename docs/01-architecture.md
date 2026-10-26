# 01 — Architecture

## The one design principle: fat engine, thin skill

Multi-agent pipelines fail when too much logic lives in prose (skills) that a
model re-interprets every run. This template pushes everything **deterministic**
into Python and leaves the skill only what needs **judgment**.

```
                 ┌─────────────────────────────────────────────┐
                 │  triage.yaml  (your domain, as data)         │
                 └───────────────────────┬─────────────────────┘
                                         │ loaded + validated by
                                         ▼
   ┌──────────────────────────  engine/  (generic, testable) ───────────────────┐
   │ config.py    TriageConfig — typed view + validation                         │
   │ engine.py    TriageEngine — dedup · score · route · build task chains       │
   │ scoring.py   apply rubric (LLM-breakdown mode + deterministic mode)         │
   │ routing.py   classification → path                                          │
   │ dedup.py     similarity (token-cosine; embedding-ready)                     │
   │ item_vault   one md file per item   hermes_board  writes the board          │
   └───────────────────────────────┬────────────────────────────────────────────┘
                                    │ called by
            ┌───────────────────────┴───────────────────────┐
            ▼                                                 ▼
  triage-orchestrator SKILL.md                      proposal_actions.py
  (judgment only: score dims,                       (gate handler: reads the
   classify, write proposal prose;                   post-gate chain from config,
   calls engine for everything else)                 spawns it on approve)
```

## Why this split

- **Testable.** `engine/` runs without a model or a live board. `tests/` exercise
  scoring, routing, dedup, and chain construction against a synthetic config. A
  prose-only pipeline can't be unit-tested.
- **Adaptable.** Repointing at a new domain is editing data (`triage.yaml`), not
  rewriting program logic.
- **Honest boundaries.** The model does the fuzzy parts (is this painful? is the
  existing solution confusing? what's a good proposal?). Code does the crisp parts
  (sum the score, compare to threshold, look up the route, build the cards).

## What the engine does NOT do

The engine returns **task specs** (plain dataclasses: title/body/role/parents/
workspace) rather than touching the board itself, except in `proposal_actions.py`
and (at runtime) the orchestrator, which turn specs into real cards via
`HermesBoard` (which calls `hermes kanban`). This keeps the planning logic pure and unit-testable; side effects
live at the edges.

## Data flow of one item

1. A **scout** writes a report and creates an `intake` card (it only detects).
2. The **orchestrator** parses it, asks the engine for dedup matches, scores it
   (judgment, validated by the engine), and — if it clears the bar — creates a
   triage card plus the **research fan-out** (`engine.research_specs`).
3. Research lanes run in parallel; a **route** card fan-ins on all of them.
4. The orchestrator reads the classifier's output and calls `engine.route()` to
   pick a path, then spawns that path's **prep** chain (`engine.prep_specs`).
5. It drafts a proposal and **sends it to the human** (`hermes send`).
6. The human replies; the orchestrator shells to `proposal_actions.py`, which
   reads `paths.<path>.fulfill` and spawns the **fulfillment** chain in a shared
   persistent workspace (`engine.fulfillment_specs`).
7. The final stage **delivers** to the human.

## Where to extend (mechanism, not topic)

- New scoring backend → add a mode in `scoring.py`, expose via `engine.py`.
- Embedding dedup → populate item `embedding`, swap the cosine source in
  `dedup.py` (contract unchanged).
- New step type → add a method on `TriageEngine` returning `TaskSpec`s.

Adding your *subject matter* is never an engine change — it's `triage.yaml`.
