#!/usr/bin/env python3
"""Drive restart-safe preparation actions before handing a plan to Phasemill run."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import select
import subprocess
import sys
from types import ModuleType
from typing import Any, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
SAFE_SLUG = re.compile(r"[^a-z0-9]+")
RECORD_STDIN_TIMEOUT_SECONDS = 1.0
OUTCOMES = frozenset(
    {"completed", "clean", "findings", "needs-input", "answered", "failed", "timed-out"}
)
GATES = frozenset(
    {
        "material-design",
        "dirty-overlap",
        "sandbox-permission",
        "network-permission",
        "write-permission",
        "worktree-approval",
        "pi-consent",
        "retry-exhaustion",
        "git-mutation",
        "external-mutation",
        "learning-application",
    }
)


def _load_sibling(name: str, filename: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / filename)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging guard
        raise RuntimeError(f"cannot load bundled module: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LAZY_STATE = _load_sibling("_phasemill_lazy_state", "lazy_state.py")
PLANNING_CONFIG = _load_sibling("_phasemill_lazy_config", "config.py")
PLAN_STATE = _load_sibling("_phasemill_lazy_plan_state", "plan_state.py")


class LazyControllerError(RuntimeError):
    """An action or result violates the current lazy phase contract."""


@dataclass(frozen=True)
class NativeAgent:
    name: str
    model: str
    model_reasoning_effort: str


@dataclass(frozen=True)
class ReviewRole:
    name: str
    source: str
    prompt: str
    agent: NativeAgent


@dataclass(frozen=True)
class LazyAction:
    action_id: str
    kind: str
    phase: str
    expected_revision: int
    iteration: int = 0
    prompt_name: str = ""
    prompt: str = ""
    plan_path: str = ""
    plan_digest: str = ""
    plan_write_mode: str = ""
    discovery_summary: str = ""
    design_summary: str = ""
    roles: tuple[ReviewRole, ...] = ()
    max_parallel_agents: int = 1
    question: str = ""
    options: tuple[str, ...] = ()
    gate: str = ""
    approved_main_root: str = ""
    approved_execution_root: str = ""
    approved_branch: str = ""
    approved_plan_path: str = ""
    run_requirements: Mapping[str, Any] | None = None
    execution_project_root: str = ""
    execution_branch: str = ""
    origin_project_root: str = ""
    origin_head: str = ""
    commit_after_stage: bool = False
    execution_plan_path: str = ""
    matching_run_id: str = ""
    matching_run_status: str = ""
    reason: str = ""


@dataclass(frozen=True)
class LazyResult:
    outcome: str
    summary: str = ""
    question: str = ""
    options: tuple[str, ...] = ()
    gate: str = ""
    answer: str = ""
    decision: str = ""
    plan_path: str = ""
    plan_digest: str = ""
    previous_plan_digest: str = ""
    findings: tuple[dict[str, str], ...] = ()
    head: str = ""
    worktree_fingerprint: str = ""
    dirty_paths: tuple[str, ...] = ()
    scope_paths: tuple[str, ...] = ()
    linked_run_id: str = ""
    execution_project_root: str = ""
    execution_plan_path: str = ""
    run_outcome: str = ""
    approved_main_root: str = ""
    approved_execution_root: str = ""
    approved_branch: str = ""
    approved_plan_path: str = ""
    execution_branch: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> LazyResult:
        unknown = set(value) - set(cls.__dataclass_fields__)
        if unknown:
            raise LazyControllerError(f"unknown lazy result fields: {', '.join(sorted(unknown))}")
        normalized = dict(value)
        for name in ("options", "findings", "dirty_paths", "scope_paths"):
            if isinstance(normalized.get(name), list):
                normalized[name] = tuple(normalized[name])
        try:
            result = cls(**normalized)
        except TypeError as exc:
            raise LazyControllerError(f"invalid lazy result: {exc}") from exc
        result.validate()
        return result

    def validate(self) -> None:
        if self.outcome not in OUTCOMES:
            raise LazyControllerError(f"invalid lazy result outcome: {self.outcome!r}")
        for name in (
            "summary",
            "question",
            "gate",
            "answer",
            "decision",
            "plan_path",
            "plan_digest",
            "previous_plan_digest",
            "head",
            "worktree_fingerprint",
            "linked_run_id",
            "execution_project_root",
            "execution_plan_path",
            "run_outcome",
            "approved_main_root",
            "approved_execution_root",
            "approved_branch",
            "approved_plan_path",
            "execution_branch",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) > LAZY_STATE.MAX_TEXT or "\0" in value:
                raise LazyControllerError(f"lazy result {name} must be a bounded string")
        if not isinstance(self.options, tuple) or not all(
            isinstance(item, str) and item.strip() and len(item) <= LAZY_STATE.MAX_TEXT
            for item in self.options
        ):
            raise LazyControllerError("lazy result options must contain bounded non-empty strings")
        if len(self.options) > 3 or len(set(self.options)) != len(self.options):
            raise LazyControllerError("lazy result options must contain at most three unique values")
        for name in ("dirty_paths", "scope_paths"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or len(values) > 1000:
                raise LazyControllerError(f"lazy result {name} must be a bounded list")
            for value in values:
                _relative_path(value, name)
        LAZY_STATE._validate_findings(self.findings)
        if self.outcome == "needs-input":
            if not self.question.strip() or self.gate not in GATES:
                raise LazyControllerError("needs-input requires a question and known gate")
            if self.options and len(self.options) not in {2, 3}:
                raise LazyControllerError("needs-input options must contain two or three choices")
        elif self.question or self.options or self.gate:
            raise LazyControllerError(f"{self.outcome} result must not contain input fields")
        if self.outcome == "answered":
            if not self.answer.strip():
                raise LazyControllerError("answered result requires a non-empty answer")
            if self.decision not in {"continue", "stop"}:
                raise LazyControllerError("answered result requires decision=continue or decision=stop")
        elif self.answer:
            raise LazyControllerError(f"{self.outcome} result must not contain an answer")
        elif self.decision:
            raise LazyControllerError(f"{self.outcome} result must not contain a decision")


def _relative_path(value: str, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > LAZY_STATE.MAX_PATH:
        raise LazyControllerError(f"{name} must be a non-empty repository-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or path.as_posix() != value:
        raise LazyControllerError(f"{name} must be a confined repository-relative path")
    return path.as_posix()


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise LazyControllerError(f"cannot read plan {path}: {exc}") from exc


def _slug(idea: str) -> str:
    value = SAFE_SLUG.sub("-", idea.lower()).strip("-")[:48]
    return value or "change"


@dataclass(frozen=True)
class GitSnapshot:
    head: str
    fingerprint: str
    dirty_paths: tuple[str, ...]
    path_digests: tuple[dict[str, str], ...]


def _git(root: Path, *arguments: str, text: bool = False) -> bytes | str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise LazyControllerError(f"cannot inspect Git state in {root}: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() if text else completed.stderr.decode("utf-8", "replace").strip()
        raise LazyControllerError(f"Git inspection failed in {root}: {detail or arguments[0]}")
    return completed.stdout


def _split_z(value: bytes) -> tuple[str, ...]:
    return tuple(
        item.decode("utf-8", "surrogateescape")
        for item in value.split(b"\0")
        if item
    )


def _git_snapshot(root: Path) -> GitSnapshot:
    head = str(_git(root, "rev-parse", "HEAD", text=True)).strip()
    tracked = _split_z(bytes(_git(root, "diff", "--name-only", "-z", "HEAD")))
    untracked = _split_z(bytes(_git(root, "ls-files", "--others", "--exclude-standard", "-z")))
    paths = tuple(
        sorted(
            {
                _relative_path(path, "Git path")
                for path in (*tracked, *untracked)
                if path != ".phasemill/runs" and not path.startswith(".phasemill/runs/")
            }
        )
    )
    digest = hashlib.sha256()
    digest.update(head.encode("ascii", "strict"))
    path_digests: list[dict[str, str]] = []
    for relative in paths:
        path_digest = hashlib.sha256()
        digest.update(b"\0path\0")
        digest.update(relative.encode("utf-8", "surrogateescape"))
        difference = bytes(_git(root, "diff", "--binary", "HEAD", "--", relative))
        digest.update(difference)
        path_digest.update(difference)
        path = root / relative
        if path.is_symlink():
            digest.update(b"\0symlink\0")
            digest.update(os.readlink(path).encode("utf-8", "surrogateescape"))
            path_digest.update(b"symlink\0" + os.readlink(path).encode("utf-8", "surrogateescape"))
        elif path.is_file():
            digest.update(b"\0file\0")
            digest.update(path.read_bytes())
            path_digest.update(b"file\0" + path.read_bytes())
        else:
            digest.update(b"\0missing\0")
            path_digest.update(b"missing\0")
        path_digests.append({"path": relative, "digest": path_digest.hexdigest()})
    return GitSnapshot(head, digest.hexdigest(), paths, tuple(path_digests))


def _toml_value(value: Any) -> str:
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(
            f"{json.dumps(key)} = {_toml_value(item)}" for key, item in sorted(value.items())
        ) + " }"
    raise LazyControllerError(f"cannot encode run override value: {type(value).__name__}")


class LazyController:
    """Emit idempotent preparation actions and apply one result per revision."""

    def __init__(self, store: Any, config: Any) -> None:
        self.store = store
        self.config = config
        self.values = config.values
        self.root = store.project_root

    @classmethod
    def start(
        cls,
        project_root: Path,
        config: Any,
        *,
        request_id: str,
        idea: str,
    ) -> tuple[LazyController, bool]:
        store, _, created = LAZY_STATE.LazyStateStore.start(
            project_root,
            request_id=request_id,
            idea=idea,
            origin_head=_git_snapshot(project_root.resolve()).head,
            lazy_worktree=config.values["lazy"]["worktree"],
            commit_after_stage=config.values["lazy"]["commit_after_stage"],
        )
        return cls(store, config), created

    def _action_id(self, state: Any, kind: str) -> str:
        return f"{state.journey_id}:{state.revision}:{kind}"

    def _terminal(self, state: Any) -> LazyAction:
        return LazyAction(
            action_id=self._action_id(state, state.status),
            kind="done" if state.status == "completed" else "failed",
            phase=state.phase,
            expected_revision=state.revision,
            plan_path=state.plan_path,
            plan_digest=state.plan_digest,
            execution_project_root=state.execution_project_root,
            execution_plan_path=state.execution_plan_path,
            matching_run_id=state.linked_run_id,
            matching_run_status=state.run_outcome,
            reason=state.failure or state.run_outcome,
        )

    def _render(self, name: str, state: Any) -> str:
        replacement = self.config.prompts[name]
        values = {
            "IDEA": state.idea,
            "PLAN_DESCRIPTION": state.idea,
            "PLAN_FILE": state.plan_path or "<reserved by controller>",
            "PLANS_DIR": self.values["plans"]["directory"],
            "PROGRESS_FILE": str(self.store.paths.progress),
        }

        def substitute(match: re.Match[str]) -> str:
            return values.get(match.group(1), match.group(0))

        sections = [
            f"## Prompt source: {replacement.source} ({replacement.path})",
            PLACEHOLDER.sub(substitute, replacement.content).rstrip(),
        ]
        if state.discovery_summary:
            sections.extend(["## Durable discovery evidence", state.discovery_summary])
        if state.design_summary:
            sections.extend(["## Durable design decision", state.design_summary])
        if name == "lazy-plan":
            make_plan = self.config.prompts["make-plan"]
            sections.extend(
                [
                    f"## Effective make-plan source: {make_plan.source} ({make_plan.path})",
                    PLACEHOLDER.sub(substitute, make_plan.content).rstrip(),
                    "## Lazy authorization override",
                    "The initial lazy request authorizes writing the local plan. Supersede only the "
                    "make-plan requirement to present a draft and wait for acceptance; preserve every "
                    "repository-grounding, executable-plan, safety, and customization requirement.",
                ]
            )
        rule_kinds = {
            "lazy-discovery": {"brainstorm", "profile", "instructions"},
            "lazy-design": {"brainstorm", "planning", "profile", "instructions"},
            "lazy-plan": {"planning", "profile", "instructions"},
            "lazy-plan-review": {"planning", "review", "profile", "instructions"},
            "lazy-plan-fix": {"planning", "review", "profile", "instructions"},
        }[name]
        for fragment in self.config.rules:
            if fragment.kind in rule_kinds:
                sections.extend(
                    [
                        f"## Rule source: {fragment.source} ({fragment.path})",
                        fragment.content.rstrip(),
                    ]
                )
        return "\n\n".join(sections).rstrip() + "\n"

    def _roles(self) -> tuple[ReviewRole, ...]:
        roles: list[ReviewRole] = []
        for name in self.config.lazy_plan_review_agents:
            replacement = self.config.agents[name]
            profile_name = self.values["review"]["agent_profiles"][name]
            profile = self.values["agents"][profile_name]
            roles.append(
                ReviewRole(
                    name=name,
                    source=replacement.source,
                    prompt=replacement.content,
                    agent=NativeAgent(
                        name=profile_name,
                        model=profile["model"],
                        model_reasoning_effort=profile["model_reasoning_effort"],
                    ),
                )
            )
        return tuple(roles)

    def _plan_candidate(self, state: Any) -> str:
        plans_dir = _relative_path(self.values["plans"]["directory"], "plans.directory")
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
        filename = f"{date}-{_slug(state.idea)}-{state.journey_id[:8]}.md"
        relative = filename if plans_dir == "." else f"{plans_dir}/{filename}"
        path = self._project_plan(state, relative)
        if path.exists():
            raise LazyControllerError(f"reserved plan path already exists: {relative}")
        return relative

    def _execution_root(self, state: Any) -> Path:
        if not state.execution_project_root:
            raise LazyControllerError("lazy execution root is not prepared")
        return Path(state.execution_project_root).resolve()

    def _project_plan(self, state: Any, relative: str) -> Path:
        normalized = _relative_path(relative, "plan_path")
        root = self._execution_root(state)
        path = (root / normalized).resolve(strict=False)
        if root != path and root not in path.parents:
            raise LazyControllerError(f"plan path escapes execution repository: {relative}")
        return path

    def _validate_plan_file(self, state: Any, result: LazyResult, *, fix: bool = False) -> str:
        if result.plan_path != state.plan_path:
            raise LazyControllerError(
                f"plan result path mismatch: expected {state.plan_path!r}, got {result.plan_path!r}"
            )
        if fix and result.previous_plan_digest != state.plan_digest:
            raise LazyControllerError("plan-fix result is not bound to the current plan digest")
        if not re.fullmatch(r"[0-9a-f]{64}", result.plan_digest):
            raise LazyControllerError("plan result requires a sha256 plan_digest")
        path = self._project_plan(state, state.plan_path)
        if not path.is_file():
            raise LazyControllerError(f"plan file does not exist: {state.plan_path}")
        actual = _digest(path)
        if actual != result.plan_digest:
            raise LazyControllerError(f"stale plan digest: expected file digest {actual}")
        plan = PLAN_STATE.parse_plan_file(path)
        if plan.next_task is None:
            raise LazyControllerError(
                "plan has no unchecked executable work (expected ### Task N: or ### Iteration N:)"
            )
        return actual

    def _validate_current_digest(self, state: Any) -> None:
        if state.plan_path and state.plan_digest:
            actual = _digest(self._project_plan(state, state.plan_path))
            if actual != state.plan_digest:
                raise LazyControllerError(
                    f"plan digest drift: state has {state.plan_digest}, file has {actual}"
                )

    def _matching_run(self, state: Any) -> tuple[str, str]:
        if self._handoff_worktree_enabled(state) and not state.approved_execution_root:
            return "", ""
        root = Path(state.execution_project_root) if state.execution_project_root else self.root
        relative = state.execution_plan_path or state.plan_path
        if not relative or not root.is_dir():
            return "", ""
        state_path = PLAN_STATE.run_paths(root, root / relative).state
        if not state_path.is_file():
            return "", ""
        try:
            run = PLAN_STATE.RunStateStore(root, Path(relative)).load()
        except PLAN_STATE.PlanStateError as exc:
            if "does not exist" in str(exc):
                return "", ""
            raise LazyControllerError(str(exc)) from exc
        if run.plan_path != relative:
            return "", ""
        return run.run_id, run.status

    def _run_overrides(self) -> tuple[str, ...]:
        override_sections = (
            "execution",
            "review",
            "agents",
            "finalize",
            "learning",
            "plans",
            "worktree",
            "profiles",
        )
        overrides: list[str] = []
        for section in override_sections:
            for key, value in sorted(self.values[section].items()):
                if section == "agents":
                    for field, field_value in sorted(value.items()):
                        overrides.append(f"agents.{key}.{field}={_toml_value(field_value)}")
                else:
                    overrides.append(f"{section}.{key}={_toml_value(value)}")
        return tuple(overrides)

    def _run_requirements(self, state: Any) -> dict[str, Any]:
        frozen = PLANNING_CONFIG.load_effective(
            project_root=self.root,
            overrides=list(state.run_overrides),
        ).values
        external = frozen["review"]["external"]
        return {
            "overrides": list(state.run_overrides),
            "overrides_digest": state.run_overrides_digest,
            "worktree_enabled": frozen["worktree"]["enabled"],
            "external_review": {
                "backend": external["backend"],
                "required": external["required"],
                "data_sharing_approved": external["data_sharing_approved"],
                "timeout_seconds": external["timeout_seconds"],
                "idle_timeout_seconds": external["idle_timeout_seconds"],
            },
            "finalize_enabled": frozen["finalize"]["enabled"],
            "learning_auto_propose": frozen["learning"]["auto_propose"],
            "lazy": {
                "journey_id": state.journey_id,
                "commit_after_stage": state.commit_after_stage,
                "execution_project_root": state.execution_project_root,
                "execution_branch": state.execution_branch,
            },
            "effective": {
                "execution": dict(frozen["execution"]),
                "review": {
                    "max_iterations": frozen["review"]["max_iterations"],
                    "max_external_iterations": frozen["review"]["max_external_iterations"],
                    "patience": frozen["review"]["patience"],
                    "external": dict(external),
                },
                "finalize": dict(frozen["finalize"]),
                "learning": dict(frozen["learning"]),
                "worktree": dict(frozen["worktree"]),
                "plans": dict(frozen["plans"]),
            },
        }

    def _handoff_worktree_enabled(self, state: Any) -> bool:
        return not state.lazy_worktree and bool(self._run_requirements(state)["worktree_enabled"])

    def _bootstrap_coordinates(self, state: Any) -> tuple[str, str]:
        branch = f"phasemill/lazy-{state.journey_id}"
        root = (self.root.parent / f".{self.root.name}-phasemill-worktrees" / branch).resolve()
        return str(root), branch

    def next_action(self) -> LazyAction:
        for _ in range(4):
            state = self.store.load()
            if state.status in {"completed", "failed"}:
                return self._terminal(state)
            if state.status == "waiting-input":
                return LazyAction(
                    action_id=self._action_id(state, "input"),
                    kind="input",
                    phase=state.phase,
                    expected_revision=state.revision,
                    question=state.pending_question,
                    options=state.pending_options,
                    gate=state.pending_gate,
                    approved_main_root=state.approved_main_root,
                    approved_execution_root=state.approved_execution_root,
                    approved_branch=state.approved_branch,
                    approved_plan_path=state.approved_plan_path,
                    origin_project_root=str(self.root),
                    origin_head=state.origin_head,
                    execution_project_root=state.execution_project_root,
                    execution_branch=state.execution_branch,
                    commit_after_stage=state.commit_after_stage,
                    reason=f"Resume {state.preserved_phase} after one scoped answer.",
                )
            if state.phase == "bootstrap-worktree":
                execution_root, branch = self._bootstrap_coordinates(state)
                return LazyAction(
                    action_id=self._action_id(state, "worktree"),
                    kind="worktree",
                    phase=state.phase,
                    expected_revision=state.revision,
                    origin_project_root=str(self.root),
                    origin_head=state.origin_head,
                    execution_project_root=execution_root,
                    execution_branch=branch,
                    commit_after_stage=state.commit_after_stage,
                    reason="Create or reuse the deterministic plan-independent lazy worktree.",
                )
            if state.phase == "bootstrap-config":
                return LazyAction(
                    action_id=self._action_id(state, "bootstrap-config"),
                    kind="bootstrap-config",
                    phase=state.phase,
                    expected_revision=state.revision,
                    origin_project_root=str(self.root),
                    origin_head=state.origin_head,
                    execution_project_root=state.execution_project_root,
                    execution_branch=state.execution_branch,
                    commit_after_stage=state.commit_after_stage,
                    reason="Resolve install-wide external-review consent before discovery.",
                )
            if state.phase == "plan" and not state.plan_path:
                state = self.store.update(state.revision, plan_path=self._plan_candidate(state))
                continue
            if state.phase in {"plan-review", "plan-fix"}:
                self._validate_current_digest(state)
            if state.phase in {"discovery", "design", "plan", "plan-review", "plan-fix"}:
                name = f"lazy-{state.phase}"
                kind = state.phase
                return LazyAction(
                    action_id=self._action_id(state, kind),
                    kind=kind,
                    phase=state.phase,
                    expected_revision=state.revision,
                    origin_project_root=str(self.root),
                    origin_head=state.origin_head,
                    execution_project_root=state.execution_project_root,
                    execution_branch=state.execution_branch,
                    commit_after_stage=state.commit_after_stage,
                    iteration=state.plan_review_iteration + 1 if state.phase == "plan-review" else 1,
                    prompt_name=name,
                    prompt=self._render(name, state),
                    plan_path=state.plan_path,
                    plan_digest=state.plan_digest,
                    plan_write_mode="create-exclusive" if state.phase == "plan" else "",
                    discovery_summary=state.discovery_summary,
                    design_summary=state.design_summary,
                    roles=self._roles() if state.phase == "plan-review" else (),
                    max_parallel_agents=(
                        min(len(self.config.lazy_plan_review_agents), self.values["review"]["max_parallel_agents"])
                        if state.phase == "plan-review"
                        else 1
                    ),
                    reason=("Create the reserved plan with no-replace semantics." if state.phase == "plan" else ""),
                )
            if state.phase == "handoff":
                run_id, run_status = self._matching_run(state)
                if not run_id:
                    self._validate_current_digest(state)
                    overlap, _ = self._new_dirty_overlap(state)
                    if overlap:
                        self._pause_for_overlap(state, overlap, preserved_phase="handoff")
                        continue
                execution_root = state.execution_project_root or str(self.root)
                execution_plan = state.execution_plan_path or state.plan_path
                return LazyAction(
                    action_id=self._action_id(state, "handoff"),
                    kind="handoff",
                    phase=state.phase,
                    expected_revision=state.revision,
                    plan_path=state.plan_path,
                    plan_digest=state.plan_digest,
                    discovery_summary=state.discovery_summary,
                    design_summary=state.design_summary,
                    run_requirements=self._run_requirements(state),
                    execution_project_root=execution_root,
                    execution_branch=state.execution_branch,
                    origin_project_root=str(self.root),
                    origin_head=state.origin_head,
                    commit_after_stage=state.commit_after_stage,
                    execution_plan_path=execution_plan,
                    matching_run_id=run_id,
                    matching_run_status=run_status,
                    reason=(
                        "Resume the exact matching existing run; do not start another."
                        if run_id
                        else "Obtain explicit worktree approval and record exact prepared sibling coordinates."
                        if self._handoff_worktree_enabled(state) and not state.approved_execution_root
                        else "Start the existing Phasemill run protocol for this validated plan."
                    ),
                )
            raise LazyControllerError(f"unsupported lazy phase: {state.phase}")
        raise LazyControllerError("automatic lazy transition loop did not converge")

    def _validate_action(self, state: Any, action_id: str, kind: str) -> None:
        expected = self._action_id(state, kind)
        if action_id != expected:
            raise LAZY_STATE.LazyStateConflictError(
                f"stale or mismatched lazy action: expected {expected}"
            )

    def _progress(self, state: Any, action_id: str, result: LazyResult) -> None:
        summary = result.summary.strip() or (
            f"answer: {result.answer.strip()}" if result.outcome == "answered" else result.outcome
        )
        self.store.append_progress(
            f"{state.phase} result: {result.outcome}\n{summary}", event_id=action_id
        )

    def _pause(self, state: Any, result: LazyResult) -> None:
        changes: dict[str, Any] = {}
        if result.gate == "worktree-approval":
            if state.phase != "handoff" or not state.plan_path:
                raise LazyControllerError("worktree approval is valid only during plan handoff")
            main_root = Path(result.approved_main_root).resolve()
            execution_root = Path(result.approved_execution_root).resolve()
            expected_root = (
                self.root.parent
                / f".{self.root.name}-phasemill-worktrees"
                / result.approved_branch
            ).resolve()
            if main_root != self.root:
                raise LazyControllerError("approved worktree main root does not match journey origin")
            if execution_root != expected_root:
                raise LazyControllerError(
                    "approved execution root does not match the packaged worktree helper"
                )
            if result.approved_plan_path != state.plan_path:
                raise LazyControllerError("approved worktree plan does not match the validated plan")
            changes.update(
                approved_main_root=str(main_root),
                approved_execution_root=str(execution_root),
                approved_branch=result.approved_branch,
                approved_plan_path=_relative_path(result.approved_plan_path, "approved_plan_path"),
            )
        self.store.update(
            state.revision,
            **changes,
            status="waiting-input",
            pending_question=result.question.strip(),
            pending_options=result.options,
            pending_gate=result.gate,
            preserved_phase=state.phase,
        )

    def _dirty_overlap(self, result: LazyResult) -> tuple[str, ...]:
        dirty = {
            path for path in result.dirty_paths if not path.startswith(".phasemill/runs/")
        }
        scope = set(result.scope_paths)
        overlaps: set[str] = set()
        for changed in dirty:
            for planned in scope:
                if (
                    planned == "."
                    or changed == planned
                    or changed.startswith(planned.rstrip("/") + "/")
                    or planned.startswith(changed.rstrip("/") + "/")
                ):
                    overlaps.add(changed)
        return tuple(sorted(overlaps))

    def _path_overlap(
        self, dirty_paths: Sequence[str], scope_paths: Sequence[str]
    ) -> tuple[str, ...]:
        return self._dirty_overlap(
            LazyResult(outcome="completed", dirty_paths=tuple(dirty_paths), scope_paths=tuple(scope_paths))
        )

    def _new_dirty_overlap(self, state: Any) -> tuple[tuple[str, ...], GitSnapshot]:
        snapshot = _git_snapshot(self._execution_root(state))
        baseline_digests = {
            item["path"]: item["digest"] for item in state.baseline_path_digests
        }
        current_digests = {item["path"]: item["digest"] for item in snapshot.path_digests}
        changed = {
            path
            for path in set(baseline_digests) | set(current_digests)
            if baseline_digests.get(path) != current_digests.get(path)
        }
        if snapshot.head != state.baseline_head:
            committed = _split_z(
                bytes(_git(self._execution_root(state), "diff", "--name-only", "-z", state.baseline_head, snapshot.head))
            )
            changed.update(committed)
        allowed = {state.plan_path} if state.plan_path else set()
        new_dirty = tuple(path for path in changed if path not in allowed)
        return self._path_overlap(new_dirty, state.scope_paths), snapshot

    def _pause_for_overlap(
        self,
        state: Any,
        overlap: Sequence[str],
        *,
        preserved_phase: str,
        **changes: Any,
    ) -> None:
        snapshot = _git_snapshot(self._execution_root(state))
        changes.update(
            baseline_head=snapshot.head,
            baseline_fingerprint=snapshot.fingerprint,
            baseline_dirty_paths=snapshot.dirty_paths,
            baseline_path_digests=snapshot.path_digests,
        )
        self.store.update(
            state.revision,
            **changes,
            phase=preserved_phase,
            status="waiting-input",
            pending_question="Existing changes overlap the lazy workflow scope: " + ", ".join(overlap),
            pending_options=("Continue with these changes", "Stop"),
            pending_gate="dirty-overlap",
            preserved_phase=preserved_phase,
        )

    def _finish_failed(self, state: Any, reason: str, **changes: Any) -> None:
        clean = " ".join(reason.split())[:200] or "unknown lazy failure"
        self.store.update(
            state.revision,
            **changes,
            status="failed",
            phase="done",
            failure=clean,
            pending_question="",
            pending_options=(),
            pending_gate="",
            preserved_phase="",
        )

    def _execution_coordinates(
        self, state: Any, result: LazyResult, *, require_validated_digest: bool
    ) -> tuple[str, str]:
        recorded_root = state.execution_project_root
        recorded_plan = state.execution_plan_path
        # An explicitly in-place lazy journey may still request the legacy
        # standalone-run worktree at handoff. Until that worktree preparation
        # is recorded, the bootstrap origin root is not an execution lock.
        if self._handoff_worktree_enabled(state) and not recorded_plan:
            recorded_root = ""
        if recorded_root and result.execution_project_root:
            if Path(result.execution_project_root).resolve() != Path(recorded_root):
                raise LazyControllerError("handoff execution root differs from recorded coordinates")
        if recorded_plan and result.execution_plan_path and result.execution_plan_path != recorded_plan:
            raise LazyControllerError("handoff execution plan differs from recorded coordinates")
        root_value = recorded_root or result.execution_project_root
        root = Path(root_value).resolve() if root_value else self.root
        plan = recorded_plan or result.execution_plan_path or state.plan_path
        _relative_path(plan, "execution_plan_path")
        if state.lazy_worktree:
            if root != self._execution_root(state):
                raise LazyControllerError("handoff execution root differs from early lazy worktree")
            if result.execution_branch and result.execution_branch != state.execution_branch:
                raise LazyControllerError("handoff execution branch differs from early lazy worktree")
            actual_branch = str(_git(root, "branch", "--show-current", text=True)).strip()
            if actual_branch != state.execution_branch:
                raise LazyControllerError("early lazy worktree is on an unexpected branch")
        elif self._handoff_worktree_enabled(state):
            if not state.approved_execution_root:
                raise LazyControllerError("worktree preparation requires stored approved helper coordinates")
            if Path(state.approved_main_root).resolve() != self.root:
                raise LazyControllerError("approved worktree main root does not match journey origin")
            if root != Path(state.approved_execution_root).resolve():
                raise LazyControllerError("prepared worktree does not match the approved execution root")
            if plan != state.approved_plan_path:
                raise LazyControllerError("prepared worktree plan does not match the approved plan path")
            if not recorded_root and result.execution_branch != state.approved_branch:
                raise LazyControllerError("prepared worktree branch does not match the approved branch")
            if root == self.root:
                raise LazyControllerError("worktree execution root must differ from the origin repository")
            registered = {
                Path(line.removeprefix("worktree ")).resolve()
                for line in str(_git(self.root, "worktree", "list", "--porcelain", text=True)).splitlines()
                if line.startswith("worktree ")
            }
            if root not in registered:
                raise LazyControllerError("worktree execution root is not registered with the origin repository")
            origin_common = Path(str(_git(self.root, "rev-parse", "--git-common-dir", text=True)).strip())
            execution_common = Path(str(_git(root, "rev-parse", "--git-common-dir", text=True)).strip())
            if not origin_common.is_absolute():
                origin_common = (self.root / origin_common).resolve()
            else:
                origin_common = origin_common.resolve()
            if not execution_common.is_absolute():
                execution_common = (root / execution_common).resolve()
            else:
                execution_common = execution_common.resolve()
            if execution_common != origin_common:
                raise LazyControllerError("worktree execution root does not share the origin Git common directory")
            actual_branch = str(_git(root, "branch", "--show-current", text=True)).strip()
            if actual_branch != state.approved_branch:
                raise LazyControllerError("registered worktree is not on the approved branch")
        elif root != self.root:
            raise LazyControllerError("execution root may differ only when worktree.enabled is true")
        if not root.is_dir():
            raise LazyControllerError(f"execution project root is not a directory: {root}")
        candidate = (root / plan).resolve(strict=False)
        if root != candidate and root not in candidate.parents:
            raise LazyControllerError("execution plan path escapes execution project root")
        if not candidate.is_file():
            raise LazyControllerError("execution plan does not exist")
        if require_validated_digest and _digest(candidate) != state.plan_digest:
            raise LazyControllerError("execution plan must be an exact copy of the validated plan")
        return str(root), plan

    def _validate_bootstrap_worktree(self, state: Any, result: LazyResult) -> tuple[str, str]:
        expected_root, expected_branch = self._bootstrap_coordinates(state)
        root = Path(result.execution_project_root).resolve()
        if str(root) != expected_root or result.execution_branch != expected_branch:
            raise LazyControllerError("prepared lazy worktree differs from deterministic coordinates")
        registered = {
            Path(line.removeprefix("worktree ")).resolve()
            for line in str(_git(self.root, "worktree", "list", "--porcelain", text=True)).splitlines()
            if line.startswith("worktree ")
        }
        if root not in registered:
            raise LazyControllerError("lazy execution root is not a registered origin worktree")
        if str(_git(root, "branch", "--show-current", text=True)).strip() != expected_branch:
            raise LazyControllerError("lazy execution worktree branch mismatch")
        actual_head = str(_git(root, "rev-parse", "HEAD", text=True)).strip()
        if actual_head != state.origin_head:
            raise LazyControllerError("lazy execution worktree advanced before bootstrap was recorded")
        if subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", state.origin_head, "HEAD"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode != 0:
            raise LazyControllerError("lazy execution worktree diverges from recorded origin HEAD")
        return str(root), expected_branch

    def _validate_result_fields(self, kind: str, result: LazyResult) -> None:
        populated = {
            name
            for name in (
                "question",
                "options",
                "gate",
                "answer",
                "decision",
                "plan_path",
                "plan_digest",
                "previous_plan_digest",
                "findings",
                "head",
                "worktree_fingerprint",
                "dirty_paths",
                "scope_paths",
                "linked_run_id",
                "execution_project_root",
                "execution_plan_path",
                "run_outcome",
                "approved_main_root",
                "approved_execution_root",
                "approved_branch",
                "approved_plan_path",
                "execution_branch",
            )
            if getattr(result, name)
        }
        allowed: set[str] = set()
        if result.outcome == "needs-input":
            allowed = {"question", "options", "gate"}
            if result.gate == "worktree-approval":
                allowed.update(
                    {"approved_main_root", "approved_execution_root", "approved_branch", "approved_plan_path"}
                )
                if not all(
                    (
                        result.approved_main_root,
                        result.approved_execution_root,
                        result.approved_branch,
                        result.approved_plan_path,
                    )
                ):
                    raise LazyControllerError("worktree approval requires exact planned coordinates")
        elif result.outcome == "answered":
            allowed = {"answer", "decision"}
        elif kind == "worktree" and result.outcome == "completed":
            allowed = {"execution_project_root", "execution_branch"}
            if not result.execution_project_root or not result.execution_branch:
                raise LazyControllerError("worktree completion requires exact root and branch")
        elif kind == "bootstrap-config" and result.outcome == "completed":
            pass
        elif kind == "discovery" and result.outcome == "completed":
            allowed = {"scope_paths"}
            if not result.summary.strip():
                raise LazyControllerError("discovery completion requires a durable summary")
            if not result.scope_paths:
                raise LazyControllerError("discovery requires at least one scoped path")
        elif kind == "design" and result.outcome == "completed":
            if not result.summary.strip():
                raise LazyControllerError("design completion requires a durable summary")
        elif kind == "plan" and result.outcome == "completed":
            allowed = {"plan_path", "plan_digest"}
            if not result.plan_path or not result.plan_digest:
                raise LazyControllerError("plan completion requires plan_path and plan_digest")
        elif kind == "plan-review" and result.outcome == "findings":
            allowed = {"findings"}
            if not result.findings:
                raise LazyControllerError("findings result requires structured findings")
        elif kind == "plan-fix" and result.outcome == "completed":
            allowed = {"plan_path", "plan_digest", "previous_plan_digest"}
            if not result.plan_path or not result.plan_digest or not result.previous_plan_digest:
                raise LazyControllerError(
                    "plan-fix completion requires plan_path, plan_digest, and previous_plan_digest"
                )
        elif kind == "handoff" and result.outcome == "completed":
            allowed = {
                "linked_run_id",
                "execution_project_root",
                "execution_plan_path",
                "run_outcome",
                "execution_branch",
            }
            if not result.execution_project_root or not result.execution_plan_path:
                raise LazyControllerError(
                    "handoff completion requires exact execution project root and plan path"
                )
            if bool(result.linked_run_id) != bool(result.run_outcome):
                raise LazyControllerError("handoff linked_run_id and run_outcome must be set together")
        if unexpected := populated - allowed:
            raise LazyControllerError(
                f"{kind} {result.outcome} has invalid fields: {', '.join(sorted(unexpected))}"
            )

    def record_result(self, action_id: str, result: LazyResult) -> LazyAction:
        # Serialize the complete accept/progress/transition sequence. The state
        # revision remains the authority, while the outer lock prevents a
        # losing same-revision result from appending progress first.
        record_lock = self.store.paths.directory / ".record.lock"
        with LAZY_STATE._exclusive_lock(record_lock):
            return self._record_result_locked(action_id, result)

    def _record_result_locked(self, action_id: str, result: LazyResult) -> LazyAction:
        result.validate()
        state = self.store.load()
        if state.status in {"completed", "failed"}:
            raise LazyControllerError(f"cannot record a result for {state.status} lazy journey")
        kind = "input" if state.status == "waiting-input" else (
            "worktree" if state.phase == "bootstrap-worktree" else state.phase
        )
        self._validate_action(state, action_id, kind)
        allowed = {
            "input": {"answered"},
            "worktree": {"completed", "needs-input", "failed", "timed-out"},
            "bootstrap-config": {"completed", "needs-input", "failed", "timed-out"},
            "discovery": {"completed", "needs-input", "failed", "timed-out"},
            "design": {"completed", "needs-input", "failed", "timed-out"},
            "plan": {"completed", "needs-input", "failed", "timed-out"},
            "plan-review": {"clean", "findings", "needs-input", "failed", "timed-out"},
            "plan-fix": {"completed", "needs-input", "failed", "timed-out"},
            "handoff": {"completed", "needs-input", "failed", "timed-out"},
        }[kind]
        if result.outcome not in allowed:
            raise LazyControllerError(f"{kind} action does not accept {result.outcome!r}")
        self._validate_result_fields(kind, result)

        snapshot: GitSnapshot | None = None
        overlap: tuple[str, ...] = ()
        digest = ""
        execution: tuple[str, str] | None = None
        matching: tuple[str, str] | None = None
        bootstrap: tuple[str, str] | None = None
        if kind == "input" and state.pending_gate == "dirty-overlap":
            overlap, snapshot = self._new_dirty_overlap(state)
            if overlap:
                self._progress(state, action_id, result)
                self._pause_for_overlap(
                    state,
                    overlap,
                    preserved_phase=state.preserved_phase,
                )
                return self.next_action()
        elif state.phase == "bootstrap-worktree" and result.outcome == "completed":
            bootstrap = self._validate_bootstrap_worktree(state, result)
        elif state.phase == "discovery" and result.outcome == "completed":
            snapshot = _git_snapshot(self._execution_root(state))
            overlap = self._path_overlap(snapshot.dirty_paths, result.scope_paths)
        elif state.phase == "plan" and result.outcome == "completed":
            digest = self._validate_plan_file(state, result)
            overlap, snapshot = self._new_dirty_overlap(state)
        elif state.phase == "plan-review" and result.outcome in {"clean", "findings"}:
            self._validate_current_digest(state)
            if result.outcome == "clean" and result.findings:
                raise LazyControllerError("clean plan review must not contain findings")
        elif state.phase == "plan-fix" and result.outcome == "completed":
            digest = self._validate_plan_file(state, result, fix=True)
        elif state.phase == "handoff" and result.outcome == "completed":
            execution = self._execution_coordinates(
                state, result, require_validated_digest=not bool(result.linked_run_id)
            )
            if result.linked_run_id:
                matching = self._matching_run(state)
                if not matching[0] or result.linked_run_id != matching[0]:
                    raise LazyControllerError("linked run id does not match the plan-keyed existing run")
                if result.run_outcome not in {"completed", "failed"}:
                    raise LazyControllerError("terminal handoff requires completed or failed run_outcome")
                if matching[1] != result.run_outcome:
                    raise LazyControllerError(
                        f"linked run is {matching[1]}, not {result.run_outcome}"
                    )
            elif state.execution_plan_path:
                raise LazyControllerError("handoff preparation is already recorded")

        # Append only accepted results, but do so before the state transition so
        # a lost response can safely replay the idempotent progress event.
        self._progress(state, action_id, result)
        if kind == "input":
            if result.decision == "stop":
                self._finish_failed(state, f"stopped by user at {state.pending_gate} gate")
                return self.next_action()
            changes: dict[str, Any] = {}
            if snapshot is not None:
                changes.update(
                    baseline_head=snapshot.head,
                    baseline_fingerprint=snapshot.fingerprint,
                    baseline_dirty_paths=snapshot.dirty_paths,
                    baseline_path_digests=snapshot.path_digests,
                )
            self.store.update(
                state.revision,
                **changes,
                status="running",
                phase=state.preserved_phase,
                pending_question="",
                pending_options=(),
                pending_gate="",
                preserved_phase="",
            )
            return self.next_action()
        if result.outcome == "needs-input":
            self._pause(state, result)
            return self.next_action()
        if result.outcome in {"failed", "timed-out"}:
            self._finish_failed(state, f"{state.phase} {result.outcome}: {result.summary}")
            return self.next_action()
        if state.phase == "bootstrap-worktree":
            assert bootstrap is not None
            self.store.update(
                state.revision,
                phase="bootstrap-config",
                execution_project_root=bootstrap[0],
                execution_branch=bootstrap[1],
            )
        elif state.phase == "bootstrap-config":
            self.store.update(state.revision, phase="discovery")
        elif state.phase == "discovery":
            assert snapshot is not None
            if overlap:
                self._pause_for_overlap(
                    state,
                    overlap,
                    preserved_phase="design",
                    discovery_summary=result.summary.strip(),
                    baseline_head=snapshot.head,
                    baseline_fingerprint=snapshot.fingerprint,
                    baseline_dirty_paths=snapshot.dirty_paths,
                    baseline_path_digests=snapshot.path_digests,
                    scope_paths=result.scope_paths,
                )
            else:
                self.store.update(
                    state.revision,
                    phase="design",
                    discovery_summary=result.summary.strip(),
                    baseline_head=snapshot.head,
                    baseline_fingerprint=snapshot.fingerprint,
                    baseline_dirty_paths=snapshot.dirty_paths,
                    baseline_path_digests=snapshot.path_digests,
                    scope_paths=result.scope_paths,
                )
        elif state.phase == "design":
            self.store.update(
                state.revision,
                phase="plan",
                design_summary=result.summary.strip(),
            )
        elif state.phase == "plan":
            if overlap:
                self._pause_for_overlap(
                    state,
                    overlap,
                    preserved_phase="plan-review",
                    plan_digest=digest,
                )
            else:
                self.store.update(state.revision, phase="plan-review", plan_digest=digest)
        elif state.phase == "plan-review":
            if result.outcome == "clean":
                run_overrides = self._run_overrides()
                run_overrides_digest = hashlib.sha256(
                    json.dumps(run_overrides, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                self.store.update(
                    state.revision,
                    phase="handoff",
                    findings=(),
                    run_overrides=run_overrides,
                    run_overrides_digest=run_overrides_digest,
                )
            else:
                if not result.findings:
                    raise LazyControllerError("findings result requires structured findings")
                if state.plan_review_iteration + 1 >= self.values["lazy"]["max_plan_review_iterations"]:
                    self._finish_failed(
                        state,
                        "plan review did not converge within configured iterations",
                        findings=result.findings,
                    )
                else:
                    self.store.update(
                        state.revision,
                        phase="plan-fix",
                        findings=result.findings,
                        plan_review_iteration=state.plan_review_iteration + 1,
                    )
        elif state.phase == "plan-fix":
            self.store.update(state.revision, phase="plan-review", plan_digest=digest, findings=())
        elif state.phase == "handoff":
            assert execution is not None
            root, plan = execution
            if not result.linked_run_id:
                self.store.update(
                    state.revision,
                    execution_project_root=root,
                    execution_plan_path=plan,
                )
            else:
                changes = {
                    "phase": "done",
                    "status": "completed" if result.run_outcome == "completed" else "failed",
                    "linked_run_id": result.linked_run_id,
                    "run_outcome": result.run_outcome,
                    "execution_project_root": root,
                    "execution_plan_path": plan,
                    "failure": "" if result.run_outcome == "completed" else "linked implementation run failed",
                }
                self.store.update(state.revision, **changes)
        return self.next_action()


def _load_effective(args: argparse.Namespace) -> Any:
    return PLANNING_CONFIG.load_effective(
        project_root=args.project_root,
        plugin_data=args.plugin_data,
        overrides=args.overrides,
        touched_files=args.touched_files,
    )


def _load_store_effective(args: argparse.Namespace, store: Any) -> Any:
    state = store.load()
    root = Path(state.execution_project_root) if state.execution_project_root else args.project_root
    return PLANNING_CONFIG.load_effective(
        project_root=root,
        plugin_data=args.plugin_data,
        overrides=args.overrides,
        touched_files=args.touched_files,
    )


def _main_worktree_root(root: Path) -> Path:
    output = str(_git(root.resolve(), "worktree", "list", "--porcelain", text=True))
    first = next(
        (line.removeprefix("worktree ") for line in output.splitlines() if line.startswith("worktree ")),
        "",
    )
    candidate = Path(first).resolve() if first else root.resolve()
    return candidate if candidate.is_dir() else root.resolve()


def _load_record_input(args: argparse.Namespace) -> dict[str, Any]:
    if args.result_file is not None:
        raw = args.result_file.read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            raise LazyControllerError(
                "record input is required; pipe JSON on stdin or use --result-file PATH"
            )
        try:
            ready, _, _ = select.select([sys.stdin], [], [], RECORD_STDIN_TIMEOUT_SECONDS)
        except (OSError, ValueError):  # pragma: no cover - non-POSIX stdin fallback
            ready = [sys.stdin]
        if not ready:
            raise LazyControllerError(
                "record input was not received within 1s; pipe JSON on stdin or use --result-file PATH"
            )
        raw = sys.stdin.read()
    if not raw.strip():
        raise LazyControllerError("record input is empty; pipe JSON on stdin or use --result-file PATH")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise LazyControllerError("record input must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--plugin-data", type=Path)
    parser.add_argument("--touched-file", dest="touched_files", action="append", default=[])
    parser.add_argument("--set", dest="overrides", action="append", default=[])
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start")
    start.add_argument("--request-id", required=True)
    start.add_argument("--idea", required=True)
    status = commands.add_parser("status")
    status.add_argument("--journey-id")
    next_parser = commands.add_parser("next")
    next_parser.add_argument("journey_id")
    record = commands.add_parser("record")
    record.add_argument("journey_id")
    record.add_argument("--action-id", required=True)
    record.add_argument("--result-file", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "start":
            args.project_root = _main_worktree_root(args.project_root)
            controller, _ = LazyController.start(
                args.project_root,
                _load_effective(args),
                request_id=args.request_id,
                idea=args.idea,
            )
            payload: Any = asdict(controller.next_action())
        elif args.command == "status":
            args.project_root = _main_worktree_root(args.project_root)
            if args.journey_id:
                state = LAZY_STATE.LazyStateStore(args.project_root, args.journey_id).load()
                payload = {"state": asdict(state)}
            else:
                payload = {
                    "active": [asdict(state) for state in LAZY_STATE.discover_journeys(args.project_root, active_only=True)],
                    "recent": [asdict(state) for state in LAZY_STATE.discover_journeys(args.project_root, limit=20)],
                }
        else:
            args.project_root = _main_worktree_root(args.project_root)
            store = LAZY_STATE.LazyStateStore(args.project_root, args.journey_id)
            controller = LazyController(store, _load_store_effective(args, store))
            if args.command == "next":
                action = controller.next_action()
            else:
                value = _load_record_input(args)
                action = controller.record_result(args.action_id, LazyResult.from_mapping(value))
            payload = asdict(action)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    except (
        LazyControllerError,
        LAZY_STATE.LazyStateError,
        PLANNING_CONFIG.ConfigError,
        PLAN_STATE.PlanStateError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
