# Adapted from ralphex pkg/config/defaults/prompts/finalize.txt at c536f66.

Perform the explicitly enabled post-completion checks for {{GOAL}}. Review the final diff, plan state, progress log, documentation, and validation results. Do not fetch, rebase, squash, commit, push, publish, deploy, or delete worktrees without a separate explicit user request. Report the branch as ready only when the configured checks have passed.
