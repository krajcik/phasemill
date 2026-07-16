#!/usr/bin/env python3
"""Bootstrap lazy project consent and create replay-safe stage commits."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import tomllib
from typing import Sequence


RUNTIME_PREFIX = ".phasemill/runs/"
CONSENT_PATH = Path(".codex/phasemill/config.toml")
_REVIEW_KEY = r"(?:review|\"review\"|'review')"
_EXTERNAL_KEY = r"(?:external|\"external\"|'external')"
TABLE = re.compile(
    rf"^\s*\[\s*{_REVIEW_KEY}\s*\.\s*{_EXTERNAL_KEY}\s*]\s*(?:#.*)?$"
)
ANY_TABLE = re.compile(r"^\s*\[")
CONSENT = re.compile(
    r"^(?P<indent>\s*)data_sharing_approved(?P<space>\s*=\s*)"
    r"(?P<value>true|false)(?P<tail>\s*(?:#.*)?)$"
)
ANY_CONSENT_FALSE = re.compile(r"(\bdata_sharing_approved\s*=\s*)false\b")
INLINE_EXTERNAL = re.compile(r"(\bexternal\s*=\s*{)")
INLINE_REVIEW = re.compile(r"(^\s*review\s*=\s*{)", re.MULTILINE)
DOTTED_EXTERNAL = re.compile(
    rf"^\s*{_REVIEW_KEY}\s*\.\s*{_EXTERNAL_KEY}\s*\.", re.MULTILINE
)
ACTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HEX_SHA = re.compile(r"^[0-9a-f]{40,64}$")


class LazyStageError(RuntimeError):
    pass


def validate_config(values: dict[str, object]) -> None:
    config_path = Path(__file__).resolve().parents[1] / "engine/config.py"
    spec = importlib.util.spec_from_file_location("_phasemill_lazy_stage_config", config_path)
    if spec is None or spec.loader is None:
        raise LazyStageError("cannot load the packaged Phasemill config validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        module.validate_mapping(values)
    except module.ConfigError as exc:
        raise LazyStageError(f"cannot update invalid Phasemill config {CONSENT_PATH}: {exc}") from exc


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise LazyStageError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed


def repository_root(value: Path) -> Path:
    root = Path(git(value.resolve(), "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if not root.is_dir():
        raise LazyStageError(f"repository root is not a directory: {root}")
    return root


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def confined_config_path(root: Path) -> Path:
    path = root / CONSENT_PATH
    resolved_parent = path.parent.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    if root != resolved_parent and root not in resolved_parent.parents:
        raise LazyStageError(f"project config directory escapes repository: {CONSENT_PATH.parent}")
    if root != resolved_path and root not in resolved_path.parents:
        raise LazyStageError(f"project config path escapes repository: {CONSENT_PATH}")
    return path


def write_validated_consent(path: Path, updated: str) -> None:
    try:
        result = tomllib.loads(updated)
    except tomllib.TOMLDecodeError as exc:
        raise LazyStageError(f"generated invalid TOML for {CONSENT_PATH}: {exc}") from exc
    validate_config(result)
    if result.get("review", {}).get("external", {}).get("data_sharing_approved") is not True:
        raise LazyStageError("consent bootstrap did not produce the required effective value")
    atomic_write(path, updated)


def replace_active_false(content: str) -> str:
    def comment_index(line: str) -> int:
        quote = ""
        escaped = False
        for index, character in enumerate(line):
            if quote == '"':
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = ""
            elif quote == "'":
                if character == quote:
                    quote = ""
            elif character in {"'", '"'}:
                quote = character
            elif character == "#":
                return index
        return -1

    lines = content.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        marker = comment_index(line)
        code = line if marker < 0 else line[:marker]
        comment = "" if marker < 0 else line[marker:]
        replaced, count = ANY_CONSENT_FALSE.subn(r"\1true", code, count=1)
        if count:
            lines[index] = replaced + comment
            return "".join(lines)
    raise LazyStageError("cannot locate the parsed false consent value in project TOML")


def consent(root: Path) -> dict[str, str]:
    path = confined_config_path(root)
    original = path.read_text(encoding="utf-8") if path.is_file() else ""
    try:
        parsed = tomllib.loads(original) if original else {}
    except tomllib.TOMLDecodeError as exc:
        raise LazyStageError(f"cannot update invalid TOML {CONSENT_PATH}: {exc}") from exc
    validate_config(parsed)
    review = parsed.get("review", {})
    external = review.get("external", {}) if isinstance(review, dict) else {}
    current = external.get("data_sharing_approved") if isinstance(external, dict) else None
    if current is not None and type(current) is not bool:
        raise LazyStageError("review.external.data_sharing_approved must be a boolean")
    if current is True:
        return {"status": "noop", "path": CONSENT_PATH.as_posix()}

    if current is False:
        updated = replace_active_false(original)
        write_validated_consent(path, updated)
        return {"status": "updated", "path": CONSENT_PATH.as_posix()}

    if INLINE_EXTERNAL.search(original):
        updated = INLINE_EXTERNAL.sub(r"\1 data_sharing_approved = true,", original, count=1)
        write_validated_consent(path, updated)
        return {"status": "updated", "path": CONSENT_PATH.as_posix()}
    if INLINE_REVIEW.search(original):
        updated = INLINE_REVIEW.sub(
            r"\1 external = { data_sharing_approved = true },", original, count=1
        )
        write_validated_consent(path, updated)
        return {"status": "updated", "path": CONSENT_PATH.as_posix()}
    if DOTTED_EXTERNAL.search(original) and not TABLE.search(original):
        prefix = "" if not original or original.endswith(("\n", "\r")) else "\n"
        updated = original + prefix + "review.external.data_sharing_approved = true\n"
        write_validated_consent(path, updated)
        return {"status": "updated", "path": CONSENT_PATH.as_posix()}

    lines = original.splitlines(keepends=True)
    table_index = next((index for index, line in enumerate(lines) if TABLE.match(line.rstrip("\r\n"))), None)
    changed = False
    if table_index is not None:
        end = next(
            (index for index in range(table_index + 1, len(lines)) if ANY_TABLE.match(lines[index])),
            len(lines),
        )
        for index in range(table_index + 1, end):
            match = CONSENT.match(lines[index].rstrip("\r\n"))
            if match:
                newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
                lines[index] = (
                    f"{match.group('indent')}data_sharing_approved{match.group('space')}true"
                    f"{match.group('tail')}{newline}"
                )
                changed = True
                break
        if not changed:
            lines.insert(end, "data_sharing_approved = true\n")
            changed = True
    else:
        prefix = "" if not original or original.endswith(("\n", "\r")) else "\n"
        separator = "" if not original else "\n"
        lines.append(f"{prefix}{separator}[review.external]\ndata_sharing_approved = true\n")
        changed = True
    updated = "".join(lines)
    if changed:
        write_validated_consent(path, updated)
    return {"status": "updated", "path": CONSENT_PATH.as_posix()}


def normalize_paths(values: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
            raise LazyStageError(f"unsafe checkpoint path: {value!r}")
        normalized = path.as_posix()
        if normalized == "." or normalized.startswith(RUNTIME_PREFIX):
            raise LazyStageError(f"checkpoint path is not allowed: {value!r}")
        if normalized not in result:
            result.append(normalized)
    if not result:
        raise LazyStageError("checkpoint requires at least one allowed path")
    return tuple(result)


def dirty_paths(root: Path) -> tuple[str, ...]:
    output = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    paths: list[str] = []
    entries = output.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if status[0] in {"R", "C"} or status[1] in {"R", "C"}:
            if index >= len(entries):
                raise LazyStageError("malformed git status rename entry")
            original_path = entries[index]
            index += 1
            paths.append(original_path)
    return tuple(sorted(path for path in dict.fromkeys(paths) if not path.startswith(RUNTIME_PREFIX)))


def checkpoint(root: Path, action_id: str, message: str, expected_head: str, paths: Sequence[str]) -> dict[str, str]:
    if ACTION_ID.fullmatch(action_id) is None:
        raise LazyStageError("checkpoint action id contains unsafe characters")
    if HEX_SHA.fullmatch(expected_head) is None:
        raise LazyStageError("checkpoint expected HEAD is not a full commit id")
    allowed = normalize_paths(paths)
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    trailer = f"Phasemill-Action: {action_id}"
    base_trailer = "Phasemill-Base: "
    current_message = git(root, "log", "-1", "--format=%B").stdout
    if trailer in current_message.splitlines():
        recorded_base = next(
            (line.removeprefix(base_trailer) for line in current_message.splitlines() if line.startswith(base_trailer)),
            "",
        )
        parents = git(root, "show", "-s", "--format=%P", "HEAD").stdout.split()
        if not recorded_base or len(parents) != 1 or parents[0] != recorded_base:
            raise LazyStageError("replayed checkpoint is not bound to its parent HEAD")
        if recorded_base != expected_head:
            raise LazyStageError("replayed checkpoint does not match the expected base HEAD")
        committed = tuple(
            filter(
                None,
                git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "HEAD^", "HEAD").stdout.split("\0"),
            )
        )
        if not committed or any(path not in allowed for path in committed):
            raise LazyStageError("replayed checkpoint changed paths outside the allowed stage scope")
        dirty = dirty_paths(root)
        if dirty:
            raise LazyStageError("replayed checkpoint has new dirty paths: " + ", ".join(dirty))
        return {"status": "reused", "head": head, "action_id": action_id}
    if head != expected_head:
        raise LazyStageError(f"checkpoint HEAD changed: expected {expected_head}, got {head}")
    dirty = dirty_paths(root)
    unexpected = [path for path in dirty if path not in allowed]
    if unexpected:
        raise LazyStageError("checkpoint found unrelated dirty paths: " + ", ".join(unexpected))
    if not dirty:
        return {"status": "noop", "head": head, "action_id": action_id}
    stageable = tuple(
        path
        for path in allowed
        if (root / path).exists()
        or git(root, "ls-files", "--error-unmatch", "--", path, check=False).returncode == 0
    )
    if stageable:
        git(root, "add", "-A", "--", *stageable)
    staged = tuple(filter(None, git(root, "diff", "--cached", "--name-only", "-z").stdout.split("\0")))
    if not staged or any(path not in allowed for path in staged):
        raise LazyStageError("checkpoint staged paths outside the allowed stage scope")
    git(root, "commit", "-m", message, "-m", f"{trailer}\n{base_trailer}{expected_head}")
    new_head = git(root, "rev-parse", "HEAD").stdout.strip()
    if dirty_paths(root):
        raise LazyStageError("checkpoint commit left non-runtime worktree changes")
    return {"status": "committed", "head": new_head, "action_id": action_id}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    consent_parser = commands.add_parser("consent")
    consent_parser.add_argument("--project-root", type=Path, required=True)
    checkpoint_parser = commands.add_parser("checkpoint")
    checkpoint_parser.add_argument("--project-root", type=Path, required=True)
    checkpoint_parser.add_argument("--action-id", required=True)
    checkpoint_parser.add_argument("--message", required=True)
    checkpoint_parser.add_argument("--expected-head", required=True)
    checkpoint_parser.add_argument("--path", action="append", dest="paths", required=True)
    args = parser.parse_args()
    try:
        root = repository_root(args.project_root)
        result = consent(root) if args.command == "consent" else checkpoint(
            root, args.action_id, args.message, args.expected_head, args.paths
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (LazyStageError, OSError, UnicodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
