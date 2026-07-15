---
name: learn
description: Extract durable project guidance from the current Phasemill run, the user's corrective comments, or an explicitly named PR review, then propose exact project-scope changes for approval. Use only when the user asks to learn, save knowledge, capture learnings, apply a learning proposal, or learn from a PR review.
---

# Learn

Produce proposal-only project learning. Never treat invocation as approval to
edit files, post externally, change plugin defaults, or commit.

## Select the bounded source

Accept exactly one source scope per pass:

- the current or explicitly named Phasemill run, including its plan, progress
  log, final diff, confirmed review findings, and the user's corrective
  comments from the current conversation; or
- one GitHub PR explicitly identified by URL or number.

For a PR, fetch metadata, reviews, general comments, inline comments, thread
resolution, commits, and changed files read-only. Do not inspect other PRs,
repository-wide review history, or background activity. Do not post or resolve
anything.

If applying candidates produced by the automatic learning phase, load the
exact proposal from the current conversation or the named run's progress log.
Reject an ambiguous candidate reference instead of guessing.

## Qualify evidence

Retain only knowledge that should change how future work in this project is
designed, implemented, tested, or reviewed.

A user comment qualifies when it is a corrective project convention, a
repeated preference, or an explicit durable instruction. Do not generalize a
question, an isolated implementation choice, or feedback tied only to the
current patch.

A comment from another developer qualifies only when all of these hold:

1. it belongs to the explicitly named PR;
2. it is verified against the relevant code and contract;
3. the author accepted it, a corresponding code change resolved it, or the
   user explicitly confirms it;
4. the resulting rule generalizes beyond that PR.

Exclude praise, bot noise, unresolved speculation, rejected findings,
subjective taste without a project convention, temporary workarounds, TODOs,
and knowledge already present in project guidance. Preserve disagreement and
uncertainty instead of averaging conflicting comments into a rule.

## Choose project or explicit user-global scope

Project scope is the default. Read existing destinations first and prefer the
narrowest one:

- `.codex/phasemill/rules/brainstorm.md`
- `.codex/phasemill/rules/planning.md`
- `.codex/phasemill/rules/implementation.md`
- `.codex/phasemill/rules/testing.md`
- `.codex/phasemill/rules/review.md`
- `.codex/phasemill/rules/writing-style.md`
- `.codex/phasemill/profiles/<language>.md`
- `.codex/phasemill/agents/<role>.md`

When, and only when, the user explicitly asks to save the learning globally,
resolve the actual non-empty `PLUGIN_DATA` used by the installed plugin and
allow the equivalent user-global destinations:

- `${PLUGIN_DATA}/rules/{brainstorm,planning,implementation,testing,review,writing-style}.md`
- `${PLUGIN_DATA}/profiles/<language>.md`
- `${PLUGIN_DATA}/agents/<role>.md`

Do not guess a user-global directory, substitute the repository's
`.phasemill/` runtime directory, or write to the installed plugin cache. If
`PLUGIN_DATA` is unavailable, show the otherwise valid proposal and report
that its global destination cannot be resolved safely.

A global candidate must be independent of the current repository and useful
across projects. Reusable language and framework correctness guidance belongs
in `${PLUGIN_DATA}/profiles/<language>.md`; domain contracts, repository
layout, local tooling, and team-only conventions remain project-scoped. Show
when a higher-precedence project fragment would supplement or shadow the
global change.

Rules and profiles are additive. Agent files are complete role replacements,
so modify one only when the user explicitly selected that destination and the
entire resulting role remains valid. Do not use this workflow to edit
`AGENTS.md`, prompts, `config.toml`, source code, documentation, the installed
plugin cache, or embedded defaults.

## Propose, then apply selected candidates

For each candidate show:

- a stable number and concise rule;
- exact destination and scope;
- provenance: run or PR, author/source, file or symbol, and supporting change;
- overlap or conflict with current guidance;
- confidence and why it generalizes;
- the exact minimal diff, not yet applied.

If nothing qualifies, report `no new durable Phasemill project guidance` and
stop. Otherwise ask which candidate numbers to apply. The user may select,
edit, or reject each candidate.

After selection, re-read every destination and regenerate one current combined
diff. Display that exact diff and ask for approval before writing. Earlier
approval of candidate wording is not approval of a changed diff. On approval,
apply only the displayed selected-scope changes, run
`mcp__phasemill__config_resolve` for the repository and touched destinations,
and show the resulting diff. For user-global changes, pass the actual
`PLUGIN_DATA` to the bundled config CLI fallback so the edited layer is
validated. Do not commit without a separate request.
