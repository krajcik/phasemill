---
name: learn
description: Extract and apply durable project guidance from the current Phasemill run, the user's corrective comments, or one explicitly named PR review. Use only when the user explicitly asks to learn, save knowledge, apply learning, or learn from a PR review.
---

# Learn

Apply durable project learning from one bounded source. Invocation authorizes
qualifying project rules and project Codex skills, but never authorizes global
writes, external posts, plugin-default changes, commits, or unrelated edits.

Before acting, read `../../defaults/prompts/learning.md` completely and use it
as the common evidence, classification, destination, validation, repair,
restore, and global-approval policy.

## Select one source

Accept exactly one source scope per pass:

- the current or explicitly named Phasemill run, including its plan, progress
  log, final diff, confirmed review findings, and corrective comments from the
  current conversation; or
- one GitHub PR explicitly identified by URL or number.

For a PR, fetch metadata, reviews, general comments, inline comments, thread
resolution, commits, and changed files read-only. Do not inspect other PRs,
repository-wide review history, or background activity. Do not post or resolve
anything.

## Execute the common policy

Apply the common prompt to the selected source exactly once. Its project
allowlist, rule-versus-skill classification, link convention, validation,
bounded repair, scoped restore, and explicit global approval gate are
authoritative; do not restate or widen them locally.

If nothing qualifies, report `no new durable Phasemill project guidance`. When
changes succeed, report provenance, classification, exact changed paths,
validation result, and repair count. Do not commit without a separate request.
