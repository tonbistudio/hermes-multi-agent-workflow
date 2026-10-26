"""Thin client for the Hermes Kanban board, via the `hermes kanban` CLI.

The Kanban board is the inter-agent bus. The engine creates tasks (cards) on it;
the Hermes gateway's dispatcher claims `ready` cards and spawns the assigned
agent. Parent links drive fan-in: a child task stays `todo` until every parent is
`done`, then Hermes promotes it to `ready`.

Why the CLI and not SQLite: earlier versions of this template INSERTed rows into
`kanban.db` directly. Current Hermes owns invariants that a raw writer bypasses —
parent validation, live-claim fencing on completion, run records, lifecycle
hooks/notifications, idempotency keys, and the board-path resolution
(`HERMES_KANBAN_HOME`, `HERMES_KANBAN_BOARD`, `HERMES_KANBAN_DB`, profiles,
Windows `%LOCALAPPDATA%\\hermes`). Going through `hermes kanban` keeps all of that
and stays stable across schema migrations.

Environment overrides:
    HERMES_BIN   the `hermes` executable to call (default: `hermes` on PATH)

This is generic Hermes plumbing — you should not need to edit it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Callable, Sequence

# (argv, stdin) -> (returncode, stdout, stderr). Injectable for tests.
Runner = Callable[[Sequence[str], "str | None"], "tuple[int, str, str]"]


class BoardError(RuntimeError):
    """A `hermes kanban` call failed. `.stderr` carries Hermes's message."""

    def __init__(self, argv: Sequence[str], returncode: int, stdout: str, stderr: str):
        self.argv, self.returncode, self.stdout, self.stderr = list(argv), returncode, stdout, stderr
        msg = (stderr or stdout).strip() or f"exit {returncode}"
        super().__init__(f"`{' '.join(argv[1:4])} …` failed: {msg}")


def _subprocess_runner(argv: Sequence[str], stdin: str | None) -> tuple[int, str, str]:
    proc = subprocess.run(
        list(argv), input=stdin, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def _hermes_bin() -> str:
    explicit = os.environ.get("HERMES_BIN")
    if explicit:
        return explicit
    return shutil.which("hermes") or "hermes"


class HermesBoard:
    """Create/comment/complete cards on one named board through `hermes kanban`."""

    def __init__(self, board: str, *, hermes_bin: str | None = None, runner: Runner | None = None):
        self.board = board
        self.hermes_bin = hermes_bin or _hermes_bin()
        self._run = runner or _subprocess_runner

    # ----- plumbing ----- #

    def _argv(self, *args: str) -> list[str]:
        return [self.hermes_bin, "kanban", "--board", self.board, *args]

    def _call(self, *args: str, stdin: str | None = None) -> str:
        argv = self._argv(*args)
        try:
            rc, out, err = self._run(argv, stdin)
        except FileNotFoundError as exc:
            raise BoardError(argv, 127, "", f"hermes executable not found ({exc}); set HERMES_BIN") from exc
        if rc != 0:
            raise BoardError(argv, rc, out, err)
        return out

    # ----- operations ----- #

    def create_task(
        self,
        *,
        title: str,
        body: str,
        assignee: str,
        parents: list[str] | None = None,
        created_by: str = "hermes-multi-agent-workflow",
        workspace_kind: str = "scratch",
        workspace_path: str | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        """Create a card and return its id.

        Hermes decides the initial status: `ready` when every parent is already
        `done` (or there are none), else `todo` until they finish. Unknown parent
        ids are rejected instead of leaving a dangling link. With
        `idempotency_key`, re-running returns the existing card's id.
        """
        args = ["create", title, "--body-file", "-", "--assignee", assignee,
                "--created-by", created_by, "--json"]
        for parent in parents or []:
            args += ["--parent", parent]
        if workspace_kind == "dir":
            if not workspace_path:
                raise ValueError("workspace_kind='dir' needs a workspace_path")
            args += ["--workspace", f"dir:{workspace_path}"]
        elif workspace_kind == "worktree":
            args += ["--workspace", f"worktree:{workspace_path}" if workspace_path else "worktree"]
        elif workspace_kind != "scratch":
            raise ValueError(f"unknown workspace_kind {workspace_kind!r}")
        if idempotency_key:
            args += ["--idempotency-key", idempotency_key]
        out = self._call(*args, stdin=body)
        try:
            return str(json.loads(out)["id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise BoardError(self._argv(*args), 0, out, f"unparseable create output: {exc}") from exc

    def comment(self, task_id: str, *, author: str, body: str) -> None:
        self._call("comment", task_id, body, "--author", author)

    def show(self, task_id: str) -> dict[str, Any]:
        """Full task view: {task, parents, children, comments, events, runs, ...}."""
        return json.loads(self._call("show", task_id, "--json"))

    def status(self, task_id: str) -> str:
        return str(self.show(task_id)["task"]["status"])

    def complete(self, task_id: str, *, result: str, metadata: dict[str, Any] | None = None,
                 force: bool = False) -> None:
        """Mark a card done with a result. `force` overrides Hermes's live-claim
        guard — reserve it for explicit human decisions (e.g. shelving at the gate)."""
        args = ["complete", task_id, "--result", result]
        if metadata:
            args += ["--metadata", json.dumps(metadata)]
        if force:
            args.append("--force")
        self._call(*args)
