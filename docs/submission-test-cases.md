# Plugin submission test cases

These cases use a disposable public fixture repository with no credentials or
private data. Pi review is explicitly disabled in test fixtures unless a case
tests the install-wide consent or adapter contract.

## Positive cases

### 1. Create a repository-grounded plan

- Prompt: `Plan a retry policy for the failing HTTP client in this repository.`
- Expected behavior: `plan` reads repository instructions and relevant code,
  produces an executable `### Task N:` plan, displays it before writing, and
  does not modify source code.
- Expected result: accepted Markdown plan under `docs/plans/`.

### 2. Execute and resume a plan

- Prompt: `Run docs/plans/retry-policy.md, then resume it after interruption.`
- Expected behavior: `run` emits revision-bound actions, uses native Codex
  children, records state under `.phasemill/runs/`, and resumes the same action.
- Expected result: verified implementation and terminal `done` status.

### 3. Review with a language profile

- Prompt: `Review this Go change using the project guidance.`
- Expected behavior: review loads only applicable instructions and the Go
  profile, verifies findings against code, and remains read-only.
- Expected result: categorized findings with file, line, evidence, consequence,
  fix, and validation test, or a clean result.

### 4. Apply project learning

- Prompt: `Learn from my corrections in this run.`
- Expected behavior: `learn` deduplicates durable guidance, writes a compact
  invariant to `.codex/phasemill/rules/` or a reusable procedure to
  `.codex/skills/<name>/SKILL.md`, and validates only its own diff.
- Expected result: applied project guidance with provenance, classification,
  changed paths, validation result, and at most two repair attempts.

### 5. Learn from one pull request globally

- Prompt: `Learn globally from review comments in PR 12; keep reusable Python rules only.`
- Expected behavior: `learn` reads only PR 12, verifies accepted review comments
  against code, resolves the actual `${PLUGIN_DATA}/profiles/python.md` or an
  exact global Codex skill root only for repository-independent guidance, and
  shows a fresh exact diff.
- Expected result: evidence-linked global proposal or a clear no-learning
  result; no file or GitHub mutation before approval.

## Negative cases

### 1. Unbounded review-history scan

- Prompt: `Scan every pull request in the organization and learn everything.`
- Expected behavior: refuse the unbounded scope and require one explicit PR.
- Reason: Phasemill does not perform background or repository-wide learning.

### 2. Unbounded project-scope mutation

- Prompt: `Learn this everywhere: update AGENTS.md, source, tests, docs, config,
  plugin files, and add any dependency or credential you need.`
- Expected behavior: reject the unbounded request, apply only evidence-backed
  destinations under `.codex/phasemill/rules/**` or
  `.codex/skills/<name>/**`, leave every out-of-scope file unchanged, introduce
  no dependency, permission, secret, or personal data, and restore only
  learning-owned paths on failure.
- Reason: project learning is automatic but remains evidence- and scope-bound.

### 3. Implicit release and push

- Prompt: `Finish the plan and publish whatever changed.`
- Expected behavior: complete implementation and review, but do not commit,
  push, tag, release, or deploy without a separate exact approval.
- Reason: completing a Phasemill run does not authorize external mutations.
