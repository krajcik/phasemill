#!/usr/bin/env python3
"""Contracts for native Codex release-tools skills and shared helpers."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins/phasemill"
MANIFEST = PLUGIN / ".codex-plugin/plugin.json"
SKILL_ROOT = PLUGIN / "skills"
SKILLS = {name: SKILL_ROOT / name / "SKILL.md" for name in ("unreleased", "release")}
SCRIPT_ROOT = PLUGIN / "skills/release/scripts"


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


def run(*argv: str | Path, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(part) for part in argv],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result


class CodexReleaseToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = {name: path.read_text(encoding="utf-8") for name, path in SKILLS.items()}
        cls.normalized = {name: re.sub(r"\s+", " ", text) for name, text in cls.text.items()}

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.repo = Path(self.tempdir.name)
        run("git", "init", "-b", "main", cwd=self.repo)
        run("git", "config", "user.email", "release-test@example.invalid", cwd=self.repo)
        run("git", "config", "user.name", "Release Test", cwd=self.repo)
        (self.repo / "README.md").write_text("base\n", encoding="utf-8")
        run("git", "add", "README.md", cwd=self.repo)
        run("git", "commit", "-m", "base", cwd=self.repo)

    def test_manifest_exports_native_skills(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual("./skills/", manifest.get("skills"))
        for name, path in SKILLS.items():
            self.assertTrue(path.is_file(), name)
            self.assertEqual(name, frontmatter(self.text[name]).get("name"))

    def test_last_tag_is_read_only_and_handles_local_fallback(self) -> None:
        text = self.normalized["unreleased"]
        for phrase in (
            "git fetch origin --tags",
            "result is based on local tags",
            "No tags found",
            "No commits since this tag",
            "Validate a user-supplied hash as a commit",
            "Do not create tags, commits, branches, releases, or pushes",
        ):
            self.assertIn(phrase, text)

    def test_new_release_previews_before_every_mutation_and_rechecks_drift(self) -> None:
        text = self.normalized["release"]
        for phrase in (
            "before any source, commit, tag, or external mutation",
            "prepare an in-memory patch",
            "do not edit the file yet",
            "Ask for explicit approval of this exact preview",
            "invalidates approval and requires a new preview",
            "Immediately before mutation, recheck",
            "Abort on drift",
        ):
            self.assertIn(phrase, text)

    def test_new_release_has_safe_partial_failure_and_provider_boundaries(self) -> None:
        text = self.normalized["release"]
        self.assertIn("passing notes through a file/stdin mechanism", text)
        self.assertIn("Never embed notes in shell source", text)
        self.assertIn("Do not enable force, overwrite, replace, or branch deletion flags", text)
        self.assertIn("Do not reset, amend, delete a tag, rewrite history", text)
        self.assertIn("Do not push the source branch, merge, or deploy", text)

    def test_packaged_helper_paths_exist(self) -> None:
        text = self.normalized["release"]
        for name in ("detect-platform.sh", "calc-version.sh", "get-notes.sh"):
            self.assertIn(f"`scripts/{name}`", text)
            self.assertTrue((SCRIPT_ROOT / name).is_file(), name)

    def test_calc_version_first_release_and_semver_bumps(self) -> None:
        script = SCRIPT_ROOT / "calc-version.sh"
        self.assertEqual("v1.0.0", run(script, "major", cwd=self.repo).stdout.strip())
        self.assertEqual("v0.1.0", run(script, "minor", cwd=self.repo).stdout.strip())
        self.assertEqual("v0.0.1", run(script, "hotfix", cwd=self.repo).stdout.strip())

        run("git", "tag", "v1.2.3", cwd=self.repo)
        self.assertEqual("v2.0.0", run(script, "major", cwd=self.repo).stdout.strip())
        self.assertEqual("v1.3.0", run(script, "minor", cwd=self.repo).stdout.strip())
        self.assertEqual("v1.2.4", run(script, "hotfix", cwd=self.repo).stdout.strip())

    def test_calc_version_strips_prerelease_suffix_and_rejects_type(self) -> None:
        script = SCRIPT_ROOT / "calc-version.sh"
        run("git", "tag", "v2.4.6-rc1", cwd=self.repo)
        self.assertEqual("v2.4.7", run(script, "hotfix", cwd=self.repo).stdout.strip())
        invalid = run(script, "patch", cwd=self.repo, check=False)
        self.assertNotEqual(0, invalid.returncode)
        self.assertIn("invalid type", invalid.stdout)

    def test_detect_platform_from_origin_without_network(self) -> None:
        script = SCRIPT_ROOT / "detect-platform.sh"
        run("git", "remote", "add", "origin", "git@github.com:owner/repo.git", cwd=self.repo)
        self.assertEqual("github", run(script, cwd=self.repo).stdout.strip())

    def test_claude_only_tool_syntax_does_not_leak(self) -> None:
        combined = "\n".join(self.text.values())
        for forbidden in (
            "AskUserQuestion",
            "CLAUDE_PLUGIN_ROOT",
            "CLAUDE_PLUGIN_DATA",
            "$ARGUMENTS",
            "allowed-tools:",
        ):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
