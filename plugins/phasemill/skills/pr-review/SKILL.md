---
name: pr-review
description: Review a GitHub pull request or investigate a GitHub issue, with quick or full repository-context analysis and a locally drafted comment. Use for "review PR", "check this pull request", "look at PR changes", "review issue", or "draft an issue comment".
---

# Pull request and issue review

Default to read-only investigation and a local draft. Posting a comment,
submitting a formal review, approving, requesting changes, or merging are
separate external mutations and require the user's explicit approval for the
exact action and current draft.

Use GitHub CLI through the current Codex sandbox and approval policy. Do not
diagnose authentication from a sandbox-blocked command. Never use a GitHub
mutation merely to gather review context.

## Resolve the target and guidance

Accept a PR/issue URL or number. For an ambiguous number, use read-only metadata
to distinguish a pull request from an issue. If no target was supplied, list a
small set of recent candidates and ask the user to choose.

Read `../../references/review-customization.md` relative to this skill. Load
applicable `AGENTS.md`, source-labelled user/project review rules, and only the
embedded/user/project language profiles matching changed files. Give the same
effective guidance to every reviewer.

## Issue flow

For an issue, fetch its title, body, labels, state, linked work, and full
discussion. Inspect repository code only where the report references behavior,
files, or symbols. Distinguish reproduced facts from hypotheses, then present
root-cause evidence, a proposed approach, material questions, or next steps.

Draft a concise issue comment with the `writing-style` skill. Display the whole
draft locally. Post only after the user explicitly approves that draft; edits
restart approval. Issue review never creates a worktree.

## Pull request preflight

Fetch read-only PR metadata, files, base/head refs, additions/deletions,
commits, reviews, general comments, inline comments, mergeability, and CI
status. Read inline suggestions and automated findings, verify them, and track
which discussion threads are resolved. Do not re-raise an issue the user
already posted or a thread that was demonstrably resolved.

Present a compact preflight summary: purpose, author/state, size, base/head,
merge status, CI, resolved discussion, and open discussion. If the user did not
choose depth, ask for `Full review` or `Quick review`, recommending full review
for large, risky, unfamiliar, or cross-cutting changes.

## Quick review

Read the complete PR diff without creating a worktree or running tests. Explain
what changed and why, group changed files, and flag only issues supported by
the diff: obvious defects, missing error handling, hard-coded behavior, new
TODOs, missing tests, or unrelated scope. State that full-file context and
validation were not checked.

The root task verifies every finding, deduplicates it against prior discussion,
and separates must-fix issues, risky or suspicious areas, missing tests, and
optional improvements.

## Full review

Full review may create a disposable detached Git worktree only after the user
selects this mode. Fetch the PR head into a namespaced temporary ref without
checking out or changing the main worktree, then add a unique temp worktree at
that ref. Record its exact path and main HEAD/branch before and after setup.
Never use a command that switches the main checkout.

The root task launches a bounded set of native Codex read-only leaf reviewers
for implementation/architecture, correctness/quality, testing, documentation,
and simplification where those roles are relevant. Reviewers receive PR
metadata, prior discussion, the diff, full changed files, effective project
guidance, and scoped language profiles. They may run repository-standard
validation in the temp worktree but may not edit source files, post externally,
or spawn more agents.

Each finding must include severity, file and line, concrete evidence,
consequence, proposed fix, and a validation test. The root task verifies and
deduplicates every claim, checks data flow beyond changed lines, and examines
error handling, retries, cancellation, concurrency, cleanup, security,
observability, compatibility, test quality, and scope creep. Unsupported
findings are discarded, not softened into vague warnings.

Present the verified report before drafting. Keep the temp worktree for
follow-up investigation. At the end, remove it and its temporary ref only when
the worktree is clean; never force-remove a dirty worktree or delete a
non-temporary branch. If cleanup is unsafe, report the exact retained path/ref.

## Draft and external actions

Draft only new, verified points using the `writing-style` skill. Do not restate
the PR description or duplicate the user's earlier comments. Omit empty
sections; use a short `LGTM` when nothing actionable remains. Display the
complete draft and intended action before asking for approval.

After explicit approval, write the approved body to a temporary file with a
safe file operation and submit exactly one selected action: comment, approve,
or request changes. Never place the review body directly in shell text.

Approval to post a review does not authorize merging. If the user separately
asks about merging, inspect commit quality and recommend rebase, squash, or a
merge commit with a short reason. Execute the chosen merge strategy only after
a second explicit approval, and report branch-protection, conflict, or CI
failures without bypassing them.

## Output

Report review depth, validated commands and results, verified findings, prior
discussion excluded from the draft, cleanup status, the complete draft, and
whether any external mutation actually occurred.
