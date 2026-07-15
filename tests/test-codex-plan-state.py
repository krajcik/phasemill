#!/usr/bin/env python3
"""Behavioral tests for the Codex planning plan/state layer."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/phasemill/engine/plan_state.py"
FIXTURE = REPO / "tests/fixtures/codex/plans/2026-07-15-plan-state.md"
SPEC = importlib.util.spec_from_file_location("plan_state", SCRIPT)
assert SPEC and SPEC.loader
PLAN_STATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PLAN_STATE
SPEC.loader.exec_module(PLAN_STATE)


class PlanStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.plan = self.root / "docs/plans/2026-07-15-plan-state.md"
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_parser_finds_next_task_and_ignores_fences_and_later_h2(self) -> None:
        plan = PLAN_STATE.parse_plan_file(self.plan)
        self.assertEqual("Plan state fixture", plan.title)
        self.assertEqual(2, len(plan.tasks))
        self.assertEqual("done", plan.tasks[0].status)
        task = plan.next_task
        assert task is not None
        self.assertEqual("iteration", task.kind)
        self.assertEqual("2", task.identifier)
        self.assertEqual("active", task.status)
        self.assertEqual(3, len(task.checkboxes))
        self.assertEqual([True, False, False], [item.checked for item in task.checkboxes])
        self.assertNotIn("Example checkbox", [item.text for item in task.checkboxes])
        self.assertNotIn("outside task scope", [item.text for item in task.checkboxes])

    def test_non_integer_identifiers_and_format_examples_match_donor_contract(self) -> None:
        plan = PLAN_STATE.parse_plan(
            "# P\n### Task 2.5: Inserted\n- [ ] describe `[ ]` format\n- [ ] real work\n"
        )
        self.assertEqual(0, plan.tasks[0].number)
        self.assertFalse(plan.tasks[0].checkboxes[0].actionable)
        self.assertTrue(plan.tasks[0].checkboxes[1].actionable)
        self.assertIs(plan.tasks[0], plan.next_task)

    def test_unscoped_detection_handles_crlf_and_fenced_examples(self) -> None:
        content = "# P\r\n```markdown\r\n- [ ] example\r\n```\r\n- [ ] real\r\n"
        self.assertTrue(PLAN_STATE.has_uncompleted_checkbox(content))
        self.assertFalse(
            PLAN_STATE.has_uncompleted_checkbox("# P\n```\n- [ ] example\n```\n- [x] done\n")
        )

    def test_malformed_plan_uses_unscoped_fallback_until_checked(self) -> None:
        malformed = self.root / "docs/plans/malformed.md"
        malformed.write_text("# P\n- [ ] real work\n", encoding="utf-8")
        store = PLAN_STATE.RunStateStore(self.root, malformed)
        state = store.initialize()
        self.assertEqual("task", state.phase)
        self.assertEqual("unscoped", state.current_task_identifier)
        self.assertEqual(2, state.current_task_line)
        with self.assertRaisesRegex(PLAN_STATE.PlanStateError, "actionable unchecked"):
            store.finish(state.revision, success=True)
        malformed.write_text("# P\n- [x] real work\n", encoding="utf-8")
        reconciled = store.reconcile_plan(state.revision)
        self.assertEqual("review-first", reconciled.phase)

    def test_alternate_date_locator_checks_active_then_completed(self) -> None:
        requested = self.root / "docs/plans/2026-07-15-feature.md"
        alternate = requested.with_name("20260715-feature.md")
        alternate.write_text("# active", encoding="utf-8")
        completed = requested.parent / "completed" / requested.name
        completed.parent.mkdir()
        completed.write_text("# completed", encoding="utf-8")
        self.assertEqual(alternate, PLAN_STATE.locate_plan(requested))
        alternate.unlink()
        self.assertEqual(completed, PLAN_STATE.locate_plan(requested))

    def test_discovery_is_direct_sorted_and_excludes_completed(self) -> None:
        (self.plan.parent / "a.md").write_text("# A", encoding="utf-8")
        completed = self.plan.parent / "completed"
        completed.mkdir()
        (completed / "hidden.md").write_text("# hidden", encoding="utf-8")
        plans = PLAN_STATE.discover_plans(self.root, "docs/plans")
        self.assertEqual(["2026-07-15-plan-state.md", "a.md"], [path.name for path in plans])

    def test_state_initialization_is_durable_and_uses_same_key_after_date_rename(self) -> None:
        store = PLAN_STATE.RunStateStore(self.root, self.plan)
        self.assertEqual(self.root.resolve() / ".phasemill/runs", store.paths.state.parent)
        self.assertNotIn(".codex", store.paths.state.parts)
        state = store.initialize()
        self.assertEqual("task", state.phase)
        self.assertEqual("2", state.current_task_identifier)
        self.assertEqual(0, state.revision)
        self.assertTrue(store.paths.state.is_file())
        self.assertIn(state.run_id, store.paths.progress.read_text(encoding="utf-8"))
        compact = self.plan.with_name("20260715-plan-state.md")
        self.plan.rename(compact)
        renamed_store = PLAN_STATE.RunStateStore(self.root, self.plan)
        self.assertEqual(store.paths, renamed_store.paths)
        restarted = renamed_store.initialize()
        self.assertEqual(state.run_id, restarted.run_id)
        self.assertEqual(1, restarted.restart_count)
        self.assertEqual(1, restarted.revision)
        self.assertIn("restarted at", store.paths.progress.read_text(encoding="utf-8"))

    def test_state_revision_prevents_lost_updates_and_reconcile_advances_phase(self) -> None:
        store = PLAN_STATE.RunStateStore(self.root, self.plan)
        state = store.initialize()
        updated = store.update(state.revision, task_iteration=1)
        with self.assertRaisesRegex(PLAN_STATE.StateConflictError, "stale"):
            store.update(state.revision, task_iteration=2)
        content = self.plan.read_text(encoding="utf-8").replace("[ ]", "[x]")
        self.plan.write_text(content, encoding="utf-8")
        reconciled = store.reconcile_plan(updated.revision)
        self.assertEqual("review-first", reconciled.phase)
        self.assertEqual("", reconciled.current_task_identifier)

    def test_failed_restart_preserves_progress_completed_restart_replaces_it(self) -> None:
        store = PLAN_STATE.RunStateStore(self.root, self.plan)
        state = store.initialize()
        store.append_progress("task started", run_id=state.run_id)
        failed = store.finish(state.revision, success=False, failure="boom\nunsafe footer")
        failed_log = store.paths.progress.read_text(encoding="utf-8")
        self.assertIn("task started", failed_log)
        self.assertIn("Failed:", failed_log)
        self.assertNotIn("boom\nunsafe", failed_log)
        restarted = store.initialize()
        self.assertEqual(failed.run_id, restarted.run_id)
        self.plan.write_text(self.plan.read_text(encoding="utf-8").replace("[ ]", "[x]"), encoding="utf-8")
        completed = store.finish(restarted.revision, success=True)
        self.assertIn("Completed:", store.paths.progress.read_text(encoding="utf-8"))
        fresh = store.initialize()
        self.assertNotEqual(completed.run_id, fresh.run_id)
        fresh_log = store.paths.progress.read_text(encoding="utf-8")
        self.assertNotIn("task started", fresh_log)
        self.assertNotIn("Completed:", fresh_log)

    def test_invalid_state_is_rejected(self) -> None:
        store = PLAN_STATE.RunStateStore(self.root, self.plan)
        state = store.initialize()
        payload = asdict(state)
        payload["phase"] = "magic"
        store.paths.state.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(PLAN_STATE.PlanStateError, "invalid state phase"):
            store.load()

    @unittest.skipIf(sys.platform == "win32", "same-process Windows lock semantics differ")
    def test_state_lock_conflict_is_explicit(self) -> None:
        store = PLAN_STATE.RunStateStore(self.root, self.plan)
        store.initialize()
        with PLAN_STATE._exclusive_lock(store.paths.lock):
            with self.assertRaisesRegex(PLAN_STATE.StateConflictError, "locked"):
                store.load()

    def test_cli_inspect_and_state_init_return_json(self) -> None:
        inspect = subprocess.run(
            [sys.executable, str(SCRIPT), "--project-root", str(self.root), "inspect", str(self.plan)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, inspect.returncode, inspect.stderr)
        self.assertEqual("2", json.loads(inspect.stdout)["next_task"]["identifier"])
        initialize = subprocess.run(
            [sys.executable, str(SCRIPT), "--project-root", str(self.root), "state-init", str(self.plan)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, initialize.returncode, initialize.stderr)
        self.assertEqual("running", json.loads(initialize.stdout)["state"]["status"])


if __name__ == "__main__":
    unittest.main()
