# Phasemill configuration

Phasemill resolves configuration in this order, from lowest to highest
precedence:

1. embedded defaults in the installed plugin;
2. user plugin data supplied through `PLUGIN_DATA`;
3. project files under `.codex/phasemill/`;
4. invocation `--set` overrides used by the deterministic CLI fallback.

Invalid higher-precedence values are errors; they are never silently ignored.
Codex safety policy, `AGENTS.md`, and the current user request always remain
outside and above plugin configuration.

## Project layout

`$config` can initialize commented templates only after explicit approval:

```text
.codex/phasemill/
├── config.toml
├── agents/
├── profiles/
├── prompts/
└── rules/
```

- `config.toml` overrides typed lazy preparation, execution, review, finalize,
  proposal-only learning, worktree, profile, and future native-agent routing
  settings.
- `prompts/<name>.md` replaces a complete embedded phase prompt.
- `agents/<role>.md` replaces or adds a complete review-role prompt.
- `profiles/<language>.md` adds project-specific language guidance.
- `rules/{brainstorm,planning,implementation,testing,review,writing-style}.md`
  adds scoped project rules without replacing embedded guidance.

The config tool reports every effective value and its source. It does not need
to print prompt or rule bodies to explain resolution.

## Language profiles

Automatic detection considers touched files, not every language found anywhere
in a polyglot repository. Built-in profiles cover Go, Python, PHP,
Java/Kotlin, JavaScript/TypeScript, and Rust. A project can force or suppress
profiles:

```toml
[profiles]
auto = true
enable = ["go"]
disable = ["javascript-typescript"]
```

Profiles include compact correctness, resource-lifecycle, error-contract,
testing, dependency, and compatibility checks. Project profile fragments are
additive, so local framework and domain rules can sit beside the generic
language baseline.

## Review roles

The default review roles are implementation, quality, testing, documentation,
and simplification. Implementation review includes language-agnostic wiring
checks for DI, handlers, background jobs, schemas and queries, fixtures,
configuration, permissions, metrics, and compatibility. Quality review owns
code-smell guidance.

Project roles can be added under `agents/` and mapped in `config.toml`. Disable
irrelevant roles explicitly; do not weaken correctness checks by hiding them in
an unrelated role.

## Lazy mode

Lazy mode has a deliberately small configuration surface:

```toml
[lazy]
max_plan_review_iterations = 2
plan_review_agents = ["implementation", "quality", "testing"]
worktree = true
commit_after_stage = true
```

Every configured lazy plan-review role must exist in `agents`, have a
`review.agent_profiles` mapping, and remain enabled; an empty effective list is
an error. The existing `review.max_parallel_agents` limit controls batching.

Embedded `lazy-discovery`, `lazy-design`, `lazy-plan`, `lazy-plan-review`, and
`lazy-plan-fix` prompts can be replaced through `prompts/`. The lazy plan prompt
composes the normal make-plan contract and overrides only its interactive
acceptance gate, producing an exclusive plan that can be handed directly to the
run state machine.

`worktree = true` creates the deterministic execution worktree before discovery;
set it to `false` for an explicit in-place journey. `commit_after_stage = true`
creates replay-safe local commits for config, plan, implementation, applied
review fixes, finalize changes, and a Git-visible plan move. Empty stages do not
commit. Lazy also resolves install-wide Pi consent on first use. It never pushes,
publishes, deploys, removes the worktree, or applies a learning proposal.

## Runtime profiles

Agent model and reasoning entries are validated routing hints. Current native
Codex children inherit the root session's selected model and reasoning effort,
so Phasemill does not claim that a configured child profile actually ran.

Defaults use Sol for implementation and correctness work, Luna for bounded
documentation and simplification review, and keep Terra disabled. Recovery
after a failed implementation is configured for `xhigh` as a future routing
hint.

## Independent Pi review

The external adapter has a deliberately fixed security and model contract:

```toml
[review.external]
backend = "pi"
required = true
command = ["pi"]
model = "zai/glm-5.2"
thinking = "high"
direct = true
timeout_seconds = 1200
idle_timeout_seconds = 120
```

Pi receives the full repository as its working directory but only read-only
`read`, `grep`, `find`, and `ls` tools. The adapter removes proxy variables,
streams JSON events, separates idle and wall-clock timeouts, and returns partial
diagnostics. It also appends a fixed 40-tool review budget: broad exploration
must stop after 30 calls and a final review is required by call 40.
Set `backend = "none"` to disable it.

`data_sharing_approved` is `false` in embedded defaults. On first use,
Phasemill stores one explicit approve/decline choice in
`${PLUGIN_DATA}/external-review-consent.json`. Approval enables Pi review for
all projects in that plugin installation; decline overlays `backend = "none"`
and `required = false`. Normal user and project config retain higher precedence.

## Automatic learning

Automatic proposal generation is enabled by default:

```toml
[learning]
auto_propose = true
```

Set it to `false` to finish immediately after finalize or review. Explicit
`$learn` analysis of a named run or PR remains available. Automatic learning
can propose changes only under `.codex/phasemill/{rules,profiles,agents}` and
cannot write them; candidate selection and approval of the current combined
diff are separate gates.

On an explicit global-learning request, the same workflow may target the
actual user plugin-data layer:

```text
${PLUGIN_DATA}/
├── agents/
├── profiles/
└── rules/
```

Global candidates must be repository-independent. Reusable language and
framework checks belong in `profiles/<language>.md`; repository architecture,
domain contracts, local tooling, and team conventions remain under the project
tree. Phasemill never invents a global path when `PLUGIN_DATA` is unavailable,
and project fragments keep higher precedence.

## State and worktrees

Durable state lives under `.phasemill/runs/`, not under the protected Codex
configuration tree. Existing implementation runs keep their flat run
directories; lazy preparation journeys use a nested namespace and link to the
normal run created at handoff. All runtime state must be Git-ignored and must
never enter fingerprints, reviews, commits, or releases.

Standalone `$run` worktree mode remains off by default and retains its explicit
approval gate. `$lazy` has a separate early-worktree default: its invocation is
authorization to create or reuse one deterministic sibling before project-file
mutation. Origin runtime state remains discoverable from either worktree.
Removal is always separate and refuses a dirty worktree.
