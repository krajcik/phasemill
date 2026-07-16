# Phasemill repository guidance

Phasemill is a standalone Codex plugin. Keep the runtime self-contained,
Codex-native, and independent from personal configuration.

## Invariants

- Keep `README.md`, plugin metadata, tests, and `CHANGELOG.md` aligned with every
  user-visible change.
- Preserve donor attribution in `NOTICE` and `UPSTREAM.md`.
- Resolve installed resources relative to the plugin root; never hardcode a
  developer checkout or home directory.
- Keep `.codex/phasemill/` for project configuration and `.phasemill/runs/` for
  disposable, Git-ignored runtime state.
- The MCP server owns validated config and state transitions. Codex owns tools,
  subagents, repository edits, approvals, and user-visible progress.
- Hooks are advisory. A missing hook must not corrupt or block a durable run.
- Automatic learning is proposal-only. It may read the current run, current
  user feedback, and one explicitly named PR, but may not edit files; applying
  an exact project `.codex/phasemill/` diff or explicitly requested user-global
  `PLUGIN_DATA` diff requires separate approval.
- Never launch nested `codex exec` to emulate per-agent model selection. Native
  child agents inherit the root runtime until Codex exposes supported routing.
- Pi review stays direct, read-only, fixed to `zai/glm-5.2` with `high`, and
  receives repository context through `read`, `grep`, `find`, and `ls` only.
- Do not silently push, publish, deploy, remove worktrees, or widen permissions.
  An explicit `$lazy` invocation is the narrow exception for its deterministic
  early worktree and replay-safe local stage commits; standalone skills keep
  their normal approval boundaries.

## Structure

- `.agents/plugins/marketplace.json`: one-plugin marketplace catalog.
- `plugins/phasemill/.codex-plugin/plugin.json`: Codex plugin manifest.
- `plugins/phasemill/skills/`: narrow user-facing workflows.
- `plugins/phasemill/mcp/`: dependency-free stdio MCP boundary.
- `plugins/phasemill/engine/`: config, plan, phase, and Pi adapters.
- `plugins/phasemill/defaults/`: embedded prompts, review roles, and language
  profiles.
- `plugins/phasemill/hooks/`: optional advisory hooks.
- `tests/test-codex-*.py`: executable contract tests.
- `tests/smoke/run-codex-plugin-smoke.sh`: clean-home installed-package smoke.

## Validation

Run each hyphenated test file directly; `unittest discover` cannot import those
filenames.

```bash
python3 scripts/validate-codex-plugins.py
for test_file in tests/test-codex-*.py; do python3 "$test_file" || exit 1; done
bash tests/smoke/run-codex-plugin-smoke.sh
```

Use `python3 -m py_compile` for touched Python helpers. Keep changes small and
add regression coverage for config precedence, state transitions, retries,
MCP protocol behavior, review convergence, and worktree invariants.
