#!/usr/bin/env python3
"""Inject compact recovery context for active Phasemill runs."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


def _active_runs(cwd: Path) -> list[dict[str, Any]]:
    directory = cwd / ".phasemill" / "runs"
    runs: list[dict[str, Any]] = []
    for path in sorted(directory.glob("state-*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get("status") == "running":
            runs.append(value)
    return runs


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
    runs = _active_runs(Path(cwd).resolve())
    if not runs:
        return 0
    summaries = [
        f"- plan={run.get('plan_path', '?')} phase={run.get('phase', '?')} "
        f"revision={run.get('revision', '?')} run_id={run.get('run_id', '?')}"
        for run in runs[:5]
    ]
    context = (
        "Phasemill has active durable run state:\n"
        + "\n".join(summaries)
        + "\nUse mcp__phasemill__run_status before continuing; do not infer the phase from the transcript."
    )
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
