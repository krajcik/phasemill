# Independent review prompt adapted from ralphex external-review contracts at c536f66.

Review {{GOAL}} in the active repository. Read the diff from {{DEFAULT_BRANCH}}, {{PLAN_FILE}}, applicable instructions, and any source needed to trace behavior. Stay inside the repository and do not read ignored credential files, secrets, or unrelated user paths. Report only actionable findings with severity, file and line, impact, and a concrete fix. Return NO ISSUES FOUND when no actionable issue remains.

Prioritize the highest-risk changed code and finish with a concise review. The
adapter supplies the authoritative tool-call budget even when this prompt is
replaced by project customization.
