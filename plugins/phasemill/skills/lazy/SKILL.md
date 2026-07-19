---
name: lazy
description: Autonomously take an idea through durable discovery, design, plan creation and review, implementation, review, finalize, and project learning with minimal user involvement. Use for "$lazy <idea>", "lazy mode", "do this end to end", or "continue lazy".
---

# Lazy end-to-end workflow

Drive one idea through the durable Phasemill preparation controller and then
the existing run controller. A new journey creates one deterministic worktree
before project-file mutation and makes local commits after mutation-bearing
stages. Proceed automatically through reversible local work and never push.

## Resolve the installed boundary

Prefer `mcp__phasemill__lazy_start`, `mcp__phasemill__lazy_status`,
`mcp__phasemill__lazy_next`, `mcp__phasemill__lazy_record`, and
`mcp__phasemill__external_review_consent`. At handoff use
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

The journey remains anchored in its recorded origin repository while every
project mutation uses the recorded execution root. Resume it from the origin,
or route an execution-worktree resume through the registered Git common
directory. Never copy or reconstruct lazy state.

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

When the durable action/state has `commit_after_stage=true`, record `HEAD`
before every mutation-bearing action and invoke the packaged
`../../scripts/lazy-stage.py checkpoint` before controller `record`,
using the exact stable action id, deterministic message, expected pre-action
HEAD, and one `--path` per verified changed path. The helper excludes runtime
state, rejects unrelated dirt, creates no empty commit, and adds
`Phasemill-Action: <action-id>`. A replay after commit but before `record` must
reuse that exact commit; recover the original expected HEAD from its
`Phasemill-Base` trailer and never create a second commit manually.

Record `timed-out` when a bounded action exceeds its deadline. Record `failed`
for a non-recoverable local failure. Use `needs-input` only with one concrete
question, a known gate, and two or three choices when choices are natural.

### Early worktree and install-wide consent

For `kind=worktree`, the explicit `$lazy` invocation authorizes calling
packaged `../../scripts/worktree.sh lazy-plan` and `lazy-prepare` with the
returned origin, journey id, and recorded HEAD. Do not pause for another
worktree approval. Verify and record the exact returned root and branch;
repeated preparation must reuse them. A dirty or drifted origin is an ambiguity
gate and its changes must never be copied into the worktree.

For `kind=bootstrap-config`, inspect effective external-review consent. If it
is already decided, record completion without writing the repository. If it is
unset, explain that Pi/ZAI receives repository code and ask once whether to
enable read-only external review for every project in this plugin installation
or disable it globally. Persist the choice with
`mcp__phasemill__external_review_consent`; when MCP is unavailable use packaged
`config.py --plugin-data <actual PLUGIN_DATA> external-review-consent
approve|decline`. Never guess `PLUGIN_DATA`. Reload config, then record the
bootstrap action. This stage creates no project file or Git commit.

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
implementation files. When `commit_after_stage=true`, checkpoint only the plan with message
`docs(phasemill): create implementation plan`, reread it, compute the SHA-256
digest, and record exact `plan_path` and `plan_digest`.

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
When `commit_after_stage=true`, checkpoint only the plan with message
`docs(phasemill): address plan review` before recording the result.
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
- continuing after exhausted task or plan-review retries;
- amend, rebase, push, pull request, release, publish, deploy, database,
  infrastructure, or other external mutation;
- applying any user-global learning diff.

Normal Codex policy remains authoritative. Config cannot widen permissions.
Push, release, publish, deploy, worktree cleanup, and application of global
learning remain outside `$lazy`. Project learning is owned by the linked
`$run`; the only implicit Git mutations are the early worktree and
trailer-bound local stage commits.

## Handoff to the existing run

For `kind=handoff`, first use the action's recorded origin, execution root,
plan path, digest, and `matching_run_id`. Never infer a worktree path.

The execution root and branch must already be registered by early bootstrap.
Do not create a second or nested worktree at handoff. Do not run raw
`git worktree add`, move the origin branch, or remove a worktree.

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
and install-wide Pi consent gates. The
run controller remains sole owner of task, code review, Pi, finalize, retry,
and project learning transitions. `$lazy` never creates a separate learning
action or approval phase.

While driving the linked run, call the same checkpoint helper before
`run_record` whenever a task, confirmed native/Pi review fix, or finalize action
leaves Git-visible changes. Pass only paths verified against that action's
diff. For successful project learning, checkpoint only validated paths under
`.codex/phasemill/rules/**` and `.codex/skills/**` before `run_record`, using
message `chore(phasemill): complete learning` and the exact run learning action
id. Clean or restored learning creates no commit. Other mutation stages use
message `chore(phasemill): complete <phase>`. This exception applies only to a
run linked from a lazy journey whose durable `commit_after_stage` is true;
standalone `$run` never inherits it.

When the linked run reaches terminal state, call `lazy_record` once with its
exact `linked_run_id`, registered `execution_project_root`,
`execution_plan_path`, and `run_outcome`. Record no implementation phase details
in lazy state. A completed learning action may apply validated project rules
and skills. It must never apply a user-global rule, profile, role, or Codex
skill without a fresh exact diff and explicit user approval.

## Completion

At terminal `done`, report the plan, implementation run id, execution root,
validation, remaining dirty changes, applied project learning, and any
unapplied global learning candidates.
After recording lazy terminal success, honor the existing run contract for
`values.plans.move_on_completion`: move only its active execution plan and
report the new path. When that move is Git-visible and `commit_after_stage` is
true, checkpoint the verified old/new plan paths with the terminal lazy action
id and message `docs(phasemill): complete implementation plan`; an ignored or
empty move is a no-op. In worktree mode never move or delete the copied plan's
origin-worktree source. Do not push, publish, deploy, delete a plan, or remove
the worktree as part of lazy completion. At terminal `failed`, report
the controller reason and exact resume or recovery boundary without inventing
a successful outcome.
