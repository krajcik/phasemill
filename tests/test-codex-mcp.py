#!/usr/bin/env python3
"""Protocol and behavior tests for the bundled Phasemill MCP server."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins/phasemill"
SERVER = PLUGIN / "mcp/server.py"


def exchange(messages: list[dict[str, Any] | str]) -> list[dict[str, Any]]:
    lines = [message if isinstance(message, str) else json.dumps(message) for message in messages]
    result = subprocess.run(
        ["python3", str(SERVER)],
        cwd=PLUGIN,
        input="\n".join(lines) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return [json.loads(line) for line in result.stdout.splitlines()]


def call(name: str, arguments: dict[str, Any], *, request_id: int = 2) -> dict[str, Any]:
    responses = exchange(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
        ]
    )
    return responses[-1]


class PhasemillMCPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.plan = self.root / "docs/plans/change.md"
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text(
            "# Change\n\n### Task 1: Implement\n\n- [ ] implement behavior\n",
            encoding="utf-8",
        )

    def test_initialize_and_tool_discovery_are_current_and_jsonl_clean(self) -> None:
        responses = exchange(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ]
        )
        self.assertEqual(2, len(responses), "notifications must not produce a response")
        initialized = responses[0]["result"]
        self.assertEqual("2025-11-25", initialized["protocolVersion"])
        self.assertEqual("phasemill", initialized["serverInfo"]["name"])
        self.assertEqual("1.1.0", initialized["serverInfo"]["version"])
        names = {tool["name"] for tool in responses[1]["result"]["tools"]}
        self.assertEqual(
            {
                "plan_inspect",
                "config_resolve",
                "run_start",
                "run_status",
                "run_next",
                "run_record",
                "external_review",
            },
            names,
        )

    def test_start_status_and_record_share_durable_revision_state(self) -> None:
        common = {"projectRoot": str(self.root), "plan": "docs/plans/change.md"}
        started = call("run_start", common)["result"]
        self.assertFalse(started["isError"])
        action = started["structuredContent"]
        self.assertEqual("task", action["kind"])
        self.assertEqual(0, action["expected_revision"])

        status = call("run_status", {"projectRoot": str(self.root)})["result"]["structuredContent"]
        self.assertEqual(action["action_id"].split(":", 1)[0], status["active"][0]["state"]["run_id"])
        self.assertEqual(".phasemill", Path(status["active"][0]["statePath"]).parts[-3])

        self.plan.write_text(self.plan.read_text(encoding="utf-8").replace("[ ]", "[x]"), encoding="utf-8")
        recorded = call(
            "run_record",
            {
                **common,
                "actionId": action["action_id"],
                "result": {"outcome": "completed", "summary": "implemented and tested"},
            },
        )["result"]
        self.assertFalse(recorded["isError"])
        self.assertEqual("review", recorded["structuredContent"]["kind"])

        stale = call(
            "run_record",
            {
                **common,
                "actionId": action["action_id"],
                "result": {"outcome": "completed"},
            },
        )["result"]
        self.assertTrue(stale["isError"])
        self.assertIn("stale or mismatched action", stale["structuredContent"]["error"])

        review = recorded["structuredContent"]
        external = call(
            "run_record",
            {
                **common,
                "actionId": review["action_id"],
                "result": {"outcome": "clean", "summary": "review clean"},
            },
        )["result"]["structuredContent"]
        self.assertEqual("external-review", external["kind"])
        learning = call(
            "run_record",
            {
                **common,
                "actionId": external["action_id"],
                "result": {"outcome": "clean", "summary": "external review clean"},
            },
        )["result"]["structuredContent"]
        self.assertEqual("learning", learning["kind"])
        self.assertIn("Proposal-only project learning", learning["prompt"])
        done = call(
            "run_record",
            {
                **common,
                "actionId": learning["action_id"],
                "result": {"outcome": "completed", "summary": "candidate 1"},
            },
        )["result"]["structuredContent"]
        self.assertEqual("done", done["kind"])

    def test_config_resolve_detects_php_and_rejects_plan_escape(self) -> None:
        config = call(
            "config_resolve",
            {"projectRoot": str(self.root), "touchedFiles": ["src/Service.php"]},
        )["result"]
        self.assertFalse(config["isError"])
        self.assertIn("php", config["structuredContent"]["profiles"])

        escaped = call(
            "plan_inspect",
            {"projectRoot": str(self.root), "plan": "../outside.md"},
        )["result"]
        self.assertTrue(escaped["isError"])
        self.assertIn("outside projectRoot", escaped["structuredContent"]["error"])

    def test_malformed_json_and_unknown_method_use_protocol_errors(self) -> None:
        responses = exchange(
            [
                "not-json",
                {"jsonrpc": "2.0", "id": 2, "method": "missing/method"},
            ]
        )
        self.assertEqual(-32700, responses[0]["error"]["code"])
        self.assertEqual(-32601, responses[1]["error"]["code"])

    def test_plugin_mcp_config_is_dependency_free_and_long_review_safe(self) -> None:
        config = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
        server = config["mcpServers"]["phasemill"]
        self.assertEqual("python3", server["command"])
        self.assertEqual(["./mcp/server.py"], server["args"])
        self.assertEqual(".", server["cwd"])
        self.assertGreater(server["tool_timeout_sec"], 900)


if __name__ == "__main__":
    unittest.main()
