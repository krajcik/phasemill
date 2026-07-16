---
name: lazy
description: Autonomously take an idea through durable discovery, design, plan creation and review, implementation, review, finalize, and proposal-only learning with minimal user involvement. Use for "$lazy <idea>", "lazy mode", "do this end to end", or "continue lazy".
---

# Lazy end-to-end workflow

Drive one idea through the durable Phasemill preparation controller and then
the existing run controller. Proceed automatically through reversible local
work. Stop only at a controller terminal action or an explicit input,
permission, consent, worktree, retry, or external-mutation gate.

## Resolve the installed boundary

Prefer `mcp__phasemill__lazy_start`, `mcp__phasemill__lazy_status`,
`mcp__phasemill__lazy_next`, and `mcp__phasemill__lazy_record`. At handoff use
the existing `mcp__phasemill__run_status`, `run_start`, `run_next`, and
`run_record` protocol exactly as specified by the sibling `phasemill:run`
skill. Read that skill before executing a handoff; do not copy or weaken its
task, review, Pi, finalize, learning, worktree, or completion rules.

When MCP is unavailable, resolve `../../engine/lazy_controller.py` relative to
this `SKILL.md`. Its `start`, `status`, `next`, and `record` commands are the
only fallback state boundary. Pass long or multiline result JSON through a
temporary sandbox-writable `--result-file`, remove it after acceptance, and
never edit `.phasemill/runs/` state or progress directly. Never depend on a
marketplace checkout path or launch a nested Codex CLI process.

Resolve effective config with `mcp__phasemill__config_resolve`, or the packaged
`../../engine/config.py` fallback using `--project-root <repo>` and global
options before `show --format json`. Include `--plugin-data` only for the
actual non-empty `PLUGIN_DATA`; project `.phasemill/` runtime and installed
plugin caches are never user config. Read applicable `AGENTS.md`, active rules,
profiles, and source-labelled prompts returned by the controller. Discover
instructions only from the repository root toward paths in scope; never search
above it or inspect sibling repositories except an approved registered
Phasemill worktree.

Before the first journey verify `/.phasemill/runs/` is ignored. If it is not,
obtain approval before adding only that ignore entry. Runtime files never enter
diff fingerprints, reviews, commits, or published artifacts.

## Start or continue

For `$lazy <idea>`, normalize only surrounding whitespace and keep the exact
idea as controller input. Generate one opaque caller-stable request id once
for this invocation, retain it before calling `lazy_start`, and reuse it for
every retry of that call. Do not derive it solely from the idea: a later
intentional run of the same idea needs a new id. A lost response replay with
the retained id must return the same journey and action.

For `$lazy continue` or a resume request, call `lazy_status` first. Select the
sole active or waiting journey automatically. If several are active, show
their journey id, phase, plan, and update time and ask the user to choose. If
none is active, report that fact; do not call `lazy_start` without a new idea.
Then call `lazy_next` for the selected journey.

The journey remains anchored in its recorded origin repository. Resume it
from that origin. An execution worktree contains only its implementation run;
do not copy or migrate lazy state into it.

## Drive the exact action protocol

For each returned action:

1. Mirror its phase in native `update_plan`; this is visibility only, never
   durable authority.
2. Execute exactly the returned `kind`, prompt, roles, paths, revision, and
   limits.
3. Send one strictly typed result to `lazy_record` with the exact `action_id`.
   Do not add unknown fields or encode decisions in `summary` when a typed
   field exists.
4. Continue with the returned action. Repeating `lazy_next` before recording a
   result must return the same action id.
5. Stop at `done`, `failed`, or `input`. Never guess past a failed record or a
   stale revision.

Record `timed-out` when a bounded action exceeds its deadline. Record `failed`
for a non-recoverable local failure. Use `needs-input` only with one concrete
question, a known gate, and two or three choices when choices are natural.

### Discovery

For `kind=discovery`, launch at most one native read-only explorer leaf with
the action prompt, exact idea, repository root, applicable instructions, and
current diff context. The child cannot edit or spawn agents. The root verifies
its evidence and determines affected source, test, documentation, and config
paths.

Return a bounded non-empty verified discovery `summary` and normalized
repository-relative `scope_paths`. The controller independently captures the
canonical HEAD, staged/unstaged/untracked content fingerprint, and dirty paths;
never fabricate or pass those boundary-owned values. Do not treat pre-existing
disjoint changes as authorization to overwrite them. If scope or a material
fact cannot be established safely, record `needs-input` rather than inventing
it.

### Design

For `kind=design`, use repository evidence and the rendered prompt to choose
the smallest maintainable approach that preserves existing contracts. Continue
without asking about discoverable or non-material details. Record
`needs-input` with gate `material-design` only when different answers change
scope, architecture, compatibility, permissions, or irreversible behavior.
Do not edit source or plan files in this phase.
Record a bounded non-empty `summary` of the selected design so a resumed
journey reconstructs the same decision from durable state.

### Plan creation

For `kind=plan`, write only the exact reserved `plan_path`. The action's
`plan_write_mode=create-exclusive` requires a no-replace creation operation
such as an `apply_patch` Add File; never open an existing file for overwrite.
If the path exists, stop and return the collision diagnostic.

