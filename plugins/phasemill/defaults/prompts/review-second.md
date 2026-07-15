# Adapted from ralphex pkg/config/defaults/prompts/review_second.txt at c536f66.

Run a final focused review of {{GOAL}} against {{PLAN_FILE}}, {{PROGRESS_FILE}}, applicable AGENTS.md files, and the complete diff from {{DEFAULT_BRANCH}}.

Use the configured implementation and quality roles in parallel. Report only verified critical or major defects that can affect correctness, security, data integrity, compatibility, resource lifecycle, or completion of the stated goal. The root agent verifies and fixes accepted findings, then reruns the relevant tests.
