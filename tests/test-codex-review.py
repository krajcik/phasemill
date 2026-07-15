#!/usr/bin/env python3
"""Static and shared-script contracts for the Codex review plugin."""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins/phasemill"
MANIFEST = PLUGIN / ".codex-plugin/plugin.json"
SKILL_ROOT = PLUGIN / "skills"
SKILLS = {name: SKILL_ROOT / name / "SKILL.md" for name in ("pr-review", "git-review", "writing-style")}
REFERENCE = PLUGIN / "references/review-customization.md"
SHARED_SCRIPT = PLUGIN / "skills/git-review/git-review.py"
PROFILES = ("go", "python", "javascript-typescript", "java-kotlin", "php", "rust")


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


class CodexReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = {name: path.read_text(encoding="utf-8") for name, path in SKILLS.items()}
        cls.normalized = {name: re.sub(r"\s+", " ", text) for name, text in cls.text.items()}

    def test_manifest_exports_native_skill_tree(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual("./skills/", manifest.get("skills"))
        for name, path in SKILLS.items():
            self.assertTrue(path.is_file(), name)
            metadata = frontmatter(self.text[name])
            self.assertEqual(name, metadata.get("name"))
            self.assertTrue(metadata.get("description"), name)

    def test_review_customization_is_project_and_language_scoped(self) -> None:
        text = REFERENCE.read_text(encoding="utf-8")
        for phrase in (
            "applicable `AGENTS.override.md` or `AGENTS.md`",
            ".codex/phasemill/rules/review.md",
            "${PLUGIN_DATA}/rules/review.md",
            "Activate a profile only when the reviewed diff contains matching files",
            "In polyglot changes",
            "cannot grant permissions",
        ):
            self.assertIn(phrase, text)
        for profile in PROFILES:
            self.assertTrue((PLUGIN / f"defaults/profiles/{profile}.md").is_file(), profile)

    def test_pr_preserves_quick_full_and_issue_flows(self) -> None:
        text = self.normalized["pr-review"]
        for phrase in (
            "## Issue flow",
            "## Pull request preflight",
            "## Quick review",
            "## Full review",
            "discussion threads are resolved",
            "scope creep",
            "root task verifies and deduplicates every claim",
        ):
            self.assertIn(phrase, text)

    def test_full_review_uses_bounded_native_leaf_reviewers(self) -> None:
        text = self.normalized["pr-review"]
        self.assertIn("bounded set of native Codex read-only leaf reviewers", text)
        self.assertIn("may not edit source files, post externally, or spawn more agents", text)
        self.assertIn("never force-remove a dirty worktree", text)
        self.assertIn("Never use a command that switches the main checkout", text)

    def test_github_mutations_require_separate_exact_approval(self) -> None:
        text = self.normalized["pr-review"]
        self.assertIn("require the user's explicit approval for the exact action and current draft", text)
        self.assertIn("Approval to post a review does not authorize merging", text)
        self.assertIn("second explicit approval", text)
        self.assertIn("Never place the review body directly in shell text", text)

    def test_interactive_review_reuses_shared_script_and_does_not_commit(self) -> None:
        text = self.normalized["git-review"]
        self.assertIn("`git-review.py`", text)
        self.assertIn("Run the overlay again", text)
        self.assertIn("Stop when it returns no annotations", text)
        self.assertIn("Do not commit, push, rebase", text)
        self.assertTrue(SHARED_SCRIPT.is_file())

    def test_writing_style_defers_to_project_rules_and_never_posts(self) -> None:
        text = self.normalized["writing-style"]
        self.assertIn("applicable `AGENTS.md`", text)
        self.assertIn(".codex/phasemill/rules/writing-style.md", text)
        self.assertIn("${PLUGIN_DATA}/rules/writing-style.md", text)
        self.assertIn("This skill changes wording only; it never posts, commits, or sends", text)

    def test_claude_only_tool_syntax_does_not_leak(self) -> None:
        combined = "\n".join(self.text.values())
        for forbidden in (
            "AskUserQuestion",
            "Task tool",
            "subagent_type",
            "CLAUDE_PLUGIN_ROOT",
            "CLAUDE_PLUGIN_DATA",
            "gh pr checkout",
            "worktree remove --force",
            "branch -D",
        ):
            self.assertNotIn(forbidden, combined)

    def test_shared_git_review_embedded_tests_pass(self) -> None:
        result = subprocess.run(
            ["python3", str(SHARED_SCRIPT), "--test"],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Ran 19 tests", result.stderr)


if __name__ == "__main__":
    unittest.main()