Follow the rendered effective make-plan guidance and active planning rules,
including executable `### Task N:` or `### Iteration N:` sections. The lazy
prompt supersedes only draft presentation and plan-acceptance waiting: create
the complete local plan without a separate acceptance pause. Do not touch
implementation files. After writing, reread it, compute the SHA-256 digest,
and record exact `plan_path` and `plan_digest`.

### Plan review and correction

For `kind=plan-review`, launch one native read-only leaf per returned role,
bounded by `max_parallel_agents`; queue excess roles. Give every reviewer the
complete plan, repository evidence, relevant code/tests, its role prompt, and
applicable instructions. Reviewers cannot edit or spawn agents.

All native children inherit the root session's model and reasoning. Returned
role `model` and `model_reasoning_effort` values are future routing hints only;
do not claim that different models ran and do not block because those hints
cannot be applied.

The root deduplicates and verifies every claim. A confirmed finding must carry
stable id, plan/repository location, evidence, consequence, and proposed fix.
Dismiss unsupported claims. Record `clean` only when no confirmed must-fix
finding remains; otherwise record typed `findings`.

For `kind=plan-fix`, edit only the reserved plan, apply only verified findings,
preserve intent and executable structure, and re-read the whole document.
Bind the result to the action's old digest using `previous_plan_digest`, then
record the same `plan_path` and the new SHA-256 `plan_digest`. Every fix returns
to review; never bypass the configured convergence limit.

### Durable input and safety gates

For `kind=input`, present the exact stored question and options and end the
turn. On the user's next answer, call `lazy_status`/`lazy_next`, then record
`answered` against that exact input action with typed `decision=continue` or
`decision=stop` plus the exact answer as audit text. A negative or stop answer
must use `decision=stop` and terminates the journey; it must never resume the
preserved phase. Continue is scoped to that gate and is not blanket or durable
permission for later operations.

Pause with `needs-input` before:

- a material design choice or overlapping dirty scope;
- any new sandbox, network, or write permission;
- `worktree.sh prepare` and every worktree creation;
- Pi data sharing when effective consent is absent;
- continuing after exhausted task or plan-review retries;
- commit, amend, rebase, push, pull request, release, publish, deploy, database,
  infrastructure, or other external mutation;
- applying any learning proposal locally or globally.

Normal Codex policy remains authoritative. Config cannot widen permissions.
Commit, push, release, publish, deploy, worktree cleanup, and application of
learning proposals remain outside `$lazy` even after an answer; report them as
separate possible follow-ups instead of performing them implicitly.

## Handoff to the existing run

For `kind=handoff`, first use the action's recorded origin, execution root,
plan path, digest, and `matching_run_id`. Never infer a worktree path.

If worktree mode is enabled and no execution coordinates are registered:

1. call packaged `../../scripts/worktree.sh plan` read-only;
2. present its exact branch, root, worktree, and plan values;
3. record `needs-input` with gate `worktree-approval`, exact
   `approved_main_root`, `approved_execution_root`, `approved_branch`, and
   repository-relative `approved_plan_path`, then obtain explicit approval;
4. in the resumed current permission context call `worktree.sh prepare`;
5. verify its returned `main_root`, `project_root`, absolute `plan_path`, branch,
   and plan digest; convert that exact absolute plan path to its confined
   repository-relative path under the returned `project_root`, then record the
   execution root, relative plan path, and `execution_branch` as a completed
   preparation result without a run id. They must exactly match the durable
   approved helper coordinates; another registered worktree is not acceptable.

Do not run raw `git worktree add`, move the origin branch, or remove a worktree.
If preparation is interrupted before coordinates are recorded, inspect and
reuse the deterministic registered worktree; never create another.

Before `run_start`, query `lazy_next` again and call `run_status` for the exact
execution plan. If the handoff action has a `matching_run_id`, or a plan-keyed
run appeared after a lost `run_start` response, call `run_next` and resume it;
never start a second run. An unrelated active run must not be linked. Call
`run_start` only when no exact plan-keyed run exists.

Drive that implementation through the complete `phasemill:run` contract. Pass
the validated execution plan, applicable touched paths, and every exact
`run_requirements.overrides` entry to `run_start`, `run_status`, `run_next`, and
`run_record` wherever those tools accept overrides. These temporary overrides
are the origin journey's run-relevant effective settings and must remain
unchanged for the linked run in an execution worktree. Follow all permission
and Pi consent gates. The
run controller remains sole owner of task, code review, Pi, finalize, retry,
and proposal-only learning transitions.

When the linked run reaches terminal state, call `lazy_record` once with its
exact `linked_run_id`, registered `execution_project_root`,
`execution_plan_path`, and `run_outcome`. Record no implementation phase details
in lazy state. A completed learning action may display numbered proposals, but
never applies `.codex/phasemill/`, user-global rules, profiles, or agent roles;
application requires a later explicit `phasemill:learn` interaction.

## Completion

At terminal `done`, report the plan, implementation run id, execution root,
validation, remaining dirty changes, and any proposal-only learning candidates.
After recording lazy terminal success, honor the existing run contract for
`values.plans.move_on_completion`: move only its active execution plan and
report the new path. In worktree mode never move or delete the copied plan's
origin-worktree source. Do not commit, push, publish, deploy, delete a plan, or
remove the worktree as part of lazy completion. At terminal `failed`, report
the controller reason and exact resume or recovery boundary without inventing
a successful outcome.
