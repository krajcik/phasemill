---
name: plan-review
description: Review an implementation plan against the repository before execution. Use for "review this plan", "check the plan", "validate the implementation plan", or an interactive plan annotation pass; do not implement the plan.
---

# Planning review

Review a plan as an executable engineering contract, grounded in the current
repository. Report findings first and edit the plan only when the user asks for
revision or accepts proposed changes.

## Resolve context

Prefer `mcp__phasemill__config_resolve`. If the MCP server is unavailable,
resolve `../../engine/config.py` relative to this `SKILL.md` and invoke it as
`python3 <config.py> --project-root <repo> [--plugin-data <dir>]
[--touched-file <path> ...] show --format json`; global options must precede
the `show` subcommand. Include `--plugin-data` only for a non-empty actual
`PLUGIN_DATA` environment value, never for project `.phasemill/` runtime or the
installed plugin cache. Resolve the plan
from an explicit path first; otherwise use `values.plans.directory`, exclude
its `completed/` subtree, select the sole Markdown plan automatically, and ask
the user to choose when multiple candidates remain.

Read the complete plan, applicable `AGENTS.md` files, and the repository files
and tests named by the plan. Run the config loader with one `--touched-file`
for each planned repository path that exists or has an existing parent, then
read the active `planning`, `testing`, `review`, `profile`, and `instructions`
rule sources. Missing customization is normal; invalid configuration is not.
Discover instructions only from the repository root down toward those planned
paths; never search above the repository root or inspect sibling repositories.

## Review modes

Use semantic review by default. If the user explicitly requests interactive
annotation and a supported terminal is available, run the packaged
`../../scripts/launch-plan-review.sh` against the plan. Treat its stdout as
user annotations, revise only the annotated parts after confirmation, and
repeat until it returns no annotations. If the overlay is unavailable, report
that fact and continue with semantic review instead of blocking.

For a large or cross-cutting plan, use a bounded set of native Codex read-only
leaf subagents for independent implementation, testing, and quality review.
The root task owns fan-out, gives every reviewer the same plan and relevant
repository context, prevents reviewers from spawning further agents, and
verifies every returned claim before reporting it. Do not use nested Codex CLI
invocations as an orchestration mechanism.

Resolve each role through `values.review.agent_profiles` and then
`values.agents`; use `values.review.fallback_agent` for a project role without
an explicit mapping. Launch normal native reviewers with the root session's
inherited model and reasoning. Use the resolved role prompt and pass the full
plan, relevant repository context, and applicable instructions in each child
message. The profile's `model` and `model_reasoning_effort` remain future
routing hints; do not claim that distinct profile models ran and do not block
review because the current surface cannot apply them.

## Review contract

Check beyond prose quality:

- requirements, acceptance criteria, scope, and non-goals are complete and
  mutually consistent;
- every proposed API, file, symbol, command, and dependency is feasible in the
  current repository;
- tasks are dependency-ordered, independently verifiable, and use recognized
  `### Task N:` or `### Iteration N:` headings;
- actionable checkboxes are scoped to executable sections and do not require
  external approvals, commits, pushes, deployments, or moving the active plan;
- data flow, error handling, retries, cancellation, resource cleanup,
  concurrency, security, observability, and backwards compatibility are
  covered where relevant;
- tests assert behavior, include regressions for fixes, and name exact commands
  that match the repository toolchain;
- migrations, rollout, documentation, and rollback are explicit when needed;
- the plan neither duplicates existing machinery nor expands scope without a
  stated reason.

Separate the result into must-fix issues, risky or suspicious areas, missing
tests, and optional improvements. Each finding needs plan location, repository
evidence, consequence, and a concrete revision. Do not invent findings when
evidence is missing.

When revising, keep the existing intent and accepted decisions, make the
smallest coherent edits, then re-read the whole plan for contradictions. End
with the exact plan path, whether it is ready for execution, and one next
action: revise again, invoke `phasemill:run`, or stop.

## Invariants

- Do not implement source changes, create branches or worktrees, commit, push,
  publish, or deploy.
- Do not edit the plan merely because review was requested.
- Do not treat reviewer output as truth until the root task verifies it.
- Keep Claude-only hooks and tool syntax out of the Codex workflow.
