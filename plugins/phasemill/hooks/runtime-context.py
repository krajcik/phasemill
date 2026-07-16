#!/usr/bin/env python3
"""Inject compact advisory recovery context for active Phasemill state."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _read_active(paths: list[Path], statuses: set[str]) -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for path in sorted(paths, key=_mtime, reverse=True):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("status") in statuses:
            active.append(value)
    return active


def _confined_state_paths(repository: Path, directory: Path, pattern: str) -> list[Path]:
    try:
        repository_root = repository.resolve()
        root = directory.resolve()
    except OSError:
        return []
    if repository_root != root and repository_root not in root.parents:
        return []
    confined: list[Path] = []
    for path in directory.glob(pattern):
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if root in resolved.parents and resolved.is_file():
            confined.append(resolved)
    return confined


def _active_runs(cwd: Path) -> list[dict[str, Any]]:
    directory = cwd / ".phasemill" / "runs"
    return _read_active(_confined_state_paths(cwd, directory, "state-*.json"), {"running"})


def _active_lazy(cwd: Path) -> list[dict[str, Any]]:
    directory = cwd / ".phasemill" / "runs"
    return _read_active(
        _confined_state_paths(cwd, directory, "lazy-*/state.json"),
        {"running", "waiting-input"},
    )


def _main_worktree(cwd: Path) -> Path:
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), "worktree", "list", "--porcelain"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return cwd
    if completed.returncode != 0:
        return cwd
    first = next(
        (line.removeprefix("worktree ") for line in completed.stdout.splitlines() if line.startswith("worktree ")),
        "",
    )
    root = Path(first).resolve() if first else cwd
    return root if root.is_dir() else cwd


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeError):
        return 0
    if not isinstance(event, dict) or event.get("hook_event_name") != "SessionStart":
        return 0
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return 0
    root = Path(cwd).resolve()
    lazy = _active_lazy(_main_worktree(root))
    runs = _active_runs(root)
    if not lazy and not runs:
        return 0
    sections = ["Phasemill durable recovery context (advisory only):"]
    if lazy:
        sections.append("Lazy journeys:")
        sections.extend(
            f"- journey={state.get('journey_id', '?')} phase={state.get('phase', '?')} "
            f"status={state.get('status', '?')} revision={state.get('revision', '?')} "
            f"plan={state.get('plan_path') or '-'} linked_run={state.get('linked_run_id') or '-'}"
            for state in lazy[:5]
        )
    if runs:
        sections.append("Implementation runs:")
        sections.extend(
            f"- run={run.get('run_id', '?')} phase={run.get('phase', '?')} "
            f"revision={run.get('revision', '?')} plan={run.get('plan_path', '?')}"
            for run in runs[:5]
        )
    sections.append(
        "Use mcp__phasemill__lazy_status and mcp__phasemill__run_status before continuing. "
        "This hook never advances or repairs either controller."
    )
    context = "\n".join(sections)
    print(
        json.dumps(
            {
                "continue": True,
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
