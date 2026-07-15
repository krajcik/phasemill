# Adapted from ralphex pkg/config/defaults/prompts/task.txt at c536f66.

Read {{PLAN_FILE}} and {{PROGRESS_FILE}}. Execute the first Task or Iteration section with unchecked actionable boxes, and complete exactly one section during this iteration.

Before editing, inspect applicable AGENTS.md files and relevant existing code. Implement every actionable item in the selected section, add behavior-focused tests, run the narrowest validation commands, and update completed plan boxes only after validation succeeds. Record decisions, deviations, failures, and commands in the progress file. Do not commit, push, rebase, or widen permissions unless the user explicitly requested that mutation.
