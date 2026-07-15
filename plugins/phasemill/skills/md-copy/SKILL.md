---
name: md-copy
description: Format a selected answer as portable Markdown and copy it to the operating-system clipboard. Use for "copy as markdown", "md copy", "copy formatted", or "copy this answer as Markdown".
---

# Copy as Markdown

Identify the exact answer or artifact first. Convert it to standalone Markdown:

- use a bold title instead of heading syntax;
- preserve fenced code blocks with language tags;
- keep real bullet and numbered lists;
- convert ASCII tables to Markdown tables;
- remove chat-only directives, transient progress updates, and UI chrome;
- preserve links and technical identifiers exactly;
- do not silently rewrite the substance.

Show the formatted Markdown when the transformation materially changes the
content. Resolve `../../scripts/clipboard.py` relative to this `SKILL.md` and
send the final Markdown through stdin. Never place content in shell source, a
command argument, environment variable, heredoc, or temporary file.

Report success only when the adapter exits zero, including its character count.
If no clipboard utility exists, return the Markdown in one fenced block with
the exact adapter error and do not install software automatically.
