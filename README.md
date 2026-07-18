# Phasemill

Phasemill is a Codex plugin for repository-grounded design, planning,
implementation, review, and release. It combines focused and autonomous skills
with a durable local state machine, native Codex subagents, optional advisory
hooks, worktree isolation, and a required independent read-only Pi review.

The plugin is self-contained and dependency-free at runtime except for
`python3`, `git`, Codex, and `pi`. It does not launch nested Codex CLI
processes and does not widen Codex permissions.

## Install

```bash
codex plugin marketplace add krajcik/phasemill --ref v1.5.0
codex plugin add phasemill@phasemill
```

For local development, replace `krajcik/phasemill --ref v1.5.0` with the
absolute path to a checkout. Codex uses its installed plugin cache at runtime.

## Core workflow

Use natural language or invoke the focused skills directly:

```text
$brainstorm design the retry policy
$plan write the accepted design to docs/plans/
$plan-review review docs/plans/20260715-retry-policy.md
$run execute docs/plans/20260715-retry-policy.md
$status show or resume the active Phasemill run
$lazy add the retry policy end to end with minimal interaction
```

`run` advances one revision-bound action at a time through implementation,
native read-only review, required Pi review, finalization, and proposal-only
learning. Durable state is stored under `.phasemill/runs/`; add
`/.phasemill/runs/` to the project `.gitignore` before an in-place run.

`lazy` creates one deterministic sibling worktree before any project mutation,
then autonomously advances discovery, design, exclusive planning, bounded plan
review/fix, and normal `$run` handoff. On first use it stores one install-wide
choice to enable Pi/ZAI review for all projects or disable it globally. Every mutation-bearing stage makes
one replay-safe local commit; empty stages make none, and `$lazy` never pushes.
After interruption, use `$lazy continue` or `$status` from either worktree.
Set `[lazy] worktree = false` for an explicit in-place journey. Release,
publish, deploy, worktree cleanup, and learning-proposal application remain
separate workflows.

Other bundled skills cover PR and local diff review, release preparation,
unreleased changes, root-cause investigation, dialectic analysis, concise
technical writing, project learning, clarification, and clipboard helpers.
Brainstorm and plan review automatically escalate at most one unresolved,
high-impact falsifiable claim to dialectic analysis when credible evidence
exists on both sides and direct inspection cannot settle it; routine trade-offs
and ordinary review findings stay in their parent workflow.

## Proposal-only project learning

After a complete successful run, Phasemill checks the current conversation and
run evidence for durable project guidance. It can also learn from comments and
inline threads in one explicitly named PR. A developer comment qualifies only
when it is verified against the code and accepted, resolved by a corresponding
change, or confirmed by the user.

The automatic phase never edits files. By default it proposes numbered,
evidence-linked diffs for project `.codex/phasemill/rules/`, `profiles/`, or
`agents/`. When explicitly requested, repository-independent guidance can use
the equivalent user-global `PLUGIN_DATA` tree, including reusable
`profiles/<language>.md`. Use `$learn` to select candidates; Phasemill then
shows a fresh combined diff and asks again before writing. It never scans
unrelated PR history, guesses a global directory, changes plugin defaults, or
commits learning updates implicitly.

## Codex-native architecture

- `skills/` exposes small intent-specific entry points instead of one oversized
  prompt.
- `mcp/server.py` exposes typed config and state-machine tools over local stdio
  JSON-RPC. Separate lazy-preparation and implementation-run transitions own
  sequencing and durable state, including the advisory learning transition,
  but never repository edits.
- native Codex subagents perform implementation and read-only review. Current
  children inherit the root session runtime; per-role model profiles remain
  validated routing hints for future native support.
- `hooks/` adds advisory skill evaluation and compact active-journey/run
  context. Hooks never become the durable source of truth.
- `engine/lazy_controller.py` persists the idea-to-plan journey and performs an
  exact, origin-bound handoff to the normal run controller; configured review,
  Pi, finalize, learning, plan-move, and worktree settings remain authoritative.
- `engine/pi_review.py` runs required independent review through Pi with
  `zai/glm-5.2`, `high`, direct networking, and read-only repository tools.
  A strict 40-tool prompt budget requires Pi to stop broad exploration after
  30 calls and return a concise final review before the wall timeout.
  It imports only the stored ZAI API key into an isolated temporary Pi config
  directory, so non-interactive Codex sandboxes do not need write access to
  `~/.pi/agent` and personal Pi settings or extensions are not loaded.
  Failed reviews retain bounded provider diagnostics without exposing proxy
  values or silently treating the review as skipped.
  The first workflow stores one choice under `PLUGIN_DATA`: approval applies to
  every project in that installation, while decline disables Pi globally.
  User or project config may override the choice; Codex sandbox and managed
  policy still take precedence.
- `engine/phase_controller.py record` accepts result JSON through stdin or
  `--result-file PATH`; missing stdin fails within one second so a malformed CLI
  fallback cannot stall an autonomous run indefinitely.

Standalone state-machine workflows never imply commit, push, release, deploy,
or worktree mutation. An explicit `$lazy` invocation authorizes only its early
worktree and trailer-bound local stage commits; it never pushes or removes the
worktree.

## Project customization

Run `$config` to inspect or validate effective settings. When explicitly asked,
it can initialize commented templates under:

```text
.codex/phasemill/
├── config.toml
├── agents/
├── profiles/
├── prompts/
└── rules/
```

Project rules and language profiles are additive. Full prompts and role prompts
are replacements. Automatic language detection is scoped to touched files and
includes Go, Python, PHP, Java/Kotlin, JavaScript/TypeScript, and Rust.

See [configuration](docs/configuration.md) and
[architecture](docs/architecture.md) for the complete contract.

## Validation

```bash
python3 scripts/validate-codex-plugins.py
for test_file in tests/test-codex-*.py; do python3 "$test_file" || exit 1; done
bash tests/smoke/run-codex-plugin-smoke.sh
```

The smoke test installs the local marketplace into a clean temporary
`CODEX_HOME` and exercises only the installed cache. It performs no model or
network calls.

## Origins and license

Phasemill is an independent Codex project derived from ideas and MIT-licensed
code in `umputun/cc-thingz` and `umputun/ralphex`. Exact source pins and adapted
areas are recorded in [NOTICE](NOTICE) and [UPSTREAM.md](UPSTREAM.md).

Support and security reports are documented in [SUPPORT.md](SUPPORT.md) and
[SECURITY.md](SECURITY.md). Use of Phasemill is governed by [TERMS.md](TERMS.md)
and its data-handling behavior is described in [PRIVACY.md](PRIVACY.md).
