---
name: status
description: Inspect or resume durable Phasemill lazy journeys and implementation runs in the current repository. Use for "Phasemill status", "what phase is running", "resume the run", or "continue Phasemill".
---

# Status and resume

Call `mcp__phasemill__lazy_status` and `mcp__phasemill__run_status` with the
absolute repository root. Pass an explicit journey id or plan only when the
user names one; otherwise discover active and recent state. These reads are
non-mutating and are the source of truth for journey/run id, phase, revision,
plan, linked run, and failure state. Never call `lazy_next` or `run_next` merely
to inspect status.

Report active or waiting lazy journeys first, labelled separately from linked
implementation runs. For a journey show journey id, phase, status, plan,
revision, pending question, execution root, linked run id/outcome, and last
update. For a run show plan, phase, status, current task, revision, restart
count, and last update. Do not infer progress from the transcript or
`update_plan` when durable state exists.

When the user asks to resume and exactly one lazy journey is active or waiting,
select it automatically, read applicable `AGENTS.md`, and invoke
`phasemill:lazy` in continue mode. If several are active, report their ids and
ask the user to choose. Do not start a new journey. When no lazy journey exists
but one implementation run is active, invoke `phasemill:run` with its plan so
that workflow calls `run_next` from the stored revision. Never call
`lazy_start` or `run_start` merely to inspect status.

Inside a registered execution worktree, lazy state intentionally remains in
the main/origin worktree. The MCP and CLI adapters resolve that origin through
the registered Git worktree list, so report and resume the same parent journey
from either location. Do not copy, migrate, or reconstruct it from run state.

If MCP is unavailable, resolve `../../engine/lazy_controller.py` and
`../../engine/plan_state.py` relative to this skill. Use lazy `status` and
`state-show` for named state only. Do not scan, parse, repair, or edit state
files directly; report structured corrupted-state diagnostics from the
adapters and leave both controllers unchanged.
