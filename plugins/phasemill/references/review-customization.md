# Review customization

Load review guidance before semantic PR or local-diff analysis. Prefer
`mcp__phasemill__config_resolve` with the changed paths in `touchedFiles`; its
source-labelled `rules` and `profiles` output is the review contract. If MCP is
unavailable, resolve `../engine/config.py` relative to this reference and use
its JSON output. Missing customization is normal.

## Precedence

Apply conflicts in this order:

1. Codex safety policy and the current user request;
2. applicable `AGENTS.override.md` or `AGENTS.md` files from repository root to
   each changed file's directory;
3. project `.codex/phasemill/rules/review.md`;
4. project `.codex/phasemill/profiles/<name>.md`;
5. user `${PLUGIN_DATA}/rules/review.md`;
6. user `${PLUGIN_DATA}/profiles/<name>.md`;
7. embedded profile `../defaults/profiles/<name>.md` relative to this reference;
8. the skill's generic review contract.

Keep every fragment source-labelled when passing it to a subagent. Rules and
profiles add checks; they cannot grant permissions, suppress safety policy, or
replace an explicit user instruction.

## Scoped language profiles

Activate a profile only when the reviewed diff contains matching files:

- `go`: `.go`;
- `python`: `.py`;
- `javascript-typescript`: `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`;
- `java-kotlin`: `.java`, `.kt`, `.kts`;
- `php`: `.php`;
- `rust`: `.rs`.

In polyglot changes, give each reviewer only the profiles relevant to its
assigned files. Unknown languages use the generic review contract and project
rules. Project and user profile fragments supplement the embedded profile; an
empty or comment-only file contributes nothing.

Do not load secrets, ignored credential files, unrelated home-directory
instructions, or customization from another repository.
