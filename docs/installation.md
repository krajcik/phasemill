# Installing Phasemill

## Requirements

- Codex with plugin marketplace support;
- Python 3.11 or newer;
- Git for repository and worktree workflows;
- optional `pi` configured for `zai/glm-5.2` when independent review is enabled.

## Install from GitHub

```bash
codex plugin marketplace add krajcik/phasemill --ref v1.1.0
codex plugin add phasemill@phasemill
```

Restart Codex after installation if the current session does not discover the
new skills, hooks, or MCP server.

For local development, clone the repository and replace
`krajcik/phasemill --ref v1.1.0` with the absolute path to the checkout.

## Verify

In a repository, ask Codex to run `$config` and show the effective Phasemill
configuration. `$status` should return no active runs in a fresh project.

Before `$run`, ignore runtime state:

```gitignore
/.phasemill/runs/
```

Project customization is optional and lives under `.codex/phasemill/`. Do not
copy or edit files inside the installed plugin cache.

## Upgrade

Add the newer release tag to the marketplace, then use the Codex plugin
marketplace upgrade command for `phasemill`. Existing `.codex/phasemill/`
customization and `.phasemill/runs/` state remain project-owned.
