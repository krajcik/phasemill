#!/usr/bin/env python3
"""Behavioral tests for the native Codex planning phase controller."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/phasemill/engine/phase_controller.py"
SPEC = importlib.util.spec_from_file_location("phase_controller", SCRIPT)
assert SPEC and SPEC.loader
CONTROLLER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CONTROLLER
SPEC.loader.exec_module(CONTROLLER)


PLAN = """# Controller plan

### Task 1: First

- [ ] first item

### Task 2: Second

- [ ] second item
"""


class PhaseControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.user = self.root / "user"
        self.user.mkdir()
        self.plan = self.root / "docs/plans/controller.md"
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text(PLAN, encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def controller(self, *overrides: str):
        effective = CONTROLLER.PLANNING_CONFIG.load_effective(
            project_root=self.root,
            plugin_data=self.user,
            overrides=list(overrides),
        )
        store = CONTROLLER.PLAN_STATE.RunStateStore(self.root, self.plan)
        return CONTROLLER.PhaseController(store, effective, default_branch="main")

    def start(self, *overrides: str):
        controller = self.controller(*overrides)
        controller.store.initialize()
        return controller, controller.next_action()

    def check(self, text: str) -> None:
        self.plan.write_text(
            self.plan.read_text(encoding="utf-8").replace(f"- [ ] {text}", f"- [x] {text}"),
            encoding="utf-8",
        )

    def result(self, outcome: str, **kwargs):
        return CONTROLLER.PhaseResult(outcome=outcome, **kwargs)

    def complete_tasks(self, controller, action):
        self.check("first item")
        action = controller.record_result(action.action_id, self.result("completed"))
        self.assertEqual("task", action.kind)
        self.assertEqual("2", action.task["identifier"])
        self.check("second item")
        return controller.record_result(action.action_id, self.result("completed"))

    def reach_external(self, controller, action):
        action = self.complete_tasks(controller, action)
        self.assertEqual("review-first", action.phase)
        action = controller.record_result(action.action_id, self.result("findings", summary="fixed"))
        self.assertEqual("review", action.phase)
        return controller.record_result(action.action_id, self.result("clean"))

    def test_happy_pipeline_emits_native_actions_and_finishes_without_finalize(self) -> None:
        controller, action = self.start()
        self.assertEqual("task", action.kind)
        self.assertEqual("implementer", action.agent.name)
        self.assertEqual("gpt-5.6-sol", action.agent.model)
        self.assertEqual("medium", action.agent.model_reasoning_effort)
        self.assertEqual(
            {"cross-module", "mechanical"},
            set(action.agent_options),
        )
        self.assertEqual(action, controller.next_action(), "next action must be idempotent")
        self.assertNotIn("{{", action.prompt)
        self.assertIn(str(self.plan), action.prompt)
        self.assertIn(str(controller.store.paths.progress), action.prompt)

        action = self.reach_external(controller, action)
        self.assertEqual("external-review", action.kind)
        self.assertEqual(900, action.external["timeout_seconds"])
        self.assertEqual(120, action.external["idle_timeout_seconds"])
        action = controller.record_result(action.action_id, self.result("clean"))
        self.assertEqual("learning", action.kind)
        self.assertEqual("learning", action.prompt_name)
        self.assertIn("Proposal-only project learning", action.prompt)
        self.assertIn(str(controller.store.paths.progress), action.prompt)
        action = controller.record_result(action.action_id, self.result("clean"))
        self.assertEqual("done", action.kind)
        self.assertEqual("completed", controller.store.load().status)

    def test_stale_action_and_invalid_outcome_do_not_mutate_state(self) -> None:
        controller, action = self.start()
        revision = controller.store.load().revision
        with self.assertRaisesRegex(CONTROLLER.PhaseControllerError, "does not accept"):
            controller.record_result(action.action_id, self.result("clean"))
        self.assertEqual(revision, controller.store.load().revision)
        self.check("first item")
        next_action = controller.record_result(action.action_id, self.result("completed"))
        with self.assertRaisesRegex(CONTROLLER.PLAN_STATE.StateConflictError, "stale"):
            controller.record_result(action.action_id, self.result("completed"))
        self.assertNotEqual(action.action_id, next_action.action_id)

    def test_task_retry_then_failure_obeys_config(self) -> None:
        controller, action = self.start("execution.task_retries=1")
        action = controller.record_result(action.action_id, self.result("failed"))
        self.assertEqual("task", action.kind)
        self.assertEqual(2, action.iteration)
        self.assertEqual("recovery-implementer", action.agent.name)
        self.assertEqual("xhigh", action.agent.model_reasoning_effort)
        self.assertEqual({}, action.agent_options)
        action = controller.record_result(action.action_id, self.result("failed"))
        self.assertEqual("failed", action.kind)
        self.assertIn("configured retries", action.reason)

    def test_task_timeout_stops_at_max_iterations(self) -> None:
        controller, action = self.start("execution.max_task_iterations=1")
        action = controller.record_result(action.action_id, self.result("timed-out"))
        self.assertEqual("failed", action.kind)
        self.assertIn("max task iterations", action.reason)

    def test_full_controller_rejects_plan_without_task_sections(self) -> None:
        self.plan.write_text("# Malformed\n- [ ] unscoped work\n", encoding="utf-8")
        controller, action = self.start()
        self.assertEqual("failed", action.kind)
        self.assertIn("no executable sections", action.reason)

    def test_review_no_change_short_circuits_to_external(self) -> None:
        controller, action = self.start()
        action = self.complete_tasks(controller, action)
        action = controller.record_result(action.action_id, self.result("findings"))
        action = controller.record_result(
            action.action_id,
            self.result(
                "findings",
                head_before="abc",
                head_after="abc",
                diff_before="same",
                diff_after="same",
            ),
        )
        self.assertEqual("external-review", action.kind)

    def test_clean_first_review_skips_focused_review(self) -> None:
        controller, action = self.start()
        action = self.complete_tasks(controller, action)

        action = controller.record_result(action.action_id, self.result("clean"))

        self.assertEqual("external-review", action.kind)
        self.assertEqual("external-review", action.phase)

    def test_first_review_findings_require_focused_review(self) -> None:
        controller, action = self.start()
        action = self.complete_tasks(controller, action)

        action = controller.record_result(action.action_id, self.result("findings"))

        self.assertEqual("review", action.kind)
        self.assertEqual("review", action.phase)
        self.assertEqual("review-second", action.prompt_name)

    def test_external_patience_runs_post_review_after_unchanged_findings(self) -> None:
        controller, action = self.start("review.patience=2")
        action = self.reach_external(controller, action)
        unchanged = self.result(
            "findings",
            head_before="abc",
            head_after="abc",
            diff_before="same",
            diff_after="same",
        )
        action = controller.record_result(action.action_id, unchanged)
        self.assertEqual("external-review", action.phase)
        action = controller.record_result(action.action_id, unchanged)
        self.assertEqual("post-review", action.phase)
        self.assertEqual("review", action.kind)
        action = controller.record_result(action.action_id, self.result("clean"))
        self.assertEqual("learning", action.kind)
        action = controller.record_result(action.action_id, self.result("clean"))
        self.assertEqual("done", action.kind)

    def test_optional_external_skip_completes_but_required_skip_fails(self) -> None:
        controller, action = self.start()
        action = self.reach_external(controller, action)
        action = controller.record_result(action.action_id, self.result("skipped"))
        self.assertEqual("learning", action.kind)
        action = controller.record_result(action.action_id, self.result("clean"))
        self.assertEqual("done", action.kind)

        self.plan.write_text(PLAN, encoding="utf-8")
        required, action = self.start("review.external.required=true")
        action = self.reach_external(required, action)
        action = required.record_result(action.action_id, self.result("skipped"))
        self.assertEqual("failed", action.kind)
        self.assertIn("required external review", action.reason)

    def test_external_disabled_and_finalize_enabled_emit_finalize_action(self) -> None:
        controller, action = self.start(
            'review.external.backend="none"',
            "finalize.enabled=true",
        )
        action = self.complete_tasks(controller, action)
        action = controller.record_result(action.action_id, self.result("clean"))
        self.assertEqual("finalize", action.kind)
        action = controller.record_result(action.action_id, self.result("completed"))
        self.assertEqual("learning", action.kind)
        action = controller.record_result(action.action_id, self.result("completed", summary="candidate 1"))
        self.assertEqual("done", action.kind)
        self.assertIn(
            "learning result: completed\ncandidate 1",
            controller.store.paths.progress.read_text(encoding="utf-8"),
        )

    def test_learning_failure_is_advisory_and_can_be_disabled(self) -> None:
        controller, action = self.start('review.external.backend="none"')
        action = self.complete_tasks(controller, action)
        action = controller.record_result(action.action_id, self.result("clean"))
        self.assertEqual("learning", action.kind)
        action = controller.record_result(action.action_id, self.result("failed", summary="unavailable"))
        self.assertEqual("done", action.kind)
        self.assertEqual("completed", controller.store.load().status)

        self.plan.write_text(PLAN, encoding="utf-8")
        disabled, action = self.start(
            'review.external.backend="none"',
            "learning.auto_propose=false",
        )
        action = self.complete_tasks(disabled, action)
        action = disabled.record_result(action.action_id, self.result("clean"))
        self.assertEqual("done", action.kind)

    def test_review_action_contains_configured_roles_and_project_guidance(self) -> None:
        custom = self.root / ".codex/phasemill"
        (custom / "agents").mkdir(parents=True)
        (custom / "rules").mkdir()
        (custom / "agents/domain.md").write_text("Review the domain invariant.\n", encoding="utf-8")
        (custom / "rules/review.md").write_text("Check project-only review rule.\n", encoding="utf-8")
        (custom / "config.toml").write_text(
            '[review]\nagents = ["quality", "domain"]\n',
            encoding="utf-8",
        )
        self.plan.write_text(self.plan.read_text(encoding="utf-8").replace("[ ]", "[x]"), encoding="utf-8")
        controller, action = self.start()
        self.assertEqual(["quality", "domain"], [role.name for role in action.roles])
        self.assertEqual("review-quality", action.roles[0].agent.name)
        self.assertEqual("gpt-5.6-sol", action.roles[0].agent.model)
        self.assertEqual("reviewer", action.roles[1].agent.name)
        self.assertIn("project-only review rule", action.prompt)

    def test_review_role_can_override_native_model_and_reasoning(self) -> None:
        custom = self.root / ".codex/phasemill"
        custom.mkdir(parents=True)
        (custom / "config.toml").write_text(
            '[review]\nagents = ["quality"]\n'
            '[agents.review-quality]\nmodel = "gpt-5.6-luna"\nmodel_reasoning_effort = "low"\n',
            encoding="utf-8",
        )
        self.plan.write_text(self.plan.read_text(encoding="utf-8").replace("[ ]", "[x]"), encoding="utf-8")

        _, action = self.start()

        self.assertEqual("gpt-5.6-luna", action.roles[0].agent.model)
        self.assertEqual("low", action.roles[0].agent.model_reasoning_effort)

    def test_project_review_role_can_select_its_own_native_profile(self) -> None:
        custom = self.root / ".codex/phasemill"
        (custom / "agents").mkdir(parents=True)
        (custom / "agents/domain.md").write_text("Review the domain invariant.\n", encoding="utf-8")
        (custom / "config.toml").write_text(
            '[review]\nagents = ["domain"]\nagent_profiles = { domain = "domain-review" }\n'
            '[agents.domain-review]\nmodel = "gpt-5.6-luna"\nmodel_reasoning_effort = "medium"\n',
            encoding="utf-8",
        )
        self.plan.write_text(self.plan.read_text(encoding="utf-8").replace("[ ]", "[x]"), encoding="utf-8")

        _, action = self.start()

        self.assertEqual("domain", action.roles[0].name)
        self.assertEqual("domain-review", action.roles[0].agent.name)
        self.assertEqual("gpt-5.6-luna", action.roles[0].agent.model)
        self.assertEqual("medium", action.roles[0].agent.model_reasoning_effort)

    def test_cli_start_returns_json_action(self) -> None:
        completed = self.plan.read_text(encoding="utf-8").replace("[ ]", "[x]")
        self.plan.write_text(completed, encoding="utf-8")
        run = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--project-root",
                str(self.root),
                "--plugin-data",
                str(self.user),
                "--default-branch",
                "main",
                "start",
                str(self.plan),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, run.returncode, run.stderr)
        payload = json.loads(run.stdout)
        self.assertEqual("review", payload["kind"])
        self.assertEqual("review-first", payload["phase"])
        self.assertEqual("gpt-5.6-sol", payload["roles"][0]["agent"]["model"])
        self.assertEqual("high", payload["roles"][0]["agent"]["model_reasoning_effort"])

    def test_cli_record_accepts_result_file(self) -> None:
        controller, action = self.start()
        self.check("first item")
        result_file = self.root / "task-result.json"
        result_file.write_text(
            json.dumps({"outcome": "completed", "summary": "long learning-style result"}),
            encoding="utf-8",
        )
        run = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--project-root",
                str(self.root),
                "--plugin-data",
                str(self.user),
                "--default-branch",
                "main",
                "record",
                str(self.plan),
                "--action-id",
                action.action_id,
                "--result-file",
                str(result_file),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual("task", json.loads(run.stdout)["kind"])

    def test_cli_record_without_input_fails_instead_of_waiting(self) -> None:
        _, action = self.start()
        process = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "--project-root",
                str(self.root),
                "--plugin-data",
                str(self.user),
                "--default-branch",
                "main",
                "record",
                str(self.plan),
                "--action-id",
                action.action_id,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        process.wait(timeout=3)
        stdout, stderr = process.communicate()
        self.assertEqual("", stdout)
        self.assertEqual(2, process.returncode)
        self.assertIn("record input was not received within 1s", stderr)


if __name__ == "__main__":
    unittest.main()
