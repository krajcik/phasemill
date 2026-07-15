#!/usr/bin/env python3
"""Contracts for native Codex workflow skills and clipboard adapter."""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins/phasemill"
MANIFEST = PLUGIN / ".codex-plugin/plugin.json"
SKILL_ROOT = PLUGIN / "skills"
NAMES = ("clarify", "learn", "md-copy", "txt-copy", "wrong")
SKILLS = {name: SKILL_ROOT / name / "SKILL.md" for name in NAMES}
ADAPTER_PATH = PLUGIN / "scripts/clipboard.py"

SPEC = importlib.util.spec_from_file_location("phasemill_clipboard", ADAPTER_PATH)
assert SPEC and SPEC.loader
CLIPBOARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLIPBOARD)


def frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            result[key.strip()] = value.strip()
    return result


class CodexWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = {name: path.read_text(encoding="utf-8") for name, path in SKILLS.items()}
        cls.normalized = {name: re.sub(r"\s+", " ", text) for name, text in cls.text.items()}

    def test_manifest_exports_all_native_skills(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual("./skills/", manifest.get("skills"))
        for name, path in SKILLS.items():
            self.assertTrue(path.is_file(), name)
            self.assertEqual(name, frontmatter(self.text[name]).get("name"))

    def test_clarify_investigates_without_implicit_fix(self) -> None:
        text = self.normalized["clarify"]
        self.assertIn("not authorization to fix code", text)
        self.assertIn("runtime evidence", text)
        self.assertIn("confirmed facts from inference and unknowns", text)
        self.assertIn("Do not mutate files, config, runtime state, or external systems", text)

    def test_wrong_preserves_evidence_and_rejects_destructive_reset(self) -> None:
        text = self.normalized["wrong"]
        self.assertIn("preserve the current diff, state, logs, and failed commands as evidence", text)
        self.assertIn("Do not reset, revert, stash, delete, force-checkout, rewrite history", text)
        self.assertIn("Never treat \"start over\" as permission for destructive cleanup", text)

    def test_learn_is_bounded_to_project_scope_and_two_confirmation_gates(self) -> None:
        text = self.normalized["learn"]
        self.assertIn("current or explicitly named Phasemill run", text)
        self.assertIn("one GitHub PR explicitly identified", text)
        self.assertIn("Do not inspect other PRs", text)
        self.assertIn("comment from another developer qualifies only", text)
        self.assertIn("`.codex/phasemill/rules/review.md`", text)
        self.assertIn("only when, the user explicitly asks to save the learning globally", text.lower())
        self.assertIn("`${PLUGIN_DATA}/profiles/<language>.md`", text)
        self.assertIn("Do not guess a user-global directory", text)
        self.assertIn("higher-precedence project fragment", text)
        self.assertIn("ask which candidate numbers to apply", text.lower())
        self.assertIn("Display that exact diff and ask for approval before writing", text)
        self.assertIn("installed plugin cache", text)
        self.assertIn("Do not commit", text)

    def test_clipboard_skills_use_stdin_only_adapter(self) -> None:
        for name in ("txt-copy", "md-copy"):
            text = self.normalized[name]
            self.assertIn("`../../scripts/clipboard.py`", text)
            self.assertIn("stdin", text)
            self.assertIn("Never", text)
            self.assertIn("heredoc", text)
            self.assertIn("temporary file", text)

    def test_clipboard_adapter_selects_platform_tools_in_order(self) -> None:
        found = {"pbcopy": "/fake/pbcopy", "xclip": "/fake/xclip", "xsel": "/fake/xsel"}
        self.assertEqual(["/fake/pbcopy"], CLIPBOARD.select_command(found.get))
        found.pop("pbcopy")
        self.assertEqual(["/fake/xclip", "-selection", "clipboard"], CLIPBOARD.select_command(found.get))
        found.pop("xclip")
        self.assertEqual(["/fake/xsel", "--clipboard", "--input"], CLIPBOARD.select_command(found.get))
        found.clear()
        self.assertIsNone(CLIPBOARD.select_command(found.get))

    def test_clipboard_adapter_passes_exact_bytes_without_shell(self) -> None:
        result = CLIPBOARD.copy("тест\n```go\n$x\n```\n".encode(), ["/bin/cat"])
        self.assertEqual(0, result.returncode)
        self.assertEqual("тест\n```go\n$x\n```\n".encode(), result.stdout)

    def test_claude_only_tool_syntax_does_not_leak(self) -> None:
        combined = "\n".join(self.text.values())
        for forbidden in (
            "AskUserQuestion",
            "EnterPlanMode",
            "CLAUDE.md",
            "CLAUDE.local.md",
            "CLAUDE_PLUGIN_ROOT",
            "allowed-tools:",
            "/tmp/claude-",
        ):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
