#!/usr/bin/env python3
"""Copy stdin to the native clipboard without a shell or temporary file."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Callable, Sequence


def select_command(which: Callable[[str], str | None] = shutil.which) -> list[str] | None:
    if path := which("pbcopy"):
        return [path]
    if path := which("xclip"):
        return [path, "-selection", "clipboard"]
    if path := which("xsel"):
        return [path, "--clipboard", "--input"]
    return None


def copy(data: bytes, command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, input=data, capture_output=True, check=False)


def main() -> int:
    data = sys.stdin.buffer.read()
    command = select_command()
    if command is None:
        print("error: no clipboard tool found (pbcopy, xclip, or xsel)", file=sys.stderr)
        return 2
    result = copy(data, command)
    if result.returncode != 0:
        reason = result.stderr.decode("utf-8", errors="replace").strip()
        print(f"error: clipboard command failed: {reason or result.returncode}", file=sys.stderr)
        return 2
    characters = len(data.decode("utf-8", errors="replace"))
    print(f"copied {characters} characters using {command[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
