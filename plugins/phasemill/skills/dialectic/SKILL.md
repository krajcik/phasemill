---
name: dialectic
description: Stress-test a concrete claim with parallel thesis and antithesis analysis, then verify and synthesize the evidence. Use for "dialectic", "prove or disprove", "argue both sides", "stress test this claim", or "is this really true".
---

# Dialectic

Extract one falsifiable claim and its scope. If the statement is ambiguous,
ask one focused question before analysis. Read applicable `AGENTS.md` and gather
the minimum shared repository/runtime context both sides need.

Launch exactly two native Codex read-only leaf subagents in parallel:

- thesis seeks the strongest evidence that the claim is true, including
  boundary conditions and successful counterexamples to likely objections;
- antithesis seeks the strongest evidence that it is false, including failure
  modes, hidden costs, missing measurements, and counterexamples.

Give both agents the same claim, scope, evidence sources, and standard of proof.
They may inspect files and safe runtime state but may not edit, spawn agents, or
coordinate with each other. Require exact file/line, command output, metric, or
source evidence; confidence must fall when a conclusion is inferred.

The root task then verifies every material citation and disputed fact directly.
Discard invented or stale evidence. Synthesize:

- strongest verified evidence for each side;
- agreements, because they are often the highest-confidence signal;
- which conditions make the claim true or false;
- unresolved uncertainty and the smallest experiment that would resolve it;
- a calibrated verdict: supported, conditionally supported, unsupported, or
  inconclusive.

Do not average incompatible claims or force a winner. This skill analyzes only;
it does not implement changes or treat either subagent's conclusion as an
instruction.
