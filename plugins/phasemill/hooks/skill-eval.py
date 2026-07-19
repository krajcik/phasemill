#!/usr/bin/env python3
"""Inject a Codex-native skill relevance check for UserPromptSubmit."""

from __future__ import annotations

import json
import sys
from typing import Any


ADDITIONAL_CONTEXT = """Evaluate the available skills against the user's current request before taking task actions.

If one or more skills are relevant:
1. In commentary, name the minimal relevant set and why each applies.
2. Read every selected SKILL.md completely before acting, including only the references it routes you to.
3. Follow all selected skill contracts and the user's higher-precedence instructions.

If no skill is relevant, proceed directly. Do not claim to use a skill without loading and following it. Do not delegate reading or interpreting skill instructions to a subagent.

Phasemill `run` owns automatic learning after a successful run. Do not select `phasemill:learn` merely because an active run reached its learning action. Select the manual skill only when the user explicitly asks to learn, save knowledge, apply learning, or learn from a named PR; never start background learning from this hook."""


def response(*, warning: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ADDITIONAL_CONTEXT,
        },
    }
    if warning:
        payload["systemMessage"] = warning
        payload.pop("hookSpecificOutput")
    return payload


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeError) as exc:
        print(json.dumps(response(warning=f"skill-eval hook received invalid JSON: {exc}")))
        return 0
    if not isinstance(event, dict):
        print(json.dumps(response(warning="skill-eval hook received a non-object event")))
        return 0
    if event.get("hook_event_name") != "UserPromptSubmit":
        return 0
    if not isinstance(event.get("prompt"), str):
        print(json.dumps(response(warning="skill-eval hook event is missing string field: prompt")))
        return 0
    print(json.dumps(response(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
