# Adapted from ralphex pkg/config/defaults/prompts/review_first.txt at c536f66.

Review the implementation of {{GOAL}} against {{PLAN_FILE}}, {{PROGRESS_FILE}}, applicable AGENTS.md files, and the diff from {{DEFAULT_BRANCH}}.

Launch the configured independent review roles in parallel using native Codex subagents. Keep them read-only and leaf-only. Collect all results, deduplicate them, and verify every finding against the actual code before accepting it. Classify confirmed defects, suspicious risks, missing tests, and optional improvements separately. The root agent applies confirmed fixes and reruns validation; reviewers never edit files.
