#!/usr/bin/env python3
"""Behavior tests for replay-safe lazy Git checkpoints."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/phasemill/scripts/lazy-stage.py"


class LazyStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name) / "repo"
        self.root.mkdir()
        self.cmd("git", "init", "-q", "-b", "main")
        self.cmd("git", "config", "user.name", "Lazy Stage Test")
        self.cmd("git", "config", "user.email", "lazy-stage@example.invalid")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        self.cmd("git", "add", "README.md")
        self.cmd("git", "commit", "-q", "-m", "base")

    def cmd(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(args, cwd=self.root, text=True, capture_output=True, check=False)
        if check and result.returncode:
            self.fail(f"command failed: {args}\nstdout={result.stdout}\nstderr={result.stderr}")
        return result

    def helper(self, *args: str, check: bool = True) -> dict[str, str]:
        result = self.cmd("python3", str(SCRIPT), *args, check=False)
        payload = json.loads(result.stdout)
        if check and result.returncode:
            self.fail(f"helper failed: {payload}")
        payload["returncode"] = str(result.returncode)
        return payload

    def head(self) -> str:
        return self.cmd("git", "rev-parse", "HEAD").stdout.strip()

    def test_checkpoint_commit_replay_noop_and_scope_guards(self) -> None:
        action = "lazy-test:2:bootstrap-config"
        config = self.root / ".codex/phasemill/config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("[review.external]\ndata_sharing_approved = true\n", encoding="utf-8")
        base = self.head()
        committed = self.helper(
            "checkpoint", "--project-root", str(self.root), "--action-id", action,
            "--message", "chore(phasemill): initialize lazy workflow",
            "--expected-head", base, "--path", ".codex/phasemill/config.toml",
        )
        self.assertEqual("committed", committed["status"])
        self.assertIn(action, self.cmd("git", "log", "-1", "--format=%B").stdout)
        replay = self.helper(
            "checkpoint", "--project-root", str(self.root), "--action-id", action,
            "--message", "ignored", "--expected-head", base,
            "--path", ".codex/phasemill/config.toml",
        )
        self.assertEqual("reused", replay["status"])
        self.assertEqual(committed["head"], replay["head"])

        next_action = "lazy-test:3:plan"
        noop = self.helper(
            "checkpoint", "--project-root", str(self.root), "--action-id", next_action,
            "--message", "docs(phasemill): create implementation plan",
            "--expected-head", self.head(), "--path", "docs/plans/test.md",
        )
        self.assertEqual("noop", noop["status"])

        (self.root / "unrelated.txt").write_text("dirty\n", encoding="utf-8")
        rejected = self.helper(
            "checkpoint", "--project-root", str(self.root), "--action-id", next_action,
            "--message", "docs(phasemill): create implementation plan",
            "--expected-head", self.head(), "--path", "docs/plans/test.md", check=False,
        )
        self.assertIn("unrelated dirty paths", rejected["error"])

    def test_checkpoint_rejects_head_drift_and_replay_with_new_dirt(self) -> None:
        base = self.head()
        (self.root / "README.md").write_text("next\n", encoding="utf-8")
        self.cmd("git", "add", "README.md")
        self.cmd("git", "commit", "-q", "-m", "concurrent")
        result = self.helper(
            "checkpoint", "--project-root", str(self.root), "--action-id", "stage:1:plan",
            "--message", "plan", "--expected-head", base, "--path", "README.md", check=False,
        )
        self.assertIn("HEAD changed", result["error"])

        current = self.head()
        (self.root / "README.md").write_text("checkpoint\n", encoding="utf-8")
        committed = self.helper(
            "checkpoint", "--project-root", str(self.root), "--action-id", "stage:2:plan",
            "--message", "plan", "--expected-head", current, "--path", "README.md",
        )
        self.assertEqual("committed", committed["status"])
        (self.root / "new.txt").write_text("unexpected\n", encoding="utf-8")
        replay = self.helper(
            "checkpoint", "--project-root", str(self.root), "--action-id", "stage:2:plan",
            "--message", "plan", "--expected-head", current, "--path", "README.md", check=False,
        )
        self.assertIn("new dirty paths", replay["error"])

    def test_checkpoint_supports_staged_and_filesystem_renames(self) -> None:
        old = self.root / "old.txt"
        old.write_text("tracked\n", encoding="utf-8")
        self.cmd("git", "add", "old.txt")
        self.cmd("git", "commit", "-q", "-m", "tracked rename source")
        base = self.head()
        self.cmd("git", "mv", "old.txt", "new.txt")
        staged = self.helper(
            "checkpoint", "--project-root", str(self.root), "--action-id", "rename:1:move",
            "--message", "move", "--expected-head", base,
            "--path", "old.txt", "--path", "new.txt",
        )
        self.assertEqual("committed", staged["status"])

        base = self.head()
        os.rename(self.root / "new.txt", self.root / "final.txt")
        unstaged = self.helper(
            "checkpoint", "--project-root", str(self.root), "--action-id", "rename:2:move",
            "--message", "move", "--expected-head", base,
            "--path", "new.txt", "--path", "final.txt",
        )
        self.assertEqual("committed", unstaged["status"])
        self.assertTrue((self.root / "final.txt").is_file())

    def test_checkpoint_rejects_forged_matching_action_trailer(self) -> None:
        base = self.head()
        (self.root / "README.md").write_text("forged\n", encoding="utf-8")
        self.cmd("git", "add", "README.md")
        self.cmd("git", "commit", "-q", "-m", "forged", "-m", "Phasemill-Action: forged:1:plan")
        result = self.helper(
            "checkpoint", "--project-root", str(self.root), "--action-id", "forged:1:plan",
            "--message", "plan", "--expected-head", base, "--path", "README.md", check=False,
        )
        self.assertEqual("2", result["returncode"])
        self.assertIn("not bound to its parent HEAD", result["error"])


if __name__ == "__main__":
    unittest.main()
