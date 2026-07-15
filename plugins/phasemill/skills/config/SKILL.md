---
name: config
description: Inspect, validate, or initialize project and user customization for the Phasemill Codex workflow. Use for config precedence, native agent routing hints, prompts, review roles, language profiles, rules, Pi review settings, retries, timeouts, proposal-only learning, finalize, or worktree options.
---

# Planning configuration

Prefer the bundled `mcp__phasemill__config_resolve` tool. It returns the same
validated values, origins, profiles, roles, and rule paths without requiring
the model to construct a shell command. If the MCP server is unavailable, use
the deterministic `../../engine/config.py` loader packaged with this plugin.
Resolve fallback paths relative to this `SKILL.md`; do not assume the
marketplace checkout remains available after installation.

## Inspect

Call `config_resolve` with the absolute `projectRoot` and one `touchedFiles`
entry per file in the current task or diff so polyglot profile detection stays
scoped. The fallback is `python3 <script> --project-root <repo>
--touched-file <path> ... show`; use `--format json` when another deterministic
helper consumes the result.

Explain the effective value and its reported origin. Do not print prompt bodies, rule bodies, environment variables, or credentials merely to explain configuration.

## Validate

Run `python3 <script> --project-root <repo> validate`. Treat unknown keys, wrong types, invalid ranges or durations, invalid future native-agent model/reasoning profiles, references to missing or disabled native agents, an external-review idle timeout that is not shorter than its wall timeout, unknown review roles or language profiles, conflicting profile lists, and changes to the fixed Pi security/model contract as errors. Per-agent model profiles are retained for future native routing; current Codex children inherit the root session runtime. Do not silently discard an invalid higher-precedence value.

Native agent profiles live under `values.agents`. Sol is the default for
planning, implementation, recovery, and correctness review; Luna is limited to
bounded exploration, documentation, and summaries. Mechanical changes use Sol
low; ordinary implementation uses Sol medium; cross-module work uses Sol high;
and a failed implementation escalates to Sol xhigh. The
bundled `terra` profile remains disabled until a project or user layer sets
`agents.terra.enabled=true` and explicitly routes an action or review role to
it. A project can override every role independently, for example
`--set 'agents.review-quality.model="gpt-5.6-sol"' --set
'agents.review-quality.model_reasoning_effort="xhigh"'`.

`values.learning.auto_propose` controls only the automatic proposal check after
a successful full run. It does not authorize writes and does not disable an
explicit `phasemill:learn` request. Project-scope learning always retains its
candidate-selection and exact-diff approval gates.

The same gates apply to user-global learning. It is available only on an
explicit request and only under the actual `PLUGIN_DATA` `rules/`, `profiles/`,
or `agents/` tree. Project customization keeps higher precedence over this
user-global layer.

## Initialize

Only when the user explicitly asks to create project customization, run `python3 <script> --project-root <repo> init --yes`. Initialization creates comment-only examples under `.codex/phasemill/`, skips existing files, and leaves embedded defaults effective until examples are deliberately uncommented or filled in.

## Invocation overrides

For a one-run override, place `--set dotted.path=<TOML value>` before the subcommand. Examples: `--set review.max_iterations=2`, `--set 'agents.implementer.model_reasoning_effort="medium"'`, `--set finalize.enabled=true`, or `--set 'profiles.enable=["go"]'`. Invocation values are ephemeral and have the highest plugin-config precedence; they never override Codex safety policy, the current user request, or applicable `AGENTS.md` instructions.
