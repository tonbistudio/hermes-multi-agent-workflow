# 07 — Runbook (stand it up + go live)

This template validates and unit-tests out of the box, but running it for real
needs a Hermes install with profiles, auth, and scouts. This is the setup
sequence. `python -m cli.triage scaffold` prints these commands tailored to your
`triage.yaml`.

> Commands assume the `hermes` CLI and your per-profile wrappers are on PATH. On
> WSL, run them in your Linux shell (Hermes runs in WSL, even if the repo lives on
> a Windows drive).

## 1. Prerequisites

- Hermes installed and working (`hermes --version`).
- `pip install -r requirements.txt` in this repo (PyYAML).
- `python -m cli.triage validate` is clean.

## 2. Create the board

```bash
hermes kanban boards create <board>     # the `board:` from triage.yaml
```

## 3. Create the profiles

One profile per distinct value in `roles:` plus each `sources[].profile`. Clone
from a base profile, then set the model in each profile's `config.yaml`.

```bash
hermes profile create <name> --clone-from <base>   # copies config/.env/SOUL.md/skills
hermes -p <name> model                             # pick provider + model for it
```

(`--clone` copies from the active profile; `--clone-all` copies all state.
Messaging bot tokens are deliberately left behind unless you pass
`--clone-channels` — only the orchestrator should hold the Telegram bot.)

Multi-model is fine: e.g. one scout on one provider, the rest on another. The
profile is where the model is bound; the engine doesn't care.

## 4. Scout profiles need the `kanban` toolset

Scouts run via cron (not the dispatcher), so kanban tools aren't auto-enabled.
Enable the toolset for each `sources[].profile` on the platform it runs on —
`cron` for scheduled sweeps, `cli` too if you smoke-test by hand:

```bash
hermes -p <scout> tools enable --platform cron kanban
hermes -p <scout> tools enable --platform cli kanban    # for manual smoke tests
```

(The old `toolsets: [hermes-cli, kanban]` line in config.yaml is now only a
legacy fallback and is ignored once a profile has saved per-platform toolsets.)

Also ensure scouts have a web-search backend (a Tavily/Serper/Brave key in their
`.env`, or the built-in `web` toolset) so they can actually search.

## 5. Install the skills

- Copy `skills/templates/triage-orchestrator/` to the orchestrator profile's
  skills dir.
- Copy `skills/templates/triage-scout/` once per source to that source's profile,
  renamed to `sources[].skill`, with the source's `query` filled in.

## 6. Auth

Log in each profile's provider once (interactive, human-run). OAuth token stores
are **per profile** — logging in one profile doesn't cover another.

## 7. Configure the gate channel

For Telegram: set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS=<your id>`, and a
home channel/thread in the orchestrator profile's `.env`. Message the bot once
(bots can't DM a user who hasn't started them). Verify delivery:

```bash
hermes -p orchestrator send --to telegram "triage engine: delivery check"
```

`hermes send --file <path>` sends the file's text. To deliver a file as an
attachment, put `MEDIA:<absolute path>` in the message text instead.

## 8. Register the scout crons — under each scout's own profile

Each scout's job lives in its own profile's cron store. Create it paused so
nothing fires before you're ready. `--continuity` hands each run the previous
run's output so the scout can skip what it already reported.

```bash
hermes -p <scout-profile> cron create '<schedule>' \
  "Run one sweep now, following the <scout-skill> skill exactly." \
  --skill <scout-skill> --name scout-<id> --continuity --paused
hermes -p <scout-profile> cron list --all     # job present, paused
```

## 9. Start the runtime

The dispatcher + cron live inside the gateway, and **one host gateway (the
default profile) serves every profile** — it multiplexes their cron stores and
dispatches every board. Don't start per-profile gateways; current Hermes refuses
them unless forced.

```bash
hermes gateway run                       # foreground (keep in tmux/screen)
# or install it as a service:  hermes gateway install && hermes gateway start
hermes gateway status                    # → running (from another shell)
hermes -p <scout-profile> cron status    # names the scheduler host + heartbeat
```

On WSL without systemd, use foreground `run`.

## 10. Smoke-test one cycle (before autonomous cron)

Trigger a scout by hand so you don't wait for the cron tick:

```bash
hermes -p <scout-profile> chat --skills <scout-skill> -q "Run one sweep now, following the skill exactly."
hermes kanban --board <board> list     # watch cards appear + promote
```

Expected flow: `intake → (dedup/score) → research lanes (parallel) → route →
prep → propose` → **proposal DM** → you reply `approve <slug>` → `fulfill chain`
→ deliverable DM. Confirm the first post-gate card is `ready` (not `todo`).

## 11. Go live

```bash
hermes -p <scout-profile> cron resume <job-id>    # start with one scout
# watch a real cycle, then resume the others
```

The gateway must stay running for cron to fire and the board to dispatch.

## Day-to-day

- **Watch:** `hermes kanban --board <board> list`. Progress also DMs to you.
- **Decide:** reply (no slash) `approve <slug>` / `shelve <slug>: reason` /
  `modify <slug>: change`; `reject the rest` (or `python proposal_actions.py
  shelve-all`) clears the queue.
- **Cost:** `python scripts/cost_report.py <slug> --gate <usd>`.
- **Stop:** Ctrl-C the gateway.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Scout runs, no card appears | `kanban` toolset not enabled for the scout's platform (step 4). |
| Crons never fire | Host gateway not running, or job still paused. `hermes -p <scout> cron status` (step 9). |
| `gateway run` refused for a profile | Expected: one host gateway serves all profiles. Run it from the default profile. |
| `kanban: board '<x>' does not exist` | Create it: `hermes kanban boards create <x>` (step 2). |
| `proposal_actions.py` → `error_kind: backend` | The `hermes kanban` call failed; the message is Hermes's own. Set `HERMES_BIN` if `hermes` isn't on PATH. |
| Card stuck in `todo` | It has an unfinished parent. Don't parent the first post-gate task to the triage card. |
| Proposal status set but no DM | Orchestrator didn't `hermes send`; status ≠ delivery (docs/05). |
| `/approve` "unknown command" | Telegram reserves `/`; reply without the slash. |
| Final delivery can't find artifacts | A stage used scratch, not the persistent `dir` workspace. |
| `gateway start` fails on WSL | No systemd service — use `hermes gateway run` (foreground). |
