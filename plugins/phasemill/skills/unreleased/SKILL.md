---
name: unreleased
description: Show unreleased commits since the latest tag, with optional per-commit details. Use for "last tag", "commits since last release", "what changed since the last tag", or "unreleased changes".
---

# Commits since the last tag

This skill is read-only with respect to source and external services. Read
applicable `AGENTS.md` files first. Run Git commands from the repository root
and pass refs/hashes as argv values, never interpolated shell text.

Refresh remote tags with `git fetch origin --tags` when an origin exists and
the current sandbox/network policy permits it. If the fetch fails, report that
the result is based on local tags; do not present it as confirmed-current.

Resolve the latest reachable tag with `git describe --tags --abbrev=0`. When no
tag exists, report `No tags found in repository` and stop. Otherwise read
`TAG..HEAD` with date, author, short hash, and subject, then render:

- the latest tag;
- a Markdown table ordered as Git returns it;
- `Date`, `Commit`, and `Description` for a single author, with that author
  shown once above the table;
- an additional `Author` column when multiple authors are present;
- `No commits since this tag` when the range is empty.

After the summary, offer all commit details, one specific commit, or stop. For
details, use `git show --stat` with full author identity, date, subject, and
body. Validate a user-supplied hash as a commit before showing it. Do not create
tags, commits, branches, releases, or pushes.
