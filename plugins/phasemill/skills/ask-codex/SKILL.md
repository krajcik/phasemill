---
name: ask-codex
description: Ask a separate native Codex leaf agent for a bounded second opinion on investigation, debugging, design, or review. Use when the user explicitly asks to "ask Codex" or "get another Codex opinion", or only after at least four distinct evidence-backed attempts have failed.
---

# Ask Codex

This is a second Codex context, not an independent model/provider. Disclose that
limitation when independence matters. Do not launch a nested Codex CLI process,
Pi, or another external model from this skill.

Build a focused handoff from the current conversation:

- the exact question and success criterion;
- observed and expected behavior;
- relevant paths, lines, errors, logs, and constraints;
- distinct approaches already tried and their outcomes;
- applicable `AGENTS.md` and project guidance the second opinion needs.

Pass paths and evidence pointers instead of dumping entire files. Launch
exactly one native Codex read-only leaf subagent. It may inspect the active
repository and run safe read-only diagnostics, but it may not edit files,
spawn more agents, post externally, or widen permissions. Ask for concrete
claims with file/line or command evidence, alternatives considered, confidence,
and one recommended next action.

The root task independently verifies the returned evidence and labels agreements,
disagreements, unsupported claims, and remaining uncertainty. For code review,
retain only material findings with severity, impact, concrete evidence,
recommendation, and validation; discard style noise and low-confidence
speculation.

Present the second opinion and the root assessment separately. Stop before
applying any suggestion and ask what the user wants to do next. If native
subagents are unavailable on the current surface, say so and offer a fresh root
analysis without pretending it is an independent opinion.
