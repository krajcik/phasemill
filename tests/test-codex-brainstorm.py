#!/usr/bin/env python3
"""Static contract tests for the Codex brainstorm skill."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "plugins/phasemill/skills/brainstorm/SKILL.md"
MANIFEST = REPO / "plugins/phasemill/.codex-plugin/plugin.json"


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


class CodexBrainstormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SKILL.read_text(encoding="utf-8")
        cls.metadata = frontmatter(cls.text)

    def test_skill_is_explicitly_invokable_and_implicitly_discoverable(self) -> None:
        self.assertEqual("brainstorm", self.metadata.get("name"))
        description = self.metadata.get("description", "").lower()
        for trigger in ("brainstorm", "think through", "explore options", "design"):
            self.assertIn(trigger, description)
        self.assertIn("skip for small obvious edits", description)

    def test_skill_preserves_the_four_phase_workflow(self) -> None:
        for phrase in (
            "Understand the idea",
            "Explore alternatives",
            "Validate the design incrementally",
            "Produce the handoff",
        ):
            self.assertIn(phrase, self.text)
        self.assertIn("2-3 genuinely different approaches", self.text)
        self.assertIn("Ask one question per turn", self.text)

    def test_rules_use_codex_project_and_plugin_data_paths(self) -> None:
        self.assertIn("${PLUGIN_DATA}/rules/brainstorm.md", self.text)
        self.assertIn(".codex/phasemill/rules/brainstorm.md", self.text)
        self.assertIn("applicable `AGENTS.md`", self.text)
        self.assertIn("Missing rule files are normal", self.text)

    def test_handoff_targets_native_planning(self) -> None:
        self.assertIn("`phasemill:plan`", self.text)
        self.assertIn("native Codex plan", self.text)
        self.assertIn("decisions, assumptions, and open questions", self.text)

    def test_high_impact_unresolved_claim_escalates_once_to_dialectic(self) -> None:
        normalized = re.sub(r"\s+", " ", self.text)
        self.assertIn("`phasemill:dialectic`", normalized)
        self.assertIn("at most once", normalized)
        self.assertIn("high-impact falsifiable claim", normalized)
        self.assertIn("claims already resolved by direct inspection", normalized)

    def test_claude_only_tool_syntax_does_not_leak(self) -> None:
        for forbidden in (
            "AskUserQuestion",
            "EnterPlanMode",
            "CLAUDE_PLUGIN_ROOT",
            "CLAUDE_PLUGIN_DATA",
            "mode: \"bypassPermissions\"",
        ):
            self.assertNotIn(forbidden, self.text)

    def test_manifest_points_to_existing_skill_tree(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual("./skills/", manifest.get("skills"))
        self.assertTrue((MANIFEST.parent.parent / manifest["skills"]).is_dir())


if __name__ == "__main__":
    unittest.main()
