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


if __name__ == "__main__":
    unittest.main()
