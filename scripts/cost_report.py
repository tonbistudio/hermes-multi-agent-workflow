#!/usr/bin/env python3
"""Per-item LLM-spend report for the cost gate.

Walks the board tasks linked to an item and sums the spend their workers reported.
Used to enforce `cost_gate_usd` from triage.yaml:
  - over budget BEFORE the gate → orchestrator pauses + notifies
  - over budget AFTER approval  → orchestrator notifies + continues

Usage (from the repo root):
  python scripts/cost_report.py <slug> [--gate 5]   # exits 1 if over --gate

Where the numbers come from: the Hermes board has no per-task cost column. Each
worker records its spend when it closes its card, as completion metadata:

    kanban_complete(summary="...", metadata={"cost_usd": 0.42, ...})

That lands on the task's run record; this script reads it through
`hermes kanban show <id> --json` and sums `cost_usd` across every run of every
linked task. Tasks with no reported cost are listed under `unreported`, so a
partial total is never presented as complete. If nothing reports a cost, it
prints "telemetry unavailable" rather than guessing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import TriageConfig  # noqa: E402
from engine.hermes_board import BoardError, HermesBoard  # noqa: E402
from engine.item_vault import ItemVault  # noqa: E402
from proposal_actions import board, vault_dir  # noqa: E402  (reuse the same resolution)


def linked_task_ids(slug: str, config: TriageConfig) -> list[str]:
    vault = ItemVault(vault_dir(config))
    fm = vault.load(slug).frontmatter
    ids = []
    for t in fm.get("linked_kanban_tasks") or []:
        ids.append(t.get("task_id") if isinstance(t, dict) else t)
    return [t for t in ids if t]


def run_cost(run: dict[str, Any]) -> float | None:
    """`cost_usd` from one run's completion metadata, or None if not reported."""
    meta = run.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            return None
    if not isinstance(meta, dict):
        return None
    value = meta.get("cost_usd")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def sum_cost(kb: HermesBoard, task_ids: list[str]) -> dict[str, Any]:
    total, reported, unreported, missing = 0.0, 0, [], []
    for tid in task_ids:
        try:
            view = kb.show(tid)
        except BoardError:
            missing.append(tid)
            continue
        costs = [c for c in (run_cost(r) for r in view.get("runs") or []) if c is not None]
        if costs:
            total += sum(costs)
            reported += 1
        else:
            unreported.append(tid)
    return {"total": total, "reported": reported, "unreported": unreported, "missing": missing}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Per-item spend report.")
    parser.add_argument("slug")
    parser.add_argument("--gate", type=float, default=None, help="USD budget; non-zero exit if exceeded.")
    parser.add_argument("--config", default="triage.yaml")
    args = parser.parse_args(argv)

    config = TriageConfig.load(args.config)
    gate = args.gate if args.gate is not None else config.cost_gate_usd
    ids = linked_task_ids(args.slug, config)
    result = sum_cost(board(config), ids)

    if result["reported"] == 0:
        print(json.dumps({"slug": args.slug, "cost_usd": None, "note": "telemetry unavailable",
                          "tasks": len(ids), "unreported": result["unreported"], "missing": result["missing"]}))
        return 0
    total = result["total"]
    over = total > gate
    print(json.dumps({"slug": args.slug, "cost_usd": round(total, 4), "gate_usd": gate, "over_budget": over,
                      "tasks": len(ids), "tasks_reporting_cost": result["reported"],
                      "unreported": result["unreported"], "missing": result["missing"]}, indent=2))
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
