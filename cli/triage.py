#!/usr/bin/env python3
"""Triage engine CLI:  python -m cli.triage <command>

Commands:
  validate   Load triage.yaml and check it for consistency. FULLY IMPLEMENTED —
             run this after every edit.
  scaffold   Print the Hermes commands to create the profiles, install the skill
             templates, create the board, and register the scout crons implied by
             triage.yaml. PRINTS the plan; it does not execute (so you can review
             before running, and because the exact `hermes` invocations depend on
             your install). Marked TODO where you must confirm syntax.
  init       Stub. Intended to copy triage.yaml + path templates into a fresh
             project. For now, copy this repo and edit triage.yaml directly.
  install    Stub. Intended to actually run the scaffold plan. Left manual on
             purpose — review the printed commands and run them yourself.

This is a TEMPLATE. `scaffold`/`init`/`install` are intentionally conservative —
they tell you what to do rather than mutate your Hermes install behind your back.
Wire them up to your environment as you adopt the template.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine.config import ConfigError, TriageConfig


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        cfg = TriageConfig.load(args.config)
    except ConfigError as exc:
        print(f"[FAIL] {exc}")
        return 1
    print(f"[OK] triage.yaml valid - pipeline {cfg.name!r}")
    print(f"  board: {cfg.board}   workspace_root: {cfg.workspace_root}   cost_gate: ${cfg.cost_gate_usd}")
    print(f"  sources: {[s.id for s in cfg.sources]}")
    print(f"  rubric: {len(cfg.rubric.dimensions)} dims, threshold {cfg.rubric.threshold}/{cfg.rubric.max_total}")
    print(f"  research lanes: {cfg.research.lanes} (classifier: {cfg.research.classifier_lane})")
    print(f"  routes: {cfg.route.map}")
    print(f"  paths: {sorted(cfg.paths)}")
    print(f"  roles -> profiles: {cfg.roles}")
    # Warn about referenced-but-missing template files (non-fatal).
    missing = []
    for p in cfg.paths.values():
        for rel in (p.scope_rails, p.deliverable_spec, p.proposal_template):
            if rel and not Path(rel).exists():
                missing.append(rel)
    if missing:
        print("  ! referenced template files not found (relative to CWD; fill them in or run from repo root):")
        for m in sorted(set(missing)):
            print(f"      - {m}")
    return 0


def cmd_scaffold(args: argparse.Namespace) -> int:
    cfg = TriageConfig.load(args.config)
    profiles = sorted(set(cfg.roles.values()) | {s.profile for s in cfg.sources})
    print(f"# Scaffold plan for pipeline {cfg.name!r}. Review, then run the commands you trust.")
    print(f"# Written against the current Hermes CLI (`hermes kanban`, `hermes -p <profile> ...`).\n")
    print(f"# 1. Create the dedicated board")
    print(f"hermes kanban boards create {cfg.board}\n")
    print(f"# 2. Create the profiles (one per role + one per source profile).")
    print(f"#    --clone-from copies config.yaml/.env/SOUL.md/skills from a base profile;")
    print(f"#    then set each profile's model:  hermes -p <profile> model")
    for prof in profiles:
        print(f"hermes profile create {prof} --clone-from <base-profile>")
    print()
    print(f"# 3. Scouts run from cron (not the dispatcher), so enable the `kanban` toolset")
    print(f"#    for their cron platform — otherwise kanban_create isn't available to them.")
    for s in cfg.sources:
        print(f"hermes -p {s.profile} tools enable --platform cron kanban")
    print()
    print(f"# 4. Install skills: copy skills/templates/triage-orchestrator → the orchestrator")
    print(f"#    profile's skills dir, and triage-scout → each source profile (renamed per source).")
    for s in cfg.sources:
        print(f"#   {s.skill} → profile {s.profile}")
    print()
    print(f"# 5. Register each scout's cron under ITS OWN profile, created paused.")
    print(f"#    One host gateway serves every profile's cron store (multiplexed by default).")
    for s in cfg.sources:
        print(f"hermes -p {s.profile} cron create '{s.schedule}' "
              f"\"Run one sweep now, following the {s.skill} skill exactly.\" "
              f"--skill {s.skill} --name scout-{s.id} --continuity --paused")
    print()
    print(f"# 6. Start the runtime: ONE host gateway (default profile) runs the dispatcher")
    print(f"#    and every profile's cron.  Foreground:  hermes gateway run")
    print(f"#    Check scheduling:  hermes -p <scout-profile> cron status")
    print(f"# See docs/07-runbook.md for the full go-live sequence.")
    return 0


def cmd_stub(name: str):
    def run(args: argparse.Namespace) -> int:
        print(f"`{name}` is a stub in this template. See `python -m cli.triage scaffold` for the plan, "
              f"and docs/04-adapting-to-your-domain.md / docs/07-runbook.md. Wire it to your environment.")
        return 0
    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cli.triage", description="Hermes Multi-Agent Workflow CLI.")
    parser.add_argument("--config", default="triage.yaml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="Validate triage.yaml.").set_defaults(func=cmd_validate)
    sub.add_parser("scaffold", help="Print the setup plan from triage.yaml.").set_defaults(func=cmd_scaffold)
    sub.add_parser("init", help="(stub) Start a new project.").set_defaults(func=cmd_stub("init"))
    sub.add_parser("install", help="(stub) Execute the scaffold plan.").set_defaults(func=cmd_stub("install"))
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
