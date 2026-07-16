#!/usr/bin/env python3
"""Create replay-safe lazy stage commits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Sequence


RUNTIME_PREFIX = ".phasemill/runs/"
ACTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HEX_SHA = re.compile(r"^[0-9a-f]{40,64}$")


class LazyStageError(RuntimeError):
    pass


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise LazyStageError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed


def repository_root(value: Path) -> Path:
    root = Path(git(value.resolve(), "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if not root.is_dir():
        raise LazyStageError(f"repository root is not a directory: {root}")
    return root


def normalize_paths(values: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
            raise LazyStageError(f"unsafe checkpoint path: {value!r}")
        normalized = path.as_posix()
        if normalized == "." or normalized.startswith(RUNTIME_PREFIX):
            raise LazyStageError(f"checkpoint path is not allowed: {value!r}")
        if normalized not in result:
            result.append(normalized)
    if not result:
        raise LazyStageError("checkpoint requires at least one allowed path")
    return tuple(result)


def dirty_paths(root: Path) -> tuple[str, ...]:
    output = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    paths: list[str] = []
    entries = output.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            if index >= len(entries):
                raise LazyStageError("malformed git status rename entry")
            original_path = entries[index]
            index += 1
            paths.append(original_path)
    return tuple(sorted(path for path in dict.fromkeys(paths) if not path.startswith(RUNTIME_PREFIX)))


def checkpoint(root: Path, action_id: str, message: str, expected_head: str, paths: Sequence[str]) -> dict[str, str]:
    if ACTION_ID.fullmatch(action_id) is None:
        raise LazyStageError("checkpoint action id contains unsafe characters")
    if HEX_SHA.fullmatch(expected_head) is None:
        raise LazyStageError("checkpoint expected HEAD is not a full commit id")
    allowed = normalize_paths(paths)
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    trailer = f"Phasemill-Action: {action_id}"
    base_trailer = "Phasemill-Base: "
    current_message = git(root, "log", "-1", "--format=%B").stdout
    if trailer in current_message.splitlines():
        recorded_base = next(
            (line.removeprefix(base_trailer) for line in current_message.splitlines() if line.startswith(base_trailer)),
            "",
        )
        parents = git(root, "show", "-s", "--format=%P", "HEAD").stdout.split()
        if not recorded_base or len(parents) != 1 or parents[0] != recorded_base:
            raise LazyStageError("replayed checkpoint is not bound to its parent HEAD")
        if recorded_base != expected_head:
            raise LazyStageError("replayed checkpoint does not match the expected base HEAD")
        committed = tuple(
            filter(
                None,
                git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "HEAD^", "HEAD").stdout.split("\0"),
            )
        )
        if not committed or any(path not in allowed for path in committed):
            raise LazyStageError("replayed checkpoint changed paths outside the allowed stage scope")
        dirty = dirty_paths(root)
        if dirty:
            raise LazyStageError("replayed checkpoint has new dirty paths: " + ", ".join(dirty))
        return {"status": "reused", "head": head, "action_id": action_id}
    if head != expected_head:
        raise LazyStageError(f"checkpoint HEAD changed: expected {expected_head}, got {head}")
    dirty = dirty_paths(root)
    unexpected = [path for path in dirty if path not in allowed]
    if unexpected:
        raise LazyStageError("checkpoint found unrelated dirty paths: " + ", ".join(unexpected))
    if not dirty:
        return {"status": "noop", "head": head, "action_id": action_id}
    stageable = tuple(
        path
        for path in allowed
        if (root / path).exists()
        or git(root, "ls-files", "--error-unmatch", "--", path, check=False).returncode == 0
    )
    if stageable:
        git(root, "add", "-A", "--", *stageable)
    staged = tuple(filter(None, git(root, "diff", "--cached", "--name-only", "-z").stdout.split("\0")))
    if not staged or any(path not in allowed for path in staged):
        raise LazyStageError("checkpoint staged paths outside the allowed stage scope")
    git(root, "commit", "-m", message, "-m", f"{trailer}\n{base_trailer}{expected_head}")
    new_head = git(root, "rev-parse", "HEAD").stdout.strip()
    if dirty_paths(root):
        raise LazyStageError("checkpoint commit left non-runtime worktree changes")
    return {"status": "committed", "head": new_head, "action_id": action_id}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    checkpoint_parser = commands.add_parser("checkpoint")
    checkpoint_parser.add_argument("--project-root", type=Path, required=True)
    checkpoint_parser.add_argument("--action-id", required=True)
    checkpoint_parser.add_argument("--message", required=True)
    checkpoint_parser.add_argument("--expected-head", required=True)
    checkpoint_parser.add_argument("--path", action="append", dest="paths", required=True)
    args = parser.parse_args()
    try:
        root = repository_root(args.project_root)
        result = checkpoint(root, args.action_id, args.message, args.expected_head, args.paths)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (LazyStageError, OSError, UnicodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
