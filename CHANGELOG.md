# Changelog

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
