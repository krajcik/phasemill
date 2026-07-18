#!/usr/bin/env python3
"""Static contracts for native Codex thinking-tools skills."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins/phasemill"
MANIFEST = PLUGIN / ".codex-plugin/plugin.json"
SKILL_ROOT = PLUGIN / "skills"
NAMES = ("ask-codex", "dialectic", "root-cause-investigator")
SKILLS = {name: SKILL_ROOT / name / "SKILL.md" for name in NAMES}


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


class CodexThinkingToolsTests(unittest.TestCase):
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

    def test_dialectic_uses_exactly_two_parallel_leaf_agents_and_root_verification(self) -> None:
        text = self.normalized["dialectic"]
        self.assertIn("exactly two native Codex read-only leaf subagents in parallel", text)
        self.assertIn("may not edit, spawn agents, or coordinate with each other", text)
        self.assertIn("root task then verifies every material citation", text)
        self.assertIn("Do not average incompatible claims or force a winner", text)

    def test_dialectic_has_bounded_automatic_escalation_contract(self) -> None:
        text = self.normalized["dialectic"]
        description = frontmatter(self.text["dialectic"]).get("description", "")
        self.assertIn("invoke automatically from Phasemill brainstorm or plan review", description)
        self.assertIn("all of these conditions hold", text)
        self.assertIn("Escalate at most once per parent phase", text)
        self.assertIn("direct repository or runtime inspection has not already resolved the claim", text)
        self.assertIn("a verdict is evidence, not user approval", text)

    def test_root_cause_uses_falsifiable_chain_without_fabricated_five_whys(self) -> None:
        text = self.normalized["root-cause-investigator"]
        self.assertIn("Diagnosis does not authorize a fix", text)
        self.assertIn("as a causal scaffold, not a quota", text)
        self.assertIn("alternative explanations tested", text)
        self.assertIn("trigger, root cause, contributing conditions", text)
        self.assertIn("Implement nothing unless the user separately asks", text)

    def test_root_cause_reuses_packaged_references(self) -> None:
        text = self.normalized["root-cause-investigator"]
        for name in ("patterns.md", "techniques.md"):
            relative = f"`references/{name}`"
            self.assertIn(relative, text)
            self.assertTrue((PLUGIN / f"skills/root-cause-investigator/references/{name}").is_file())

    def test_ask_codex_is_honest_bounded_and_non_mutating(self) -> None:
        text = self.normalized["ask-codex"]
        self.assertIn("second Codex context, not an independent model/provider", text)
        self.assertIn("exactly one native Codex read-only leaf subagent", text)
        self.assertIn("may not edit files, spawn more agents, post externally, or widen permissions", text)
        self.assertIn("root task independently verifies", text)
        self.assertIn("Stop before applying any suggestion", text)

    def test_nested_cli_and_claude_syntax_do_not_leak(self) -> None:
        combined = "\n".join(self.text.values())
        for forbidden in (
            "codex exec",
            "AskUserQuestion",
            "Task tool",
            "subagent_type",
            "CLAUDE.md",
            "CLAUDE_PLUGIN_ROOT",
            "allowed-tools:",
            "run_in_background",
        ):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
