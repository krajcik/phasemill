# Phasemill architecture

Phasemill separates durable decisions from agent execution. The local MCP
server validates configuration and emits the next revision-bound action;
Codex executes that action with its native tools and subagents, then records one
structured result.

```text
user intent
  -> focused skill or $lazy
  -> Phasemill MCP (config + durable preparation/run transition)
  -> native Codex action (task/review/finalize/learning)
  -> one structured result
  -> next durable transition
```

## Components

- Skills provide intent routing, repository context, mutation gates, and
  action-specific instructions.
- The dependency-free stdio MCP server exposes `plan_inspect`,
  `config_resolve`, `lazy_start`, `lazy_status`, `lazy_next`, `lazy_record`,
  `run_start`, `run_status`, `run_next`, `run_record`, and `external_review`.
- The engine validates layered configuration, parses plans, persists run state,
  applies retry and convergence policy, and wraps Pi.
- Native Codex subagents implement tasks and perform bounded read-only reviews.
- Hooks suggest relevant skills and inject compact active-run context. They do
  not advance state.

## State-machine contract

Every action has an identity bound to the run revision. Calling `run_next`
again before recording a result returns the same action. `run_record` accepts
the exact action identity once, persists the result, and returns the next
action. Stale and out-of-order results are rejected.

The normal flow is:

```text
task -> first review -> convergence review -> required Pi review -> finalize -> learning -> done
```

The lazy preparation flow is:

```text
early worktree -> install consent checkpoint -> discovery -> design -> exclusive plan
-> bounded plan review/fix -> exact run handoff
```

Lazy actions use the same revision-bound replay contract. Waiting for user
input preserves the current phase. Runtime state stays in the origin while all
project mutation uses the early execution worktree; handoff records its exact
root, branch, and plan digest before linking one
normal run. Restarting across that boundary reuses the matching run instead of
starting a second one.

Retries, review iterations, configured external review, finalization, and
automatic project learning are config-driven. The engine never edits
implementation or project-scope files and never treats ephemeral Codex
`update_plan` state as durable truth.

Lazy mode additionally owns its deterministic early worktree, install consent
bootstrap, and local mutation-stage checkpoints. Stable action trailers make a
commit replay-safe across the commit-before-record crash window. Ambiguity,
overlapping active work, permission changes, external mutations, and exhausted
policy limits still pause the journey; push, release, publish, deploy, worktree
cleanup, and user-global learning retain their explicit gates. Linked lazy
runs checkpoint validated project-learning paths through the existing
replay-safe stage helper.

The `learning` action runs in the root Codex task because it needs the user's
current corrective comments. It may inspect only the current run and one
explicitly named PR. A compact invariant goes to
`.codex/phasemill/rules/`; a reusable multi-step procedure goes to
`.codex/skills/<name>/SKILL.md`. Project changes apply without another
approval, are validated with at most two repair attempts, and restore only
their own paths on failure. Learning remains advisory and cannot retroactively
fail a validated implementation run.

An explicit user request may route repository-independent guidance to the
installed plugin's actual `PLUGIN_DATA` tree or an exact global Codex skill
root. Every global write requires approval of a fresh exact diff; unavailable
roots are reported rather than guessed, and the project layer retains higher
precedence.

## MCP boundary

The server uses newline-delimited JSON-RPC over stdio. Stdout contains protocol
messages only; logs belong on stderr. It negotiates supported MCP protocol
versions and returns tool failures as structured `isError` results while
malformed requests and unknown methods use JSON-RPC errors.

All project roots must be absolute. Plan and state paths are resolved within
that root so callers cannot escape into sibling repositories, except for an
already approved worktree bound to the same lazy journey. The transport has no
third-party Python dependencies and performs no network discovery.

## Native execution boundary

Codex remains responsible for reading repository instructions, selecting tools,
launching children, applying edits, testing, approvals, and user-visible
progress. Phasemill supplies prompts and future routing hints but does not
launch nested Codex processes to force child model selection.

This boundary keeps the state machine restart-safe without replacing Codex's
native permissions, worktrees, hooks, or collaboration semantics.
