#!/usr/bin/env python3
"""Drive the Codex planning phase state machine through native action records.

The controller never launches Codex, subagents, Pi, Git, or a shell. It emits
the next bounded action for the root Codex task and records the structured
outcome using restart-safe state from plan_state.py.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import importlib.util
import json
from pathlib import Path
import re
import sys
from types import ModuleType
from typing import Any, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
RESULT_OUTCOMES = frozenset({"completed", "clean", "findings", "failed", "timed-out", "skipped"})


def _load_sibling(module_name: str, filename: str) -> ModuleType:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_DIR / filename)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging guard
        raise RuntimeError(f"cannot load bundled module: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


PLAN_STATE = _load_sibling("_phasemill_plan_state", "plan_state.py")
PLANNING_CONFIG = _load_sibling("_phasemill_config", "config.py")


class PhaseControllerError(RuntimeError):
    """The action or result violates the current phase contract."""


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
class PhaseAction:
    action_id: str
    kind: str
    phase: str
    iteration: int
    expected_revision: int
    prompt_name: str = ""
    prompt: str = ""
    task: Mapping[str, Any] | None = None
    agent: NativeAgent | None = None
    agent_options: Mapping[str, NativeAgent] | None = None
    roles: tuple[ReviewRole, ...] = ()
    max_parallel_agents: int = 1
    external: Mapping[str, Any] | None = None
    reason: str = ""


@dataclass(frozen=True)
class PhaseResult:
    outcome: str
    summary: str = ""
    head_before: str = ""
    head_after: str = ""
    diff_before: str = ""
    diff_after: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> PhaseResult:
        unknown = set(value) - set(cls.__dataclass_fields__)
        if unknown:
            raise PhaseControllerError(f"unknown result fields: {', '.join(sorted(unknown))}")
        try:
            result = cls(**value)
        except TypeError as exc:
            raise PhaseControllerError(f"invalid result: {exc}") from exc
        result.validate()
        return result

    def validate(self) -> None:
        if self.outcome not in RESULT_OUTCOMES:
            raise PhaseControllerError(f"invalid result outcome: {self.outcome!r}")
        for name in ("summary", "head_before", "head_after", "diff_before", "diff_after"):
            if not isinstance(getattr(self, name), str):
                raise PhaseControllerError(f"result {name} must be a string")


def _snapshot_changed(result: PhaseResult) -> bool | None:
    comparisons: list[bool] = []
    if result.head_before and result.head_after:
        comparisons.append(result.head_before != result.head_after)
    if result.diff_before and result.diff_after:
        comparisons.append(result.diff_before != result.diff_after)
    return any(comparisons) if comparisons else None


class PhaseController:
    """Emit idempotent actions and apply revision-checked outcomes."""

    def __init__(self, store: Any, effective_config: Any, *, default_branch: str) -> None:
        if not default_branch.strip():
            raise PhaseControllerError("default branch must not be empty")
        self.store = store
        self.config = effective_config
        self.default_branch = default_branch.strip()

    @property
    def values(self) -> Mapping[str, Any]:
        return self.config.values

    def _action_id(self, state: Any, kind: str) -> str:
        return f"{state.run_id}:{state.revision}:{kind}"

    def _plan_context(self) -> tuple[str, Any]:
        try:
            content = self.store.plan_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PhaseControllerError(f"cannot read plan {self.store.plan_path}: {exc}") from exc
        return content, PLAN_STATE.parse_plan(content)

    def _goal(self) -> str:
        _, plan = self._plan_context()
        return plan.title or self.store.plan_path.stem

    def _guidance(self, kind: str) -> str:
        relevant = {
            "task": {"implementation", "testing", "profile", "instructions"},
            "review": {"review", "testing", "profile", "instructions"},
            "external-review": {"review", "profile", "instructions"},
            "finalize": {"implementation", "testing", "review", "profile", "instructions"},
            "learning": {
                "brainstorm",
                "planning",
                "implementation",
                "testing",
                "review",
                "writing-style",
                "profile",
                "instructions",
            },
        }[kind]
        fragments = [fragment for fragment in self.config.rules if fragment.kind in relevant]
        if not fragments:
            return ""
        parts = ["## Active project guidance"]
        for fragment in fragments:
            parts.append(f"### {fragment.source}: {fragment.path}\n{fragment.content.strip()}")
        return "\n\n".join(parts)

    def _prompt(self, name: str, kind: str) -> str:
        replacement = self.config.prompts[name]
        values = {
            "GOAL": self._goal(),
            "PLAN_FILE": str(self.store.plan_path.resolve()),
            "PROGRESS_FILE": str(self.store.paths.progress.resolve()),
            "DEFAULT_BRANCH": self.default_branch,
        }
        prompt = replacement.content
        for key, value in values.items():
            prompt = prompt.replace(f"{{{{{key}}}}}", value)
        unresolved = sorted(set(PLACEHOLDER.findall(prompt)))
        if unresolved:
            raise PhaseControllerError(
                f"prompt {name!r} has unresolved placeholders: {', '.join(unresolved)}"
            )
        guidance = self._guidance(kind)
        return f"{prompt.rstrip()}\n\n{guidance}\n" if guidance else prompt

    def _roles(self, critical_only: bool) -> tuple[ReviewRole, ...]:
        selected = list(self.config.selected_agents)
        if critical_only:
            narrowed = [name for name in ("implementation", "quality") if name in selected]
            selected = narrowed or selected
        return tuple(
            ReviewRole(
                name=name,
                source=self.config.agents[name].source,
                prompt=self.config.agents[name].content,
                agent=self._native_agent(
                    self.values["review"]["agent_profiles"].get(
                        name,
                        self.values["review"]["fallback_agent"],
                    )
                ),
            )
            for name in selected
        )

    def _native_agent(self, name: str) -> NativeAgent:
        profile = self.values["agents"][name]
        return NativeAgent(
            name=name,
            model=profile["model"],
            model_reasoning_effort=profile["model_reasoning_effort"],
        )

    def _task_agents(self, state: Any) -> tuple[NativeAgent, Mapping[str, NativeAgent]]:
        execution = self.values["execution"]
        if state.task_retry_count > 0:
            return self._native_agent(execution["recovery_agent"]), {}
        return self._native_agent(execution["implementer_agent"]), {
            "cross-module": self._native_agent(execution["cross_module_agent"]),
            "mechanical": self._native_agent(execution["mechanical_agent"]),
        }

    def _terminal_action(self, state: Any) -> PhaseAction:
        kind = "done" if state.status == "completed" else "failed"
        reason = "completed" if state.status == "completed" else state.failure
        return PhaseAction(
            action_id=self._action_id(state, kind),
            kind=kind,
            phase=state.phase,
            iteration=0,
            expected_revision=state.revision,
            reason=reason,
        )

    def _transition(self, state: Any, phase: str, message: str, **changes: Any) -> Any:
        self.store.append_progress(message, run_id=state.run_id)
        return self.store.update(
            state.revision,
            phase=phase,
            current_task_identifier="",
            current_task_line=0,
            **changes,
        )

    def _finish_failed(self, state: Any, reason: str) -> PhaseAction:
        failed = self.store.finish(state.revision, success=False, failure=reason)
        return self._terminal_action(failed)

    def next_action(self) -> PhaseAction:
        for _ in range(8):
            state = self.store.load()
            if state.status != "running":
                return self._terminal_action(state)

            if state.phase == "task":
                state = self.store.reconcile_plan(state.revision)
                if state.phase != "task":
                    continue
                if state.current_task_identifier == "unscoped":
                    return self._finish_failed(
                        state,
                        "plan has no executable sections (expected ### Task N: or ### Iteration N:)",
                    )
                max_iterations = self.values["execution"]["max_task_iterations"]
                if state.task_iteration >= max_iterations:
                    return self._finish_failed(state, f"max task iterations reached: {max_iterations}")
                _, plan = self._plan_context()
                task = asdict(plan.next_task) if plan.next_task is not None else {
                    "identifier": state.current_task_identifier,
                    "header_line": state.current_task_line,
                    "title": "Unscoped actionable work",
                }
                agent, agent_options = self._task_agents(state)
                return PhaseAction(
                    action_id=self._action_id(state, "task"),
                    kind="task",
                    phase=state.phase,
                    iteration=state.task_iteration + 1,
                    expected_revision=state.revision,
                    prompt_name="task",
                    prompt=self._prompt("task", "task"),
                    task=task,
                    agent=agent,
                    agent_options=agent_options,
                )

            if state.phase == "review-first":
                return PhaseAction(
                    action_id=self._action_id(state, "review"),
                    kind="review",
                    phase=state.phase,
                    iteration=0,
                    expected_revision=state.revision,
                    prompt_name="review-first",
                    prompt=self._prompt("review-first", "review"),
                    roles=self._roles(critical_only=False),
                    max_parallel_agents=self.values["review"]["max_parallel_agents"],
                )

            if state.phase in {"review", "post-review"}:
                max_iterations = self.values["review"]["max_iterations"]
                if state.review_iteration >= max_iterations:
                    next_phase = "external-review" if state.phase == "review" else "finalize"
                    state = self._transition(
                        state,
                        next_phase,
                        f"{state.phase}: max iterations reached",
                        review_iteration=0,
                    )
                    continue
                return PhaseAction(
                    action_id=self._action_id(state, "review"),
                    kind="review",
                    phase=state.phase,
                    iteration=state.review_iteration + 1,
                    expected_revision=state.revision,
                    prompt_name="review-second",
                    prompt=self._prompt("review-second", "review"),
                    roles=self._roles(critical_only=True),
                    max_parallel_agents=min(2, self.values["review"]["max_parallel_agents"]),
                )

            if state.phase == "external-review":
                external = self.values["review"]["external"]
                if external["backend"] == "none":
                    state = self._transition(state, "finalize", "external review disabled")
                    continue
                max_iterations = self._max_external_iterations()
                if state.external_review_iteration >= max_iterations:
                    phase = "post-review" if state.external_had_findings else "finalize"
                    state = self._transition(
                        state,
                        phase,
                        "external review: max iterations reached",
                        review_iteration=0,
                    )
                    continue
                return PhaseAction(
                    action_id=self._action_id(state, "external-review"),
                    kind="external-review",
                    phase=state.phase,
                    iteration=state.external_review_iteration + 1,
                    expected_revision=state.revision,
                    prompt_name="pi-review",
                    prompt=self._prompt("pi-review", "external-review"),
                    external={
                        "backend": external["backend"],
                        "required": external["required"],
                        "command": external["command"],
                        "timeout_seconds": external["timeout_seconds"],
                        "idle_timeout_seconds": external["idle_timeout_seconds"],
                    },
                )

            if state.phase == "finalize":
                if not self.values["finalize"]["enabled"]:
                    if self.values["learning"]["auto_propose"]:
                        state = self._transition(
                            state,
                            "learning",
                            "finalize disabled; checking learning signals",
                        )
                        continue
                    completed = self.store.finish(state.revision, success=True)
                    return self._terminal_action(completed)
                return PhaseAction(
                    action_id=self._action_id(state, "finalize"),
                    kind="finalize",
                    phase=state.phase,
                    iteration=1,
                    expected_revision=state.revision,
                    prompt_name="finalize",
                    prompt=self._prompt("finalize", "finalize"),
                )

            if state.phase == "learning":
                if not self.values["learning"]["auto_propose"]:
                    completed = self.store.finish(state.revision, success=True)
                    return self._terminal_action(completed)
                return PhaseAction(
                    action_id=self._action_id(state, "learning"),
                    kind="learning",
                    phase=state.phase,
                    iteration=1,
                    expected_revision=state.revision,
                    prompt_name="learning",
                    prompt=self._prompt("learning", "learning"),
                )

            raise PhaseControllerError(f"unsupported running phase: {state.phase}")
        raise PhaseControllerError("automatic phase transition loop did not converge")

    def _max_external_iterations(self) -> int:
        configured = self.values["review"]["max_external_iterations"]
        if configured > 0:
            return configured
        return max(3, self.values["execution"]["max_task_iterations"] // 5)

    def _validate_action(self, state: Any, action_id: str, kind: str) -> None:
        expected = self._action_id(state, kind)
        if action_id != expected:
            raise PLAN_STATE.StateConflictError(f"stale or mismatched action: expected {expected}")

    def _record_summary(self, state: Any, result: PhaseResult) -> None:
        summary = result.summary.strip() or result.outcome
        self.store.append_progress(
            f"{state.phase} result: {result.outcome}\n{summary}",
            run_id=state.run_id,
        )

    def _validate_phase_outcome(self, state: Any, outcome: str) -> None:
        allowed = {
            "task": {"completed", "failed", "timed-out"},
            "review-first": {"clean", "findings", "failed", "timed-out"},
            "review": {"clean", "findings", "failed", "timed-out"},
            "post-review": {"clean", "findings", "failed", "timed-out"},
            "external-review": {"clean", "findings", "failed", "timed-out", "skipped"},
            "finalize": {"completed", "failed", "timed-out"},
            "learning": {"completed", "clean", "failed", "timed-out", "skipped"},
        }[state.phase]
        if outcome not in allowed:
            raise PhaseControllerError(f"{state.phase} action does not accept {outcome!r}")

    def record_result(self, action_id: str, result: PhaseResult) -> PhaseAction:
        result.validate()
        state = self.store.load()
        if state.status != "running":
            raise PhaseControllerError(f"cannot record a result for {state.status} run")
        kind = (
            "external-review"
            if state.phase == "external-review"
            else "finalize"
            if state.phase == "finalize"
            else "learning"
            if state.phase == "learning"
            else "review"
            if state.phase.startswith("review") or state.phase == "post-review"
            else "task"
        )
        self._validate_action(state, action_id, kind)
        self._validate_phase_outcome(state, result.outcome)
        self._record_summary(state, result)

        if state.phase == "task":
            self._record_task(state, result)
        elif state.phase == "review-first":
            self._record_first_review(state, result)
        elif state.phase in {"review", "post-review"}:
            self._record_review_loop(state, result)
        elif state.phase == "external-review":
            self._record_external(state, result)
        elif state.phase == "finalize":
            self._record_finalize(state, result)
        elif state.phase == "learning":
            self._record_learning(state, result)
        else:  # pragma: no cover - state validation protects this
            raise PhaseControllerError(f"unsupported result phase: {state.phase}")
        return self.next_action()

    def _record_task(self, state: Any, result: PhaseResult) -> None:
        if result.outcome not in {"completed", "failed", "timed-out"}:
            raise PhaseControllerError(f"task action does not accept {result.outcome!r}")
        iteration = state.task_iteration + 1
        if result.outcome == "failed":
            retries = self.values["execution"]["task_retries"]
            if state.task_retry_count >= retries:
                self.store.finish(state.revision, success=False, failure="task failed after configured retries")
                return
            self.store.update(
                state.revision,
                task_iteration=iteration,
                task_retry_count=state.task_retry_count + 1,
            )
            return
        updated = self.store.update(
            state.revision,
            task_iteration=iteration,
            task_retry_count=0 if result.outcome == "completed" else state.task_retry_count,
        )
        if result.outcome == "completed":
            self.store.reconcile_plan(updated.revision)

    def _record_first_review(self, state: Any, result: PhaseResult) -> None:
        if result.outcome not in {"clean", "findings", "failed", "timed-out"}:
            raise PhaseControllerError(f"first review action does not accept {result.outcome!r}")
        if result.outcome in {"failed", "timed-out"}:
            self.store.finish(state.revision, success=False, failure=f"first review {result.outcome}")
            return
        phase = "external-review" if result.outcome == "clean" else "review"
        self.store.update(state.revision, phase=phase, review_iteration=0)

    def _record_review_loop(self, state: Any, result: PhaseResult) -> None:
        if result.outcome not in {"clean", "findings", "failed", "timed-out"}:
            raise PhaseControllerError(f"review action does not accept {result.outcome!r}")
        if result.outcome == "failed":
            self.store.finish(state.revision, success=False, failure=f"{state.phase} failed")
            return
        next_phase = "external-review" if state.phase == "review" else "finalize"
        if result.outcome == "clean" or (
            result.outcome == "findings" and _snapshot_changed(result) is False
        ):
            self.store.update(
                state.revision,
                phase=next_phase,
                review_iteration=0,
                current_task_identifier="",
                current_task_line=0,
            )
            return
        self.store.update(state.revision, review_iteration=state.review_iteration + 1)

    def _record_external(self, state: Any, result: PhaseResult) -> None:
        if result.outcome not in {"clean", "findings", "failed", "timed-out", "skipped"}:
            raise PhaseControllerError(f"external review action does not accept {result.outcome!r}")
        external = self.values["review"]["external"]
        if result.outcome in {"failed", "skipped"}:
            if external["required"]:
                self.store.finish(
                    state.revision,
                    success=False,
                    failure=f"required external review {result.outcome}",
                )
                return
            phase = "post-review" if state.external_had_findings else "finalize"
            self.store.update(
                state.revision,
                phase=phase,
                review_iteration=0,
                current_task_identifier="",
                current_task_line=0,
            )
            return
        if result.outcome == "clean":
            phase = "post-review" if state.external_had_findings else "finalize"
            self.store.update(
                state.revision,
                phase=phase,
                review_iteration=0,
                current_task_identifier="",
                current_task_line=0,
            )
            return

        iteration = state.external_review_iteration + 1
        if result.outcome == "timed-out":
            self.store.update(state.revision, external_review_iteration=iteration)
            return

        changed = _snapshot_changed(result)
        unchanged = state.external_unchanged_rounds + 1 if changed is False else 0
        patience = self.values["review"]["patience"]
        if patience > 0 and unchanged >= patience:
            self.store.update(
                state.revision,
                phase="post-review",
                review_iteration=0,
                external_review_iteration=iteration,
                external_unchanged_rounds=unchanged,
                external_had_findings=True,
                current_task_identifier="",
                current_task_line=0,
            )
            return
        self.store.update(
            state.revision,
            external_review_iteration=iteration,
            external_unchanged_rounds=unchanged,
            external_had_findings=True,
        )

    def _record_finalize(self, state: Any, result: PhaseResult) -> None:
        if result.outcome not in {"completed", "failed", "timed-out"}:
            raise PhaseControllerError(f"finalize action does not accept {result.outcome!r}")
        if result.outcome == "completed":
            if self.values["learning"]["auto_propose"]:
                self.store.update(state.revision, phase="learning")
            else:
                self.store.finish(state.revision, success=True)
        else:
            self.store.finish(state.revision, success=False, failure=f"finalize {result.outcome}")

    def _record_learning(self, state: Any, result: PhaseResult) -> None:
        if result.outcome not in {"completed", "clean", "failed", "timed-out", "skipped"}:
            raise PhaseControllerError(f"learning action does not accept {result.outcome!r}")
        # Learning is advisory and proposal-only. A failure must not turn an
        # already validated implementation into a failed run.
        self.store.finish(state.revision, success=True)


def _action_payload(action: PhaseAction) -> dict[str, Any]:
    return asdict(action)


def _load_effective(args: argparse.Namespace) -> Any:
    return PLANNING_CONFIG.load_effective(
        project_root=args.project_root,
        plugin_data=args.plugin_data,
        overrides=args.overrides,
        touched_files=args.touched_files,
    )


def _controller(args: argparse.Namespace) -> PhaseController:
    store = PLAN_STATE.RunStateStore(args.project_root, args.plan)
    return PhaseController(store, _load_effective(args), default_branch=args.default_branch)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--plugin-data", type=Path)
    parser.add_argument("--default-branch", default="")
    parser.add_argument("--touched-file", dest="touched_files", action="append", default=[])
    parser.add_argument("--set", dest="overrides", action="append", default=[])
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "next", "show"):
        command = subparsers.add_parser(name)
        command.add_argument("plan", type=Path)
    record = subparsers.add_parser("record")
    record.add_argument("plan", type=Path)
    record.add_argument("--action-id", required=True)
    args = parser.parse_args()

    try:
        if args.command == "show":
            state = PLAN_STATE.RunStateStore(args.project_root, args.plan).load()
            payload: Any = {"state": asdict(state)}
        else:
            controller = _controller(args)
            if args.command == "start":
                controller.store.initialize()
                action = controller.next_action()
            elif args.command == "next":
                action = controller.next_action()
            else:
                value = json.load(sys.stdin)
                if not isinstance(value, dict):
                    raise PhaseControllerError("record input must be a JSON object")
                action = controller.record_result(args.action_id, PhaseResult.from_mapping(value))
            payload = _action_payload(action)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    except (
        PhaseControllerError,
        PLAN_STATE.PlanStateError,
        PLANNING_CONFIG.ConfigError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
