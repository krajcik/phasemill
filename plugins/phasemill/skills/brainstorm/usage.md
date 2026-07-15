# Brainstorm skill usage in Codex

Invoke the skill explicitly as `$brainstorm`, or ask Codex to brainstorm,
explore options, think through a feature, or design an architectural change.

## Rule locations

Rules are additive and are loaded from lower to higher precedence:

1. `${PLUGIN_DATA}/rules/brainstorm.md` for user defaults;
2. `.codex/phasemill/rules/brainstorm.md` for repository-specific choices;
3. applicable root and nested `AGENTS.md` files;
4. the current user request.

Empty files contribute nothing. Rule fragments influence the dialogue and
design but are not copied verbatim into the handoff.

Examples of useful rules include supported technologies, compatibility
constraints, naming conventions, required design sections, and domain
invariants. Rules cannot widen permissions or override safety policy.

The skill never edits its bundled plugin files. Rule changes are made only when
the user explicitly requests them, and clearing a rule file requires deletion
confirmation.
