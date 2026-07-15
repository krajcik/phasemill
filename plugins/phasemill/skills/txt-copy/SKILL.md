---
name: txt-copy
description: Copy exact generated text to the operating-system clipboard. Use for "copy this", "copy to clipboard", "copy the message", "I need to paste this", or "put it in my clipboard".
---

# Copy text

Identify the exact user-selected text and preserve its bytes, whitespace,
Unicode, code fences, and trailing newline. If multiple recent artifacts could
be meant, ask which one; do not guess.

Resolve `../../scripts/clipboard.py` relative to this `SKILL.md` and send the
content through the process stdin. Never put clipboard content in shell source,
a command-line argument, environment variable, heredoc, or temporary file.

The adapter chooses `pbcopy`, `xclip`, or `xsel` without a shell and reports the
character count. Report success only on exit zero. If no clipboard utility is
available, return the content in a fenced block and the adapter's exact error;
do not install software without a separate request.
