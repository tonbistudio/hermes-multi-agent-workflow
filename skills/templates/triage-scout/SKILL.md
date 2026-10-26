---
name: triage-scout
description: >
  Scout skill template for the Hermes Multi-Agent Workflow. Runs on a cron under a
  source profile, searches for candidate items in your domain, writes a report to
  the intake vault, and creates one `intake` Kanban task on the triage board.
  COPY this per source (e.g. triage-scout-x, triage-scout-web) and fill the TODOs.
metadata:
  hermes:
    tags: [triage, scout, intake]
---

# Triage scout

> **For the adapting agent:** this is a TEMPLATE. Make one copy per `sources[]`
> entry in `triage.yaml` (e.g. `triage-scout-x`, `triage-scout-web`), give each
> the matching `name`, and paste that source's `query` into "What to look for".
> Install each copy on the profile named in that source. See
> `docs/04-adapting-to-your-domain.md` and `docs/05-pipeline-stages.md`.
>
> **Want a worked example?** `examples/ai-agent-pain-points/reference-skills/pain-point-scout-x/SKILL.md`
> is a real, filled-in copy of this template from the live system.

## When to use

Fired hourly by cron (the `schedule` in `triage.yaml`). Also runnable by hand for
a smoke test:

```
<profile> chat --skills <this-skill-name> -q "Run one sweep now, following this skill exactly."
```

## Prerequisite (read once)

This skill runs via **cron, not the dispatcher**, so `HERMES_KANBAN_TASK` is
unset and kanban tools are NOT auto-enabled. Enable the `kanban` toolset for the
scout profile's cron platform or `kanban_create` won't be available:
`hermes -p <profile> tools enable --platform cron kanban` (the scaffold plan prints
this; verify it).

## What to look for

<!-- TODO: paste the `query` from this source's entry in triage.yaml. -->
<your domain search instructions here>

## Procedure

1. Search your assigned surface for candidate items matching the query above.
2. For each distinct candidate, capture: a one-line **claim**, **source URLs**
   (every claim traceable to a primary source), a verbatim quote where possible,
   and one line on **why it may matter**.
3. Drop low-signal noise — vague hype, single-person rants with no corroboration.
4. Write the full report to:
   `${HERMES_PROFILE_DIR}/vault/intake/<UTC-timestamp>-<source-id>.md`
   in the format below.
5. Create ONE intake Kanban task on the triage board:

   ```
   kanban_create(
     board: "<board from triage.yaml>",
     title: "intake: <source-id> <UTC-date>",
     assignee: "orchestrator",
     body: "<path to the report file you just wrote>",
   )   # no parents → lands `ready`; the orchestrator picks it up
   ```

## Report format (contract with engine/intake_parser.py)

```
source: <source-id>
captured_at: <UTC timestamp>

## Candidate: <title>
Claim: <one-line claim>
Sources:
  - url: https://...
    quote: "verbatim"
Why it may matter: <one line>

## Candidate: <title>
...
```

If you change these fields, update `item_schema` in `triage.yaml` AND
`engine/intake_parser.py` to match.

## Don't

- Don't dedup, score, or route — that's the orchestrator's job. You only detect.
- Don't post anywhere except the intake vault + the one intake task.
- Don't fabricate sources. No URL → don't include the claim.
