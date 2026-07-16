#!/usr/bin/env python3
"""Behavioral state tests for the durable Phasemill lazy workflow."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/phasemill/engine/lazy_state.py"
SPEC = importlib.util.spec_from_file_location("lazy_state", SCRIPT)
assert SPEC and SPEC.loader
LAZY_STATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LAZY_STATE
SPEC.loader.exec_module(LAZY_STATE)

CONTROLLER_PATH = REPO / "plugins/phasemill/engine/lazy_controller.py"
CONTROLLER_SPEC = importlib.util.spec_from_file_location("lazy_controller", CONTROLLER_PATH)
assert CONTROLLER_SPEC and CONTROLLER_SPEC.loader
CONTROLLER = importlib.util.module_from_spec(CONTROLLER_SPEC)
sys.modules[CONTROLLER_SPEC.name] = CONTROLLER
CONTROLLER_SPEC.loader.exec_module(CONTROLLER)

CONFIG_PATH = REPO / "plugins/phasemill/engine/config.py"
CONFIG_SPEC = importlib.util.spec_from_file_location("lazy_test_config", CONFIG_PATH)
assert CONFIG_SPEC and CONFIG_SPEC.loader
CONFIG = importlib.util.module_from_spec(CONFIG_SPEC)
sys.modules[CONFIG_SPEC.name] = CONFIG
CONFIG_SPEC.loader.exec_module(CONFIG)


class LazyStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def start(self, request_id: str = "request-1", idea: str = "Add bounded retries"):
        return LAZY_STATE.LazyStateStore.start(
            self.root,
            request_id=request_id,
            idea=idea,
        )

    def assert_mode(self, path: Path, expected: int) -> None:
        self.assertEqual(expected, stat.S_IMODE(path.stat().st_mode), path)

    def test_initialization_is_confined_versioned_and_mode_safe(self) -> None:
        store, state, created = self.start()
        self.assertTrue(created)
        self.assertEqual(1, state.version)
        self.assertEqual("discovery", state.phase)
        self.assertEqual("running", state.status)
        self.assertEqual(0, state.revision)
        self.assertEqual(
            self.root / ".phasemill/runs" / f"lazy-{state.journey_id}",
            store.paths.directory,
        )
        self.assertEqual(self.root, Path(state.origin_project_root))
        self.assert_mode(store.paths.directory, 0o700)
        self.assert_mode(store.paths.state, 0o600)
        self.assert_mode(store.paths.progress, 0o600)
        self.assert_mode(store.paths.lock, 0o600)
        self.assert_mode(self.root / ".phasemill/runs/.lazy-create.lock", 0o600)


class LazyControllerTests(unittest.TestCase):
    PLAN = "# Lazy plan\n\n### Task 1: Implement\n\n- [ ] implement behavior\n"

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name).resolve()
        (self.root / "docs/plans").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "lazy@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Lazy Test"], cwd=self.root, check=True)
        (self.root / ".gitignore").write_text("/.phasemill/runs/\n", encoding="utf-8")
        (self.root / "README.md").write_text("# Fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore", "README.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=self.root, check=True)
        self.user = self.root / "user-data"
        self.user.mkdir()

    def config(self, body: str = ""):
        if body:
            custom = self.root / ".codex/phasemill/config.toml"
            custom.parent.mkdir(parents=True, exist_ok=True)
            custom.write_text(body, encoding="utf-8")
        return CONFIG.load_effective(project_root=self.root, plugin_data=self.user)

    def start(self, request_id: str = "controller-request", config=None):
        controller, created = CONTROLLER.LazyController.start(
            self.root,
            config or self.config(),
            request_id=request_id,
            idea="Add bounded retries",
        )
        return controller, controller.next_action(), created

    def record(self, controller, action, **value):
        return controller.record_result(action.action_id, CONTROLLER.LazyResult.from_mapping(value))

    def write_plan(self, action, content: str | None = None, *, exclusive: bool = True) -> str:
        path = self.root / action.plan_path
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "x" if exclusive else "w"
        with path.open(mode, encoding="utf-8") as output:
            output.write(content or self.PLAN)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def to_plan(self, controller, action):
        action = self.record(
            controller,
            action,
            outcome="completed",
            summary="repository inspected",
            scope_paths=["src"],
        )
        self.assertEqual("design", action.kind)
        action = self.record(controller, action, outcome="completed", summary="minimal design")
        self.assertEqual("plan", action.kind)
        self.assertEqual("create-exclusive", action.plan_write_mode)
        self.assertIn("Create the reserved plan with no-replace semantics", action.reason)
        return action

    def to_review(self, controller, action):
        action = self.to_plan(controller, action)
        digest = self.write_plan(action)
        review = self.record(
            controller,
            action,
            outcome="completed",
            plan_path=action.plan_path,
            plan_digest=digest,
        )
        self.assertEqual("plan-review", review.kind)
        return review

    def finding(self, number: int = 1):
        return {
            "id": f"finding-{number}",
            "location": "docs/plans/change.md:1",
            "evidence": "missing validation step",
            "consequence": "implementation can regress",
            "proposed_fix": "add an explicit validation command",
        }

    def test_full_phase_order_prompt_composition_and_role_resolution(self) -> None:
        controller, action, created = self.start()
        self.assertTrue(created)
        self.assertEqual("discovery", action.kind)
        review = self.to_review(controller, action)
        self.assertEqual(3, len(review.roles))
        self.assertEqual(3, review.max_parallel_agents)
        self.assertIn("Prompt source:", review.prompt)
        plan_prompt = controller.config.prompts["make-plan"].content
        state = controller.store.load()
        rendered = controller._render("lazy-plan", state)
        self.assertIn(plan_prompt.splitlines()[0], rendered)
        self.assertIn("Lazy authorization override", rendered)
        self.assertIn("supersede only", rendered)

    def test_restart_returns_same_action_at_every_preparation_revision(self) -> None:
        controller, action, _ = self.start("restart-everywhere")
        self.assertEqual(action, controller.next_action())
        design = self.record(
            controller,
            action,
            outcome="completed",
            summary="restartable discovery",
            scope_paths=["src"],
        )
        self.assertEqual(design, controller.next_action())
        controller = CONTROLLER.LazyController(controller.store, controller.config)
        self.assertIn("restartable discovery", controller.next_action().prompt)
        plan = self.record(controller, design, outcome="completed", summary="minimal design")
        self.assertEqual(plan, controller.next_action())
        controller = CONTROLLER.LazyController(controller.store, controller.config)
        self.assertIn("restartable discovery", controller.next_action().prompt)
        self.assertIn("minimal design", controller.next_action().prompt)
        digest = self.write_plan(plan)
        review = self.record(
            controller,
            plan,
            outcome="completed",
            plan_path=plan.plan_path,
            plan_digest=digest,
        )
        self.assertEqual(review, controller.next_action())
        fix = self.record(controller, review, outcome="findings", findings=[self.finding()])
        self.assertEqual(fix, controller.next_action())
        previous = fix.plan_digest
        digest = self.write_plan(
            fix,
            (self.root / fix.plan_path).read_text(encoding="utf-8") + "\nValidation added.\n",
            exclusive=False,
        )
        review = self.record(
            controller,
            fix,
            outcome="completed",
            plan_path=fix.plan_path,
            previous_plan_digest=previous,
            plan_digest=digest,
        )
        self.assertEqual(review, controller.next_action())
        handoff = self.record(controller, review, outcome="clean")
        self.assertEqual(handoff, controller.next_action())

    def test_two_review_attempts_then_convergence_failure(self) -> None:
        controller, action, _ = self.start()
        review = self.to_review(controller, action)
        fix = self.record(
            controller,
            review,
            outcome="findings",
            findings=[self.finding(1)],
        )
        self.assertEqual("plan-fix", fix.kind)
        previous = fix.plan_digest
        content = (self.root / fix.plan_path).read_text(encoding="utf-8") + "\nFix 1.\n"
        digest = self.write_plan(fix, content, exclusive=False)
        review = self.record(
            controller,
            fix,
            outcome="completed",
            plan_path=fix.plan_path,
            previous_plan_digest=previous,
            plan_digest=digest,
        )
        self.assertEqual(2, review.iteration)
        failed = self.record(
            controller,
            review,
            outcome="findings",
            findings=[self.finding(2)],
        )
        self.assertEqual("failed", failed.kind)
        self.assertIn("did not converge", failed.reason)
        terminal = controller.store.load()
        self.assertEqual((self.finding(2),), terminal.findings)
        self.assertEqual("failed", terminal.status)

    def test_waiting_input_is_stable_and_answer_resumes_exact_phase(self) -> None:
        controller, action, _ = self.start()
        waiting = self.record(
            controller,
            action,
            outcome="needs-input",
            question="Which compatibility contract should be preserved?",
            options=["Existing API", "New API"],
            gate="material-design",
        )
        self.assertEqual("input", waiting.kind)
        self.assertEqual(waiting, controller.next_action())
        state = controller.store.load()
        self.assertEqual("waiting-input", state.status)
        self.assertEqual("discovery", state.preserved_phase)
        self.assertEqual("material-design", state.pending_gate)
        self.assertEqual("material-design", waiting.gate)
        resumed = self.record(
            controller, waiting, outcome="answered", answer="Existing API", decision="continue"
        )
        self.assertEqual("discovery", resumed.kind)
        progress = controller.store.paths.progress.read_text(encoding="utf-8")
        self.assertIn("answer: Existing API", progress)
        with self.assertRaisesRegex(CONTROLLER.LAZY_STATE.LazyStateConflictError, "stale"):
            self.record(
                controller, waiting, outcome="answered", answer="New API", decision="continue"
            )

    def test_stop_decision_is_terminal_and_never_resumes(self) -> None:
        controller, action, _ = self.start("stop-gate")
        waiting = self.record(
            controller,
            action,
            outcome="needs-input",
            question="Continue?",
            options=["Continue", "Stop"],
            gate="material-design",
        )
        stopped = self.record(
            controller, waiting, outcome="answered", answer="Stop", decision="stop"
        )
        self.assertEqual("failed", stopped.kind)
        self.assertIn("stopped by user", stopped.reason)

    def test_empty_and_wrong_phase_answers_are_rejected_without_revision_change(self) -> None:
        controller, action, _ = self.start("bad-answer")
        revision = controller.store.load().revision
        with self.assertRaisesRegex(CONTROLLER.LazyControllerError, "does not accept"):
            self.record(controller, action, outcome="answered", answer="yes", decision="continue")
        self.assertEqual(revision, controller.store.load().revision)
        waiting = self.record(
            controller,
            action,
            outcome="needs-input",
            question="Choose?",
            options=["A", "B"],
            gate="material-design",
        )
        waiting_revision = controller.store.load().revision
        with self.assertRaisesRegex(CONTROLLER.LazyControllerError, "non-empty answer"):
            CONTROLLER.LazyResult.from_mapping(
                {"outcome": "answered", "answer": "", "decision": "continue"}
            )
        self.assertEqual(waiting_revision, controller.store.load().revision)
        self.assertEqual(waiting, controller.next_action())

    def test_all_permission_and_external_gates_pause_without_approval_leakage(self) -> None:
        for gate in sorted(CONTROLLER.GATES - {"dirty-overlap", "worktree-approval"}):
            with self.subTest(gate=gate):
                controller, action, _ = self.start(f"gate-{gate}")
                waiting = self.record(
                    controller,
                    action,
                    outcome="needs-input",
                    question=f"Approve scoped {gate}?",
                    options=["Approve once", "Stop"],
                    gate=gate,
                )
                self.assertEqual("input", waiting.kind)
                resumed = self.record(
                    controller,
                    waiting,
                    outcome="answered",
                    answer="Approve once",
                    decision="continue",
                )
                self.assertEqual("discovery", resumed.kind)
                state = controller.store.load()
                self.assertEqual("", state.pending_question)
                self.assertEqual("", state.pending_gate)
                self.assertEqual("", state.preserved_phase)

    def test_controller_computes_dirty_overlap_and_detects_later_drift(self) -> None:
        source = self.root / "src/service.py"
        source.parent.mkdir(parents=True)
        source.write_text("baseline\n", encoding="utf-8")
        subprocess.run(["git", "add", "src/service.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "source"], cwd=self.root, check=True)

        controller, action, _ = self.start("dirty-real")
        design = self.record(
            controller,
            action,
            outcome="completed",
            summary="src is in scope",
            scope_paths=["src"],
        )
        self.assertEqual("design", design.kind)
        source.write_text("user drift\n", encoding="utf-8")
        plan = self.record(controller, design, outcome="completed", summary="keep API")
        digest = self.write_plan(plan)
        waiting = self.record(
            controller,
            plan,
            outcome="completed",
            plan_path=plan.plan_path,
            plan_digest=digest,
        )
        self.assertEqual("input", waiting.kind)
        self.assertEqual("dirty-overlap", waiting.gate)

    def test_disjoint_drift_does_not_pause(self) -> None:
        controller, action, _ = self.start("dirty-disjoint")
        design = self.record(
            controller,
            action,
            outcome="completed",
            summary="src is in scope",
            scope_paths=["src"],
        )
        (self.root / "notes.txt").write_text("disjoint\n", encoding="utf-8")
        plan = self.record(controller, design, outcome="completed", summary="keep API")
        digest = self.write_plan(plan)
        review = self.record(
            controller,
            plan,
            outcome="completed",
            plan_path=plan.plan_path,
            plan_digest=digest,
        )
        self.assertEqual("plan-review", review.kind)

    def test_repository_scope_overlaps_all_non_runtime_changes(self) -> None:
        controller, _, _ = self.start("repository-scope")
        self.assertEqual(
            ("README.md", "new.txt", "src/staged.py"),
            controller._path_overlap(
                (
                    "README.md",
                    "new.txt",
                    "src/staged.py",
                    ".phasemill/runs/runtime.json",
                ),
                (".",),
            ),
        )
        action = controller.next_action()
        design = self.record(
            controller,
            action,
            outcome="completed",
            summary="the whole repository is in scope",
            scope_paths=["."],
        )
        self.assertEqual("design", design.kind)
        self.assertEqual((".",), controller.store.load().scope_paths)

    def test_approved_dirty_path_content_change_and_head_change_re_gate(self) -> None:
        source = self.root / "src/service.py"
        source.parent.mkdir(parents=True)
        source.write_text("dirty one\n", encoding="utf-8")
        controller, action, _ = self.start("dirty-content")
        waiting = self.record(
            controller,
            action,
            outcome="completed",
            summary="src scope",
            scope_paths=["src"],
        )
        design = self.record(
            controller,
            waiting,
            outcome="answered",
            answer="Continue",
            decision="continue",
        )
        source.write_text("dirty two\n", encoding="utf-8")
        plan = self.record(controller, design, outcome="completed", summary="design")
        digest = self.write_plan(plan)
        waiting_again = self.record(
            controller, plan, outcome="completed", plan_path=plan.plan_path, plan_digest=digest
        )
        self.assertEqual("dirty-overlap", waiting_again.gate)

        source.write_text("committed\n", encoding="utf-8")
        subprocess.run(["git", "add", "src/service.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "scoped head drift"], cwd=self.root, check=True)
        refreshed = self.record(
            controller,
            waiting_again,
            outcome="answered",
            answer="Continue",
            decision="continue",
        )
        self.assertEqual("input", refreshed.kind)
        self.assertEqual("dirty-overlap", refreshed.gate)
        progress = controller.store.paths.progress.read_text(encoding="utf-8")
        self.assertIn("answer: Continue", progress)
        continued = self.record(
            controller,
            refreshed,
            outcome="answered",
            answer="Continue",
            decision="continue",
        )
        self.assertEqual("plan-review", continued.kind)
        source.write_text("committed again\n", encoding="utf-8")
        subprocess.run(["git", "add", "src/service.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "later scoped head drift"], cwd=self.root, check=True)
        waiting_head = self.record(controller, continued, outcome="clean")
        self.assertEqual("input", waiting_head.kind)
        self.assertEqual("dirty-overlap", waiting_head.gate)

    def test_invalid_fields_stale_action_and_plan_digest_drift_do_not_advance(self) -> None:
        controller, action, _ = self.start()
        revision = controller.store.load().revision
        with self.assertRaisesRegex(CONTROLLER.LazyControllerError, "invalid fields"):
            self.record(
                controller,
                action,
                outcome="completed",
                plan_path="docs/plans/wrong.md",
                summary="repo evidence",
                scope_paths=["src"],
            )
        self.assertEqual(revision, controller.store.load().revision)
        review = self.to_review(controller, action)
        path = self.root / review.plan_path
        path.write_text(path.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
        with self.assertRaisesRegex(CONTROLLER.LazyControllerError, "digest drift"):
            controller.next_action()

    def test_reserved_plan_collision_does_not_replace_existing_file(self) -> None:
        controller, action, _ = self.start()
        state = controller.store.load()
        expected = controller._plan_candidate(state)
        collision = self.root / expected
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_text("keep me\n", encoding="utf-8")
        design = self.record(
            controller,
            action,
            outcome="completed",
            summary="repo evidence",
            scope_paths=["src"],
        )
        with self.assertRaisesRegex(CONTROLLER.LazyControllerError, "already exists"):
            self.record(controller, design, outcome="completed", summary="minimal design")
        self.assertEqual("keep me\n", collision.read_text(encoding="utf-8"))

    def test_new_plan_requires_unchecked_work_and_rejection_does_not_log_progress(self) -> None:
        controller, action, _ = self.start("all-checked-plan")
        plan = self.to_plan(controller, action)
        digest = self.write_plan(
            plan,
            "# Done plan\n\n### Task 1: Implement\n\n- [x] already implemented\n",
        )
        progress_before = controller.store.paths.progress.read_text(encoding="utf-8")
        with self.assertRaisesRegex(CONTROLLER.LazyControllerError, "no unchecked executable work"):
            self.record(
                controller,
                plan,
                outcome="completed",
                plan_path=plan.plan_path,
                plan_digest=digest,
            )
        self.assertEqual(
            progress_before,
            controller.store.paths.progress.read_text(encoding="utf-8"),
        )

    def test_plan_failure_after_reservation_is_terminal_and_preserves_diagnostics(self) -> None:
        controller, action, _ = self.start("plan-failure")
        plan = self.to_plan(controller, action)
        failed = self.record(controller, plan, outcome="failed", summary="writer unavailable")
        self.assertEqual("failed", failed.kind)
        self.assertIn("writer unavailable", failed.reason)

    def test_handoff_discovers_exact_existing_run_and_records_terminal_result(self) -> None:
        controller, action, _ = self.start()
        review = self.to_review(controller, action)
        handoff = self.record(controller, review, outcome="clean")
        self.assertEqual("handoff", handoff.kind)
        run_store = CONTROLLER.PLAN_STATE.RunStateStore(self.root, Path(handoff.execution_plan_path))
        run = run_store.initialize()
        resumed = controller.next_action()
        self.assertEqual(run.run_id, resumed.matching_run_id)
        other = self.root / "docs/plans/other.md"
        other.write_text(self.PLAN, encoding="utf-8")
        unrelated = CONTROLLER.PLAN_STATE.RunStateStore(self.root, other).initialize()
        self.assertNotEqual(unrelated.run_id, controller.next_action().matching_run_id)
        path = self.root / handoff.execution_plan_path
        path.write_text(path.read_text(encoding="utf-8").replace("[ ]", "[x]"), encoding="utf-8")
        reconciled = run_store.reconcile_plan(run.revision)
        restarted = CONTROLLER.LazyController(controller.store, controller.config).next_action()
        self.assertEqual(run.run_id, restarted.matching_run_id)
        completed_run = run_store.finish(reconciled.revision, success=True)
        done = self.record(
            controller,
            resumed,
            outcome="completed",
            linked_run_id=completed_run.run_id,
            execution_project_root=str(self.root),
            execution_plan_path=handoff.execution_plan_path,
            run_outcome="completed",
        )
        self.assertEqual("done", done.kind)

    def test_worktree_handoff_ignores_origin_run_until_coordinates_are_approved(self) -> None:
        controller, action, _ = self.start(
            "worktree-origin-run",
            self.config("[worktree]\nenabled = true\n"),
        )
        handoff = self.record(controller, self.to_review(controller, action), outcome="clean")
        run_store = CONTROLLER.PLAN_STATE.RunStateStore(
            self.root, Path(handoff.execution_plan_path)
        )
        run_store.initialize()

        gated = controller.next_action()
        self.assertEqual("", gated.matching_run_id)
        self.assertIn("worktree approval", gated.reason)

    def test_failed_linked_run_records_terminal_diagnostics(self) -> None:
        controller, action, _ = self.start("failed-run")
        handoff = self.record(controller, self.to_review(controller, action), outcome="clean")
        run_store = CONTROLLER.PLAN_STATE.RunStateStore(self.root, Path(handoff.execution_plan_path))
        run = run_store.initialize()
        failed_run = run_store.finish(run.revision, success=False, failure="tests failed")
        failed = self.record(
            controller,
            handoff,
            outcome="completed",
            linked_run_id=failed_run.run_id,
            execution_project_root=str(self.root),
            execution_plan_path=handoff.execution_plan_path,
            run_outcome="failed",
        )
        self.assertEqual("failed", failed.kind)
        self.assertIn("linked implementation run failed", failed.reason)

    def test_optional_run_settings_are_forwarded_unchanged(self) -> None:
        config = self.config(
            "[review.external]\nbackend = \"none\"\nrequired = false\n"
            "[finalize]\nenabled = true\n"
            "[learning]\nauto_propose = false\n"
        )
        controller, action, _ = self.start("optional-config", config)
        handoff = self.record(controller, self.to_review(controller, action), outcome="clean")
        requirements = handoff.run_requirements
        self.assertEqual("none", requirements["external_review"]["backend"])
        self.assertFalse(requirements["external_review"]["required"])
        self.assertTrue(requirements["finalize_enabled"])
        self.assertFalse(requirements["learning_auto_propose"])
        self.assertEqual(
            config.values["review"]["external"],
            requirements["effective"]["review"]["external"],
        )
        reloaded = CONFIG.load_effective(
            project_root=self.root,
            plugin_data=self.user,
            overrides=requirements["overrides"],
        )
        for section in (
            "execution", "review", "agents", "finalize", "learning", "plans", "worktree", "profiles"
        ):
            self.assertEqual(config.values[section], reloaded.values[section], section)

    def test_handoff_run_overrides_are_frozen_across_config_reload(self) -> None:
        controller, action, _ = self.start("frozen-overrides")
        handoff = self.record(controller, self.to_review(controller, action), outcome="clean")
        frozen = list(handoff.run_requirements["overrides"])
        changed = self.config("[execution]\ntask_retries = 7\n")
        reconstructed = CONTROLLER.LazyController(controller.store, changed).next_action()
        self.assertEqual(frozen, reconstructed.run_requirements["overrides"])
        self.assertEqual(handoff.run_requirements, reconstructed.run_requirements)
        self.assertIn("execution.task_retries=1", frozen)

    def test_concurrent_different_results_record_only_the_winner_progress(self) -> None:
        controller, action, _ = self.start("concurrent-result")
        barrier = threading.Barrier(2)
        outcomes: list[str] = []

        def record(summary: str) -> None:
            barrier.wait()
            try:
                self.record(
                    controller,
                    action,
                    outcome="completed",
                    summary=summary,
                    scope_paths=["src"],
                )
                outcomes.append(summary)
            except CONTROLLER.LAZY_STATE.LazyStateConflictError:
                outcomes.append("stale")

        threads = [threading.Thread(target=record, args=(summary,)) for summary in ("winner-a", "winner-b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, outcomes.count("stale"))
        winner = next(item for item in outcomes if item != "stale")
        progress = controller.store.paths.progress.read_text(encoding="utf-8")
        self.assertIn(winner, progress)
        self.assertNotIn("winner-b" if winner == "winner-a" else "winner-a", progress)
    def test_required_pi_without_consent_reaches_handoff_unchanged(self) -> None:
        config = self.config(
            "[review.external]\nrequired = true\ndata_sharing_approved = false\n"
        )
        controller, action, _ = self.start("required-pi", config)
        handoff = self.record(controller, self.to_review(controller, action), outcome="clean")
        external = handoff.run_requirements["external_review"]
        self.assertEqual("pi", external["backend"])
        self.assertTrue(external["required"])
        self.assertFalse(external["data_sharing_approved"])

    def test_worktree_coordinates_must_be_registered_sibling_with_exact_plan(self) -> None:
        config = self.config("[worktree]\nenabled = true\n")
        controller, action, _ = self.start("worktree", config)
        handoff = self.record(controller, self.to_review(controller, action), outcome="clean")
        self.assertIn("explicit worktree approval", handoff.reason)
        plain_sibling = self.root.parent / f"{self.root.name}-plain-sibling"
        plain_sibling.mkdir()
        self.addCleanup(lambda: __import__("shutil").rmtree(plain_sibling, ignore_errors=True))
        plain_target = plain_sibling / handoff.plan_path
        plain_target.parent.mkdir(parents=True)
        plain_target.write_bytes((self.root / handoff.plan_path).read_bytes())
        branch = "lazy-test-worktree"
        sibling = self.root.parent / f".{self.root.name}-phasemill-worktrees" / branch
        with self.assertRaisesRegex(CONTROLLER.LazyControllerError, "packaged worktree helper"):
            self.record(
                controller,
                handoff,
                outcome="needs-input",
                question="Create approved worktree?",
                options=["Continue", "Stop"],
                gate="worktree-approval",
                approved_main_root=str(self.root),
                approved_execution_root=str(self.root.parent / f"{self.root.name}-worktree"),
                approved_branch=branch,
                approved_plan_path=handoff.plan_path,
            )
        waiting = self.record(
            controller,
            handoff,
            outcome="needs-input",
            question="Create approved worktree?",
            options=["Continue", "Stop"],
            gate="worktree-approval",
            approved_main_root=str(self.root),
            approved_execution_root=str(sibling),
            approved_branch=branch,
            approved_plan_path=handoff.plan_path,
        )
        handoff = self.record(
            controller,
            waiting,
            outcome="answered",
            answer="Continue",
            decision="continue",
        )
        progress_before = controller.store.paths.progress.read_text(encoding="utf-8")
        with self.assertRaisesRegex(CONTROLLER.LazyControllerError, "approved execution root"):
            self.record(
                controller,
                handoff,
                outcome="completed",
                execution_project_root=str(plain_sibling),
                execution_plan_path=handoff.plan_path,
                execution_branch="lazy-test-worktree",
            )
        self.assertEqual(
            progress_before,
            controller.store.paths.progress.read_text(encoding="utf-8"),
        )
        other_worktree = self.root.parent / f"{self.root.name}-other-worktree"
        subprocess.run(
            ["git", "worktree", "add", "-q", "-b", "lazy-other-worktree", str(other_worktree)],
            cwd=self.root,
            check=True,
        )
        self.addCleanup(
            lambda: subprocess.run(
                ["git", "worktree", "remove", "--force", str(other_worktree)],
                cwd=self.root,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        other_target = other_worktree / handoff.plan_path
        other_target.parent.mkdir(parents=True)
        other_target.write_bytes((self.root / handoff.plan_path).read_bytes())
        with self.assertRaisesRegex(CONTROLLER.LazyControllerError, "approved execution root"):
            self.record(
                controller,
                handoff,
                outcome="completed",
                execution_project_root=str(other_worktree),
                execution_plan_path=handoff.plan_path,
                execution_branch="lazy-other-worktree",
            )
        sibling.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "-q", "-b", branch, str(sibling)],
            cwd=self.root,
            check=True,
        )
        self.addCleanup(
            lambda: subprocess.run(
                ["git", "worktree", "remove", "--force", str(sibling)],
                cwd=self.root,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        target = sibling / handoff.plan_path
        target.parent.mkdir(parents=True)
        target.write_bytes((self.root / handoff.plan_path).read_bytes())
        prepared = self.record(
            controller,
            handoff,
            outcome="completed",
            execution_project_root=str(sibling),
            execution_plan_path=handoff.plan_path,
            execution_branch=branch,
        )
        self.assertEqual("handoff", prepared.kind)
        self.assertEqual(str(sibling), prepared.execution_project_root)
        with self.assertRaisesRegex(CONTROLLER.LazyControllerError, "differs from recorded"):
            self.record(
                controller,
                prepared,
                outcome="completed",
                execution_project_root=str(sibling) + "-other",
                execution_plan_path=handoff.plan_path,
                execution_branch=branch,
            )
        run_store = CONTROLLER.PLAN_STATE.RunStateStore(sibling, Path(handoff.plan_path))
        run = run_store.initialize()
        target.write_text(target.read_text(encoding="utf-8").replace("[ ]", "[x]"), encoding="utf-8")
        run = run_store.reconcile_plan(run.revision)
        run = run_store.finish(run.revision, success=True)
        terminal = controller.next_action()
        self.assertEqual(run.run_id, terminal.matching_run_id)
        done = self.record(
            controller,
            terminal,
            outcome="completed",
            linked_run_id=run.run_id,
            execution_project_root=str(sibling),
            execution_plan_path=handoff.plan_path,
            run_outcome="completed",
        )
        self.assertEqual("done", done.kind)

    def test_discovery_skips_corrupt_state_but_direct_load_remains_strict(self) -> None:
        healthy, _, _ = self.start("healthy-discovery")
        corrupt = self.root / ".phasemill/runs/lazy-corrupt/state.json"
        corrupt.parent.mkdir(parents=True)
        corrupt.write_text("{broken", encoding="utf-8")

        discovered = CONTROLLER.LAZY_STATE.discover_journeys(self.root, active_only=True)
        self.assertEqual([healthy.store.load().journey_id], [state.journey_id for state in discovered])
        with self.assertRaises(CONTROLLER.LAZY_STATE.LazyStateError):
            CONTROLLER.LAZY_STATE.LazyStateStore(self.root, "corrupt").load()

    def test_cli_start_status_next_and_result_file(self) -> None:
        import subprocess

        start = subprocess.run(
            [
                sys.executable,
                str(CONTROLLER_PATH),
                "--project-root",
                str(self.root),
                "--plugin-data",
                str(self.user),
                "start",
                "--request-id",
                "cli-request",
                "--idea",
                "Add a CLI feature",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, start.returncode, start.stderr)
        action = json.loads(start.stdout)
        result_file = self.root / "result.json"
        result_file.write_text(
            json.dumps({"outcome": "needs-input", "question": "Choose?", "options": ["A", "B"], "gate": "material-design"}),
            encoding="utf-8",
        )
        recorded = subprocess.run(
            [
                sys.executable,
                str(CONTROLLER_PATH),
                "--project-root",
                str(self.root),
                "--plugin-data",
                str(self.user),
                "record",
                action["action_id"].split(":", 1)[0],
                "--action-id",
                action["action_id"],
                "--result-file",
                str(result_file),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, recorded.returncode, recorded.stderr)
        self.assertEqual("input", json.loads(recorded.stdout)["kind"])
class LazyStateContinuationTests(LazyStateTests):
    def test_lost_response_replay_returns_same_journey_and_distinct_request_is_new(self) -> None:
        store, state, created = self.start()
        replay_store, replay, replay_created = self.start()
        other_store, other, other_created = self.start("request-2")
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(state, replay)
        self.assertEqual(store.paths, replay_store.paths)
        self.assertTrue(other_created)
        self.assertNotEqual(state.journey_id, other.journey_id)
        self.assertNotEqual(store.paths, other_store.paths)
        with self.assertRaisesRegex(LAZY_STATE.LazyStateConflictError, "different request payload"):
            self.start(idea="A different idea")

    def test_serialization_is_strict_and_size_bounded(self) -> None:
        store, state, _ = self.start()
        self.assertEqual(state, LAZY_STATE.LazyState.from_mapping(json.loads(store.paths.state.read_text())))
        payload = asdict(state)
        payload["extra"] = "unexpected"
        with self.assertRaisesRegex(LAZY_STATE.LazyStateError, "extra"):
            LAZY_STATE.LazyState.from_mapping(payload)
        with self.assertRaisesRegex(LAZY_STATE.LazyStateError, "safe size"):
            self.start("x" * (LAZY_STATE.MAX_REQUEST_ID + 1))
        payload = asdict(state)
        payload["findings"] = [
            {
                "id": "finding-1",
                "location": "src/example.py:1",
                "evidence": "x" * (LAZY_STATE.MAX_TEXT + 1),
                "consequence": "incorrect behavior",
                "proposed_fix": "validate the input",
            }
        ]
        with self.assertRaisesRegex(LAZY_STATE.LazyStateError, "safe size"):
            LAZY_STATE.LazyState.from_mapping(payload)

    def test_path_and_journey_slug_confinement(self) -> None:
        for journey_id in ("../escape", "UPPER", "", "a/b"):
            with self.subTest(journey_id=journey_id):
                with self.assertRaises(LAZY_STATE.LazyStateError):
                    LAZY_STATE.lazy_paths(self.root, journey_id)
        _, state, _ = self.start()
        payload = asdict(state)
        payload["plan_path"] = "../outside.md"
        payload["plan_digest"] = "a" * 64
        with self.assertRaisesRegex(LAZY_STATE.LazyStateError, "confined"):
            LAZY_STATE.LazyState.from_mapping(payload)
        payload = asdict(state)
        payload["origin_project_root"] = "relative/root"
        with self.assertRaisesRegex(LAZY_STATE.LazyStateError, "absolute"):
            LAZY_STATE.LazyState.from_mapping(payload)

    def test_symlinked_runtime_directory_cannot_escape_repository(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside"
        outside.mkdir()
        self.addCleanup(outside.rmdir)
        runs = self.root / ".phasemill"
        runs.mkdir()
        (runs / "runs").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(LAZY_STATE.LazyStateError, "escapes project root"):
            self.start()

    def test_stale_updates_and_per_journey_lock_are_explicit(self) -> None:
        store, state, _ = self.start()
        updated = store.update(state.revision, phase="design")
        self.assertEqual(1, updated.revision)
        with self.assertRaisesRegex(LAZY_STATE.LazyStateConflictError, "stale"):
            store.update(state.revision, phase="plan")
        with LAZY_STATE._exclusive_lock(store.paths.lock):
            with self.assertRaisesRegex(LAZY_STATE.LazyStateConflictError, "locked"):
                store.load()
        self.assertEqual(updated, store.load())

    def test_concurrent_creation_converges_on_one_journey(self) -> None:
        results: list[tuple[str, bool]] = []
        errors: list[Exception] = []
        barrier = threading.Barrier(3)

        def create() -> None:
            barrier.wait()
            for _ in range(50):
                try:
                    _, state, created = self.start()
                    results.append((state.journey_id, created))
                    return
                except LAZY_STATE.LazyStateConflictError:
                    time.sleep(0.002)
            errors.append(RuntimeError("creation lock did not become available"))

        threads = [threading.Thread(target=create) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual([], errors)
        self.assertEqual(2, len(results))
        self.assertEqual(1, len({journey_id for journey_id, _ in results}))
        self.assertEqual(1, sum(created for _, created in results))

    def test_active_and_recent_discovery_are_sorted(self) -> None:
        first_store, first, _ = self.start("first")
        _, second, _ = self.start("second")
        completed = first_store.update(first.revision, phase="done", status="completed")
        active = LAZY_STATE.discover_journeys(self.root, active_only=True)
        recent = LAZY_STATE.discover_journeys(self.root, limit=1)
        self.assertEqual([second.journey_id], [state.journey_id for state in active])
        self.assertIn(recent[0].journey_id, {second.journey_id, completed.journey_id})

    def test_malformed_state_is_rejected_and_lock_is_released(self) -> None:
        store, _, _ = self.start()
        store.paths.state.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(LAZY_STATE.LazyStateError, "cannot read"):
            store.load()
        with self.assertRaisesRegex(LAZY_STATE.LazyStateError, "cannot read"):
            store.load()

    def test_replace_failure_preserves_last_valid_json_and_cleans_temporary_file(self) -> None:
        store, state, _ = self.start()
        before = store.paths.state.read_text(encoding="utf-8")
        with mock.patch.object(LAZY_STATE.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaisesRegex(LAZY_STATE.LazyStateIOError, "replace failed"):
                store.update(state.revision, phase="design")
        self.assertEqual(before, store.paths.state.read_text(encoding="utf-8"))
        self.assertEqual([], list(store.paths.directory.glob(f".{store.paths.state.name}.*")))
        updated = store.update(state.revision, phase="design")
        self.assertEqual(1, updated.revision)
        self.assert_mode(store.paths.state, 0o600)

    def test_fsync_failure_is_recoverable_and_releases_lock(self) -> None:
        store, state, _ = self.start()
        before = store.paths.state.read_text(encoding="utf-8")
        with mock.patch.object(LAZY_STATE.os, "fsync", side_effect=OSError("fsync failed")):
            with self.assertRaisesRegex(LAZY_STATE.LazyStateIOError, "fsync failed"):
                store.update(state.revision, phase="design")
        self.assertEqual(before, store.paths.state.read_text(encoding="utf-8"))
        self.assertEqual(state, store.load())
        self.assertEqual([], list(store.paths.directory.glob(f".{store.paths.state.name}.*")))

    def test_progress_append_is_atomic_idempotent_and_mode_safe(self) -> None:
        store, _, _ = self.start()
        before = store.paths.progress.read_text(encoding="utf-8")
        with mock.patch.object(LAZY_STATE.os, "replace", side_effect=OSError("append failed")):
            with self.assertRaisesRegex(LAZY_STATE.LazyStateIOError, "append failed"):
                store.append_progress("Discovery complete", event_id="discovery-1")
        self.assertEqual(before, store.paths.progress.read_text(encoding="utf-8"))
        self.assertEqual([], list(store.paths.directory.glob(f".{store.paths.progress.name}.*")))
        self.assertTrue(store.append_progress("Discovery complete", event_id="discovery-1"))
        self.assertFalse(store.append_progress("Discovery complete", event_id="discovery-1"))
        progress = store.paths.progress.read_text(encoding="utf-8")
        self.assertEqual(1, progress.count("Discovery complete"))
        self.assert_mode(store.paths.progress, 0o600)


if __name__ == "__main__":
    unittest.main()
