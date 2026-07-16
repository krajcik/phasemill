#!/usr/bin/env python3
"""Behavioral tests for the Codex planning configuration loader."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO / "plugins/phasemill/engine/config.py"
SPEC = importlib.util.spec_from_file_location("planning_config", CONFIG_PATH)
assert SPEC and SPEC.loader
CONFIG = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CONFIG
SPEC.loader.exec_module(CONFIG)


class PlanningConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.project = self.root / "project"
        self.user = self.root / "user"
        self.project.mkdir()
        self.user.mkdir()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @property
    def custom(self) -> Path:
        return self.project / ".codex/phasemill"

    def write(self, path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def load(self, **kwargs):
        return CONFIG.load_effective(project_root=self.project, plugin_data=self.user, **kwargs)

    def test_per_field_precedence_preserves_false_zero_and_empty_list(self) -> None:
        self.write(
            self.user / "config.toml",
            "[execution]\ntask_retries = 4\n[finalize]\nenabled = true\n"
            "[review]\ndisabled_agents = [\"documentation\"]\n",
        )
        self.write(
            self.custom / "config.toml",
            "[execution]\ntask_retries = 0\n[finalize]\nenabled = false\n"
            "[review]\ndisabled_agents = []\n",
        )
        config = self.load(overrides=["execution.max_task_iterations=7"])
        self.assertEqual(0, config.values["execution"]["task_retries"])
        self.assertEqual(7, config.values["execution"]["max_task_iterations"])
        self.assertFalse(config.values["finalize"]["enabled"])
        self.assertEqual([], config.values["review"]["disabled_agents"])
        self.assertTrue(config.origins["execution.task_retries"].startswith("project:"))
        self.assertEqual("invocation", config.origins["execution.max_task_iterations"])

    def test_invocation_is_highest_precedence(self) -> None:
        self.write(self.custom / "config.toml", "[execution]\ntask_retries = 2\n")
        config = self.load(overrides=["execution.task_retries=0"])
        self.assertEqual(0, config.values["execution"]["task_retries"])
        self.assertEqual("invocation", config.origins["execution.task_retries"])

    def test_prompt_is_replaced_as_a_complete_file(self) -> None:
        self.write(self.user / "prompts/task.md", "user task body\n")
        self.write(self.custom / "prompts/task.md", "project task body\n")
        config = self.load()
        self.assertEqual("project", config.prompts["task"].source)
        self.assertEqual("project task body\n", config.prompts["task"].content)
        self.assertNotIn("user task body", config.prompts["task"].content)

    def test_comment_only_prompt_falls_through_to_user_then_embedded(self) -> None:
        self.write(self.custom / "prompts/task.md", "# untouched project example\n")
        self.write(self.user / "prompts/task.md", "user replacement\n")
        self.assertEqual("user", self.load().prompts["task"].source)
        self.write(self.user / "prompts/task.md", "# untouched user example\n")
        self.assertEqual("embedded", self.load().prompts["task"].source)

    def test_custom_agent_can_be_selected_and_embedded_agent_can_be_disabled(self) -> None:
        self.write(self.custom / "agents/domain.md", "Review the domain invariant.\n")
        self.write(
            self.custom / "config.toml",
            "[review]\nagents = [\"quality\", \"domain\"]\n"
            "disabled_agents = [\"quality\"]\n",
        )
        config = self.load()
        self.assertEqual(("domain",), config.selected_agents)
        self.assertEqual("project", config.agents["domain"].source)

    def test_native_agent_defaults_use_sol_luna_and_keep_terra_disabled(self) -> None:
        config = self.load()

        self.assertEqual(
            {"model": "gpt-5.6-sol", "model_reasoning_effort": "medium"},
            config.values["agents"]["planner"],
        )
        self.assertEqual("medium", config.values["agents"]["implementer"]["model_reasoning_effort"])
        self.assertEqual("high", config.values["agents"]["cross-module-implementer"]["model_reasoning_effort"])
        self.assertEqual("xhigh", config.values["agents"]["recovery-implementer"]["model_reasoning_effort"])
        self.assertEqual("high", config.values["agents"]["review-quality"]["model_reasoning_effort"])
        self.assertEqual("gpt-5.6-luna", config.values["agents"]["explorer"]["model"])
        self.assertEqual(
            {"model": "gpt-5.6-sol", "model_reasoning_effort": "low"},
            config.values["agents"]["mechanical"],
        )
        self.assertFalse(config.values["agents"]["terra"]["enabled"])

    def test_project_can_override_each_role_model_and_reasoning(self) -> None:
        self.write(
            self.custom / "config.toml",
            "[agents.review-quality]\n"
            'model = "gpt-5.6-luna"\n'
            'model_reasoning_effort = "low"\n',
        )

        config = self.load()

        self.assertEqual("gpt-5.6-luna", config.values["agents"]["review-quality"]["model"])
        self.assertEqual("low", config.values["agents"]["review-quality"]["model_reasoning_effort"])
        self.assertTrue(config.origins["agents.review-quality.model"].startswith("project:"))

    def test_disabled_terra_requires_explicit_enable_before_routing(self) -> None:
        self.write(
            self.custom / "config.toml",
            '[execution]\nimplementer_agent = "terra"\n',
        )
        with self.assertRaisesRegex(CONFIG.ConfigError, "is disabled"):
            self.load()

        self.write(
            self.custom / "config.toml",
            '[execution]\nimplementer_agent = "terra"\n'
            "[agents.terra]\nenabled = true\n",
        )
        config = self.load()
        self.assertEqual("terra", config.values["execution"]["implementer_agent"])

    def test_invalid_native_agent_reasoning_and_unknown_profile_are_errors(self) -> None:
        cases = (
            ('[agents.implementer]\nmodel_reasoning_effort = "huge"\n', "expected one of"),
            ('[execution]\nimplementer_agent = "missing"\n', "unknown native agent profile"),
            ('[agents.planner]\nenabled = false\n', "is disabled"),
        )
        for body, message in cases:
            with self.subTest(body=body):
                self.write(self.custom / "config.toml", body)
                with self.assertRaisesRegex(CONFIG.ConfigError, message):
                    self.load()

    def test_rules_profiles_and_nested_agents_compose_low_to_high(self) -> None:
        self.write(self.project / "go.mod", "module example.test/project\n")
        self.write(self.project / "AGENTS.md", "Root project instructions.\n")
        self.write(self.project / "internal/AGENTS.md", "Internal instructions.\n")
        self.write(self.user / "profiles/go.md", "User Go profile.\n")
        self.write(self.custom / "profiles/go.md", "Project Go profile.\n")
        self.write(self.user / "rules/review.md", "User review rule.\n")
        self.write(self.custom / "rules/review.md", "Project review rule.\n")
        config = self.load(touched_files=["internal/store/store.go"])
        self.assertEqual(["go"], list(config.profiles))
        self.assertEqual(
            [
                "profile:embedded",
                "profile:user",
                "profile:project",
                "rule:user",
                "rule:project",
                "AGENTS.md",
                "AGENTS.md",
            ],
            [fragment.source for fragment in config.rules],
        )
        self.assertEqual(
            ["AGENTS.md", "AGENTS.md"],
            [fragment.path.name for fragment in config.rules[-2:]],
        )

    def test_touched_file_narrows_polyglot_marker_detection(self) -> None:
        self.write(self.project / "go.mod", "module example.test/project\n")
        self.write(self.project / "package.json", "{}\n")
        config = self.load(touched_files=["tools/check.py"])
        self.assertEqual(["python"], list(config.profiles))
        self.assertEqual(("tools/check.py",), config.profiles["python"].detected_from)

    def test_php_profile_uses_touched_files_and_composer_marker(self) -> None:
        self.write(self.project / "composer.json", "{}\n")
        self.write(self.project / "package.json", "{}\n")

        php_config = self.load(touched_files=["src/Service.php"])
        self.assertEqual(["php"], list(php_config.profiles))
        self.assertEqual(("src/Service.php",), php_config.profiles["php"].detected_from)
        php_guidance = "\n".join(
            fragment.content for fragment in php_config.profiles["php"].fragments
        )
        self.assertIn("numeric-string coercion", php_guidance)
        self.assertIn("composer.lock", php_guidance)
        self.assertIn("named-argument compatibility", php_guidance)

        javascript_config = self.load(touched_files=["web/app.ts"])
        self.assertEqual(["javascript-typescript"], list(javascript_config.profiles))

        marker_config = self.load()
        self.assertEqual(["javascript-typescript", "php"], list(marker_config.profiles))

    def test_php_profile_is_not_selected_for_unrelated_project(self) -> None:
        self.write(self.project / "pyproject.toml", "[project]\nname = 'example'\n")
        config = self.load()
        self.assertEqual(["python"], list(config.profiles))
        python_guidance = "\n".join(
            fragment.content for fragment in config.profiles["python"].fragments
        )
        self.assertIn("raise ... from ...", python_guidance)
        self.assertIn("background-task ownership", python_guidance)
        self.assertIn("mutable argument and dataclass defaults", python_guidance)
        self.assertIn("unsafe YAML loading", python_guidance)
        self.assertNotIn("numeric-string coercion", python_guidance)

    def test_explicit_profile_enable_disable_wins_over_touched_files(self) -> None:
        self.write(
            self.custom / "config.toml",
            "[profiles]\nenable = [\"go\"]\ndisable = [\"javascript-typescript\"]\n",
        )
        config = self.load(touched_files=["web/app.ts"])
        self.assertEqual(["go"], list(config.profiles))

    def test_profile_enable_disable_conflict_is_an_error(self) -> None:
        self.write(
            self.custom / "config.toml",
            "[profiles]\nenable = [\"go\"]\ndisable = [\"go\"]\n",
        )
        with self.assertRaisesRegex(CONFIG.ConfigError, "both enabled and disabled"):
            self.load()

    def test_unknown_keys_and_agents_are_errors(self) -> None:
        self.write(self.custom / "config.toml", "[execution]\nmagic = 1\n")
        with self.assertRaisesRegex(CONFIG.ConfigError, "unknown configuration key"):
            self.load()
        self.write(self.custom / "config.toml", "[review]\nagents = [\"missing\"]\n")
        with self.assertRaisesRegex(CONFIG.ConfigError, "unknown review agents"):
            self.load()

    def test_invalid_duration_range_and_fixed_pi_contract_are_errors(self) -> None:
        cases = (
            ("[execution]\nsession_timeout = \"1 hour\"\n", "invalid duration"),
            ("[review]\nmax_iterations = 0\n", "must be >= 1"),
            ("[review.external]\nmodel = \"other/model\"\n", "must remain"),
            ("[review.external]\nthinking = \"xhigh\"\n", "must remain"),
            ("[review.external]\ndirect = false\n", "must remain"),
            ("[review.external]\nbackend = \"none\"\nrequired = true\n", "cannot be true"),
        )
        for body, message in cases:
            with self.subTest(body=body):
                self.write(self.custom / "config.toml", body)
                with self.assertRaisesRegex(CONFIG.ConfigError, message):
                    self.load()

    def test_malformed_toml_is_an_error(self) -> None:
        self.write(self.custom / "config.toml", "[review\nmax_iterations = 2\n")
        with self.assertRaisesRegex(CONFIG.ConfigError, "cannot read"):
            self.load()

    def test_missing_optional_directories_use_embedded_defaults(self) -> None:
        config = self.load()
        self.assertEqual("embedded", config.prompts["task"].source)
        self.assertEqual("embedded", config.agents["quality"].source)
        self.assertEqual(1, config.values["execution"]["task_retries"])
        self.assertEqual(1200, config.values["review"]["external"]["timeout_seconds"])
        self.assertEqual(120, config.values["review"]["external"]["idle_timeout_seconds"])
        self.assertFalse(config.values["review"]["external"]["data_sharing_approved"])

    def test_project_can_persist_external_review_data_sharing_consent(self) -> None:
        self.write(
            self.custom / "config.toml",
            "[review.external]\ndata_sharing_approved = true\n",
        )
        config = self.load()
        self.assertTrue(config.values["review"]["external"]["data_sharing_approved"])
        self.assertIn("project:", config.origins["review.external.data_sharing_approved"])
        self.assertTrue(config.values["learning"]["auto_propose"])
        self.assertEqual("embedded", config.prompts["learning"].source)

    def test_lazy_defaults_and_effective_sources_are_reported(self) -> None:
        config = self.load()
        self.assertEqual(2, config.values["lazy"]["max_plan_review_iterations"])
        self.assertEqual(
            ("implementation", "quality", "testing"),
            config.lazy_plan_review_agents,
        )
        payload = CONFIG.show_payload(config)
        self.assertEqual(
            ["implementation", "quality", "testing"],
            payload["lazy_plan_review_agents"],
        )
        self.assertTrue(config.origins["lazy.max_plan_review_iterations"].startswith("embedded:"))
        for prompt in (
            "lazy-discovery",
            "lazy-design",
            "lazy-plan",
            "lazy-plan-review",
            "lazy-plan-fix",
        ):
            self.assertEqual("embedded", config.prompts[prompt].source)

    def test_lazy_project_and_user_precedence_is_per_field(self) -> None:
        self.write(
            self.user / "config.toml",
            "[lazy]\nmax_plan_review_iterations = 4\n"
            'plan_review_agents = ["implementation", "quality"]\n',
        )
        self.write(
            self.custom / "config.toml",
            "[lazy]\nmax_plan_review_iterations = 3\n",
        )
        config = self.load()
        self.assertEqual(3, config.values["lazy"]["max_plan_review_iterations"])
        self.assertEqual(("implementation", "quality"), config.lazy_plan_review_agents)
        self.assertTrue(config.origins["lazy.max_plan_review_iterations"].startswith("project:"))
        self.assertTrue(config.origins["lazy.plan_review_agents"].startswith("user:"))

    def test_lazy_roles_reject_unknown_duplicate_and_unmapped_entries(self) -> None:
        cases = (
            ('[lazy]\nplan_review_agents = ["missing"]\n', "unknown lazy plan-review agents"),
            (
                '[lazy]\nplan_review_agents = ["quality", "quality"]\n',
                "duplicate entries",
            ),
        )
        for body, message in cases:
            with self.subTest(body=body):
                self.write(self.custom / "config.toml", body)
                with self.assertRaisesRegex(CONFIG.ConfigError, message):
                    self.load()
        self.write(self.custom / "agents/domain.md", "Review domain behavior.\n")
        self.write(self.custom / "config.toml", '[lazy]\nplan_review_agents = ["domain"]\n')
        with self.assertRaisesRegex(CONFIG.ConfigError, "no review.agent_profiles mapping"):
            self.load()

    def test_lazy_disabled_roles_are_filtered_but_result_must_not_be_empty(self) -> None:
        self.write(
            self.custom / "config.toml",
            '[review]\ndisabled_agents = ["quality"]\n'
            '[lazy]\nplan_review_agents = ["implementation", "quality"]\n',
        )
        self.assertEqual(("implementation",), self.load().lazy_plan_review_agents)
        self.write(
            self.custom / "config.toml",
            '[review]\ndisabled_agents = ["implementation", "quality"]\n'
            '[lazy]\nplan_review_agents = ["implementation", "quality"]\n',
        )
        with self.assertRaisesRegex(CONFIG.ConfigError, "all configured roles are disabled"):
            self.load()

    def test_lazy_iteration_bounds_and_required_packaged_prompts(self) -> None:
        for value in (0, 11):
            with self.subTest(value=value):
                self.write(
                    self.custom / "config.toml",
                    f"[lazy]\nmax_plan_review_iterations = {value}\n",
                )
                with self.assertRaisesRegex(CONFIG.ConfigError, "must be"):
                    self.load()
        copied_defaults = self.root / "defaults"
        (self.custom / "config.toml").unlink()
        shutil.copytree(REPO / "plugins/phasemill/defaults", copied_defaults)
        (copied_defaults / "prompts/lazy-plan.md").unlink()
        self.write(self.custom / "prompts/lazy-plan.md", "project replacement must not mask packaging\n")
        with self.assertRaisesRegex(CONFIG.ConfigError, "lazy-plan"):
            self.load(defaults_root=copied_defaults)

    def test_embedded_review_guidance_covers_wiring_smells_and_go_boundaries(self) -> None:
        self.write(self.project / "go.mod", "module example.test/project\n")
        config = self.load(touched_files=["internal/store/store.go"])
        go_guidance = "\n".join(fragment.content for fragment in config.profiles["go"].fragments)

        self.assertIn("Trace wiring end to end", config.agents["implementation"].content)
        self.assertIn("maintainability smells", config.agents["quality"].content)
        self.assertIn("rows.Err()", go_guidance)
        self.assertIn("typed nil interfaces", go_guidance)
        self.assertIn("accepted status codes", go_guidance)

    def test_external_review_idle_timeout_must_be_shorter_than_wall_timeout(self) -> None:
        self.write(
            self.custom / "config.toml",
            "[review.external]\ntimeout_seconds = 60\nidle_timeout_seconds = 60\n",
        )
        with self.assertRaisesRegex(CONFIG.ConfigError, "must be less than timeout_seconds"):
            self.load()

    def test_init_requires_confirmation_skips_existing_and_keeps_defaults_active(self) -> None:
        with self.assertRaisesRegex(CONFIG.ConfigError, "--yes"):
            CONFIG.init_project(self.project, confirmed=False)
        existing = self.write(self.custom / "rules/review.md", "keep me\n")
        created = CONFIG.init_project(self.project, confirmed=True)
        self.assertIn((self.custom / "config.toml").resolve(), created)
        self.assertIn((self.custom / "profiles/php.md").resolve(), created)
        self.assertIn((self.custom / "rules/brainstorm.md").resolve(), created)
        self.assertIn((self.custom / "rules/writing-style.md").resolve(), created)
        self.assertIn((self.custom / "prompts/learning.md").resolve(), created)
        self.assertEqual("keep me\n", existing.read_text(encoding="utf-8"))
        self.assertEqual("embedded", self.load().prompts["task"].source)
        self.assertEqual([], CONFIG.init_project(self.project, confirmed=True))

    def test_show_reports_origins_without_bodies_or_sensitive_values(self) -> None:
        self.write(self.custom / "rules/review.md", "private review wording\n")
        payload = CONFIG.show_payload(self.load())
        encoded = json.dumps(payload)
        self.assertIn("execution.task_retries", payload["origins"])
        self.assertNotIn("private review wording", encoded)
        self.assertEqual("<redacted>", CONFIG._redact({"api_token": "do-not-print"})["api_token"])

    def test_cli_json_show_and_validate(self) -> None:
        validate = subprocess.run(
            [sys.executable, str(CONFIG_PATH), "--project-root", str(self.project), "--plugin-data", str(self.user), "validate"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, validate.returncode, validate.stderr)
        show = subprocess.run(
            [
                sys.executable,
                str(CONFIG_PATH),
                "--project-root",
                str(self.project),
                "--plugin-data",
                str(self.user),
                "show",
                "--format",
                "json",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, show.returncode, show.stderr)
        self.assertEqual(1, json.loads(show.stdout)["values"]["execution"]["task_retries"])

    def test_touched_file_outside_root_is_rejected(self) -> None:
        with self.assertRaisesRegex(CONFIG.ConfigError, "outside project root"):
            self.load(touched_files=[self.root / "outside.py"])

    def test_init_rejects_a_missing_project_root(self) -> None:
        with self.assertRaisesRegex(CONFIG.ConfigError, "not a directory"):
            CONFIG.init_project(self.root / "missing", confirmed=True)


if __name__ == "__main__":
    unittest.main()
