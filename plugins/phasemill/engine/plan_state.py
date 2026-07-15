#!/usr/bin/env python3
"""Parse planning files and persist restart-safe Codex planning run state.

Plan parsing, alternate-date lookup, and progress restart behavior are adapted
from umputun/ralphex at c536f66ad2868796ddb0220ab00c19e6b56152a6.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Iterator, Mapping
from uuid import uuid4


STATE_VERSION = 2
STATE_PHASES = frozenset(
    {
        "plan",
        "task",
        "review-first",
        "review",
        "external-review",
        "post-review",
        "finalize",
        "learning",
    }
)
STATE_STATUSES = frozenset({"running", "completed", "failed"})
# Codex protects project-local .codex/ as configuration, even in
# workspace-write mode. Runtime state must remain writable without a recurring
# approval, so keep it in a separate project-local data directory.
RUNS_DIRECTORY = Path(".phasemill/runs")

TASK_HEADER = re.compile(r"^###\s+(Task|Iteration)\s+([^:]+?):\s*(.*)$")
CHECKBOX = re.compile(r"^\s*-\s+\[([ xX])\]\s*(.*)$")
TITLE = re.compile(r"^#\s+(.*)$")
FORMAT_IN_TEXT = re.compile(r"\[\s*[ xX]?\s*\]")
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
FENCE_CLOSE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*\r?$")
DASHED_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+\.md)$")
COMPACT_DATE = re.compile(r"^(\d{8})-(.+\.md)$")
DATE_PREFIX = re.compile(r"^[\d-]+")
SAFE_STEM = re.compile(r"[^a-zA-Z0-9._-]+")


class PlanStateError(RuntimeError):
    """The plan, persisted state, or state transition is invalid."""


class StateConflictError(PlanStateError):
    """Another process changed the state or currently owns its file lock."""


@dataclass(frozen=True)
class CheckboxItem:
    text: str
    checked: bool
    actionable: bool
    line: int


@dataclass(frozen=True)
class TaskSection:
    kind: str
    identifier: str
    number: int
    title: str
    status: str
    header_line: int
    end_line: int
    checkboxes: tuple[CheckboxItem, ...]

    @property
    def has_uncompleted_actionable_work(self) -> bool:
        return any(not item.checked and item.actionable for item in self.checkboxes)


@dataclass(frozen=True)
class PlanDocument:
    title: str
    tasks: tuple[TaskSection, ...]
    digest: str

    @property
    def next_task(self) -> TaskSection | None:
        return next((task for task in self.tasks if task.has_uncompleted_actionable_work), None)


@dataclass(frozen=True)
class RunPaths:
    state: Path
    progress: Path
    lock: Path


@dataclass(frozen=True)
class RunState:
    version: int
    run_id: str
    plan_path: str
    plan_digest: str
    phase: str
    status: str
    current_task_identifier: str
    current_task_line: int
    task_iteration: int
    task_retry_count: int
    review_iteration: int
    external_review_iteration: int
    external_unchanged_rounds: int
    external_had_findings: bool
    restart_count: int
    revision: int
    started_at: str
    updated_at: str
    failure: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> RunState:
        if value.get("version") == 1:
            value = dict(value)
            value["version"] = STATE_VERSION
            value["phase"] = "review-first" if value.get("phase") == "review" else value.get("phase")
            value["task_retry_count"] = 0
            value["external_unchanged_rounds"] = 0
            value["external_had_findings"] = False
        fields = cls.__dataclass_fields__
        if set(value) != set(fields):
            missing = sorted(set(fields) - set(value))
            extra = sorted(set(value) - set(fields))
            raise PlanStateError(f"invalid state fields (missing={missing}, extra={extra})")
        try:
            state = cls(**value)
        except TypeError as exc:
            raise PlanStateError(f"invalid state: {exc}") from exc
        state.validate()
        return state

    def validate(self) -> None:
        if type(self.version) is not int or self.version != STATE_VERSION:
            raise PlanStateError(f"unsupported state version: {self.version!r}")
        if not isinstance(self.run_id, str) or not self.run_id:
            raise PlanStateError("state run_id must be a non-empty string")
        if not isinstance(self.plan_path, str) or not self.plan_path:
            raise PlanStateError("state plan_path must be a non-empty string")
        if not isinstance(self.plan_digest, str) or not self.plan_digest:
            raise PlanStateError("state plan_digest must be a non-empty string")
        if self.phase not in STATE_PHASES:
            raise PlanStateError(f"invalid state phase: {self.phase!r}")
        if self.status not in STATE_STATUSES:
            raise PlanStateError(f"invalid state status: {self.status!r}")
        if self.status == "failed" and not self.failure:
            raise PlanStateError("failed state must include a failure reason")
        if self.status != "failed" and self.failure:
            raise PlanStateError(f"{self.status} state must not include a failure reason")
        for name in (
            "current_task_line",
            "task_iteration",
            "task_retry_count",
            "review_iteration",
            "external_review_iteration",
            "external_unchanged_rounds",
            "restart_count",
            "revision",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise PlanStateError(f"state {name} must be a non-negative integer")
        for name in ("current_task_identifier", "started_at", "updated_at", "failure"):
            if not isinstance(getattr(self, name), str):
                raise PlanStateError(f"state {name} must be a string")
        if bool(self.current_task_identifier) != bool(self.current_task_line):
            raise PlanStateError("state current task identifier and line must be set together")
        if self.phase != "task" and self.current_task_identifier:
            raise PlanStateError("only task phase may have a current task")
        if type(self.external_had_findings) is not bool:
            raise PlanStateError("state external_had_findings must be a boolean")


class _FenceTracker:
    def __init__(self) -> None:
        self.open_marker = ""

    def skip(self, line: str) -> bool:
        if not self.open_marker:
            match = FENCE_OPEN.match(line)
            if match is None:
                return False
            self.open_marker = match.group(1)
            return True
        match = FENCE_CLOSE.match(line)
        if match is not None:
            marker = match.group(1)
            if marker[0] == self.open_marker[0] and len(marker) >= len(self.open_marker):
                self.open_marker = ""
        return True


def _task_status(items: tuple[CheckboxItem, ...]) -> str:
    if not items or not any(item.checked for item in items):
        return "pending"
    if all(item.checked for item in items):
        return "done"
    return "active"


def parse_plan(content: str) -> PlanDocument:
    """Parse Task/Iteration sections without treating fenced examples as work."""

    title = ""
    tasks: list[TaskSection] = []
    current: dict[str, Any] | None = None
    fence = _FenceTracker()
    lines = content.splitlines()

    def finish(end_line: int) -> None:
        nonlocal current
        if current is None:
            return
        items = tuple(current.pop("checkboxes"))
        tasks.append(TaskSection(**current, status=_task_status(items), end_line=end_line, checkboxes=items))
        current = None

    for line_number, line in enumerate(lines, start=1):
        if fence.skip(line):
            continue
        if not title:
            match = TITLE.match(line)
            if match is not None:
                title = match.group(1).strip()
                continue

        match = TASK_HEADER.match(line)
        if match is not None:
            finish(line_number - 1)
            identifier = match.group(2).strip()
            try:
                number = int(identifier)
            except ValueError:
                number = 0
            current = {
                "kind": match.group(1).lower(),
                "identifier": identifier,
                "number": number,
                "title": match.group(3).strip(),
                "header_line": line_number,
                "checkboxes": [],
            }
            continue

        is_h2 = line.startswith("##") and not line.startswith("###")
        is_later_h1 = line.startswith("#") and bool(title) and not line.startswith("##")
        if current is not None and (is_h2 or is_later_h1):
            finish(line_number - 1)
            continue

        if current is not None:
            match = CHECKBOX.match(line)
            if match is not None:
                text = match.group(2).strip()
                current["checkboxes"].append(
                    CheckboxItem(
                        text=text,
                        checked=match.group(1).lower() == "x",
                        actionable=FORMAT_IN_TEXT.search(text) is None,
                        line=line_number,
                    )
                )

    finish(len(lines))
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return PlanDocument(title=title, tasks=tuple(tasks), digest=digest)


def parse_plan_file(path: Path) -> PlanDocument:
    try:
        return parse_plan(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise PlanStateError(f"cannot read plan file {path}: {exc}") from exc


def has_uncompleted_checkbox(content: str) -> bool:
    """Detect actionable unchecked work even in a malformed unscoped plan."""

    return first_uncompleted_checkbox_line(content) != 0


def first_uncompleted_checkbox_line(content: str) -> int:
    """Return the first actionable unchecked line outside fences, or zero."""

    fence = _FenceTracker()
    for line_number, line in enumerate(content.split("\n"), start=1):
        if fence.skip(line):
            continue
        match = CHECKBOX.match(line)
        if match is None or match.group(1).lower() == "x":
            continue
        if FORMAT_IN_TEXT.search(match.group(2).strip()) is None:
            return line_number
    return 0


def _current_work(plan: PlanDocument, content: str) -> tuple[str, int]:
    if plan.next_task is not None:
        return plan.next_task.identifier, plan.next_task.header_line
    if not plan.tasks:
        line = first_uncompleted_checkbox_line(content)
        if line:
            return "unscoped", line
    return "", 0


def alternate_date_basename(name: str) -> str:
    if match := DASHED_DATE.match(name):
        return f"{match.group(1)}{match.group(2)}{match.group(3)}-{match.group(4)}"
    if match := COMPACT_DATE.match(name):
        date = match.group(1)
        return f"{date[:4]}-{date[4:6]}-{date[6:]}-{match.group(2)}"
    return ""


def locate_plan(requested: Path) -> Path:
    """Locate an active, alternate-date, or completed form of a plan path."""

    alternate = alternate_date_basename(requested.name)
    candidates = [requested]
    if alternate:
        candidates.append(requested.with_name(alternate))
    candidates.append(requested.parent / "completed" / requested.name)
    if alternate:
        candidates.append(requested.parent / "completed" / alternate)
    return next((candidate for candidate in candidates if candidate.is_file()), requested)


def discover_plans(project_root: Path, plans_directory: str) -> tuple[Path, ...]:
    root = project_root.resolve()
    directory = (root / plans_directory).resolve()
    try:
        directory.relative_to(root)
    except ValueError as exc:
        raise PlanStateError(f"plans directory is outside project root: {directory}") from exc
    if not directory.is_dir():
        raise PlanStateError(f"plans directory does not exist: {directory}")
    plans = tuple(sorted(path for path in directory.glob("*.md") if path.is_file()))
    if not plans:
        raise PlanStateError(f"no plans found in {directory}")
    return plans


def derive_branch_name(plan_path: Path) -> str:
    stem = plan_path.stem
    branch = DATE_PREFIX.sub("", stem).lstrip("-")
    return branch or stem


def _canonical_plan_stem(plan_path: Path) -> str:
    name = plan_path.name
    if match := DASHED_DATE.match(name):
        name = f"{match.group(1)}{match.group(2)}{match.group(3)}-{match.group(4)}"
    stem = Path(name).stem
    safe = SAFE_STEM.sub("-", stem).strip("-.")
    return safe[:100] or "plan"


def run_paths(project_root: Path, plan_path: Path) -> RunPaths:
    directory = project_root.resolve() / RUNS_DIRECTORY
    stem = _canonical_plan_stem(plan_path)
    return RunPaths(
        state=directory / f"state-{stem}.json",
        progress=directory / f"progress-{stem}.md",
        lock=directory / f".{stem}.lock",
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.open("a+b")
    os.chmod(path, 0o600)
    acquired = False
    try:
        if os.name == "nt":  # pragma: no cover - exercised on Windows
            import msvcrt

            if path.stat().st_size == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise StateConflictError(f"planning state is locked: {path}") from exc
        else:
            import fcntl

            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StateConflictError(f"planning state is locked: {path}") from exc
        acquired = True
        yield
    finally:
        try:
            if acquired and os.name == "nt":  # pragma: no cover - exercised on Windows
                import msvcrt

                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            elif acquired:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        finally:
            lock.close()


class RunStateStore:
    """Persist state atomically and reject concurrent stale transitions."""

    def __init__(self, project_root: Path, plan_path: Path) -> None:
        self.project_root = project_root.resolve()
        if not self.project_root.is_dir():
            raise PlanStateError(f"project root is not a directory: {self.project_root}")
        self.requested_plan = plan_path if plan_path.is_absolute() else self.project_root / plan_path
        self.plan_path = locate_plan(self.requested_plan)
        self.paths = run_paths(self.project_root, self.plan_path)

    def _relative_plan_path(self) -> str:
        try:
            return self.plan_path.resolve().relative_to(self.project_root).as_posix()
        except ValueError as exc:
            raise PlanStateError(f"plan file is outside project root: {self.plan_path}") from exc

    def _load_unlocked(self) -> RunState:
        try:
            value = json.loads(self.paths.state.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PlanStateError(f"planning state does not exist: {self.paths.state}") from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PlanStateError(f"cannot read planning state {self.paths.state}: {exc}") from exc
        if not isinstance(value, dict):
            raise PlanStateError("planning state must be a JSON object")
        return RunState.from_mapping(value)

    def _write_unlocked(self, state: RunState) -> None:
        state.validate()
        self.paths.state.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.paths.state.name}.", dir=self.paths.state.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(asdict(state), output, ensure_ascii=False, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_name, self.paths.state)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

    def _append_progress_unlocked(self, text: str) -> None:
        self.paths.progress.parent.mkdir(parents=True, exist_ok=True)
        with self.paths.progress.open("a", encoding="utf-8") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(self.paths.progress, 0o600)

    def initialize(self) -> RunState:
        if not self.plan_path.is_file():
            raise PlanStateError(f"plan file does not exist: {self.plan_path}")
        try:
            content = self.plan_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PlanStateError(f"cannot read plan file {self.plan_path}: {exc}") from exc
        plan = parse_plan(content)
        task_identifier, task_line = _current_work(plan, content)
        now = _utc_now()
        with _exclusive_lock(self.paths.lock):
            existing: RunState | None = None
            if self.paths.state.is_file():
                existing = self._load_unlocked()
            if existing is not None and existing.status != "completed":
                state = replace(
                    existing,
                    plan_path=self._relative_plan_path(),
                    plan_digest=plan.digest,
                    phase="review-first" if existing.phase == "task" and not task_identifier else existing.phase,
                    status="running",
                    current_task_identifier=task_identifier if existing.phase == "task" else "",
                    current_task_line=task_line if existing.phase == "task" else 0,
                    restart_count=existing.restart_count + 1,
                    revision=existing.revision + 1,
                    updated_at=now,
                    failure="",
                )
                self._append_progress_unlocked(f"\n--- restarted at {now} ---\n\n")
            else:
                state = RunState(
                    version=STATE_VERSION,
                    run_id=str(uuid4()),
                    plan_path=self._relative_plan_path(),
                    plan_digest=plan.digest,
                    phase="task" if task_identifier else "review-first",
                    status="running",
                    current_task_identifier=task_identifier,
                    current_task_line=task_line,
                    task_iteration=0,
                    task_retry_count=0,
                    review_iteration=0,
                    external_review_iteration=0,
                    external_unchanged_rounds=0,
                    external_had_findings=False,
                    restart_count=0,
                    revision=0,
                    started_at=now,
                    updated_at=now,
                    failure="",
                )
                self.paths.progress.parent.mkdir(parents=True, exist_ok=True)
                self.paths.progress.write_text(
                    "# Codex Planning Progress\n"
                    f"Plan: {state.plan_path}\n"
                    f"Run: {state.run_id}\n"
                    f"Started: {now}\n"
                    "---\n\n",
                    encoding="utf-8",
                )
                os.chmod(self.paths.progress, 0o600)
            self._write_unlocked(state)
            return state

    def load(self) -> RunState:
        with _exclusive_lock(self.paths.lock):
            return self._load_unlocked()

    def update(self, expected_revision: int, **changes: Any) -> RunState:
        allowed = {
            "plan_digest",
            "phase",
            "current_task_identifier",
            "current_task_line",
            "task_iteration",
            "task_retry_count",
            "review_iteration",
            "external_review_iteration",
            "external_unchanged_rounds",
            "external_had_findings",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise PlanStateError(f"unsupported state changes: {', '.join(sorted(unknown))}")
        with _exclusive_lock(self.paths.lock):
            state = self._load_unlocked()
            if state.revision != expected_revision:
                raise StateConflictError(
                    f"stale planning state revision: expected {expected_revision}, current {state.revision}"
                )
            updated = replace(state, **changes, revision=state.revision + 1, updated_at=_utc_now())
            updated.validate()
            self._write_unlocked(updated)
            return updated

    def reconcile_plan(self, expected_revision: int) -> RunState:
        try:
            content = self.plan_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PlanStateError(f"cannot read plan file {self.plan_path}: {exc}") from exc
        plan = parse_plan(content)
        task_identifier, task_line = _current_work(plan, content)
        state = self.load()
        if state.revision != expected_revision:
            raise StateConflictError(
                f"stale planning state revision: expected {expected_revision}, current {state.revision}"
            )
        phase = "review-first" if state.phase == "task" and not task_identifier else state.phase
        changes = {
            "plan_digest": plan.digest,
            "phase": phase,
            "current_task_identifier": task_identifier if phase == "task" else "",
            "current_task_line": task_line if phase == "task" else 0,
        }
        if all(getattr(state, name) == value for name, value in changes.items()):
            return state
        return self.update(
            expected_revision,
            **changes,
        )

    def append_progress(self, message: str, *, run_id: str) -> None:
        if not message.strip():
            raise PlanStateError("progress message must not be empty")
        with _exclusive_lock(self.paths.lock):
            state = self._load_unlocked()
            if state.run_id != run_id:
                raise StateConflictError(f"progress belongs to another run: {state.run_id}")
            self._append_progress_unlocked(f"[{_utc_now()}] {message.rstrip()}\n")

    def finish(self, expected_revision: int, *, success: bool, failure: str = "") -> RunState:
        if success:
            try:
                content = self.plan_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise PlanStateError(f"cannot read plan file {self.plan_path}: {exc}") from exc
            plan = parse_plan(content)
            if plan.next_task is not None or (not plan.tasks and has_uncompleted_checkbox(content)):
                raise PlanStateError("cannot complete a run while the plan has actionable unchecked work")
        with _exclusive_lock(self.paths.lock):
            state = self._load_unlocked()
            if state.revision != expected_revision:
                raise StateConflictError(
                    f"stale planning state revision: expected {expected_revision}, current {state.revision}"
                )
            now = _utc_now()
            clean_failure = " ".join(failure.split())[:200]
            if not success and not clean_failure:
                clean_failure = "unknown error"
            status = "completed" if success else "failed"
            updated = replace(
                state,
                status=status,
                revision=state.revision + 1,
                updated_at=now,
                failure="" if success else clean_failure,
            )
            self._write_unlocked(updated)
            footer = f"\n---\nCompleted: {now}\n" if success else f"\n---\nFailed: {now} - {clean_failure}\n"
            self._append_progress_unlocked(footer)
            return updated


def _plan_payload(path: Path) -> dict[str, Any]:
    located = locate_plan(path)
    if not located.is_file():
        raise PlanStateError(f"plan file does not exist: {path}")
    content = located.read_text(encoding="utf-8")
    plan = parse_plan(content)
    return {
        "path": str(located),
        "title": plan.title,
        "digest": plan.digest,
        "tasks": [asdict(task) for task in plan.tasks],
        "next_task": asdict(plan.next_task) if plan.next_task else None,
        "has_uncompleted_checkbox": has_uncompleted_checkbox(content),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="parse a plan and report its next task")
    inspect_parser.add_argument("plan", type=Path)
    locate_parser = subparsers.add_parser("locate", help="resolve active/completed alternate-date paths")
    locate_parser.add_argument("plan", type=Path)
    init_parser = subparsers.add_parser("state-init", help="initialize or restart durable run state")
    init_parser.add_argument("plan", type=Path)
    show_parser = subparsers.add_parser("state-show", help="show durable run state")
    show_parser.add_argument("plan", type=Path)
    args = parser.parse_args()

    try:
        if args.command == "inspect":
            plan_path = args.plan if args.plan.is_absolute() else args.project_root / args.plan
            payload: Any = _plan_payload(plan_path)
        elif args.command == "locate":
            plan_path = args.plan if args.plan.is_absolute() else args.project_root / args.plan
            payload = {"path": str(locate_plan(plan_path))}
        else:
            store = RunStateStore(args.project_root, args.plan)
            state = store.initialize() if args.command == "state-init" else store.load()
            payload = {"state": asdict(state), "paths": asdict(store.paths)}
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    except (PlanStateError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
