#!/usr/bin/env python3
"""Durable, revision-checked preparation state for Phasemill lazy journeys."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any, Iterator, Mapping


STATE_VERSION = 1
RUNS_DIRECTORY = Path(".phasemill/runs")
ACTIVE_STATUSES = frozenset({"running", "waiting-input"})
STATUSES = ACTIVE_STATUSES | {"completed", "failed"}
PHASES = frozenset({"discovery", "design", "plan", "plan-review", "plan-fix", "handoff", "done"})
JOURNEY_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
EVENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
MAX_REQUEST_ID = 128
MAX_IDEA = 20_000
MAX_TEXT = 4_000
MAX_PATH = 1_024
MAX_FINDINGS = 100


class LazyStateError(RuntimeError):
    """Lazy state is malformed, unsafe, or unavailable."""


class LazyStateConflictError(LazyStateError):
    """Another process owns the state or the caller used a stale revision."""


class LazyStateIOError(LazyStateError):
    """A durable write failed and may be retried after inspecting state."""


@dataclass(frozen=True)
class LazyPaths:
    directory: Path
    state: Path
    progress: Path
    lock: Path


@dataclass(frozen=True)
class LazyState:
    version: int
    request_id: str
    journey_id: str
    origin_project_root: str
    origin_identity: str
    idea: str
    phase: str
    status: str
    revision: int
    started_at: str
    updated_at: str
    plan_path: str
    plan_digest: str
    plan_review_iteration: int
    discovery_summary: str
    design_summary: str
    findings: tuple[dict[str, str], ...]
    pending_question: str
    pending_options: tuple[str, ...]
    pending_gate: str
    preserved_phase: str
    execution_project_root: str
    execution_plan_path: str
    linked_run_id: str
    run_outcome: str
    baseline_head: str
    baseline_fingerprint: str
    baseline_dirty_paths: tuple[str, ...]
    baseline_path_digests: tuple[dict[str, str], ...]
    scope_paths: tuple[str, ...]
    approved_main_root: str
    approved_execution_root: str
    approved_branch: str
    approved_plan_path: str
    run_overrides: tuple[str, ...]
    run_overrides_digest: str
    failure: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> LazyState:
        fields = cls.__dataclass_fields__
        if set(value) != set(fields):
            missing = sorted(set(fields) - set(value))
            extra = sorted(set(value) - set(fields))
            raise LazyStateError(f"invalid lazy state fields (missing={missing}, extra={extra})")
        normalized = dict(value)
        if isinstance(normalized.get("findings"), list):
            normalized["findings"] = tuple(normalized["findings"])
        if isinstance(normalized.get("pending_options"), list):
            normalized["pending_options"] = tuple(normalized["pending_options"])
        for name in ("baseline_dirty_paths", "scope_paths", "run_overrides"):
            if isinstance(normalized.get(name), list):
                normalized[name] = tuple(normalized[name])
        if isinstance(normalized.get("baseline_path_digests"), list):
            normalized["baseline_path_digests"] = tuple(normalized["baseline_path_digests"])
        try:
            state = cls(**normalized)
        except TypeError as exc:
            raise LazyStateError(f"invalid lazy state: {exc}") from exc
        state.validate()
        return state

    def validate(self) -> None:
        if type(self.version) is not int or self.version != STATE_VERSION:
            raise LazyStateError(f"unsupported lazy state version: {self.version!r}")
        _validate_request_id(self.request_id)
        _validate_journey_id(self.journey_id)
        _validate_text("idea", self.idea, MAX_IDEA, required=True)
        _validate_text("origin_identity", self.origin_identity, MAX_TEXT, required=True)
        _validate_absolute_path("origin_project_root", self.origin_project_root, required=True)
        if self.phase not in PHASES:
            raise LazyStateError(f"invalid lazy state phase: {self.phase!r}")
        if self.status not in STATUSES:
            raise LazyStateError(f"invalid lazy state status: {self.status!r}")
        if type(self.revision) is not int or self.revision < 0:
            raise LazyStateError("lazy state revision must be a non-negative integer")
        if type(self.plan_review_iteration) is not int or self.plan_review_iteration < 0:
            raise LazyStateError("lazy state plan_review_iteration must be a non-negative integer")
        for name in ("started_at", "updated_at"):
            _validate_text(name, getattr(self, name), 64, required=True)
        _validate_relative_path("plan_path", self.plan_path)
        _validate_digest("plan_digest", self.plan_digest)
        if self.plan_digest and not self.plan_path:
            raise LazyStateError("lazy state plan_digest requires plan_path")
        if self.plan_path and not self.plan_digest and self.phase != "plan" and self.status != "failed":
            raise LazyStateError("only plan phase may hold a reserved path without a digest")
        _validate_findings(self.findings)
        _validate_text("discovery_summary", self.discovery_summary, MAX_TEXT)
        _validate_text("design_summary", self.design_summary, MAX_TEXT)
        _validate_text("pending_question", self.pending_question, MAX_TEXT)
        _validate_text("pending_gate", self.pending_gate, MAX_TEXT)
        if not isinstance(self.pending_options, tuple) or not all(
            isinstance(option, str) and option.strip() and len(option) <= MAX_TEXT
            for option in self.pending_options
        ):
            raise LazyStateError("lazy state pending_options must contain bounded non-empty strings")
        if len(self.pending_options) > 3:
            raise LazyStateError("lazy state pending_options must contain at most three entries")
        if len(set(self.pending_options)) != len(self.pending_options):
            raise LazyStateError("lazy state pending_options must not contain duplicates")
        if self.status == "waiting-input":
            if (
                not self.pending_question
                or not self.pending_gate
                or self.preserved_phase not in PHASES - {"done"}
            ):
                raise LazyStateError(
                    "waiting-input state requires a question, gate, and preserved phase"
                )
            if self.pending_options and len(self.pending_options) not in {2, 3}:
                raise LazyStateError("waiting-input options must contain two or three choices")
        elif self.pending_question or self.pending_options or self.pending_gate or self.preserved_phase:
            raise LazyStateError(f"{self.status} state must not contain pending input")
        _validate_absolute_path("execution_project_root", self.execution_project_root)
        _validate_relative_path("execution_plan_path", self.execution_plan_path)
        if bool(self.execution_project_root) != bool(self.execution_plan_path):
            raise LazyStateError("execution project root and plan path must be set together")
        for name in ("linked_run_id", "run_outcome", "baseline_head", "baseline_fingerprint", "failure"):
            _validate_text(name, getattr(self, name), MAX_TEXT)
        _validate_paths("baseline_dirty_paths", self.baseline_dirty_paths)
        _validate_paths("scope_paths", self.scope_paths, allow_repository_root=True)
        _validate_path_digests(self.baseline_path_digests)
        for name in ("approved_main_root", "approved_execution_root"):
            _validate_absolute_path(name, getattr(self, name))
        _validate_text("approved_branch", self.approved_branch, MAX_PATH)
        _validate_relative_path("approved_plan_path", self.approved_plan_path)
        if any((self.approved_main_root, self.approved_execution_root, self.approved_branch, self.approved_plan_path)) and not all(
            (self.approved_main_root, self.approved_execution_root, self.approved_branch, self.approved_plan_path)
        ):
            raise LazyStateError("worktree approval coordinates must be set together")
        if not isinstance(self.run_overrides, tuple) or len(self.run_overrides) > 256 or not all(
            isinstance(item, str) and item and len(item) <= MAX_TEXT for item in self.run_overrides
        ):
            raise LazyStateError("lazy state run_overrides must be a bounded string collection")
        _validate_digest("run_overrides_digest", self.run_overrides_digest)
        if bool(self.run_overrides) != bool(self.run_overrides_digest):
            raise LazyStateError("run override snapshot and digest must be set together")
        if self.run_outcome and not self.linked_run_id:
            raise LazyStateError("lazy state run_outcome requires linked_run_id")
        if self.status == "failed" and not self.failure:
            raise LazyStateError("failed lazy state must include a failure reason")
        if self.status != "failed" and self.failure:
            raise LazyStateError(f"{self.status} state must not include a failure reason")
        if self.status == "completed" and self.phase != "done":
            raise LazyStateError("completed lazy state must be in done phase")
        if self.phase == "done" and self.status not in {"completed", "failed"}:
            raise LazyStateError("done phase must be terminal")


def _validate_text(name: str, value: Any, maximum: int, *, required: bool = False) -> None:
    if not isinstance(value, str):
        raise LazyStateError(f"lazy state {name} must be a string")
    if required and not value.strip():
        raise LazyStateError(f"lazy state {name} must not be empty")
    if len(value) > maximum or "\0" in value:
        raise LazyStateError(f"lazy state {name} exceeds its safe size")


def _validate_request_id(value: Any) -> None:
    _validate_text("request_id", value, MAX_REQUEST_ID, required=True)
    if value != value.strip() or any(ord(character) < 32 for character in value):
        raise LazyStateError("lazy state request_id contains unsafe characters")


def _validate_journey_id(value: Any) -> None:
    if not isinstance(value, str) or JOURNEY_ID.fullmatch(value) is None:
        raise LazyStateError(f"invalid lazy journey id: {value!r}")


def _validate_relative_path(name: str, value: Any) -> None:
    _validate_text(name, value, MAX_PATH)
    if not value:
        return
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or "\\" in value
        or path.as_posix() != value
    ):
        raise LazyStateError(f"lazy state {name} must be a confined repository-relative path")


def _validate_absolute_path(name: str, value: Any, *, required: bool = False) -> None:
    _validate_text(name, value, MAX_PATH, required=required)
    if value and (
        not Path(value).is_absolute()
        or ".." in Path(value).parts
        or str(Path(value)) != value
    ):
        raise LazyStateError(f"lazy state {name} must be an absolute normalized path")


def _validate_digest(name: str, value: Any) -> None:
    _validate_text(name, value, 64)
    if value and HEX_DIGEST.fullmatch(value) is None:
        raise LazyStateError(f"lazy state {name} must be a sha256 digest")


def _validate_findings(value: Any) -> None:
    if not isinstance(value, tuple) or len(value) > MAX_FINDINGS:
        raise LazyStateError("lazy state findings must be a bounded collection")
    required = {"id", "location", "evidence", "consequence", "proposed_fix"}
    seen: set[str] = set()
    for finding in value:
        if not isinstance(finding, dict) or set(finding) != required:
            raise LazyStateError("lazy state finding fields are invalid")
        for name, text in finding.items():
            _validate_text(f"finding.{name}", text, MAX_TEXT, required=True)
        if finding["id"] in seen:
            raise LazyStateError("lazy state finding ids must be unique")
        seen.add(finding["id"])


def _validate_paths(name: str, value: Any, *, allow_repository_root: bool = False) -> None:
    if not isinstance(value, tuple) or len(value) > 1000:
        raise LazyStateError(f"lazy state {name} must be a bounded path collection")
    for item in value:
        if allow_repository_root and item == ".":
            continue
        _validate_relative_path(name, item)


def _validate_path_digests(value: Any) -> None:
    if not isinstance(value, tuple) or len(value) > 1000:
        raise LazyStateError("lazy state baseline_path_digests must be bounded")
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "digest"}:
            raise LazyStateError("lazy state baseline path digest fields are invalid")
        _validate_relative_path("baseline_path_digests.path", item["path"])
        _validate_digest("baseline_path_digests.digest", item["digest"])
        if item["path"] in seen:
            raise LazyStateError("lazy state baseline path digests must be unique")
        seen.add(item["path"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _root_identity(project_root: Path) -> str:
    try:
        stat = project_root.stat()
    except OSError as exc:
        raise LazyStateError(f"cannot stat project root {project_root}: {exc}") from exc
    return f"{stat.st_dev}:{stat.st_ino}"


def _journey_id(origin_identity: str, request_id: str) -> str:
    digest = hashlib.sha256(f"{origin_identity}\0{request_id}".encode("utf-8")).hexdigest()
    return digest[:24]


def lazy_paths(project_root: Path, journey_id: str) -> LazyPaths:
    _validate_journey_id(journey_id)
    root = project_root.resolve()
    directory = root / RUNS_DIRECTORY / f"lazy-{journey_id}"
    resolved_directory = directory.resolve(strict=False)
    if root not in resolved_directory.parents:
        raise LazyStateError(f"lazy journey directory escapes project root: {directory}")
    return LazyPaths(directory, directory / "state.json", directory / "progress.md", directory / ".lock")


def _creation_lock(project_root: Path) -> Path:
    return project_root.resolve() / RUNS_DIRECTORY / ".lazy-create.lock"


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
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
                raise LazyStateConflictError(f"lazy state is locked: {path}") from exc
        else:
            import fcntl

            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise LazyStateConflictError(f"lazy state is locked: {path}") from exc
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


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            descriptor = -1
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    except BaseException as exc:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        if isinstance(exc, LazyStateError):
            raise
        raise LazyStateIOError(f"cannot durably write {path}: {exc}") from exc


class LazyStateStore:
    """Persist one lazy journey and reject stale or concurrent transitions."""

    def __init__(self, project_root: Path, journey_id: str) -> None:
        self.project_root = project_root.resolve()
        if not self.project_root.is_dir():
            raise LazyStateError(f"project root is not a directory: {self.project_root}")
        self.origin_identity = _root_identity(self.project_root)
        self.journey_id = journey_id
        self.paths = lazy_paths(self.project_root, journey_id)

    @classmethod
    def start(cls, project_root: Path, *, request_id: str, idea: str) -> tuple[LazyStateStore, LazyState, bool]:
        root = project_root.resolve()
        if not root.is_dir():
            raise LazyStateError(f"project root is not a directory: {root}")
        _validate_request_id(request_id)
        _validate_text("idea", idea, MAX_IDEA, required=True)
        identity = _root_identity(root)
        journey_id = _journey_id(identity, request_id)
        store = cls(root, journey_id)
        with _exclusive_lock(_creation_lock(root)):
            if store.paths.state.exists():
                state = store.load()
                if state.request_id != request_id or state.idea != idea:
                    raise LazyStateConflictError(
                        "lazy request id already belongs to a different request payload"
                    )
                return store, state, False
            now = _utc_now()
            state = LazyState(
                version=STATE_VERSION,
                request_id=request_id,
                journey_id=journey_id,
                origin_project_root=str(root),
                origin_identity=identity,
                idea=idea,
                phase="discovery",
                status="running",
                revision=0,
                started_at=now,
                updated_at=now,
                plan_path="",
                plan_digest="",
                plan_review_iteration=0,
                discovery_summary="",
                design_summary="",
                findings=(),
                pending_question="",
                pending_options=(),
                pending_gate="",
                preserved_phase="",
                execution_project_root="",
                execution_plan_path="",
                linked_run_id="",
                run_outcome="",
                baseline_head="",
                baseline_fingerprint="",
                baseline_dirty_paths=(),
                baseline_path_digests=(),
                scope_paths=(),
                approved_main_root="",
                approved_execution_root="",
                approved_branch="",
                approved_plan_path="",
                run_overrides=(),
                run_overrides_digest="",
                failure="",
            )
            state.validate()
            with _exclusive_lock(store.paths.lock):
                header = (
                    "# Phasemill Lazy Progress\n"
                    f"Journey: {journey_id}\n"
                    f"Started: {now}\n"
                    "---\n\n"
                )
                _atomic_write_text(store.paths.progress, header)
                store._write_unlocked(state)
            return store, state, True

    def _load_unlocked(self) -> LazyState:
        try:
            value = json.loads(self.paths.state.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise LazyStateError(f"lazy state does not exist: {self.paths.state}") from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LazyStateError(f"cannot read lazy state {self.paths.state}: {exc}") from exc
        if not isinstance(value, dict):
            raise LazyStateError("lazy state must be a JSON object")
        state = LazyState.from_mapping(value)
        if state.journey_id != self.journey_id:
            raise LazyStateError("lazy state journey id does not match its directory")
        if state.origin_project_root != str(self.project_root) or state.origin_identity != self.origin_identity:
            raise LazyStateError("lazy state belongs to a different project root")
        return state

    def _write_unlocked(self, state: LazyState) -> None:
        state.validate()
        if state.journey_id != self.journey_id:
            raise LazyStateError("cannot write state for another lazy journey")
        content = json.dumps(asdict(state), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        _atomic_write_text(self.paths.state, content)

    def load(self) -> LazyState:
        with _exclusive_lock(self.paths.lock):
            return self._load_unlocked()

    def update(self, expected_revision: int, **changes: Any) -> LazyState:
        immutable = {
            "version",
            "request_id",
            "journey_id",
            "origin_project_root",
            "origin_identity",
            "idea",
            "revision",
            "started_at",
            "updated_at",
        }
        unknown = set(changes) - (set(LazyState.__dataclass_fields__) - immutable)
        if unknown:
            raise LazyStateError(f"unsupported lazy state changes: {', '.join(sorted(unknown))}")
        with _exclusive_lock(self.paths.lock):
            state = self._load_unlocked()
            if state.revision != expected_revision:
                raise LazyStateConflictError(
                    f"stale lazy state revision: expected {expected_revision}, current {state.revision}"
                )
            normalized = dict(changes)
            if "findings" in normalized and isinstance(normalized["findings"], list):
                normalized["findings"] = tuple(normalized["findings"])
            if "pending_options" in normalized and isinstance(normalized["pending_options"], list):
                normalized["pending_options"] = tuple(normalized["pending_options"])
            for name in ("baseline_dirty_paths", "scope_paths", "run_overrides"):
                if name in normalized and isinstance(normalized[name], list):
                    normalized[name] = tuple(normalized[name])
            if "baseline_path_digests" in normalized and isinstance(normalized["baseline_path_digests"], list):
                normalized["baseline_path_digests"] = tuple(normalized["baseline_path_digests"])
            updated = replace(state, **normalized, revision=state.revision + 1, updated_at=_utc_now())
            self._write_unlocked(updated)
            return updated

    def append_progress(self, message: str, *, event_id: str) -> bool:
        _validate_text("progress message", message, MAX_TEXT, required=True)
        _validate_text("progress event id", event_id, MAX_REQUEST_ID, required=True)
        if EVENT_ID.fullmatch(event_id) is None:
            raise LazyStateError("progress event id contains unsafe characters")
        marker = f"<!-- event:{event_id} -->"
        with _exclusive_lock(self.paths.lock):
            self._load_unlocked()
            try:
                current = self.paths.progress.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise LazyStateError(f"cannot read lazy progress {self.paths.progress}: {exc}") from exc
            if marker in current:
                return False
            addition = f"{marker}\n[{_utc_now()}] {message.rstrip()}\n"
            _atomic_write_text(self.paths.progress, current + addition)
            return True


def discover_journeys(
    project_root: Path, *, active_only: bool = False, limit: int | None = None
) -> tuple[LazyState, ...]:
    root = project_root.resolve()
    if not root.is_dir():
        raise LazyStateError(f"project root is not a directory: {root}")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise LazyStateError("journey discovery limit must be a positive integer")
    directory = root / RUNS_DIRECTORY
    if not directory.is_dir():
        return ()
    if root not in directory.resolve().parents:
        raise LazyStateError(f"lazy runs directory escapes project root: {directory}")
    states: list[LazyState] = []
    for state_path in sorted(directory.glob("lazy-*/state.json")):
        journey_id = state_path.parent.name.removeprefix("lazy-")
        try:
            state = LazyStateStore(root, journey_id).load()
        except LazyStateError:
            continue
        if not active_only or state.status in ACTIVE_STATUSES:
            states.append(state)
    states.sort(key=lambda state: (state.updated_at, state.journey_id), reverse=True)
    return tuple(states[:limit] if limit is not None else states)
