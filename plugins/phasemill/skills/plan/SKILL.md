---
name: plan
description: Create a repository-grounded implementation plan for a feature, refactor, migration, or bug fix. Use for "make a plan", "write an implementation plan", "plan this change", or as the accepted handoff from brainstorm; do not implement the change.
---

# Planning make

Create an executable Markdown plan from repository evidence and an accepted
technical direction. This skill produces the plan only; it does not implement,
commit, create a branch, or mutate a worktree.

## Load the effective contract

Prefer `mcp__phasemill__config_resolve`. If the bundled MCP server is
unavailable, resolve `../../engine/config.py` relative to this `SKILL.md` and
never depend on the marketplace checkout path. From the repository root, run
the fallback in this exact
argument order: `python3 <config.py> --project-root <repo> [--plugin-data
<dir>] [--touched-file <path> ...] show --format json`. Global options must
precede the `show` subcommand. Include `--plugin-data` only when the actual
`PLUGIN_DATA` environment value is non-empty; never substitute the project
`.phasemill/` runtime directory or the installed plugin cache.

Read the source-labelled file at `prompts.make-plan.path`, every active rule
whose kind is `planning`, `profile`, or `instructions`, and all applicable
`AGENTS.md` files. Discover them only from the repository root down toward the
files in scope; never search above the repository root or inspect sibling
repositories. The current user request and applicable repository
instructions take precedence over plugin customization. Missing user or
project customization is normal.

Use `values.plans.directory` as the plan directory. Reject invalid effective
configuration instead of silently falling back.

Read `values.agents.planner` for the leaf planner. Its embedded default uses
`gpt-5.6-sol` with `medium` reasoning. The user owns the root-session model
choice; the plugin neither validates nor changes it. Launch one normal
read-only native leaf planner with the inherited root model and reasoning.
Treat the planner profile's `model` and `model_reasoning_effort` as future
routing hints only: they must not block planning and must not be reported as
the actual child runtime. Give the child the complete plan request, applicable
instructions, and repository context, then verify its evidence and draft in
the root task. Never use a nested Codex CLI process as a fallback.

## Discover before asking

Inspect the relevant code, tests, documentation, build configuration, and
recent repository history before asking questions. Identify:

- affected files and functions;
- current behavior and intended behavior;
- invariants and backwards-compatibility constraints;
- existing test, error-handling, cancellation, observability, and cleanup
  patterns;
- dependencies, migrations, rollout concerns, and explicit non-goals.

After identifying the repository paths in scope, rerun the config command with
one `--touched-file` per source, test, documentation, or configuration path so
language profiles and nested instructions match the planned change rather than
the plan Markdown file.

Do not ask for facts available in the repository. Ask one concise question at
a time only when different answers would materially change the plan. If this
skill received an accepted `brainstorm` handoff, reuse its evidence, decisions,
constraints, and open questions instead of repeating discovery.

When the approach is not already decided, present 2-3 viable approaches, lead
with a recommendation, and obtain the user's choice before drafting. Do not
invent false alternatives when repository constraints rule them out.

## Draft the plan

Present the complete draft in chat before writing it. Write the file only after
the user accepts the draft or explicitly asks to write without a separate
review. Name it `<YYYYMMDD>-<short-kebab-slug>.md` under the configured plan
directory and avoid overwriting an existing file.

The plan must contain:

1. a concrete objective, current behavior, intended behavior, and non-goals;
2. affected components, data/control flow, public contracts, and invariants;
3. a development approach with important decisions and rejected alternatives;
4. a testing strategy with exact narrow and broad validation commands;
5. sequential `### Task N: <outcome>` sections with actionable `- [ ]` items;
6. exact repository-relative files and functions wherever they are known;
7. compatibility, migration, documentation, and rollout work when applicable;
8. assumptions, risks, and unresolved questions without smoothing over
   uncertainty.

Each task should leave the repository in a coherent state and include its own
tests. Order tasks by dependency. Keep external approvals, deployments, manual
production actions, commits, pushes, and moving the plan to `completed/` out of
the executable checkboxes; record them as post-completion notes instead.

The phase controller recognizes only `### Task N:` and `### Iteration N:` as
execution sections. Never put actionable unchecked boxes outside those
sections, and do not include unchecked examples in fenced code blocks.

## Handoff

After the accepted plan is written, report its exact path and offer one next
action: `phasemill:plan-review`, `phasemill:run`, or stop. Do not start execution
without the user's choice.
