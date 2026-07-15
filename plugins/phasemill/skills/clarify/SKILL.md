---
name: clarify
description: Investigate and explain a mismatch between expected and actual behavior before deciding whether anything should change. Use for confusion, "this doesn't make sense", "why is this happening", "I expected X", or frustrated contradictory reports.
---

# Clarify

Clarification is an evidence-gathering task, not authorization to fix code.
Treat the user's expectation as a useful hypothesis without assuming either
user error or a product bug.

1. State the expected behavior, observed behavior, and exact gap in one compact
   summary. Ask one question only if the observation itself is ambiguous.
2. Read applicable `AGENTS.md`, relevant code, configuration, documentation,
   history, logs, and live state that can be inspected safely. Consider project
   mixing, stale documentation, version drift, configuration, and genuine
   implementation defects.
3. Explain the current behavior with exact paths, symbols, values, or runtime
   evidence. Separate confirmed facts from inference and unknowns; do not use a
   gentle tone as a substitute for proof.
4. Classify the result as expected behavior, project/context mix-up, stale
   understanding, documentation issue, configuration issue, or real defect.

For expected behavior, answer the user's concrete question and stop. For a
documentation/configuration issue or real defect, explain scope and 1-3 viable
options with a recommendation, then ask whether to invoke `phasemill:plan`,
implement directly when the change is genuinely small, or stop. Do not mutate
files, config, runtime state, or external systems until the user chooses a
change action.
