---
name: run
description: Execute an accepted implementation plan through the durable native Codex task, review, Pi external-review, finalize, and proposal-only learning state machine. Use for "execute this plan", "implement the plan", "run planning exec", or "continue the plan".
---

# Run

Execute an accepted plan through native Codex orchestration. The bundled phase
controller owns durable sequencing and retries; the root Codex task owns tools,
subagents, verification, approvals, and all repository mutations.

## Resolve packaged helpers and the plan

Prefer the bundled MCP tools `mcp__phasemill__run_start`,
`mcp__phasemill__run_status`, `mcp__phasemill__run_next`,
`mcp__phasemill__run_record`, and `mcp__phasemill__external_review`. They are
the typed state-machine boundary. Resolve these fallback paths relative to this
`SKILL.md` only when the MCP server is unavailable:

- `../../engine/config.py` for effective configuration;
- `../../engine/phase_controller.py` for durable actions;
- `../../engine/pi_review.py` for independent read-only review;
- `../../scripts/worktree.sh` for guarded, restart-safe Git worktree setup;
- `../../scripts/detect-branch.sh` for local default-branch
  detection.

Never assume a marketplace checkout path and never orchestrate by launching a
nested Codex CLI process.

Resolve an explicit plan path first. Otherwise load effective config, list
Markdown files under `values.plans.directory` excluding `completed/`, use the
sole candidate automatically, and ask the user to choose when multiple plans
remain. Read the plan and applicable `AGENTS.md` files before mutation. Discover
instructions only from the repository root down toward files in scope; never
search above the repository root or inspect sibling repositories. Reject
an invalid config or a plan without executable `### Task N:` or `### Iteration
N:` sections.

Invoke the config loader as `python3 <config.py> --project-root <repo>
[--plugin-data <dir>] [--touched-file <path> ...] show --format json`; global
options must precede the `show` subcommand. Include `--plugin-data` only for a
non-empty actual `PLUGIN_DATA` environment value; never substitute project
`.phasemill/` runtime or the installed plugin cache. Extract the source, test,
documentation, and configuration paths named by the plan, then rerun config
loading with one `--touched-file` per existing path or path with an existing
parent. Do not use the plan Markdown path as a substitute: language profiles
and nested instructions must be scoped to the planned repository changes. Detect the
default branch locally with the packaged helper; do not fetch merely to detect
it.

If `worktree.enabled` is true or the user requests isolation, call
`worktree.sh plan` first. It is read-only and returns the deterministic branch,
worktree path, and active plan path. Present those exact values and obtain
explicit approval before calling `worktree.sh prepare`. Do not run raw `git
worktree add` or reproduce its safety checks in the skill.

`prepare` must preserve the main branch and HEAD, rejects changes outside the
plan, creates or reuses the deterministic sibling worktree, copies an untracked
or modified plan without committing it, and returns line-oriented fields. Use
the returned `project_root` and `plan_path` for config loading, the controller,
subagents, tests, reviews, and finalization. A resumed run calls `prepare`
again; the helper reuses the registered branch/path and never overwrites the
worktree's newer plan copy. If the current repository is already that linked
worktree, reuse still resolves through the main worktree.

New worktree preparation requires the main worktree to remain on the detected
default branch. When that guard fails, offer in-place execution or stop; do not
move or detach an existing feature branch implicitly. Do not create a branch or
worktree when isolation was not selected.

Never remove the worktree automatically. `worktree.sh remove --yes` is a
separate user-requested cleanup operation and refuses a dirty worktree. When
`plan_copied=true`, the original plan in the main working tree remains in place
and must be reported at completion; isolation must not silently delete it.

## Drive the action protocol

Start or resume the controller with the repository root, detected default
branch, touched files, and plan path. Use `run_status` first when the user asks
to continue without naming a plan. Use `run_start` only for a new or explicitly
restarted run and `run_next` for an existing run. Treat the returned structured
content as the sole phase authority. The Python CLI exposes the same protocol
as a fallback.

The controller writes only runtime data under `.phasemill/runs/`, outside
Codex's protected `.codex/` configuration tree. Before the first run, verify
that `/.phasemill/runs/` is ignored by repository Git rules. If it is not,
obtain approval before adding that exact entry to `.gitignore`; stop if the
user declines. Never include runtime files in implementation fingerprints,
reviews, commits, or published artifacts.

For every action:

1. Mirror its phase and selected task in native `update_plan` so the user can
   see current progress, but never use `update_plan` as durable state.
2. Execute exactly the returned `kind` using its rendered prompt and metadata.
3. Send one result object to `run_record`, with the exact `actionId`. With the
   CLI fallback, send short JSON on stdin to `phase_controller.py record` or
   write long/multiline JSON to a sandbox-writable temporary file and pass it
   with `--result-file PATH`, always using the exact `action_id`. Never put a
   result payload in argv or invoke `record` without an input source. Never edit
   the state or progress files directly. Remove a temporary result file after
   the controller accepts it.
4. Continue with the action returned by `run_record`. Repeating `run_next` before a
   result must return the same revision-bound action; never guess past it.
5. Stop only at terminal `done` or `failed`, and report the controller reason.

Respect configured session, idle, and iteration delays when they are non-zero.
Record `timed-out` instead of silently retrying outside the controller. Normal
Codex sandbox and approval policy always applies; plugin config cannot widen
permissions.

## Execute task actions

For `kind=task`, announce the selected task and give exactly one native
implementation subagent the action prompt, selected task, full plan path,
progress path, applicable instructions, and relevant repository context. The
implementation agent may edit only in the selected project root and may not
spawn more agents.

