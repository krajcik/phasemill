# Source lineage

Phasemill is maintained as an independent Codex plugin. It is not a synchronized
fork and does not preserve donor directory boundaries or runtime behavior.

| Source | Pinned commit | Adapted area |
|---|---|---|
| `umputun/cc-thingz` | `dd01fa7f181528b564d86ce2f48c8e47a4b99011` | skill UX, review and release helpers, hooks, supporting scripts |
| `umputun/ralphex` | `c536f66ad2868796ddb0220ab00c19e6b56152a6` | prompts, phase policy, config, state, progress, retries, convergence, worktrees |

Source changes are reviewed selectively. A newer upstream commit is not copied
automatically: each useful behavior is restated against Codex-native subagents,
permissions, hooks, plugin manifests, and the Phasemill MCP boundary, then
covered by a focused regression test.

When importing additional donor code:

1. record the source repository, commit, and paths in this file or `NOTICE`;
2. preserve the donor license and copyright notice;
3. adapt path resolution to the installed Phasemill plugin root;
4. keep Codex responsible for actions and approvals;
5. add regression coverage for the imported behavior;
6. update `CHANGELOG.md` when behavior is user-visible.
