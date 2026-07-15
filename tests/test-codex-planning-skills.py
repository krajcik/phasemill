#!/usr/bin/env python3
"""Static contracts for the native Codex planning skills."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO / "plugins/phasemill/skills"
MANIFEST = REPO / "plugins/phasemill/.codex-plugin/plugin.json"
SKILLS = {
    name: SKILL_ROOT / name / "SKILL.md"
    for name in ("plan", "plan-review", "run", "status")
}


def frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip()
    return values


class CodexPlanningSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = {name: path.read_text(encoding="utf-8") for name, path in SKILLS.items()}
        cls.normalized = {name: re.sub(r"\s+", " ", text) for name, text in cls.text.items()}
        cls.metadata = {name: frontmatter(text) for name, text in cls.text.items()}

    def test_manifest_exposes_all_native_skills(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual("./skills/", manifest.get("skills"))
        for name, path in SKILLS.items():
            self.assertTrue(path.is_file(), name)
            self.assertEqual(name, self.metadata[name].get("name"))
            self.assertTrue(self.metadata[name].get("description"), name)

    def test_make_uses_configured_prompt_and_executable_plan_shape(self) -> None:
        text = self.normalized["plan"]
        for phrase in (
            "prompts.make-plan.path",
            "values.plans.directory",
            "Present the complete draft in chat before writing it",
            "### Task N:",
            "phasemill:plan-review",
            "phasemill:run",
        ):
            self.assertIn(phrase, text)
        self.assertIn("does not implement", text)
        self.assertIn("Do not start execution", text)
        self.assertIn("`values.agents.planner`", text)
        self.assertIn("`gpt-5.6-sol` with `medium` reasoning", text)

    def test_config_invocation_order_and_repository_scope_are_explicit(self) -> None:
        for name in ("plan", "plan-review", "run"):
            text = self.normalized[name]
            with self.subTest(skill=name):
                self.assertIn("--project-root <repo>", text)
                self.assertIn("show --format json", text)
                self.assertIn("global options must precede the `show` subcommand", text.lower())
                self.assertIn("never search above the repository root", text.lower())
                self.assertIn("sibling repositories", text)
                self.assertIn("actual `PLUGIN_DATA`", text)
                self.assertIn("`.phasemill/` runtime", text)

    def test_exec_scopes_profiles_to_planned_change_paths(self) -> None:
        text = self.normalized["run"]
        self.assertIn("source, test, documentation, and configuration paths named by the plan", text)
        self.assertIn("Do not use the plan Markdown path as a substitute", text)

    def test_exec_keeps_runtime_outside_protected_config_and_git_diff(self) -> None:
        text = self.normalized["run"]
        self.assertIn("`.phasemill/runs/`", text)
        self.assertIn("outside Codex's protected `.codex/`", text)
        self.assertIn("`/.phasemill/runs/` is ignored", text)
        self.assertIn("Never include runtime files in implementation fingerprints", text)

    def test_review_is_repository_grounded_and_non_mutating_by_default(self) -> None:
        text = self.normalized["plan-review"]
        for phrase in (
            "launch-plan-review.sh",
            "native Codex read-only",
            "must-fix issues",
            "risky or suspicious areas",
            "missing tests",
            "optional improvements",
            "Do not edit the plan merely because review was requested",
        ):
            self.assertIn(phrase, text)
        self.assertIn("verifies every returned claim", text)

    def test_exec_is_driven_by_revision_bound_controller_actions(self) -> None:
        text = self.normalized["run"]
        for phrase in (
            "phase_controller.py",
            "native `update_plan`",
            "exact `action_id`",
            "Never edit the state or progress files directly",
            "Stop only at terminal `done` or `failed`",
            "kind=task",
            "kind=review",
            "kind=external-review",
            "kind=finalize",
            "kind=learning",
        ):
            self.assertIn(phrase, text)

    def test_learning_is_root_only_proposal_and_never_blocks_success(self) -> None:
        text = self.normalized["run"]
        for phrase in (
            "Do not delegate this action",
            "current conversation",
            "Do not edit `.codex/phasemill/`",
            "separate `phasemill:learn` interaction",
            "Learning is advisory",
            "Project scope is the default",
            "only when the user explicitly requested global learning",
            "Never infer the global directory",
        ):
            self.assertIn(phrase, text)

    def test_exec_bounds_native_fanout_and_keeps_reviewers_read_only(self) -> None:
        text = self.normalized["run"]
        self.assertIn("exactly one native implementation subagent", text)
        self.assertIn("bounded by `max_parallel_agents`", text)
        self.assertIn("Reviewers cannot edit files or spawn agents", text)
        self.assertIn("root task deduplicates and verifies every finding", text)

    def test_native_agents_preserve_per_role_model_and_reasoning(self) -> None:
        make = self.normalized["plan"]
        review = self.normalized["plan-review"]
        execute = self.normalized["run"]

        self.assertIn("inherited root model and reasoning", make)
        self.assertIn("future routing hints", make)
        self.assertIn("`values.review.agent_profiles`", review)
        self.assertIn("`values.review.fallback_agent`", review)
        self.assertIn("`action.agent.model`", execute)
        self.assertIn("`action.agent.model_reasoning_effort`", execute)
        self.assertIn("`agent_options`", execute)
        self.assertIn("must not be downgraded", execute)
        self.assertIn("Every returned role includes its future", execute)
        self.assertIn("must not be reported as the actual child runtime", make)
        self.assertIn("do not claim that distinct profile models ran", review.lower())
        self.assertIn("Do not claim that the hinted model ran", execute)

    def test_external_review_uses_only_the_packaged_security_boundary(self) -> None:
        text = self.normalized["run"]
        for phrase in (
            "`mcp__phasemill__external_review`",
            "pass the prompt through stdin",
            "direct without proxy",
            "`zai/glm-5.2` at `xhigh`",
            "`read,grep,find,ls`",
            "Do not call Pi directly",
            "`review.external.data_sharing_approved=true`",
            "durable prior authorization",
        ):
            self.assertIn(phrase, text)

    def test_git_and_worktree_mutations_are_not_implicit(self) -> None:
        text = self.normalized["run"]
        self.assertIn("`../../scripts/worktree.sh`", text)
        self.assertIn("call `worktree.sh plan` first", text)
        self.assertIn("before calling `worktree.sh prepare`", text)
        self.assertIn("Do not run raw `git worktree add`", text)
        self.assertIn("obtain explicit approval", text)
        self.assertIn("Never remove the worktree automatically", text)
        self.assertIn("`worktree.sh remove --yes`", text)
        self.assertIn("Do not commit, push, rebase", text)
        self.assertIn("without committing the move", text)
        self.assertIn("separate explicit user request", text)

    def test_claude_only_and_nested_cli_syntax_does_not_leak(self) -> None:
        combined = "\n".join(self.text.values())
        for forbidden in (
            "AskUserQuestion",
            "EnterPlanMode",
            "ExitPlanMode",
            "TaskCreate",
            "TaskUpdate",
            "CLAUDE_PLUGIN_ROOT",
            "CLAUDE_PLUGIN_DATA",
            'mode: "bypassPermissions"',
            "codex exec",
        ):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
