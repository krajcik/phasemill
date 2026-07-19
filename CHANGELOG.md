# Changelog

## Unreleased

## Phasemill v1.6.0 - 2026-07-19

### Changed

- focus lazy plan review on implementation and quality reviewers by default
  while retaining testing review after implementation
- raise the default lazy plan-review convergence limit from 2 to 7 iterations

## Phasemill v1.5.0 - 2026-07-19

### Changed

- let brainstorm and plan review automatically escalate one unresolved,
  high-impact falsifiable claim to bounded dialectic analysis while keeping
  preferences, routine findings, and directly verifiable questions local

## Phasemill v1.4.0 - 2026-07-16

### Changed

- require the independent read-only Pi review by default and persist one
  explicit Pi/ZAI data-sharing choice per plugin installation instead of per
  project
- keep a global opt-out, project and user overrides, and all Codex sandbox and
  managed-policy approval boundaries

## Phasemill v1.3.0 - 2026-07-16

### New features

- make `$lazy` create one deterministic worktree before project mutation,
  bootstrap project-owned Pi consent on first use, and create replay-safe local
  commits after every mutation-bearing stage without ever pushing
- add `[lazy] worktree` and `commit_after_stage` project overrides while
  preserving standalone `$run` worktree and commit behavior
- resume the same origin-owned lazy journey from either the main repository or
  its registered execution worktree
- add `$lazy` for a durable autonomous journey from an idea through discovery,
  design, exclusive planning, bounded plan review/fix, normal execution, and
  proposal-only learning
- expose typed lazy start, status, next, and record MCP tools with replay-safe
  waiting and an exact origin-bound handoff to the normal run state machine
- include lazy journeys and their linked runs in `$status` and advisory runtime
  context without letting status or hooks advance durable state

### Safety

- bind lazy commits to stable action ids with `Phasemill-Action` trailers,
  reject unrelated dirty paths or HEAD drift, reuse commits after a
  commit-before-record crash, and avoid empty commits
- preserve valid project TOML comments and layout while enabling external-review
  consent, and refuse malformed or schema-invalid configuration without writes
- preserve accepted dirty-overlap answers in the durable progress log when
  repository drift forces the input gate to refresh
- run Pi/GLM review at `high` reasoning and append a fixed 40-tool budget that
  stops broad exploration after 30 calls and requires a concise final result,
  while extending the wall timeout from 15 to 20 minutes so nearly complete
  reviews are not discarded at the previous boundary
- preserve explicit gates for ambiguity, overlapping work, permissions,
  worktrees, Pi data sharing, external mutations, commits, publishing,
  deployment, cleanup, and application of learning proposals
- extend installed-cache smoke coverage across interrupted lazy preparation,
  findings/fix, handoff, synthetic run completion, and terminal lazy completion
  with no model, network, Git, or project-learning mutation

## Phasemill v1.2.0 - 2026-07-15

### Fixed

- preserve Pi provider, model, upstream `errorMessage`, and a bounded stderr
  tail when required external review fails, instead of reporting only a
  context-free `stopReason='error'`
- run Pi with an isolated temporary config directory and pass only the stored
  ZAI API key through the child environment, avoiding sandbox-denied writes to
  `~/.pi/agent` during autonomous `codex exec` runs
- make the phase-controller CLI reject a missing `record` payload within one
  second and accept long or multiline results through `--result-file`, avoiding
  indefinite fallback hangs and oversized shell arguments

### New features

- add project-scoped `review.external.data_sharing_approved` consent so an
  autonomous run can invoke Pi without a repeated workflow confirmation while
  remaining subject to Codex and tenant policy

## Phasemill v1.1.0 - 2026-07-15

### New features

- add an advisory proposal-only learning phase after a successful full run
- learn durable project guidance from current-session user corrections and
  verified accepted review comments in one explicitly named PR
- route numbered evidence-linked candidates only to project-owned
  `.codex/phasemill/rules`, `profiles`, or explicitly selected agent roles
- allow explicitly requested repository-independent guidance, including
  language-specific instructions, to target the actual user-global
  `PLUGIN_DATA` rules, profiles, or agent roles
- publish Phasemill as an independent Codex plugin repository with pinned
  marketplace installation, release checks, branding, support, security,
  privacy, and submission documentation

### Safety

- automatic learning never edits files and cannot turn an already validated
  implementation into a failed run
- applying learning requires candidate selection followed by approval of a
  freshly generated exact diff; commits remain a separate request
- unrelated PR history, rejected findings, bot noise, plugin defaults,
  prompts, `config.toml`, and `AGENTS.md` are outside the learning boundary
- global learning fails closed when `PLUGIN_DATA` is unavailable and never
  promotes repository-specific guidance automatically

## Phasemill v1.0.0 - 2026-07-15

### New features

- publish one standalone Codex plugin with focused design, planning,
  implementation, review, investigation, release, and workflow skills
- add a dependency-free local stdio MCP server for typed configuration, plan
  inspection, durable run transitions, status, and independent review
- add restart-safe task, retry, bounded native review, convergence, optional
  Pi/GLM review, finalization, and guarded worktree behavior
- add layered project and user customization with source-labelled rules,
  replaceable prompts and roles, and scoped Go, Python, PHP, Java/Kotlin,
  JavaScript/TypeScript, and Rust profiles
- add advisory skill-evaluation and active-run context hooks

### Compatibility

- native Codex children inherit the root model and reasoning effort; per-agent
  profiles are retained as validated future routing hints
- independent Pi review uses direct networking, `zai/glm-5.2` at `xhigh`, full
  repository context, and read-only tools
- donor lineage and MIT attribution are preserved in `NOTICE` and
  `UPSTREAM.md`
