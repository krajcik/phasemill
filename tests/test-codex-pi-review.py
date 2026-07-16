#!/usr/bin/env python3
"""Tests for the read-only Pi review subprocess adapter."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO / "plugins/phasemill/engine/pi_review.py"
SPEC = importlib.util.spec_from_file_location("pi_review", RUNNER_PATH)
assert SPEC and SPEC.loader
PI_REVIEW = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PI_REVIEW
SPEC.loader.exec_module(PI_REVIEW)


FAKE_PI = r'''#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

mode = os.environ.get("FAKE_PI_MODE", "ok")
Path(os.environ["FAKE_PI_ARGS"]).write_text(json.dumps(sys.argv[1:]))
Path(os.environ["FAKE_PI_PROMPT"]).write_text(sys.stdin.read())
Path(os.environ["FAKE_PI_ENV"]).write_text(json.dumps({
    key: os.environ.get(key) for key in (
        "ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
        "all_proxy", "http_proxy", "https_proxy", "no_proxy",
        "PI_SKIP_VERSION_CHECK", "PI_CODING_AGENT_DIR", "ZAI_API_KEY"
    )
}))

def emit(event):
    print(json.dumps(event), flush=True)

if mode == "timeout":
    time.sleep(2)
elif mode == "malformed":
    print("not-json", flush=True)
elif mode == "nonzero":
    print("provider connection failed", file=sys.stderr)
    raise SystemExit(7)
elif mode == "stream":
    emit({"type": "agent_start"})
    emit({"type": "turn_start"})
    emit({"type": "tool_execution_start", "toolCallId": "call-1", "toolName": "read"})
    emit({
        "type": "message_update",
        "assistantMessageEvent": {"type": "text_delta", "delta": "partial text"}
    })
    emit({"type": "tool_execution_end", "toolCallId": "call-1"})
    emit({
        "type": "message_end",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "MAJOR: streamed finding"}],
            "provider": "zai",
            "model": "glm-5.2",
            "stopReason": "stop"
        }
    })
elif mode == "idle-timeout":
    emit({"type": "agent_start"})
    emit({"type": "turn_start"})
    emit({"type": "tool_execution_start", "toolCallId": "call-1", "toolName": "grep"})
    emit({
        "type": "message_update",
        "assistantMessageEvent": {"type": "text_delta", "delta": "visible partial"}
    })
    emit({
        "type": "message_update",
        "assistantMessageEvent": {"type": "thinking_delta", "delta": "private reasoning"}
    })
    time.sleep(2)
elif mode == "wall-timeout":
    emit({"type": "agent_start"})
    while True:
        emit({"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "."}})
        time.sleep(0.02)
else:
    emit({"type": "session", "version": 3, "id": "test", "cwd": os.getcwd()})
    stop_reason = "error" if mode == "model-error" else "stop"
    text = "" if mode == "empty" else "MAJOR: app.go:10 - broken invariant"
    emit({
        "type": "message_end",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
            "provider": "zai",
            "model": "glm-5.2",
            "stopReason": stop_reason,
            "errorMessage": "boom" if stop_reason == "error" else None
        }
    })
'''


class PiReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.fake = self.root / "fake-pi.py"
        self.fake.write_text(FAKE_PI, encoding="utf-8")
        self.args_file = self.root / "args.json"
        self.prompt_file = self.root / "prompt.txt"
        self.env_file = self.root / "env.json"
        self.source_agent_dir = self.root / "source-pi-agent"
        self.source_agent_dir.mkdir()
        (self.source_agent_dir / "auth.json").write_text(
            json.dumps({"zai": {"type": "api_key", "key": "test-zai-key"}}),
            encoding="utf-8",
        )
        self.env = mock.patch.dict(
            os.environ,
            {
                "FAKE_PI_ARGS": str(self.args_file),
                "FAKE_PI_PROMPT": str(self.prompt_file),
                "FAKE_PI_ENV": str(self.env_file),
                "FAKE_PI_MODE": "ok",
                "PI_CODING_AGENT_DIR": str(self.source_agent_dir),
                "ZAI_API_KEY": "",
            },
        )
        self.env.start()
        self.command = [sys.executable, str(self.fake)]

    def tearDown(self) -> None:
        self.env.stop()
        self.tempdir.cleanup()

    def run_adapter(self, *, required: bool = False, timeout: float = 1, idle: float = 0.2):
        return PI_REVIEW.run_pi_review(
            "Review this diff",
            cwd=self.root,
            command=self.command,
            timeout_seconds=timeout,
            idle_timeout_seconds=idle,
            required=required,
        )

    def test_command_uses_fixed_model_high_and_read_only_tools(self) -> None:
        result = self.run_adapter()
        self.assertEqual("ok", result.status)
        args = json.loads(self.args_file.read_text(encoding="utf-8"))
        self.assertEqual(list(PI_REVIEW.PI_ARGS), args)
        self.assertEqual("zai/glm-5.2", args[args.index("--model") + 1])
        self.assertEqual("high", args[args.index("--thinking") + 1])
        self.assertEqual("read,grep,find,ls", args[args.index("--tools") + 1])
        self.assertNotIn("--no-tools", args)
        for forbidden in ("bash", "edit", "write"):
            self.assertNotIn(forbidden, args[args.index("--tools") + 1].split(","))
        prompt = self.prompt_file.read_text(encoding="utf-8")
        self.assertIn("Use at most 40 tool calls", prompt)
        self.assertIn("Stop broad exploration after 30 tool calls", prompt)
        self.assertIn("A concise final review is required", prompt)

    def test_subprocess_forces_direct_network_without_proxy(self) -> None:
        for key in PI_REVIEW.PROXY_ENV_KEYS:
            os.environ[key] = "http://127.0.0.1:12334"
        result = self.run_adapter()
        self.assertEqual("ok", result.status)
        child_env = json.loads(self.env_file.read_text(encoding="utf-8"))
        for key in PI_REVIEW.PROXY_ENV_KEYS:
            self.assertEqual("", child_env[key])
        self.assertEqual("1", child_env["PI_SKIP_VERSION_CHECK"])

    def test_subprocess_uses_isolated_temporary_agent_dir_and_zai_credential(self) -> None:
        result = self.run_adapter()
        self.assertEqual("ok", result.status)
        child_env = json.loads(self.env_file.read_text(encoding="utf-8"))
        runtime_agent_dir = Path(child_env["PI_CODING_AGENT_DIR"])
        self.assertNotEqual(self.source_agent_dir, runtime_agent_dir)
        self.assertEqual("test-zai-key", child_env["ZAI_API_KEY"])
        self.assertFalse(runtime_agent_dir.exists())
        self.assertNotIn("test-zai-key", self.args_file.read_text(encoding="utf-8"))

    def test_malformed_auth_does_not_break_adapter_startup(self) -> None:
        (self.source_agent_dir / "auth.json").write_text("not-json", encoding="utf-8")
        result = self.run_adapter()
        self.assertEqual("ok", result.status)
        child_env = json.loads(self.env_file.read_text(encoding="utf-8"))
        self.assertEqual("", child_env["ZAI_API_KEY"])

    def test_prompt_and_fixed_budget_are_passed_through_stdin(self) -> None:
        result = self.run_adapter()
        self.assertEqual(
            f"Review this diff\n\n{PI_REVIEW.REVIEW_BUDGET_INSTRUCTION}\n",
            self.prompt_file.read_text(encoding="utf-8"),
        )
        self.assertEqual("zai", result.provider)
        self.assertEqual("glm-5.2", result.model)
        self.assertIn("broken invariant", result.review)

    def test_missing_optional_pi_is_an_explicit_skip(self) -> None:
        result = PI_REVIEW.run_pi_review(
            "review", cwd=self.root, command=["definitely-missing-pi-binary"], required=False
        )
        self.assertEqual("skipped", result.status)
        self.assertIn("not found", result.reason)

    def test_missing_required_pi_is_an_error(self) -> None:
        result = PI_REVIEW.run_pi_review(
            "review", cwd=self.root, command=["definitely-missing-pi-binary"], required=True
        )
        self.assertEqual("error", result.status)

    def test_timeout_obeys_required_policy(self) -> None:
        os.environ["FAKE_PI_MODE"] = "idle-timeout"
        self.assertEqual("skipped", self.run_adapter(required=False, timeout=0.2, idle=0.05).status)
        self.assertEqual("error", self.run_adapter(required=True, timeout=0.2, idle=0.05).status)

    def test_stream_tracks_turns_tools_and_final_message(self) -> None:
        os.environ["FAKE_PI_MODE"] = "stream"
        result = self.run_adapter(required=True)
        self.assertEqual("ok", result.status)
        self.assertEqual(1, result.turn_count)
        self.assertEqual(1, result.tool_call_count)
        self.assertEqual("message_end", result.last_event)
        self.assertEqual("", result.current_tool)
        self.assertIn("streamed finding", result.review)

    def test_idle_timeout_returns_progress_without_thinking(self) -> None:
        os.environ["FAKE_PI_MODE"] = "idle-timeout"
        result = self.run_adapter(required=True, timeout=3, idle=1)
        self.assertEqual("error", result.status)
        self.assertIn("idle timeout", result.reason)
        self.assertEqual(1, result.turn_count)
        self.assertEqual(1, result.tool_call_count)
        self.assertEqual("grep", result.current_tool)
        self.assertEqual("message_update", result.last_event)
        self.assertEqual("visible partial", result.partial_review)
        self.assertNotIn("private reasoning", result.partial_review)

    def test_wall_timeout_wins_while_events_keep_idle_alive(self) -> None:
        os.environ["FAKE_PI_MODE"] = "wall-timeout"
        # Leave enough process-startup margin for a loaded CI host. Once the
        # synthetic Pi starts, 20ms events keep the one-second idle deadline
        # refreshed while the two-second wall deadline remains the winner.
        result = self.run_adapter(required=True, timeout=2, idle=1)
        self.assertEqual("error", result.status)
        self.assertIn("wall timeout", result.reason)
        self.assertEqual("message_update", result.last_event)
        self.assertGreater(len(result.partial_review), 1)

    def test_malformed_json_obeys_required_policy(self) -> None:
        os.environ["FAKE_PI_MODE"] = "malformed"
        self.assertEqual("skipped", self.run_adapter(required=False).status)
        self.assertEqual("error", self.run_adapter(required=True).status)

    def test_nonzero_exit_is_not_parsed_as_a_review(self) -> None:
        os.environ["FAKE_PI_MODE"] = "nonzero"
        result = self.run_adapter(required=True)
        self.assertEqual("error", result.status)
        self.assertIn("Pi exited with code 7", result.reason)
        self.assertIn("provider connection failed", result.reason)

    def test_model_error_is_rejected_even_when_process_exits_zero(self) -> None:
        os.environ["FAKE_PI_MODE"] = "model-error"
        result = self.run_adapter(required=True)
        self.assertEqual("error", result.status)
        self.assertIn("stopReason", result.reason)
        self.assertIn("boom", result.reason)
        self.assertEqual("zai", result.provider)
        self.assertEqual("glm-5.2", result.model)

    def test_empty_review_is_rejected(self) -> None:
        os.environ["FAKE_PI_MODE"] = "empty"
        self.assertEqual("error", self.run_adapter(required=True).status)

    def test_invalid_command_and_prompt_fail_without_spawning(self) -> None:
        self.assertEqual(
            "error",
            PI_REVIEW.run_pi_review("review", cwd=self.root, command=[], required=True).status,
        )
        self.assertEqual(
            "skipped",
            PI_REVIEW.run_pi_review("  ", cwd=self.root, command=self.command, required=False).status,
        )
        self.assertEqual(
            "error",
            PI_REVIEW.run_pi_review(
                "review", cwd=self.root / "missing", command=self.command, required=True
            ).status,
        )
        self.assertIn(
            "less than wall timeout",
            PI_REVIEW.run_pi_review(
                "review",
                cwd=self.root,
                command=self.command,
                timeout_seconds=10,
                idle_timeout_seconds=10,
                required=True,
            ).reason,
        )


if __name__ == "__main__":
    unittest.main()
