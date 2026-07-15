# Proposal-only project learning

Inspect the completed Phasemill run for durable project knowledge. This action
must never edit repository files, plugin files, configuration, runtime state,
or external systems. Its only output is either a learning proposal or a clean
result stating that no durable signal exists.

## Allowed evidence

Use only:

1. corrective comments from the user in the current conversation;
2. confirmed implementation, testing, native-review, or Pi-review findings
   recorded for this run in `{{PROGRESS_FILE}}`;
3. comments and inline review threads from another developer in a PR explicitly
   named in the current request, conversation, or `{{PLAN_FILE}}`.

Do not search unrelated PRs or repository history. A developer review comment
qualifies only when it is verified against the code and was accepted by the
author, resolved by a corresponding code change, or explicitly confirmed by
the user. Exclude questions, praise, bot noise, rejected findings, subjective
preferences without a declared project convention, one-off compromises,
temporary workarounds, task-specific facts, and knowledge already documented.

## Allowed destinations and scope

Project scope is the default. Propose project changes under
`.codex/phasemill/`:

- `rules/brainstorm.md`, `rules/planning.md`, `rules/implementation.md`,
  `rules/testing.md`, `rules/review.md`, or `rules/writing-style.md` for durable
  project conventions;
- `profiles/<language>.md` for language- or framework-specific guidance;
- `agents/<role>.md` for a project-specific review role.

Only when the user explicitly asks to make the learning global, a candidate
may instead target the actual non-empty `${PLUGIN_DATA}` root used by the
installed plugin:

- `${PLUGIN_DATA}/rules/<kind>.md` for a cross-project user convention;
- `${PLUGIN_DATA}/profiles/<language>.md` for reusable language or framework
  guidance;
- `${PLUGIN_DATA}/agents/<role>.md` for a reusable complete review role.

Never infer or invent a global path when `PLUGIN_DATA` is unavailable, and
never promote a project/domain convention merely because it occurred more than
once. A global candidate must be repository-independent and useful across the
user's projects. State that project files have higher precedence and identify
any project rule that would shadow or supplement the global proposal.

Never propose changes outside the selected project or user-global Phasemill
scope, or to the installed plugin, embedded defaults, `AGENTS.md`, prompts,
`config.toml`, source code, tests, or documentation through this automatic
phase. Do not create a new role unless existing rule/profile files cannot
express the learning.

## Proposal contract

Read existing destinations first and deduplicate against them. For each
candidate provide:

- a stable candidate number and concise rule;
- exact destination;
- source type and provenance: user feedback or explicit PR review, plus the
  run/PR, relevant file or symbol, and supporting code change;
- why it generalizes beyond the completed task;
- conflicts or overlap with existing guidance;
- an exact minimal unified diff that has not been applied;
- confidence: high, medium, or low.

Return `clean` when no candidate survives these checks. Return `completed`
with the proposal in the result summary when candidates exist. The user must
select candidates and approve the resulting current diff in a separate
`phasemill:learn` interaction before any project-scope file changes.
