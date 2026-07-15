# Phasemill architecture

Phasemill separates durable decisions from agent execution. The local MCP
server validates configuration and emits the next revision-bound action;
Codex executes that action with its native tools and subagents, then records one
structured result.

```text
user intent
  -> focused skill
  -> Phasemill MCP (config + durable transition)
  -> native Codex action (task/review/finalize/learning)
  -> one structured result
  -> next durable transition
```

## Components

- Skills provide intent routing, repository context, mutation gates, and
  action-specific instructions.
- The dependency-free stdio MCP server exposes `plan_inspect`,
  `config_resolve`, `run_start`, `run_status`, `run_next`, `run_record`, and
  `external_review`.
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
task -> first review -> convergence review -> optional Pi review -> finalize -> learning -> done
```

Retries, review iterations, optional external review, finalization, and
automatic learning proposals are config-driven. The engine never edits
implementation or project-scope files and never treats ephemeral Codex
`update_plan` state as durable truth.

The `learning` action runs in the root Codex task because it needs the user's
current corrective comments. It may inspect only the current run and one
explicitly named PR. Its result is recorded in the run progress log, but every
project-scope change remains a separate `$learn` selection and exact-diff
approval. Learning failure is advisory and cannot retroactively fail a
validated implementation run.

Project scope is the default learning destination. An explicit user request
may route repository-independent conventions, language profiles, or complete
review roles to the installed plugin's actual `PLUGIN_DATA` tree. The project
layer retains higher precedence, and an unavailable global root is reported
rather than guessed.

## MCP boundary

The server uses newline-delimited JSON-RPC over stdio. Stdout contains protocol
messages only; logs belong on stderr. It negotiates supported MCP protocol
versions and returns tool failures as structured `isError` results while
malformed requests and unknown methods use JSON-RPC errors.

All project roots must be absolute. Plan and state paths are resolved within
that root so callers cannot escape into sibling repositories. The transport has
no third-party Python dependencies and performs no network discovery.

## Native execution boundary

Codex remains responsible for reading repository instructions, selecting tools,
launching children, applying edits, testing, approvals, and user-visible
progress. Phasemill supplies prompts and future routing hints but does not
launch nested Codex processes to force child model selection.

This boundary keeps the state machine restart-safe without replacing Codex's
native permissions, worktrees, hooks, or collaboration semantics.
