---
name: root-cause-investigator
description: Diagnose the root cause of a bug, error, test/build failure, performance regression, or unexpected behavior with evidence-driven causal analysis. Use for "root cause", "why is this failing", "investigate this error", or repeated unexplained failures.
---

# Root cause investigator

Diagnosis does not authorize a fix. Preserve the failing state when safe,
capture the exact symptom, and read applicable `AGENTS.md` before running
diagnostics.

Establish observed versus expected behavior, reproduction, environment,
frequency, onset, blast radius, and recent relevant changes. Prefer primary
evidence: exact errors, logs, traces, metrics, configuration origins, code flow,
dependency state, and a minimal reproduction. Do not print secrets or infer
production state from stale documentation.

Use successive `why` questions as a causal scaffold, not a quota. Stop when an
answer is both supported by evidence and explains the preceding link; continue
past five when the causal chain is still superficial. For every link record:

- claim and supporting evidence;
- alternative explanations tested;
- observation or experiment that falsified each alternative;
- affected scope and confidence.

Separate trigger, root cause, contributing conditions, and detection/response
gaps. Check code and data flow beyond the failing line, configuration and
environment, concurrency/order, resource exhaustion, dependency/version drift,
deploy/build process, retries/timeouts, and observability where relevant.

Load `references/patterns.md` next to this skill
when the symptom matches one of its categories. Load
`references/techniques.md` only for the
specific diagnostic family needed; adapt commands to the repository and avoid
broad environment dumps.

Finish with the verified root cause, causal chain, confidence, ruled-out
alternatives, impact, and the smallest regression test or observation that
would prove a fix. If evidence is insufficient, state the leading hypotheses
and next discriminating check instead of declaring a cause. Implement nothing
unless the user separately asks for a fix.
