# Verifying Phasemill

## Repository checks

```bash
python3 scripts/validate-codex-plugins.py
for test_file in tests/test-codex-*.py; do python3 "$test_file" || exit 1; done
bash tests/smoke/run-codex-plugin-smoke.sh
```

The contract suite covers the manifest, MCP protocol, config precedence,
language-profile selection, durable lazy and run state, retry and convergence
behavior, Pi adapter, skills, hooks, release safeguards, and worktree isolation.

The smoke test creates a clean temporary `CODEX_HOME`, adds the local
marketplace, installs `phasemill@phasemill`, and exercises the installed copy.
It executes an interrupted and resumed lazy journey through discovery, design,
exclusive planning, findings/fix, exact run handoff, synthetic run completion,
and terminal lazy completion. It verifies stable action replay, durable waiting,
ignored runtime state, unchanged HEAD and branch, and no commit, push, project
learning write, network request, or model call. The original planning and run
smoke remains part of the same check.

## Manual signed-in check

Use a disposable repository with `/.phasemill/runs/` ignored:

1. Start `$lazy` from an idea, interrupt during discovery or design, and use
   `$status` to confirm the same action and revision resume without a separate
   plan-acceptance prompt. Supply requested input and confirm the same phase
   continues durably.
2. Continue that same `$lazy` journey through exclusive plan creation and its
   bounded review/fix loop. Interrupt once and confirm `$lazy continue` returns
   the same revision-bound action without creating another journey or plan.
3. Let `$lazy` hand the validated plan to `$run`. Interrupt after run creation,
   resume from `$status`, and confirm the existing plan-keyed run is linked
   rather than starting a duplicate. In worktree mode, confirm handoff pauses
   for approval and uses the exact path and branch reported by `worktree.sh`.
4. Continue through native review, optional Pi review, finalize, and learning.
   Confirm terminal `$status` reports one completed lazy journey and its linked
   run, and that learning only displays a proposal.
5. Confirm native implementation and read-only review children inherit the root
   Codex runtime; configured per-role profiles should be reported only as
   routing hints.
6. With Pi enabled, confirm the adapter reports elapsed time, turns, tool calls,
   last event, current tool, and partial output on timeout.
7. Add a corrective user comment or name a test PR, then confirm the learning
   action proposes an evidence-linked `.codex/phasemill/` diff without writing
   it. Confirm `$learn` asks once for candidate selection and again for the
   regenerated exact diff.
8. Explicitly request a reusable language rule globally and confirm its
   proposal targets the actual `${PLUGIN_DATA}/profiles/<language>.md`, while
   an unset global root fails closed and project-specific guidance remains
   under `.codex/phasemill/`.
9. Confirm commit, push, release, deploy, and worktree mutations still require
   separate explicit approval.

Live model and network checks are intentionally separate from the offline suite
because they depend on user credentials, provider availability, and selected
Codex runtime.
