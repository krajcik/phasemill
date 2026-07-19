# Project learning

Inspect the completed Phasemill run for durable project knowledge. The root
Codex task owns this action because it can inspect the current conversation as
well as the plan and progress log.

## Allowed evidence

Use only:

1. corrective comments from the user in the current conversation;
2. confirmed implementation, testing, native-review, or Pi-review findings
   recorded for this run in `{{PROGRESS_FILE}}`;
3. comments and inline review threads from one PR explicitly named in the
   current request, conversation, or `{{PLAN_FILE}}`.

Do not search unrelated PRs or repository history. A developer comment
qualifies only when it was verified against the code and accepted, resolved by
a corresponding code change, or explicitly confirmed by the user. Exclude
questions, praise, bot noise, rejected findings, one-off compromises,
temporary workarounds, task-specific facts, and knowledge already documented.

## Choose a project destination

Read existing destinations first and deduplicate against them. Project scope
is the default and may be applied without another approval:

- put a compact invariant or activation condition in the narrowest matching
  `.codex/phasemill/rules/{brainstorm,planning,implementation,testing,review,writing-style}.md`;
- put a reusable multi-step procedure in
  `.codex/skills/<kebab-case-name>/SKILL.md`, with only the references,
  examples, templates, assets, or scripts required by that procedure;
- when a rule delegates to a skill, name `$<skill-name>` and link
  `../../skills/<skill-name>/SKILL.md`.

A project skill must have valid `name` and `description` frontmatter, keep all
support files inside its own directory, avoid new dependencies or permissions,
and contain reusable instructions rather than facts from the completed task.
Do not edit `AGENTS.md`, plugin files, embedded defaults, ordinary source,
tests, documentation, configuration, or any path outside these project
learning destinations.

## Apply and verify project learning

Before editing, capture the current content or absence of every exact
destination selected for this action. Apply only the minimal deduplicated
project diff, then verify:

- every changed path is inside the project allowlist above;
- skill frontmatter, directory names, and relative links are valid;
- rule-to-skill links resolve;
- unrelated existing guidance and files are unchanged;
- no task-specific knowledge, dependency, permission, secret, or personal data
  was introduced.

If verification fails, repair the learning diff and verify again. Make at most
two repair attempts. If it still fails, restore only the destinations changed
by this learning action to their captured content or absence and report the
diagnostic. Never reset, restore, or delete unrelated project changes.

Return `clean` when no durable signal qualifies. Return `completed` with the
provenance, classification, exact changed paths, validation result, and repair
count when project learning is applied successfully. Return `failed` or
`timed-out` only after the learning-owned diff was restored. Learning remains
advisory, so any result finishes the already validated implementation run.

## Explicit global learning

Never apply a global change automatically. Only when the user explicitly asks
for global learning may a repository-independent candidate target the actual
non-empty `${PLUGIN_DATA}` rules, profiles, or agents tree, or an exact global
Codex skill root already exposed by the current skill catalog or explicitly
provided by the user.

Never guess a global root, including `~/.codex/skills`. Re-read every exact
destination, show one fresh combined unified diff, and obtain explicit approval
of that exact diff before writing. Project files retain higher precedence, and
global changes never become part of an automatic run or implicit commit.
