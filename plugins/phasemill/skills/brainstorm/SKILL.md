---
name: brainstorm
description: Brainstorm and design a feature, architectural change, or other significant creative work before implementation. Use for "brainstorm", "think through", "explore options", "analyze this feature", and design requests; skip for small obvious edits or when the user already supplied an approved design and asks to implement it.
---

# Brainstorm

Turn an idea into a validated design suitable as direct input to the
`phasemill:plan` skill. Stay in dialogue; do not implement while the design is
still being explored.

## Load context and rules

Before asking design questions:

1. Read applicable `AGENTS.md` files and inspect only repository files, docs,
   history, and current state relevant to the idea.
2. If present and non-empty, read user rules from
   `${PLUGIN_DATA}/rules/brainstorm.md`.
3. If present and non-empty, read project rules from
   `.codex/phasemill/rules/brainstorm.md`.
4. Apply both rule files as source-labelled additions. Project rules have
   higher precedence than user rules, and applicable `AGENTS.md` plus the
   current user request have higher precedence than both.

Missing rule files are normal. Do not ask the user to create them before
continuing.

When the user explicitly asks to manage rules:

- show both existing rule files with their source paths;
- write project rules only to `.codex/phasemill/rules/brainstorm.md`;
- write user rules only to `${PLUGIN_DATA}/rules/brainstorm.md`;
- before clearing a rule file, identify the exact path and obtain deletion
  confirmation;
- never modify this plugin's own skills, scripts, references, or manifest.

See `usage.md` next to this skill for the complete rule layout and precedence.

## Process

### 1. Understand the idea

Summarize the problem from repository evidence, then ask one question at a
time. Prefer 2-3 concrete choices when the answers are naturally exclusive;
otherwise ask one concise open question. Establish purpose, constraints,
success criteria, compatibility requirements, integration points, and what is
out of scope.

Do not ask for information that can be discovered safely from the repository.
If the user does not answer a non-blocking detail, state a conservative
assumption and continue. Stop for input only when different answers would
materially change the design.

### 2. Explore alternatives

Once the problem is understood, present 2-3 genuinely different approaches.
Lead with a recommendation and explain the mechanism, trade-offs, migration
cost, and operational consequences. Remove speculative features and premature
abstractions.

If the recommendation depends on one unresolved high-impact falsifiable claim
with credible evidence on both sides, invoke `phasemill:dialectic` at most once
before asking the user to choose. Pass the exact claim, scope, shared evidence,
and standard of proof, then incorporate its verified verdict into the
alternatives. Do not escalate preferences, generic trade-offs, claims already
resolved by direct inspection, or low-impact uncertainty.

Ask which direction to take. If the evidence strongly rules out an option, say
so instead of presenting false symmetry.

### 3. Validate the design incrementally

Present the selected design in small coherent sections and validate each before
continuing. Cover only relevant areas among:

- architecture and component boundaries;
- data flow, state, and lifecycle;
- public contracts and backwards compatibility;
- error handling, cancellation, retries, and cleanup;
- security and permissions;
- testing and rollout.

When feedback invalidates an earlier choice, revise that section and propagate
the consequence through later decisions.

### 4. Produce the handoff

Finish with a compact design handoff containing:

- objective and non-goals;
- selected approach and rejected alternatives;
- affected components and invariants;
- data/control flow;
- failure behavior;
- verification strategy;
- decisions, assumptions, and open questions.

Then offer one next action: invoke `phasemill:plan` with this handoff, start a
native Codex plan, implement directly if the change is genuinely small, or stop
after design. Use structured input when available; otherwise ask the choice in
one concise question.

If `phasemill:plan` is selected, pass the repository evidence, selected
approach, decisions, constraints, and open questions so planning does not repeat
discovery.

## Invariants

- Ask one question per turn.
- Explore alternatives before committing to a significant design.
- Prefer the smallest maintainable design that satisfies the stated goal.
- Make uncertainty and conflicting rules visible.
- Do not write a plan, durable rule, or source change without the user's chosen
  next action.
- Keep the final handoff independent of Claude-specific tool names or syntax.
