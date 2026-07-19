#!/usr/bin/env python3
"""Contracts for the Codex-native skill-eval UserPromptSubmit hook."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins/phasemill"
MANIFEST = PLUGIN / ".codex-plugin/plugin.json"
HOOKS = PLUGIN / "hooks/hooks.json"
SCRIPT = PLUGIN / "hooks/skill-eval.py"
RUNTIME_CONTEXT = PLUGIN / "hooks/runtime-context.py"


def invoke(raw: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT)],
        input=raw,
        text=True,
        capture_output=True,
        check=False,
    )


def invoke_runtime(raw: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(RUNTIME_CONTEXT)],
        input=raw,
        text=True,
        capture_output=True,
        check=False,
    )


class CodexSkillEvalTests(unittest.TestCase):
    def test_default_plugin_hook_tree_is_self_contained(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertNotIn("hooks", manifest)
        hooks = json.loads(HOOKS.read_text(encoding="utf-8"))
        handler = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        self.assertEqual("command", handler["type"])
        self.assertIn("${PLUGIN_ROOT}/hooks/skill-eval.py", handler["command"])
        self.assertNotIn("CLAUDE_PLUGIN_ROOT", handler["command"])
        self.assertEqual(10, handler["timeout"])
        session_handler = hooks["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertIn("${PLUGIN_ROOT}/hooks/runtime-context.py", session_handler["command"])
        self.assertEqual("startup|resume|compact", hooks["hooks"]["SessionStart"][0]["matcher"])

    def test_valid_prompt_adds_skill_context_without_echoing_prompt(self) -> None:
        secret_prompt = "implement feature with token super-secret-value"
        event = {
            "session_id": "session",
            "turn_id": "turn",
            "cwd": "/repo",
            "hook_event_name": "UserPromptSubmit",
            "model": "gpt-test",
            "permission_mode": "default",
            "prompt": secret_prompt,
        }
        result = invoke(json.dumps(event))
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["continue"])
        output = payload["hookSpecificOutput"]
        self.assertEqual("UserPromptSubmit", output["hookEventName"])
        context = output["additionalContext"]
        self.assertIn("minimal relevant set", context)
        self.assertIn("SKILL.md", context)
        self.assertIn("Do not delegate", context)
        self.assertIn("`run` owns automatic learning", context)
        self.assertIn("Do not select `phasemill:learn` merely because", context)
        self.assertIn("only when the user explicitly asks", context)
        self.assertIn("never start background learning", context)
        self.assertNotIn(secret_prompt, result.stdout)
        self.assertNotIn("super-secret-value", result.stdout)

    def test_non_target_event_is_ignored(self) -> None:
        result = invoke(json.dumps({"hook_event_name": "Stop", "prompt": "ignored"}))
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout)

    def test_schema_errors_are_visible_but_do_not_block_prompt(self) -> None:
        for raw, message in (
            ("not-json", "invalid JSON"),
            ("[]", "non-object event"),
            (json.dumps({"hook_event_name": "UserPromptSubmit"}), "missing string field: prompt"),
        ):
            with self.subTest(raw=raw):
                result = invoke(raw)
                self.assertEqual(0, result.returncode)
                payload = json.loads(result.stdout)
                self.assertTrue(payload["continue"])
                self.assertIn(message, payload["systemMessage"])
                self.assertNotIn("hookSpecificOutput", payload)

    def test_session_start_injects_only_active_durable_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / ".phasemill/runs"
            runs.mkdir(parents=True)
            (runs / "state-active.json").write_text(
                json.dumps(
                    {
                        "status": "running",
                        "plan_path": "docs/plans/change.md",
                        "phase": "review",
                        "revision": 3,
                        "run_id": "run-active",
                    }
                ),
                encoding="utf-8",
            )
            (runs / "state-done.json").write_text(
                json.dumps({"status": "completed", "run_id": "run-done"}),
                encoding="utf-8",
            )
            result = invoke_runtime(
                json.dumps({"hook_event_name": "SessionStart", "cwd": str(root)})
            )
            self.assertEqual(0, result.returncode, result.stderr)
            payload = json.loads(result.stdout)
            context = payload["hookSpecificOutput"]["additionalContext"]
            self.assertIn("run-active", context)
            self.assertIn("mcp__phasemill__run_status", context)
            self.assertNotIn("run-done", context)

    def test_session_start_without_active_state_is_silent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = invoke_runtime(
                json.dumps({"hook_event_name": "SessionStart", "cwd": directory})
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout)

    def test_session_start_labels_waiting_lazy_and_linked_run_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / ".phasemill/runs"
            lazy = runs / "lazy-journey-active"
            lazy.mkdir(parents=True)
            (lazy / "state.json").write_text(
                json.dumps(
                    {
                        "status": "waiting-input",
                        "journey_id": "journey-active",
                        "phase": "handoff",
                        "revision": 7,
                        "plan_path": "docs/plans/lazy.md",
                        "linked_run_id": "run-linked",
                    }
                ),
                encoding="utf-8",
            )
            (runs / "state-linked.json").write_text(
                json.dumps(
                    {
                        "status": "running",
                        "plan_path": "docs/plans/lazy.md",
                        "phase": "review",
                        "revision": 4,
                        "run_id": "run-linked",
                    }
                ),
                encoding="utf-8",
            )
            result = invoke_runtime(
                json.dumps({"hook_event_name": "SessionStart", "cwd": str(root)})
            )
            self.assertEqual(0, result.returncode, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("Lazy journeys:", context)
            self.assertIn("status=waiting-input", context)
            self.assertIn("journey=journey-active", context)
            self.assertIn("linked_run=run-linked", context)
            self.assertIn("Implementation runs:", context)
            self.assertIn("run=run-linked", context)
            self.assertIn("advisory only", context)
            self.assertIn("never advances or repairs", context)

    def test_session_start_from_registered_worktree_reads_origin_lazy_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Hook Test"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "hook@example.invalid"], cwd=root, check=True)
            (root / "README.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root, check=True)
            worktree = Path(directory) / "execution"
            subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "lazy-execution", str(worktree)],
                cwd=root,
                check=True,
            )
            lazy = root / ".phasemill/runs/lazy-origin-active"
            lazy.mkdir(parents=True)
            (lazy / "state.json").write_text(
                json.dumps(
                    {
                        "status": "running",
                        "journey_id": "origin-active",
                        "phase": "plan",
                        "revision": 4,
                        "plan_path": "docs/plans/lazy.md",
                        "linked_run_id": "",
                    }
                ),
                encoding="utf-8",
            )
            result = invoke_runtime(
                json.dumps({"hook_event_name": "SessionStart", "cwd": str(worktree)})
            )
            self.assertEqual(0, result.returncode, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("journey=origin-active", context)

    def test_session_start_tolerates_corrupted_lazy_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / ".phasemill/runs"
            corrupt = runs / "lazy-corrupt"
            valid = runs / "lazy-valid"
            corrupt.mkdir(parents=True)
            valid.mkdir(parents=True)
            (corrupt / "state.json").write_text("{broken", encoding="utf-8")
            (valid / "state.json").write_text(
                json.dumps(
                    {
                        "status": "running",
                        "journey_id": "valid",
                        "phase": "design",
                        "revision": 1,
                        "plan_path": "",
                        "linked_run_id": "",
                    }
                ),
                encoding="utf-8",
            )
            result = invoke_runtime(
                json.dumps({"hook_event_name": "SessionStart", "cwd": str(root)})
            )
            self.assertEqual(0, result.returncode, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("journey=valid", context)
            self.assertNotIn("corrupt", context)

    def test_session_start_with_only_completed_or_corrupt_lazy_state_is_silent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / ".phasemill/runs"
            completed = runs / "lazy-completed"
            corrupt = runs / "lazy-corrupt"
            completed.mkdir(parents=True)
            corrupt.mkdir(parents=True)
            (completed / "state.json").write_text(
                json.dumps({"status": "completed", "journey_id": "done"}),
                encoding="utf-8",
            )
            (corrupt / "state.json").write_text("not json", encoding="utf-8")
            result = invoke_runtime(
                json.dumps({"hook_event_name": "SessionStart", "cwd": str(root)})
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout)

    def test_session_start_does_not_follow_state_symlinks_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            runs = root / ".phasemill/runs"
            runs.mkdir(parents=True)
            external = Path(outside) / "state.json"
            external.write_text(
                json.dumps(
                    {
                        "status": "running",
                        "journey_id": "outside-secret",
                        "phase": "design",
                    }
                ),
                encoding="utf-8",
            )
            link = runs / "lazy-escape"
            try:
                link.symlink_to(Path(outside), target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks are unavailable")
            result = invoke_runtime(
                json.dumps({"hook_event_name": "SessionStart", "cwd": str(root)})
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout)
            self.assertNotIn("outside-secret", result.stdout)

    def test_session_start_does_not_follow_symlinked_runs_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            phasemill = root / ".phasemill"
            phasemill.mkdir()
            external_runs = Path(outside) / "runs"
            lazy = external_runs / "lazy-escape"
            lazy.mkdir(parents=True)
            (lazy / "state.json").write_text(
                json.dumps(
                    {"status": "running", "journey_id": "outside-secret", "phase": "design"}
                ),
                encoding="utf-8",
            )
            try:
                (phasemill / "runs").symlink_to(external_runs, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks are unavailable")
            result = invoke_runtime(
                json.dumps({"hook_event_name": "SessionStart", "cwd": str(root)})
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout)


if __name__ == "__main__":
    unittest.main()
