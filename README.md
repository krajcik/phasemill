# Phasemill

Phasemill is a Codex plugin for repository-grounded design, planning,
implementation, review, and release. It combines narrow skills with a durable
local state machine, native Codex subagents, optional advisory hooks, worktree
isolation, and an independent read-only Pi review.

The plugin is self-contained and dependency-free at runtime except for
`python3`, `git`, Codex, and optional `pi`. It does not launch nested Codex CLI
processes and does not widen Codex permissions.

## Install

```bash
codex plugin marketplace add krajcik/phasemill --ref v1.1.0
codex plugin add phasemill@phasemill
```

For local development, replace `krajcik/phasemill --ref v1.1.0` with the
absolute path to a checkout. Codex uses its installed plugin cache at runtime.

## Core workflow

Use natural language or invoke the focused skills directly:

```text
$brainstorm design the retry policy
$plan write the accepted design to docs/plans/
$plan-review review docs/plans/20260715-retry-policy.md
$run execute docs/plans/20260715-retry-policy.md
$status show or resume the active Phasemill run
```

`run` advances one revision-bound action at a time through implementation,
native read-only review, optional Pi review, finalization, and proposal-only
learning. Durable state is stored under `.phasemill/runs/`; add
`/.phasemill/runs/` to the project `.gitignore` before an in-place run.

Other bundled skills cover PR and local diff review, release preparation,
unreleased changes, root-cause investigation, dialectic analysis, concise
technical writing, project learning, clarification, and clipboard helpers.

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
  JSON-RPC. It owns sequencing and durable state, including the advisory
  learning transition, but never repository edits.
- native Codex subagents perform implementation and read-only review. Current
  children inherit the root session runtime; per-role model profiles remain
  validated routing hints for future native support.
- `hooks/` adds advisory skill evaluation and compact active-run context. Hooks
  never become the durable source of truth.
- `engine/pi_review.py` runs optional independent review through Pi with
  `zai/glm-5.2`, `xhigh`, direct networking, and read-only repository tools.

The state machine never implies commit, push, release, deploy, worktree
creation, or worktree removal. Those mutations retain their explicit approval
gates.

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
