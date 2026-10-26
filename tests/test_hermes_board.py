"""Board-client tests — run with:  python -m unittest discover -s tests

`engine.hermes_board.HermesBoard` writes the board through `hermes kanban`. These
tests swap in a fake runner, so they check the exact CLI calls it builds and how
it handles results and errors. No Hermes install is needed. Set HMAW_LIVE_HERMES=1
to also run one round trip against a real `hermes` on a throwaway
HERMES_KANBAN_HOME.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.hermes_board import BoardError, HermesBoard  # noqa: E402
from scripts.cost_report import run_cost, sum_cost  # noqa: E402


class FakeRunner:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, argv, stdin):
        self.calls.append((list(argv), stdin))
        return self.replies.pop(0)


class TestHermesBoard(unittest.TestCase):
    def test_create_builds_cli_call_and_parses_id(self):
        run = FakeRunner([(0, json.dumps({"id": "t_abc", "status": "todo"}), "")])
        kb = HermesBoard("my-board", hermes_bin="hermes", runner=run)
        tid = kb.create_task(
            title="do_build: s", body="line1\n--flag-looking line", assignee="builder",
            parents=["t_p1"], workspace_kind="dir", workspace_path="/w/builds/s",
            idempotency_key="k1",
        )
        self.assertEqual(tid, "t_abc")
        argv, stdin = run.calls[0]
        self.assertEqual(argv[:5], ["hermes", "kanban", "--board", "my-board", "create"])
        self.assertIn("--json", argv)
        # Body goes through stdin so newlines / flag-like lines survive.
        self.assertEqual(argv[argv.index("--body-file") + 1], "-")
        self.assertEqual(stdin, "line1\n--flag-looking line")
        self.assertEqual(argv[argv.index("--parent") + 1], "t_p1")
        self.assertEqual(argv[argv.index("--workspace") + 1], "dir:/w/builds/s")
        self.assertEqual(argv[argv.index("--idempotency-key") + 1], "k1")
        self.assertEqual(argv[argv.index("--assignee") + 1], "builder")

    def test_scratch_create_has_no_parent_or_workspace_flags(self):
        run = FakeRunner([(0, '{"id": "t_1"}', "")])
        HermesBoard("b", hermes_bin="hermes", runner=run).create_task(title="x", body="", assignee="a")
        argv = run.calls[0][0]
        self.assertNotIn("--parent", argv)
        self.assertNotIn("--workspace", argv)

    def test_dir_workspace_requires_path(self):
        kb = HermesBoard("b", hermes_bin="hermes", runner=FakeRunner([]))
        with self.assertRaises(ValueError):
            kb.create_task(title="x", body="", assignee="a", workspace_kind="dir")

    def test_cli_failure_raises_board_error_with_hermes_message(self):
        run = FakeRunner([(1, "", "kanban: unknown parent task(s): t_nope\n")])
        kb = HermesBoard("b", hermes_bin="hermes", runner=run)
        with self.assertRaises(BoardError) as ctx:
            kb.create_task(title="x", body="", assignee="a", parents=["t_nope"])
        self.assertIn("unknown parent", str(ctx.exception))

    def test_complete_passes_result_metadata_and_force(self):
        run = FakeRunner([(0, "Completed t_1", "")])
        HermesBoard("b", hermes_bin="hermes", runner=run).complete(
            "t_1", result="shelved", metadata={"outcome": "shelved_by_human"}, force=True)
        argv = run.calls[0][0]
        self.assertEqual(argv[4:6], ["complete", "t_1"])
        self.assertEqual(json.loads(argv[argv.index("--metadata") + 1]), {"outcome": "shelved_by_human"})
        self.assertIn("--force", argv)

    def test_comment_and_status(self):
        show = {"task": {"id": "t_1", "status": "ready"}, "runs": []}
        run = FakeRunner([(0, "Comment added", ""), (0, json.dumps(show), "")])
        kb = HermesBoard("b", hermes_bin="hermes", runner=run)
        kb.comment("t_1", author="human", body="hello")
        self.assertEqual(run.calls[0][0][4:], ["comment", "t_1", "hello", "--author", "human"])
        self.assertEqual(kb.status("t_1"), "ready")


class TestCostReport(unittest.TestCase):
    def test_run_cost_reads_metadata(self):
        self.assertEqual(run_cost({"metadata": {"cost_usd": 0.5}}), 0.5)
        self.assertEqual(run_cost({"metadata": '{"cost_usd": "1.25"}'}), 1.25)
        self.assertIsNone(run_cost({"metadata": None}))
        self.assertIsNone(run_cost({"metadata": {"cost_usd": "n/a"}}))

    def test_sum_cost_separates_unreported_and_missing(self):
        views = {
            "t_a": {"runs": [{"metadata": {"cost_usd": 0.4}}, {"metadata": {"cost_usd": 0.1}}]},
            "t_b": {"runs": [{"metadata": {}}]},
        }

        def runner(argv, stdin):
            tid = argv[5]
            if tid not in views:
                return 1, "", "unknown task"
            return 0, json.dumps(views[tid]), ""

        kb = HermesBoard("b", hermes_bin="hermes", runner=runner)
        r = sum_cost(kb, ["t_a", "t_b", "t_missing"])
        self.assertAlmostEqual(r["total"], 0.5)
        self.assertEqual(r["reported"], 1)
        self.assertEqual(r["unreported"], ["t_b"])
        self.assertEqual(r["missing"], ["t_missing"])


@unittest.skipUnless(os.environ.get("HMAW_LIVE_HERMES") == "1", "set HMAW_LIVE_HERMES=1 to hit a real hermes")
class TestLiveHermes(unittest.TestCase):
    """Round trip against a real `hermes` on an isolated, throwaway kanban home."""

    def test_fan_in_and_complete(self):
        import subprocess

        with tempfile.TemporaryDirectory() as home:
            old = os.environ.get("HERMES_KANBAN_HOME")
            os.environ["HERMES_KANBAN_HOME"] = home
            try:
                subprocess.run(["hermes", "kanban", "boards", "create", "hmaw-live"], check=True,
                               capture_output=True)
                kb = HermesBoard("hmaw-live")
                root = kb.create_task(title="root", body="r", assignee="nobody")
                child = kb.create_task(title="child", body="c\n--x", assignee="nobody", parents=[root],
                                       workspace_kind="dir", workspace_path=str(Path(home) / "ws"))
                self.assertEqual(kb.status(root), "ready")
                self.assertEqual(kb.status(child), "todo")
                again = kb.create_task(title="root", body="r", assignee="nobody", idempotency_key="k")
                self.assertEqual(kb.create_task(title="root", body="r", assignee="nobody",
                                                idempotency_key="k"), again)
                kb.comment(root, author="human", body="hi")
                kb.complete(root, result="ok", metadata={"cost_usd": 0.25})
                self.assertEqual(kb.status(root), "done")
                self.assertEqual(kb.status(child), "ready")  # fan-in promotion
                self.assertAlmostEqual(sum_cost(kb, [root, child])["total"], 0.25)
                with self.assertRaises(BoardError):
                    kb.create_task(title="x", body="", assignee="a", parents=["t_doesnotexist"])
            finally:
                if old is None:
                    os.environ.pop("HERMES_KANBAN_HOME", None)
                else:
                    os.environ["HERMES_KANBAN_HOME"] = old


if __name__ == "__main__":
    unittest.main()
