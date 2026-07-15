---
name: git-review
description: Open an interactive local Git diff for user annotations and address the accepted feedback in a loop. Use for "git review", "annotate changes", "interactive diff review", or "open this diff for review".
---

# Interactive Git review

Use `git-review.py` packaged next to this skill. Resolve it relative to this
`SKILL.md`; do not assume a marketplace
checkout path.

Read applicable `AGENTS.md` files before running the overlay. Invoke the script
from the repository root, passing the user's optional base ref and branch as
separate argv values. Do not shell-interpolate either value.

The script reviews uncommitted staged, unstaged, and untracked files when they
exist; otherwise it compares the current branch to the detected default branch.
It opens a cleaned diff in a supported terminal overlay and prints only the
user's annotations as a diff.

For every annotation pass:

1. Read all annotations and map them back to the real repository files.
2. Separate actionable requests, questions, and ambiguous notes. Verify each
   claim against the current code and applicable instructions.
3. Present a compact change plan before editing. Straightforward annotations
   are user-directed edits; ask only when an annotation is ambiguous, unsafe,
   or would materially expand scope.
4. Apply the smallest coherent changes, run narrow validation, and report any
   annotation that was declined with concrete evidence.
5. Run the overlay again against the updated diff. Stop when it returns no
   annotations or the user asks to stop.

If no supported overlay terminal is available, report the script error and
offer a normal semantic diff review; do not pretend that interactive review
occurred. Do not commit, push, rebase, publish, deploy, or delete source files
as part of this skill. The script's temp review repository is not the source
repository and must not be treated as implementation state.
