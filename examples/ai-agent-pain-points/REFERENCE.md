# Reference implementation — the pain-point pipeline

> This is a **reference write-up only.** It describes the real, working pipeline
> this template was extracted from, so you can see one complete instantiation of
> the engine before adapting it. It contains no secrets, IDs, or machine
> specifics — just the architecture and the decisions behind it. The live config
> for this instance is the repo-root `triage.yaml`.

## What it is

A single-machine, autonomous pipeline that detects pain points AI-agent users hit,
validates them against a rubric, and routes each one to either **building a fix**
or **producing an explainer video** for a confusing existing solution — with one
human approval gate. It runs as a fleet of Hermes profiles on one PC sharing one
Kanban board.

## Why single-machine, one board

An earlier design used three devices coordinating over a Telegram bot-to-bot bus.
That proved unreliable (bot-to-bot Telegram is staged-rollout and flaky). The
working design collapses everything onto **one host, one Kanban board** as the
inter-agent bus, and keeps Telegram for the **human gate only** (human↔bot is
reliable). No cross-device transport, no message queue between agents.

## The fleet (roles → models)

Eight profiles on one install, each bound to a model in its own config:

| Role | Model | Job |
|---|---|---|
| scout (X) | Grok via OAuth | Hourly scrape of X for pain points |
| scout (web) | GPT via OAuth | Hourly scrape of Reddit / YouTube / web |
| orchestrator | GPT | Pipeline driver; the only Telegram-facing profile |
| researcher | GPT | The three research lanes (verify / context / solutions audit) |
| analyst | GPT | Synthesize problem + ideate solutions (build path) |
| builder | GPT | Build the approved prototype |
| tester | GPT | Test the prototype on real inputs |
| video_producer | GPT | Tutorial research, outline, slides, script (video path) |

The point of mixing models: the X scout uses a provider with first-class X access;
everything else uses one general model. The engine doesn't care — the model is
bound per profile, and `roles:` in `triage.yaml` maps roles to profiles.

## The flow

```
scouts (cron, staggered)  →  intake card on the board
        │
   orchestrator: dedup → score (rubric, threshold 65/100)
        │   (< 65 → auto-shelved, human never bothered)
        ▼
   research fan-out (3 parallel lanes; route fan-ins on all 3)
        │
   ROUTE on existing-solutions audit:
     missing / broken         → BUILD
     confusing / poorly-doc'd → VIDEO
     good                     → SHELVE
        │
   prep → PROPOSAL  → ── HUMAN GATE (Telegram) ── approve / shelve / modify
        │
   BUILD:  prototype → test → report          VIDEO: slides → script → deliver
        │
   delivered to the human (DM)
```

## The rubric

Five dimensions, 0–100, ship at 65: frequency (25), pain intensity (20),
agent-solvable-or-explainable (25), solution gap (15), strategic fit (15). The
"OR-explainable" dimension is what makes one pipeline able to either build or
explain — it's path-agnostic.

## The two-branch trick

The same rubric, gate, and reply verbs serve two very different outcomes (ship
code vs. ship a teaching video). Only the proposal content and the fulfillment
chain differ. In the engine this is just two entries under `paths:`.

## Why one human gate

The build path is the most expensive, error-prone stage, and agent-tested
agent-code shares blind spots. Gating *before* fulfillment bounds cost and keeps a
person in control of what actually ships. Below-threshold items are dropped
automatically, so the human only ever sees things worth a decision.

## Hard scope rails (build path)

Acceptable build targets are bounded on purpose: a Hermes skill/plugin, a CLI
tool, a markdown playbook, a small script, or a cron + skill. Explicitly **not**:
full SaaS apps, stateful auth flows, anything needing un-provisioned keys, or real
UI beyond a dashboard plugin. When a proposal doesn't fit, it's shelved or
re-routed — the rails are never widened to fit. This is the safety boundary.

## Lessons that became engine guarantees

These cost real debugging and are now baked into the template so you don't repeat
them (see `docs/05-pipeline-stages.md`):

- Scouts run via cron, not the dispatcher, so they need the `kanban` toolset
  enabled for their cron platform explicitly — otherwise they write a report but
  can't create the intake card.
- Post-gate stages must share a persistent workspace; scratch dirs are wiped
  between tasks and strand the final delivery step.
- A headless orchestrator must actively send messages — setting a status field
  notifies no one.
- The first post-gate task must be created `ready` (no blocking parent) or it
  waits forever behind the still-open triage card.
- Telegram reserves `/commands`, so gate replies carry no leading slash.

## What this instance proves

It ran end-to-end autonomously: scouts surfaced candidates, the rubric shelved the
weak ones, research and routing ran on the board, a proposal reached the human,
one approval spawned the fulfillment chain, and a finished deliverable was sent
back — all without manual steps between intake and the gate.
