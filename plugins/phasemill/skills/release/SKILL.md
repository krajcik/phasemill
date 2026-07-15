---
name: release
description: Prepare and publish a semantic release on GitHub, GitLab, or Gitea with generated notes and an exact confirmation gate. Use for "create release", "cut release", "publish version", "bump version", or "tag and release".
---

# New release

Prepare a complete release preview before any source, commit, tag, or external
mutation. Publishing is authorized only by an explicit confirmation that names
the version, target commit, changelog action, provider, and exact external
action.

## Resolve packaged helpers

Resolve these scripts relative to this `SKILL.md`:

- `scripts/detect-platform.sh`;
- `scripts/calc-version.sh`;
- `scripts/get-notes.sh`.

Invoke scripts with separate argv values. Never use a marketplace checkout
path, Claude-specific environment variables, or shell interpolation for user
content, release notes, refs, paths, or versions.

Read applicable `AGENTS.md` files and repository release documentation first.
Project rules and the current user request override this generic workflow.

## Read-only preflight

1. Resolve `major`, `minor`, or `hotfix` from the request; ask one concise
   question when it is not specified.
2. Require an attached branch and a clean staged, unstaged, and untracked
   working tree. Do not stash, discard, or commit existing changes.
3. Record the current branch and full `HEAD`. Fetch origin tags when permitted;
   if freshness cannot be established, stop before publication unless the user
   explicitly accepts local-only tag state.
4. Run `detect-platform.sh`, verify the matching provider CLI is available,
   and keep all provider lookups read-only during preview.
5. Resolve the latest `v*` tag, run `calc-version.sh` with the selected type,
   validate the result as `vX.Y.Z`, and reject an existing local or remote tag.
6. Run `get-notes.sh` for the detected provider. Deduplicate equivalent PR/MR
   and commit entries after stripping conventional prefixes, prefer PR/MR
   entries with author/number, and preserve New Features, Improvements, Bug
   Fixes, and Other grouping.
7. Detect `CHANGELOG.md`, `changelog.md`, or `CHANGELOG` with exact case. Read
   its format and prepare an in-memory patch for the new version; do not edit
   the file yet. When no changelog exists, state that no changelog is planned.

Provider CLI and API reads run through the current Codex sandbox and approval
policy. Do not diagnose authentication from a sandbox-blocked invocation.

## Preview and approval

Show one complete preview containing:

- provider and repository;
- current tag, release type, new tag, current branch, and full target commit;
- release title and final deduplicated notes;
- exact changelog path and proposed patch, or `none`;
- planned local commit message when a changelog will be changed;
- the fact that publication creates the tag/release externally and whether it
  pushes or otherwise updates a remote ref.

Ask for explicit approval of this exact preview. Editing notes, version,
changelog content, target, provider, or publication mode invalidates approval
and requires a new preview. Cancellation performs no mutation.

## Publish after approval

Immediately before mutation, recheck that branch, `HEAD`, clean status, latest
tag, and absence of the new tag still match the preview. Abort on drift.

If a changelog patch was approved, apply only that patch, validate its format,
stage only the exact changelog path, and create the exact previewed commit. Do
not include unrelated files. Record the new full `HEAD` as the release target.

Write release notes to a private temporary file with a safe file operation.
Use the detected provider CLI to create the previewed tag/release at the exact
target commit, passing notes through a file/stdin mechanism or a direct argv
value when the provider has no file option. Never embed notes in shell source.
Do not enable force, overwrite, replace, or branch deletion flags.

If changelog commit or publication fails, report the exact partial state and
stop. Do not reset, amend, delete a tag, rewrite history, or retry with broader
permissions automatically. Remove only the temporary notes file created by
this run.

## Result

Report provider, version, target commit, changelog commit when present, release
URL, exact commands that ran, and any remaining local/remote divergence. Do not
push the source branch, merge, or deploy unless the user separately requests
that action.
