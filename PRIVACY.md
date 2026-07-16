# Privacy Policy

Effective date: July 15, 2026

Phasemill is an open-source Codex plugin that runs in the user's Codex
environment. The Phasemill project does not operate a hosted service, collect
telemetry, maintain user accounts, or receive repository content.

## Local data

Phasemill reads repository files and project instructions needed for the
requested workflow. Restart-safe run state is stored locally under
`.phasemill/runs/`. Project guidance is stored under `.codex/phasemill/`, and
explicitly approved user-global guidance may be stored under the installed
plugin's `PLUGIN_DATA` directory.

Automatic learning is proposal-only. It does not write project or user-global
guidance until the user selects candidates and approves the current exact diff.

## External services

Phasemill can use services already configured by the user:

- Codex and OpenAI process prompts, repository context, and tool results under
  the terms and privacy policy applicable to the user's OpenAI account.
- Independent review is required by the shipped workflow and invokes the
  user's local `pi` installation with the `zai/glm-5.2` model. Before the first
  review, each installation asks once whether Pi and ZAI may receive prompts
  and repository content read through the adapter's `read`, `grep`, `find`, and
  `ls` tools. Approval applies to every project using that installation;
  decline disables Pi globally. The choice is stored locally under
  `PLUGIN_DATA` and can be overridden with `review.external.backend = "none"`.
- GitHub workflows use the user's authenticated GitHub CLI session to read an
  explicitly named pull request. Phasemill posts or changes GitHub state only
  after separate approval of the exact action.

Phasemill does not proxy these services or receive their data. Their respective
operators control retention and processing. Users should review those policies
before enabling the integrations and should not provide secrets or personal
data that the selected service should not process.

## Security and contact

Phasemill does not intentionally collect personal information. Questions about
this policy can be opened through the support channel in [SUPPORT.md](SUPPORT.md).
Security issues should follow [SECURITY.md](SECURITY.md).

Material changes to this policy are recorded in the repository history and
release notes.
