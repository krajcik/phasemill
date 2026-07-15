#!/usr/bin/env python3
"""Dependency-free stdio MCP adapter for the Phasemill state engine."""

from __future__ import annotations

from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from typing import Any, Callable, Mapping


SERVER_NAME = "phasemill"
SERVER_VERSION = "1.2.0"
LATEST_PROTOCOL = "2025-11-25"
SUPPORTED_PROTOCOLS = frozenset({LATEST_PROTOCOL, "2025-06-18", "2025-03-26", "2024-11-05"})
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = PLUGIN_ROOT / "engine"


class ToolError(RuntimeError):
    """An actionable tool execution error that should be visible to the model."""


def _load_module(name: str, filename: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ENGINE_ROOT / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load bundled engine module: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PLAN_STATE = _load_module("_phasemill_mcp_plan_state", "plan_state.py")
CONFIG = _load_module("_phasemill_mcp_config", "config.py")
CONTROLLER = _load_module("_phasemill_mcp_controller", "phase_controller.py")
PI_REVIEW = _load_module("_phasemill_mcp_pi_review", "pi_review.py")


def _object(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ToolError(f"{name} must be an object")
    return value


def _string(arguments: Mapping[str, Any], name: str, *, required: bool = True) -> str:
    value = arguments.get(name)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        suffix = "a non-empty string" if required else "a string"
        raise ToolError(f"{name} must be {suffix}")
    return value.strip() if required else value


def _string_list(arguments: Mapping[str, Any], name: str) -> list[str]:
    value = arguments.get(name, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ToolError(f"{name} must be an array of non-empty strings")
    return list(value)


def _number(
    arguments: Mapping[str, Any],
    name: str,
    default: float,
    *,
    minimum: float,
) -> float:
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
        raise ToolError(f"{name} must be a number greater than or equal to {minimum:g}")
    return float(value)


def _boolean(arguments: Mapping[str, Any], name: str, default: bool) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise ToolError(f"{name} must be a boolean")
    return value


def _project_root(arguments: Mapping[str, Any]) -> Path:
    root = Path(_string(arguments, "projectRoot")).expanduser().resolve()
    if not root.is_dir():
        raise ToolError(f"projectRoot is not a directory: {root}")
    return root


def _plan_path(project_root: Path, arguments: Mapping[str, Any]) -> Path:
    requested = Path(_string(arguments, "plan"))
    candidate = requested.resolve() if requested.is_absolute() else (project_root / requested).resolve()
    if candidate != project_root and project_root not in candidate.parents:
        raise ToolError(f"plan is outside projectRoot: {candidate}")
    return candidate


def _run_git(project_root: Path, *argv: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(project_root), *argv],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _default_branch(project_root: Path, arguments: Mapping[str, Any]) -> str:
    supplied = _string(arguments, "defaultBranch", required=False).strip()
    if supplied:
        return supplied
    remote = _run_git(project_root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if remote.startswith("origin/"):
        return remote.removeprefix("origin/")
    for candidate in ("main", "master", "trunk", "develop"):
        if _run_git(project_root, "show-ref", "--verify", f"refs/heads/{candidate}"):
            return candidate
    return "main"


def _load_effective(project_root: Path, arguments: Mapping[str, Any]) -> Any:
    plugin_data = os.environ.get("PLUGIN_DATA", "").strip()
    return CONFIG.load_effective(
        project_root=project_root,
        plugin_data=Path(plugin_data) if plugin_data else None,
        overrides=_string_list(arguments, "overrides"),
        touched_files=_string_list(arguments, "touchedFiles"),
    )


def _controller(project_root: Path, plan: Path, arguments: Mapping[str, Any]) -> Any:
    store = PLAN_STATE.RunStateStore(project_root, plan)
    return CONTROLLER.PhaseController(
        store,
        _load_effective(project_root, arguments),
        default_branch=_default_branch(project_root, arguments),
    )


def plan_inspect(arguments: Mapping[str, Any]) -> dict[str, Any]:
    project_root = _project_root(arguments)
    return PLAN_STATE._plan_payload(_plan_path(project_root, arguments))


def config_resolve(arguments: Mapping[str, Any]) -> dict[str, Any]:
    return CONFIG.show_payload(_load_effective(_project_root(arguments), arguments))


def run_start(arguments: Mapping[str, Any]) -> dict[str, Any]:
    project_root = _project_root(arguments)
    controller = _controller(project_root, _plan_path(project_root, arguments), arguments)
    controller.store.initialize()
    return asdict(controller.next_action())


def _state_files(project_root: Path) -> list[Path]:
    directory = project_root / PLAN_STATE.RUNS_DIRECTORY
    return sorted(directory.glob("state-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def _read_state_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ToolError(f"cannot read state {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ToolError(f"state must be an object: {path}")
    state = PLAN_STATE.RunState.from_mapping(value)
    return {"state": asdict(state), "statePath": str(path)}


def run_status(arguments: Mapping[str, Any]) -> dict[str, Any]:
    project_root = _project_root(arguments)
    plan = _string(arguments, "plan", required=False).strip()
    if plan:
        store = PLAN_STATE.RunStateStore(project_root, _plan_path(project_root, arguments))
        return {
            "state": asdict(store.load()),
            "paths": {name: str(path) for name, path in asdict(store.paths).items()},
        }
    runs = [_read_state_file(path) for path in _state_files(project_root)]
    active = [item for item in runs if item["state"]["status"] == "running"]
    return {"active": active, "recent": runs[:20]}


def run_next(arguments: Mapping[str, Any]) -> dict[str, Any]:
    project_root = _project_root(arguments)
    controller = _controller(project_root, _plan_path(project_root, arguments), arguments)
    return asdict(controller.next_action())


def run_record(arguments: Mapping[str, Any]) -> dict[str, Any]:
    project_root = _project_root(arguments)
    controller = _controller(project_root, _plan_path(project_root, arguments), arguments)
    action_id = _string(arguments, "actionId")
    result = CONTROLLER.PhaseResult.from_mapping(_object(arguments.get("result"), "result"))
    return asdict(controller.record_result(action_id, result))


def external_review(arguments: Mapping[str, Any]) -> dict[str, Any]:
    project_root = _project_root(arguments)
    command = _string_list(arguments, "command") or ["pi"]
    result = PI_REVIEW.run_pi_review(
        _string(arguments, "prompt"),
        cwd=project_root,
        command=command,
        timeout_seconds=_number(arguments, "timeoutSeconds", 900, minimum=1),
        idle_timeout_seconds=_number(arguments, "idleTimeoutSeconds", 120, minimum=1),
        required=_boolean(arguments, "required", False),
    )
    return asdict(result)


COMMON_RUN_PROPERTIES: dict[str, Any] = {
    "projectRoot": {"type": "string", "description": "Absolute repository root."},
    "plan": {"type": "string", "description": "Plan path relative to projectRoot."},
    "defaultBranch": {"type": "string", "description": "Optional default branch override."},
    "touchedFiles": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Files touched by the current action for language profile selection.",
    },
    "overrides": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Temporary config overrides as dotted.path=TOML_VALUE.",
    },
}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "plan_inspect",
        "description": "Parse a Phasemill plan and report its tasks and next actionable item without mutation.",
        "inputSchema": {
            "type": "object",
            "properties": {key: COMMON_RUN_PROPERTIES[key] for key in ("projectRoot", "plan")},
            "required": ["projectRoot", "plan"],
            "additionalProperties": False,
        },
    },
    {
        "name": "config_resolve",
        "description": "Resolve and validate effective Phasemill config, profiles, roles, and rules.",
        "inputSchema": {
            "type": "object",
            "properties": {key: COMMON_RUN_PROPERTIES[key] for key in ("projectRoot", "touchedFiles", "overrides")},
            "required": ["projectRoot"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_start",
        "description": "Start or restart a durable run and return the first bounded Codex action.",
        "inputSchema": {
            "type": "object",
            "properties": COMMON_RUN_PROPERTIES,
            "required": ["projectRoot", "plan"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_status",
        "description": "Read a specific run or discover active and recent runs without mutation.",
        "inputSchema": {
            "type": "object",
            "properties": {key: COMMON_RUN_PROPERTIES[key] for key in ("projectRoot", "plan")},
            "required": ["projectRoot"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_next",
        "description": "Return the current bounded action for an existing run and apply automatic phase transitions.",
        "inputSchema": {
            "type": "object",
            "properties": COMMON_RUN_PROPERTIES,
            "required": ["projectRoot", "plan"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_record",
        "description": "Atomically record a bounded action result and return the next action.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **COMMON_RUN_PROPERTIES,
                "actionId": {"type": "string"},
                "result": {
                    "type": "object",
                    "properties": {
                        "outcome": {
                            "type": "string",
                            "enum": ["completed", "clean", "findings", "failed", "timed-out", "skipped"],
                        },
                        "summary": {"type": "string"},
                        "head_before": {"type": "string"},
                        "head_after": {"type": "string"},
                        "diff_before": {"type": "string"},
                        "diff_after": {"type": "string"},
                    },
                    "required": ["outcome"],
                    "additionalProperties": False,
                },
            },
            "required": ["projectRoot", "plan", "actionId", "result"],
            "additionalProperties": False,
        },
    },
    {
        "name": "external_review",
        "description": "Run the independent read-only Pi/GLM review with direct networking and bounded timeouts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectRoot": COMMON_RUN_PROPERTIES["projectRoot"],
                "prompt": {"type": "string"},
                "command": {"type": "array", "items": {"type": "string"}, "default": ["pi"]},
                "timeoutSeconds": {"type": "number", "minimum": 1, "default": 900},
                "idleTimeoutSeconds": {"type": "number", "minimum": 1, "default": 120},
                "required": {"type": "boolean", "default": False},
            },
            "required": ["projectRoot", "prompt"],
            "additionalProperties": False,
        },
    },
]


TOOL_HANDLERS: dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]] = {
    "plan_inspect": plan_inspect,
    "config_resolve": config_resolve,
    "run_start": run_start,
    "run_status": run_status,
    "run_next": run_next,
    "run_record": run_record,
    "external_review": external_review,
}


def _response(message_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": message_id, "error": error}


def _tool_result(value: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, indent=2, default=str)}],
        "structuredContent": value,
        "isError": is_error,
    }


def _dispatch(message: Mapping[str, Any]) -> dict[str, Any] | None:
    message_id = message.get("id")
    method = message.get("method")
    if not isinstance(method, str):
        return _error(message_id, -32600, "Invalid Request")
    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        params = _object(message.get("params"), "params")
        requested = params.get("protocolVersion")
        protocol = requested if requested in SUPPORTED_PROTOCOLS else LATEST_PROTOCOL
        return _response(
            message_id,
            {
                "protocolVersion": protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "Use run_start/run_next/run_record as the durable state-machine boundary. Native Codex subagents execute returned actions.",
            },
        )
    if method == "ping":
        return _response(message_id, {})
    if method == "tools/list":
        return _response(message_id, {"tools": TOOLS})
    if method == "tools/call":
        params = _object(message.get("params"), "params")
        name = params.get("name")
        arguments = _object(params.get("arguments"), "arguments")
        if not isinstance(name, str) or name not in TOOL_HANDLERS:
            return _error(message_id, -32602, "Unknown tool", {"name": name})
        try:
            return _response(message_id, _tool_result(TOOL_HANDLERS[name](arguments)))
        except (
            ToolError,
            PLAN_STATE.PlanStateError,
            CONTROLLER.PLAN_STATE.PlanStateError,
            CONTROLLER.PhaseControllerError,
            CONFIG.ConfigError,
            CONTROLLER.PLANNING_CONFIG.ConfigError,
            OSError,
            UnicodeError,
            ValueError,
        ) as exc:
            return _response(message_id, _tool_result({"error": str(exc)}, is_error=True))
    return _error(message_id, -32601, "Method not found", {"method": method})


def serve(input_stream: Any = sys.stdin, output_stream: Any = sys.stdout) -> int:
    for raw_line in input_stream:
        if not raw_line.strip():
            continue
        try:
            message = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, "Parse error", {"detail": exc.msg})
        else:
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                response = _error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
            else:
                try:
                    response = _dispatch(message)
                except (ToolError, RuntimeError, TypeError, ValueError) as exc:
                    response = _error(message.get("id"), -32603, "Internal error", {"detail": str(exc)})
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
            output_stream.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
