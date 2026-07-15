# Verifying Phasemill

## Repository checks

```bash
python3 scripts/validate-codex-plugins.py
for test_file in tests/test-codex-*.py; do python3 "$test_file" || exit 1; done
bash tests/smoke/run-codex-plugin-smoke.sh
```

The contract suite covers the manifest, MCP protocol, config precedence,
language-profile selection, durable state, retry and convergence behavior,
Pi adapter, skills, hooks, release safeguards, and worktree isolation.

The smoke test creates a clean temporary `CODEX_HOME`, adds the local
marketplace, installs `phasemill@phasemill`, and exercises the installed copy.
It verifies that no commit, push, network request, or model call occurs.

## Manual signed-in check

Use a disposable repository with `/.phasemill/runs/` ignored:

1. Ask `$plan` for a one-task accepted plan.
2. Ask `$plan-review` to validate it against the repository.
3. Start `$run`, interrupt after the first durable action, and use `$status` to
   confirm the same action and revision are resumed.
4. Confirm native implementation and read-only review children inherit the root
   Codex runtime; configured per-role profiles should be reported only as
   routing hints.
5. With Pi enabled, confirm the adapter reports elapsed time, turns, tool calls,
   last event, current tool, and partial output on timeout.
6. Add a corrective user comment or name a test PR, then confirm the learning
   action proposes an evidence-linked `.codex/phasemill/` diff without writing
   it. Confirm `$learn` asks once for candidate selection and again for the
   regenerated exact diff.
7. Explicitly request a reusable language rule globally and confirm its
   proposal targets the actual `${PLUGIN_DATA}/profiles/<language>.md`, while
   an unset global root fails closed and project-specific guidance remains
   under `.codex/phasemill/`.
8. Confirm commit, push, release, deploy, and worktree mutations still require
   separate explicit approval.

Live model and network checks are intentionally separate from the offline suite
because they depend on user credentials, provider availability, and selected
Codex runtime.
