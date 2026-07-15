#!/usr/bin/env python3
"""Behavior tests for the guarded Codex planning worktree helper."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/phasemill/scripts/worktree.sh"


def run(*argv: str | Path, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(part) for part in argv],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(map(str, argv))}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def fields(output: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


class CodexWorktreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name) / "repo"
        self.root.mkdir()
        run("git", "init", "-b", "main", cwd=self.root)
        run("git", "config", "user.email", "codex-test@example.invalid", cwd=self.root)
        run("git", "config", "user.name", "Codex Test", cwd=self.root)
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        run("git", "add", "README.md", cwd=self.root)
        run("git", "commit", "-m", "base", cwd=self.root)
        self.head = run("git", "rev-parse", "HEAD", cwd=self.root).stdout.strip()
        self.plan = self.root / "docs/plans/20260715-worktree-port.md"
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text("# Plan\n\n### Task 1: Work\n\n- [ ] implement\n", encoding="utf-8")

    def prepare(self, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return run(
            SCRIPT,
            "prepare",
            "--repo",
            self.root,
            "--plan",
            self.plan,
            "--default-branch",
            "main",
            cwd=self.root,
            check=check,
        )

    def test_prepare_copies_untracked_plan_without_touching_main_and_reuses(self) -> None:
        first = fields(self.prepare().stdout)
        worktree = Path(first["project_root"])
        worktree_plan = Path(first["plan_path"])

        self.assertEqual("created", first["status"])
        self.assertEqual("worktree-port", first["branch"])
        self.assertEqual("true", first["plan_copied"])
        self.assertTrue(worktree_plan.is_file())
        self.assertEqual("main", run("git", "branch", "--show-current", cwd=self.root).stdout.strip())
        self.assertEqual(self.head, run("git", "rev-parse", "HEAD", cwd=self.root).stdout.strip())
        self.assertEqual("worktree-port", run("git", "branch", "--show-current", cwd=worktree).stdout.strip())

        runtime = worktree / ".phasemill/runs/state.json"
        runtime.parent.mkdir(parents=True)
        runtime.write_text("{}\n", encoding="utf-8")
        status = run("git", "status", "--porcelain=v1", "--untracked-files=all", cwd=worktree).stdout
        self.assertNotIn(".phasemill/runs", status)

        worktree_plan.write_text("worktree progress\n", encoding="utf-8")
        second = fields(self.prepare().stdout)
        self.assertEqual("reused", second["status"])
        self.assertEqual("false", second["plan_copied"])
        self.assertEqual("worktree progress\n", worktree_plan.read_text(encoding="utf-8"))

        resumed_inside = fields(
            run(
                SCRIPT,
                "prepare",
                "--repo",
                worktree,
                "--plan",
                worktree_plan,
                "--default-branch",
                "main",
                cwd=worktree,
            ).stdout
        )
        self.assertEqual("reused", resumed_inside["status"])
        self.assertEqual(str(worktree), resumed_inside["project_root"])

    def test_prepare_rejects_changes_outside_plan(self) -> None:
        (self.root / "other.txt").write_text("dirty\n", encoding="utf-8")
        result = self.prepare(check=False)
        self.assertEqual(2, result.returncode)
        self.assertIn("changes outside the plan", result.stderr)
        self.assertIn("other.txt", result.stderr)
        expected = Path(self.tempdir.name) / ".repo-phasemill-worktrees/worktree-port"
        self.assertFalse(expected.exists())

    def test_prepare_requires_the_resolved_default_branch(self) -> None:
        run("git", "checkout", "-b", "feature", cwd=self.root)
        result = self.prepare(check=False)
        self.assertEqual(2, result.returncode)
        self.assertIn("requires main branch, currently on feature", result.stderr)

    def test_clean_tracked_plan_needs_no_copy_and_can_be_explicitly_removed(self) -> None:
        run("git", "add", "-f", "docs/plans/20260715-worktree-port.md", cwd=self.root)
        run("git", "commit", "-m", "add plan", cwd=self.root)
        prepared = fields(self.prepare().stdout)
        worktree = Path(prepared["project_root"])
        self.assertEqual("false", prepared["plan_copied"])
        self.assertTrue(Path(prepared["plan_path"]).is_file())

        inspect = fields(
            run(
                SCRIPT,
                "inspect",
                "--repo",
                self.root,
                "--plan",
                self.plan,
                cwd=self.root,
            ).stdout
        )
        self.assertEqual("reused", inspect["status"])

        denied = run(
            SCRIPT,
            "remove",
            "--repo",
            self.root,
            "--plan",
            self.plan,
            cwd=self.root,
            check=False,
        )
        self.assertEqual(2, denied.returncode)
        self.assertIn("explicit --yes", denied.stderr)
        self.assertTrue(worktree.exists())

        removed = fields(
            run(
                SCRIPT,
                "remove",
                "--repo",
                self.root,
                "--plan",
                self.plan,
                "--yes",
                cwd=self.root,
            ).stdout
        )
        self.assertEqual("removed", removed["status"])
        self.assertFalse(worktree.exists())
        self.assertEqual(
            "worktree-port",
            run("git", "branch", "--list", "worktree-port", "--format=%(refname:short)", cwd=self.root).stdout.strip(),
        )

    def test_inspect_reports_absent_worktree(self) -> None:
        planned = fields(
            run(
                SCRIPT,
                "plan",
                "--repo",
                self.root,
                "--plan",
                self.plan,
                cwd=self.root,
            ).stdout
        )
        self.assertEqual("planned", planned["status"])
        self.assertEqual("worktree-port", planned["branch"])
        self.assertFalse(Path(planned["project_root"]).exists())

        result = run(
            SCRIPT,
            "inspect",
            "--repo",
            self.root,
            "--plan",
            self.plan,
            cwd=self.root,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("does not exist", result.stderr)


if __name__ == "__main__":
    unittest.main()
