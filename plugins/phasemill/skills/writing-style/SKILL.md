---
name: writing-style
description: Apply concise, direct technical writing to issue comments, pull-request reviews, commit messages, and internal engineering discussion. Use for drafting or editing technical comments; skip for README files, official documentation, public release notes, and blog posts.
---

# Technical writing style

Use the repository's own communication rules first. Read applicable
`AGENTS.md` writing/tone sections, then meaningful project
`.codex/phasemill/rules/writing-style.md` and user
`${PLUGIN_DATA}/rules/writing-style.md` files. The current user request has
higher precedence. Missing custom rules are normal.

If custom rules fully define the style, follow them instead of blending in
conflicting defaults. Otherwise apply these defaults:

- lead with the concrete point and remove greetings, sign-offs, filler, and
  meta-commentary;
- state problems directly, explain the consequence, and propose a specific
  fix when evidence supports one;
- use exact paths, lines, identifiers, commits, commands, and links;
- distinguish verified facts, inferences, questions, and uncertainty;
- use a numbered list only for multiple independent issues and omit empty
  sections;
- do not restate what the PR or issue already explains;
- avoid corporate language, artificial praise, excessive hedging, and phrases
  such as "important to note", "comprehensive", "leverage", "utilize",
  "seamless", or "hope this helps".

For a clean review, a short `LGTM` is enough. For a finding, include the actual
defect or risk, why it matters, and the smallest useful next action. Never
convert uncertain speculation into an asserted defect.

Use proper complete prose for README files, official documentation, public
release notes, blog posts, and other general-audience material. This skill
changes wording only; it never posts, commits, or sends the result.
