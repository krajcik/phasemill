# Security Policy

## Supported versions

Security fixes target the latest published Phasemill release.

## Reporting a vulnerability

Use GitHub private vulnerability reporting for
[`krajcik/phasemill`](https://github.com/krajcik/phasemill/security/advisories/new).
Do not include credentials, unrelated private source code, or personal data.
Provide a minimal reproduction, affected version, impact, and suggested
mitigation when known.

If private reporting is unavailable, open a public issue containing no exploit
details and ask the maintainer to establish a private channel.

## Security boundaries

Phasemill never widens Codex permissions. Repository writes, worktrees, GitHub
posts, commits, pushes, releases, and project-learning changes retain explicit
approval gates. Optional Pi review has full read-only repository context and
can send selected content to the configured ZAI model; disable it when that
data flow is not acceptable.
