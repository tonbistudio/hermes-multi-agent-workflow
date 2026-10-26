# 02 — The board (how the fleet coordinates)

The pipeline has no message bus and no inter-agent chat. **The Hermes Kanban board
is the bus and the audit log.** Every unit of work is a card; every agent reads
and writes the same board.

## Cards and columns

A card (task) is mostly: a **title**, a **body** (instructions), an **assignee**
(which profile runs it), a **status** (`todo → ready → running → done`), and
optional **parent links**.

`engine/hermes_board.py` is the thin client that writes the board by calling
`hermes kanban --board <board> ...` (create / comment / complete / show). You
rarely edit it.

## Assignee = routing

The whole multi-agent mechanism is a name on a card. A card assigned to `builder`
runs on the builder profile; one assigned to `video_producer` runs on that
profile. The engine maps abstract **roles** (in `triage.yaml`) to real **profiles**
via the `roles:` block, so your config talks in roles and the board gets profiles.

## The dispatcher

The Hermes **gateway** runs a dispatcher loop: it finds `ready` cards, claims one
atomically, spawns the assigned agent in its own workspace, and marks the card
`done` when the agent finishes — then repeats. It covers **all** boards. You don't
write this; you just keep the gateway running (`docs/07-runbook.md`).

## Fan-in (the part that makes it event-driven)

A card with parents starts in `todo` and **auto-promotes to `ready` only when
every parent is `done`.** That single rule gives you parallelism + sequencing with
no polling:

- The research lanes are all parented to the triage card → they run in parallel.
- A `route` card is parented to **all** the lanes → it fires the instant the last
  lane finishes.
- The post-gate fulfillment chain links each stage to the previous → they run in
  order.

`engine.research_specs()` and `engine.fulfillment_specs()` build exactly these
parent relationships. See the parent-linking in `proposal_actions.py::action_approve`.

## Two board gotchas the engine already handles

1. **First post-gate task must be `ready`, not `todo`.** If you parent the first
   fulfillment task to the still-open triage card, it waits forever (the triage
   card never completes). The handler creates the first stage with *no* parent
   (so it's `ready`) and chains the rest. Don't "fix" this by parenting it.

2. **Hermes sets the initial status from the parents:** none (or all already
   `done`) → `ready`, any unfinished → `todo`. Unknown parent ids are rejected.
   That's the whole promotion contract; respect it when you create cards yourself.

## Dedicated board

Each pipeline uses its own board (`board:` in `triage.yaml`), isolated from
`default`, so triage cards don't mix with unrelated work. Create it once with
`hermes kanban boards create <board>`.

You never need the DB path: every board operation goes through
`hermes kanban --board <board>`, and Hermes resolves where the board lives
(shared Hermes root or `HERMES_KANBAN_HOME`, `default` vs. named boards, the
dispatcher-pinned `HERMES_KANBAN_BOARD` / `HERMES_KANBAN_DB` inside workers, and
`%LOCALAPPDATA%\hermes` on native Windows). Set `HERMES_BIN` if `hermes` isn't on
`PATH`.

## Version note

Earlier versions of this template wrote the board's SQLite schema directly.
Current Hermes owns invariants a raw writer skips — parent validation, live-claim
fencing on completion, run records, lifecycle hooks/notifications, idempotency
keys — and migrates its schema between releases. `engine/hermes_board.py` uses the
CLI instead, so it keeps working across schema changes. The dispatcher + cron live
**inside the gateway**; one host gateway serves every profile by default.