Launch a normal native child with the current root session runtime. The child
inherits the model and reasoning effort selected by the user for the root
session. `action.agent.model` and `action.agent.model_reasoning_effort` remain
future routing hints and must not block execution or be reported as the actual
runtime. Include the action's complete task, plan, instructions, and repository
context in the child message. On a first attempt, use the returned default
profile prompt unless the plan makes one of the returned `agent_options`
objectively
applicable: select `cross-module` only for coordinated changes across multiple
modules or public boundaries, and select `mechanical` only for a bounded edit
with known files, an unambiguous result, and a predetermined validation test.
State the selected option in progress. A retry action already selects the
recovery prompt profile and must not be downgraded. Do not launch a nested
Codex CLI process to emulate per-agent model selection.

The root task then inspects the diff, runs the narrowest relevant tests, checks
that every completed checkbox is truthful, and fixes only small integration
issues itself. Record:

- `completed` only after the task's behavior and validation pass and its
  checkboxes are updated;
- `failed` for an implementation or validation failure that should use the
  configured retry budget;
- `timed-out` when the configured deadline expires.

Do not commit, push, rebase, publish, deploy, or broaden permissions as part of
a task action unless the user separately requested that mutation.

## Execute review actions

Before a review, capture `head_before` and a deterministic `diff_before`
fingerprint covering staged, unstaged, and untracked worktree content.

For `kind=review`, launch one native read-only leaf reviewer per returned role,
bounded by `max_parallel_agents`; queue remaining roles rather than exceeding
the bound. Give each reviewer the action prompt, its role prompt, plan, final
diff, relevant code and tests, and applicable instructions. Reviewers cannot
edit files or spawn agents.

Every returned role includes its future `agent.name`, `agent.model`, and
`agent.model_reasoning_effort` routing hints. Use its role prompt, but launch
the reviewer with the inherited root runtime. A project role without an
explicit mapping is already resolved by the controller to the configured
fallback reviewer. Do not claim that the hinted model ran.

Require findings to include severity, file and line, concrete evidence,
consequence, proposed fix, and a validation test. The root task deduplicates
and verifies every finding against the repository. Dismiss unsupported claims.
Apply confirmed fixes through the root task or one implementation agent, rerun
relevant validation, and capture `head_after` plus the same deterministic
`diff_after` fingerprint.

Record `clean` when no confirmed actionable findings remain. Record `findings`
with both snapshots when confirmed findings were addressed. If confirmed
must-fix issues remain unresolved or validation fails, record `failed` instead
of letting the controller's no-change convergence rule advance the run.

## Execute external review actions

For `kind=external-review`, invoke `mcp__phasemill__external_review` with the
action's command, wall and idle timeouts, required flag, repository root, and
rendered prompt. If MCP is unavailable, invoke only the packaged
`pi_review.py`, pass the prompt through stdin, and keep every argument separate.
Never put the prompt on a command line or interpolate it into shell source.

External Pi review sends repository code, diff, plan, and applicable
instructions to the configured third-party model. When effective config
`review.external.data_sharing_approved=true`, treat that project-owned setting
as durable prior authorization and do not pause for another user confirmation.
When it is false, obtain explicit approval before the first external review in
the run. This consent never bypasses Codex sandbox, network, managed, or tenant
policy and never converts a denied or failed required review into success.

The adapter is the security boundary: Pi runs direct without proxy, uses
`zai/glm-5.2` at `xhigh`, receives the full repository as cwd, and has only the
read-only `read,grep,find,ls` tools. Do not call Pi directly or grant additional
tools.

Parse the adapter JSON. Preserve its elapsed time, turns, tool calls, last
event, current tool, and partial output in timeout/failure summaries. Verify Pi
findings exactly like native review findings, apply confirmed fixes, rerun
tests, and report before/after HEAD and diff fingerprints. Map adapter success
with no confirmed findings to `clean`, addressed findings to `findings`, an
optional unavailable review to `skipped`, and required failures or unresolved
must-fix findings to `failed`.

## Finalize and complete

For `kind=finalize`, execute only the returned prompt. Re-read the final diff,
plan, progress, documentation, and validation results. Finalize never implies
fetch, rebase, squash, commit, push, publish, deploy, or worktree deletion;
those require a separate explicit user request. Record `completed`, `failed`,
or `timed-out`.

For `kind=learning`, execute the returned proposal-only prompt in the root task
so it can inspect the current conversation as well as the plan and progress
log. Do not delegate this action: a child does not have reliable access to the
user's corrective comments. Inspect only the current run and a PR explicitly
named by the user, current conversation, or plan. Any GitHub access is
read-only and must not scan unrelated PRs or repository history.

Do not edit `.codex/phasemill/` or any other file during the learning action.
Return `completed` with the complete numbered proposal in `summary` when
durable candidates exist, `clean` when no evidence qualifies, and
`failed`/`timed-out` only for diagnostics. Learning is advisory: all outcomes
finish the already successful implementation run. Display candidates to the
user, but defer selection and mutation to a separate `phasemill:learn`
interaction with a fresh exact diff and approval.

Project scope is the default. A proposal may target actual user-global
`PLUGIN_DATA` rules, language profiles, or agent roles only when the user
explicitly requested global learning. Never infer the global directory or
promote repository-specific guidance into it.

After terminal `done`, if `values.plans.move_on_completion` is true, move the
active plan into the sibling `completed/` directory without committing the
move and report the new path. In worktree mode this means only the returned
worktree plan; never move or delete a copied plan's main-worktree source. Do
not move it earlier because later phases still use the original path. Leave
the plan in place on terminal `failed`.

Finish with completed task count, review phases, external-review status,
learning proposal status, exact validation commands and results, remaining
risks, final branch/worktree, plan path, and whether any user-requested Git
mutation was performed.
