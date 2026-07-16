#!/usr/bin/env python3
"""Layered configuration and customization loader for Codex planning.

The merge and complete-file fallback behavior is adapted from
umputun/ralphex pkg/config at c536f66ad2868796ddb0220ab00c19e6b56152a6.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_ROOT = PLUGIN_ROOT / "defaults"
PROJECT_CONFIG_DIR = Path(".codex/phasemill")

PROFILE_SUFFIXES = {
    ".go": "go",
    ".py": "python",
    ".js": "javascript-typescript",
    ".jsx": "javascript-typescript",
    ".mjs": "javascript-typescript",
    ".cjs": "javascript-typescript",
    ".ts": "javascript-typescript",
    ".tsx": "javascript-typescript",
    ".java": "java-kotlin",
    ".kt": "java-kotlin",
    ".kts": "java-kotlin",
    ".php": "php",
    ".rs": "rust",
}
PROFILE_MARKERS = {
    "go.mod": "go",
    "pyproject.toml": "python",
    "setup.py": "python",
    "package.json": "javascript-typescript",
    "pom.xml": "java-kotlin",
    "build.gradle": "java-kotlin",
    "build.gradle.kts": "java-kotlin",
    "composer.json": "php",
    "Cargo.toml": "rust",
}
RULE_KINDS = (
    "brainstorm",
    "planning",
    "implementation",
    "testing",
    "review",
    "writing-style",
)
REQUIRED_PROMPTS = frozenset(
    {
        "make-plan",
        "task",
        "review-first",
        "review-second",
        "finalize",
        "pi-review",
        "learning",
        "lazy-discovery",
        "lazy-design",
        "lazy-plan",
        "lazy-plan-review",
        "lazy-plan-fix",
    }
)
REQUIRED_AGENTS = frozenset({"implementation", "quality", "testing", "documentation", "simplification"})
REQUIRED_NATIVE_AGENTS = frozenset(
    {
        "planner",
        "implementer",
        "cross-module-implementer",
        "recovery-implementer",
        "reviewer",
        "explorer",
        "mechanical",
        "review-implementation",
        "review-quality",
        "review-testing",
        "review-documentation",
        "review-simplification",
        "terra",
    }
)
SENSITIVE_KEY = re.compile(r"(?:token|secret|password|credential|api[_-]?key)", re.I)
_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")


class ConfigError(ValueError):
    """Configuration is invalid or unsafe to apply."""


@dataclass(frozen=True)
class FieldSpec:
    kind: str
    minimum: int | None = None
    maximum: int | None = None
    choices: frozenset[str] | None = None
    fixed: Any = None
    has_fixed: bool = False
    allow_empty: bool = True


@dataclass(frozen=True)
class DynamicTableSpec:
    schema: Mapping[str, Any]


AGENT_PROFILE_SCHEMA: dict[str, Any] = {
    "model": FieldSpec("str", allow_empty=False),
    "model_reasoning_effort": FieldSpec(
        "str",
        choices=frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}),
    ),
    "enabled": FieldSpec("bool"),
}


SCHEMA: dict[str, Any] = {
    "execution": {
        "task_retries": FieldSpec("int", 0, 10),
        "max_task_iterations": FieldSpec("int", 1, 1000),
        "iteration_delay_ms": FieldSpec("int", 0, 600_000),
        "session_timeout": FieldSpec("duration"),
        "idle_timeout": FieldSpec("duration"),
        "implementer_agent": FieldSpec("str", allow_empty=False),
        "cross_module_agent": FieldSpec("str", allow_empty=False),
        "recovery_agent": FieldSpec("str", allow_empty=False),
        "mechanical_agent": FieldSpec("str", allow_empty=False),
    },
    "review": {
        "agents": FieldSpec("string-list"),
        "disabled_agents": FieldSpec("string-list"),
        "agent_profiles": FieldSpec("string-map"),
        "fallback_agent": FieldSpec("str", allow_empty=False),
        "max_parallel_agents": FieldSpec("int", 1, 16),
        "max_iterations": FieldSpec("int", 1, 100),
        "max_external_iterations": FieldSpec("int", 0, 100),
        "patience": FieldSpec("int", 0, 100),
        "external": {
            "backend": FieldSpec("str", choices=frozenset({"pi", "none"})),
            "required": FieldSpec("bool"),
            "command": FieldSpec("string-list", allow_empty=False),
            "model": FieldSpec("str", fixed="zai/glm-5.2", has_fixed=True),
            "thinking": FieldSpec("str", fixed="high", has_fixed=True),
            "direct": FieldSpec("bool", fixed=True, has_fixed=True),
            "data_sharing_approved": FieldSpec("bool"),
            "timeout_seconds": FieldSpec("int", 1, 86_400),
            "idle_timeout_seconds": FieldSpec("int", 1, 86_400),
        },
    },
    "agents": DynamicTableSpec(AGENT_PROFILE_SCHEMA),
    "finalize": {"enabled": FieldSpec("bool")},
    "learning": {"auto_propose": FieldSpec("bool")},
    "lazy": {
        "max_plan_review_iterations": FieldSpec("int", 1, 10),
        "plan_review_agents": FieldSpec("string-list", allow_empty=False),
        "worktree": FieldSpec("bool"),
        "commit_after_stage": FieldSpec("bool"),
    },
    "plans": {
        "directory": FieldSpec("str", allow_empty=False),
        "move_on_completion": FieldSpec("bool"),
    },
    "worktree": {"enabled": FieldSpec("bool")},
    "profiles": {
        "auto": FieldSpec("bool"),
        "enable": FieldSpec("string-list"),
        "disable": FieldSpec("string-list"),
    },
}


@dataclass(frozen=True)
class Replacement:
    name: str
    source: str
    path: Path
    content: str


@dataclass(frozen=True)
class Fragment:
    kind: str
    source: str
    path: Path
    content: str


@dataclass(frozen=True)
class ProfileSelection:
    name: str
    detected_from: tuple[str, ...]
    fragments: tuple[Fragment, ...]


@dataclass(frozen=True)
class EffectiveConfig:
    values: dict[str, Any]
    origins: dict[str, str]
    prompts: dict[str, Replacement]
    agents: dict[str, Replacement]
    selected_agents: tuple[str, ...]
    lazy_plan_review_agents: tuple[str, ...]
    profiles: dict[str, ProfileSelection]
    rules: tuple[Fragment, ...]


def _parse_duration(value: str) -> bool:
    if value == "":
        return True
    if value == "0" or value == "0s":
        return True
    position = 0
    for match in _DURATION_PART.finditer(value):
        if match.start() != position:
            return False
        position = match.end()
    return position == len(value) and position > 0


def _validate_field(path: str, value: Any, spec: FieldSpec) -> None:
    if spec.kind == "bool":
        valid = type(value) is bool
    elif spec.kind == "int":
        valid = type(value) is int
    elif spec.kind in {"str", "duration"}:
        valid = isinstance(value, str)
    elif spec.kind == "string-list":
        valid = isinstance(value, list) and all(isinstance(item, str) and item for item in value)
    elif spec.kind == "string-map":
        valid = isinstance(value, dict) and all(
            isinstance(key, str) and key and isinstance(item, str) and item
            for key, item in value.items()
        )
    else:  # pragma: no cover - schema authoring guard
        raise AssertionError(f"unsupported schema kind: {spec.kind}")
    if not valid:
        raise ConfigError(f"{path}: expected {spec.kind}")
    if isinstance(value, str) and not spec.allow_empty and not value:
        raise ConfigError(f"{path}: must not be empty")
    if isinstance(value, list) and not spec.allow_empty and not value:
        raise ConfigError(f"{path}: must not be empty")
    if spec.kind == "duration" and not _parse_duration(value):
        raise ConfigError(f"{path}: invalid duration {value!r}")
    if type(value) is int:
        if spec.minimum is not None and value < spec.minimum:
            raise ConfigError(f"{path}: must be >= {spec.minimum}")
        if spec.maximum is not None and value > spec.maximum:
            raise ConfigError(f"{path}: must be <= {spec.maximum}")
    if spec.choices is not None and value not in spec.choices:
        raise ConfigError(f"{path}: expected one of {sorted(spec.choices)}")
    if spec.has_fixed and value != spec.fixed:
        raise ConfigError(f"{path}: must remain {spec.fixed!r}")


def validate_mapping(values: Mapping[str, Any], schema: Mapping[str, Any] = SCHEMA, prefix: str = "") -> None:
    for key, value in values.items():
        path = f"{prefix}.{key}" if prefix else key
        if key not in schema:
            raise ConfigError(f"{path}: unknown configuration key")
        expected = schema[key]
        if isinstance(expected, FieldSpec):
            _validate_field(path, value, expected)
        elif isinstance(expected, DynamicTableSpec):
            if not isinstance(value, dict):
                raise ConfigError(f"{path}: expected table")
            for item_name, item in value.items():
                if not isinstance(item_name, str) or not item_name:
                    raise ConfigError(f"{path}: agent profile names must not be empty")
                if not isinstance(item, dict):
                    raise ConfigError(f"{path}.{item_name}: expected table")
                validate_mapping(item, expected.schema, f"{path}.{item_name}")
        else:
            if not isinstance(value, dict):
                raise ConfigError(f"{path}: expected table")
            validate_mapping(value, expected, path)


def _flatten_leaves(values: Mapping[str, Any], prefix: str = "") -> Iterable[tuple[str, Any]]:
    for key, value in values.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _flatten_leaves(value, path)
        else:
            yield path, value


def merge_layer(target: dict[str, Any], origins: dict[str, str], layer: Mapping[str, Any], source: str) -> None:
    def merge(current: dict[str, Any], incoming: Mapping[str, Any], prefix: str = "") -> None:
        for key, value in incoming.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                child = current.setdefault(key, {})
                if not isinstance(child, dict):  # guarded by schema; defensive for callers
                    child = {}
                    current[key] = child
                merge(child, value, path)
            else:
                current[key] = copy.deepcopy(value)
                origins[path] = source

    merge(target, layer)


def _read_toml(path: Path, *, required: bool = False) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise ConfigError(f"missing embedded config: {path}")
        return {}
    try:
        values = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    validate_mapping(values)
    return values


def parse_override(raw: str) -> tuple[str, Any]:
    if "=" not in raw:
        raise ConfigError(f"invalid --set {raw!r}; expected dotted.path=value")
    path, raw_value = raw.split("=", 1)
    keys = path.split(".")
    if not path or any(not key for key in keys):
        raise ConfigError(f"invalid override path {path!r}")
    try:
        value = tomllib.loads(f"value = {raw_value}\n")["value"]
    except tomllib.TOMLDecodeError:
        value = raw_value
    layer: dict[str, Any] = {}
    cursor = layer
    for key in keys[:-1]:
        child: dict[str, Any] = {}
        cursor[key] = child
        cursor = child
    cursor[keys[-1]] = value
    validate_mapping(layer)
    return path, value


def _override_layer(overrides: Sequence[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw in overrides:
        path, value = parse_override(raw)
        cursor = result
        keys = path.split(".")
        for key in keys[:-1]:
            cursor = cursor.setdefault(key, {})
        cursor[keys[-1]] = value
    return result


def meaningful_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    lines = content.splitlines()
    body = lines
    if lines and lines[0].strip() == "---":
        try:
            end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
        except StopIteration:
            end = -1
        if end >= 0:
            body = lines[end + 1 :]
    if not any(line.strip() and not line.lstrip().startswith("#") for line in body):
        return None
    return content.rstrip() + "\n"


def _named_files(*directories: Path) -> set[str]:
    names: set[str] = set()
    for directory in directories:
        if directory.is_dir():
            names.update(path.stem for path in directory.glob("*.md") if path.is_file())
    return names


def resolve_replacements(kind: str, embedded: Path, user: Path, project: Path) -> dict[str, Replacement]:
    result: dict[str, Replacement] = {}
    for name in sorted(_named_files(embedded, user, project)):
        candidates = (
            ("project", project / f"{name}.md"),
            ("user", user / f"{name}.md"),
            ("embedded", embedded / f"{name}.md"),
        )
        for source, path in candidates:
            content = meaningful_text(path)
            if content is not None:
                result[name] = Replacement(name, source, path.resolve(), content)
                break
        else:
            if (embedded / f"{name}.md").is_file():
                raise ConfigError(f"{kind} {name!r} has no meaningful definition")
    return result


def _known_profiles(embedded: Path, user: Path, project: Path) -> set[str]:
    names = _named_files(embedded, user, project)
    return {
        name
        for name in names
        if any(meaningful_text(directory / f"{name}.md") is not None for directory in (embedded, user, project))
    }


def _resolve_touched(project_root: Path, touched_files: Sequence[str | Path]) -> list[tuple[Path, str]]:
    result: list[tuple[Path, str]] = []
    root = project_root.resolve()
    for item in touched_files:
        raw = Path(item)
        path = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
        if path != root and root not in path.parents:
            raise ConfigError(f"touched file is outside project root: {item}")
        result.append((path, path.relative_to(root).as_posix()))
    return result


def select_profiles(
    project_root: Path,
    touched_files: Sequence[str | Path],
    profile_config: Mapping[str, Any],
    embedded_dir: Path,
    user_dir: Path,
    project_dir: Path,
) -> dict[str, ProfileSelection]:
    known = _known_profiles(embedded_dir, user_dir, project_dir)
    enabled = set(profile_config["enable"])
    disabled = set(profile_config["disable"])
    unknown = (enabled | disabled) - known
    if unknown:
        raise ConfigError(f"unknown profiles: {', '.join(sorted(unknown))}")
    conflict = enabled & disabled
    if conflict:
        raise ConfigError(f"profiles both enabled and disabled: {', '.join(sorted(conflict))}")

    detected: dict[str, list[str]] = {name: ["config:profiles.enable"] for name in enabled}
    touched = _resolve_touched(project_root, touched_files)
    if profile_config["auto"]:
        touched_profiles: dict[str, list[str]] = {}
        for path, relative in touched:
            profile = PROFILE_SUFFIXES.get(path.suffix.lower())
            if profile in known:
                touched_profiles.setdefault(profile, []).append(relative)
        if touched_profiles:
            for profile, sources in touched_profiles.items():
                detected.setdefault(profile, []).extend(sources)
        else:
            for marker, profile in PROFILE_MARKERS.items():
                if profile in known and (project_root / marker).is_file():
                    detected.setdefault(profile, []).append(marker)
    for name in disabled:
        detected.pop(name, None)

    result: dict[str, ProfileSelection] = {}
    for name in sorted(detected):
        fragments: list[Fragment] = []
        for source, directory in (
            ("profile:embedded", embedded_dir),
            ("profile:user", user_dir),
            ("profile:project", project_dir),
        ):
            path = directory / f"{name}.md"
            content = meaningful_text(path)
            if content is not None:
                fragments.append(Fragment("profile", source, path.resolve(), content))
        result[name] = ProfileSelection(name, tuple(dict.fromkeys(detected[name])), tuple(fragments))
    return result


def applicable_agent_files(project_root: Path, touched_files: Sequence[str | Path]) -> list[Path]:
    root = project_root.resolve()
    touched = _resolve_touched(root, touched_files)
    directories: set[Path] = {root}
    for path, _ in touched:
        current = path if path.is_dir() else path.parent
        while current == root or root in current.parents:
            directories.add(current)
            if current == root:
                break
            current = current.parent

    found: list[Path] = []
    for directory in sorted(directories, key=lambda item: (len(item.relative_to(root).parts), str(item))):
        for filename in ("AGENTS.override.md", "AGENTS.md"):
            candidate = directory / filename
            if meaningful_text(candidate) is not None:
                found.append(candidate.resolve())
                break
    return found


def _compose_rules(
    profiles: Mapping[str, ProfileSelection],
    user_root: Path,
    project_custom: Path,
    repository_root: Path,
    touched_files: Sequence[str | Path],
) -> tuple[Fragment, ...]:
    fragments: list[Fragment] = []
    for profile in profiles.values():
        fragments.extend(profile.fragments)
    for source, root in (("rule:user", user_root), ("rule:project", project_custom)):
        for kind in RULE_KINDS:
            path = root / "rules" / f"{kind}.md"
            content = meaningful_text(path)
            if content is not None:
                fragments.append(Fragment(kind, source, path.resolve(), content))
    for path in applicable_agent_files(repository_root, touched_files):
        content = meaningful_text(path)
        assert content is not None
        fragments.append(Fragment("instructions", "AGENTS.md", path, content))
    return tuple(fragments)


def load_effective(
    *,
    project_root: Path,
    plugin_data: Path | None = None,
    overrides: Sequence[str] = (),
    touched_files: Sequence[str | Path] = (),
    defaults_root: Path = DEFAULTS_ROOT,
) -> EffectiveConfig:
    root = project_root.resolve()
    if not root.is_dir():
        raise ConfigError(f"project root is not a directory: {root}")
    if plugin_data is None:
        data_value = os.environ.get("PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA") or ""
        user_root = Path(data_value).expanduser().resolve() if data_value else Path("/__phasemill_no_user_data__")
    else:
        user_root = plugin_data.expanduser().resolve()
    project_custom = root / PROJECT_CONFIG_DIR

    values: dict[str, Any] = {}
    origins: dict[str, str] = {}
    layers = (
        (f"embedded:{defaults_root / 'config.toml'}", _read_toml(defaults_root / "config.toml", required=True)),
        (f"user:{user_root / 'config.toml'}", _read_toml(user_root / "config.toml")),
        (f"project:{project_custom / 'config.toml'}", _read_toml(project_custom / "config.toml")),
        ("invocation", _override_layer(overrides)),
    )
    for source, layer in layers:
        merge_layer(values, origins, layer, source)
    validate_mapping(values)
    native_agents = values["agents"]
    if missing := REQUIRED_NATIVE_AGENTS - set(native_agents):
        raise ConfigError(f"missing required native agents: {', '.join(sorted(missing))}")
    for name, profile in native_agents.items():
        missing_fields = {"model", "model_reasoning_effort"} - set(profile)
        if missing_fields:
            raise ConfigError(
                f"agents.{name}: missing required fields: {', '.join(sorted(missing_fields))}"
            )

    def require_enabled_agent(name: str, source: str) -> None:
        if name not in native_agents:
            raise ConfigError(f"{source}: unknown native agent profile {name!r}")
        if native_agents[name].get("enabled", True) is False:
            raise ConfigError(f"{source}: native agent profile {name!r} is disabled")

    for name in ("planner", "explorer"):
        require_enabled_agent(name, f"agents.{name}")
    for key in ("implementer_agent", "cross_module_agent", "recovery_agent", "mechanical_agent"):
        require_enabled_agent(values["execution"][key], f"execution.{key}")
    require_enabled_agent(values["review"]["fallback_agent"], "review.fallback_agent")
    for role, agent_name in values["review"]["agent_profiles"].items():
        require_enabled_agent(agent_name, f"review.agent_profiles.{role}")
    if values["review"]["external"]["backend"] == "none" and values["review"]["external"]["required"]:
        raise ConfigError("review.external.required cannot be true when backend is none")
    external_review = values["review"]["external"]
    if external_review["idle_timeout_seconds"] >= external_review["timeout_seconds"]:
        raise ConfigError("review.external.idle_timeout_seconds must be less than timeout_seconds")
    for path in (
        "review.agents",
        "review.disabled_agents",
        "lazy.plan_review_agents",
        "profiles.enable",
        "profiles.disable",
    ):
        table, key = path.split(".")
        entries = values[table][key]
        if len(entries) != len(set(entries)):
            raise ConfigError(f"{path}: duplicate entries are not allowed")

    missing_embedded_prompts = {
        name
        for name in REQUIRED_PROMPTS
        if meaningful_text(defaults_root / "prompts" / f"{name}.md") is None
    }
    if missing_embedded_prompts:
        raise ConfigError(
            "missing required embedded prompts: " + ", ".join(sorted(missing_embedded_prompts))
        )
    prompts = resolve_replacements(
        "prompt", defaults_root / "prompts", user_root / "prompts", project_custom / "prompts"
    )
    agents = resolve_replacements(
        "agent", defaults_root / "agents", user_root / "agents", project_custom / "agents"
    )
    if missing := REQUIRED_PROMPTS - set(prompts):
        raise ConfigError(f"missing required embedded prompts: {', '.join(sorted(missing))}")
    if missing := REQUIRED_AGENTS - set(agents):
        raise ConfigError(f"missing required embedded agents: {', '.join(sorted(missing))}")
    profiles = select_profiles(
        root,
        touched_files,
        values["profiles"],
        defaults_root / "profiles",
        user_root / "profiles",
        project_custom / "profiles",
    )
    configured_agents = values["review"]["agents"]
    disabled_agents = set(values["review"]["disabled_agents"])
    unknown_agents = (set(configured_agents) | disabled_agents) - set(agents)
    if unknown_agents:
        raise ConfigError(f"unknown review agents: {', '.join(sorted(unknown_agents))}")
    selected_agents = tuple(name for name in configured_agents if name not in disabled_agents)
    lazy_agents = values["lazy"]["plan_review_agents"]
    unknown_lazy_agents = set(lazy_agents) - set(agents)
    if unknown_lazy_agents:
        raise ConfigError(f"unknown lazy plan-review agents: {', '.join(sorted(unknown_lazy_agents))}")
    unmapped_lazy_agents = set(lazy_agents) - set(values["review"]["agent_profiles"])
    if unmapped_lazy_agents:
        raise ConfigError(
            "lazy plan-review agents have no review.agent_profiles mapping: "
            + ", ".join(sorted(unmapped_lazy_agents))
        )
    lazy_plan_review_agents = tuple(name for name in lazy_agents if name not in disabled_agents)
    if not lazy_plan_review_agents:
        raise ConfigError("lazy.plan_review_agents: all configured roles are disabled")
    rules = _compose_rules(profiles, user_root, project_custom, root, touched_files)
    return EffectiveConfig(
        values,
        origins,
        prompts,
        agents,
        selected_agents,
        lazy_plan_review_agents,
        profiles,
        rules,
    )


def _redact(values: Any, path: str = "") -> Any:
    if isinstance(values, dict):
        return {
            key: ("<redacted>" if SENSITIVE_KEY.search(key) else _redact(value, f"{path}.{key}"))
            for key, value in values.items()
        }
    return copy.deepcopy(values)


def show_payload(config: EffectiveConfig) -> dict[str, Any]:
    return {
        "values": _redact(config.values),
        "origins": dict(sorted(config.origins.items())),
        "prompts": {
            name: {"source": item.source, "path": str(item.path)} for name, item in sorted(config.prompts.items())
        },
        "agents": {
            name: {"source": item.source, "path": str(item.path), "selected": name in config.selected_agents}
            for name, item in sorted(config.agents.items())
        },
        "selected_agents": list(config.selected_agents),
        "lazy_plan_review_agents": list(config.lazy_plan_review_agents),
        "profiles": {
            name: {
                "detected_from": list(item.detected_from),
                "fragments": [
                    {"source": fragment.source, "path": str(fragment.path)} for fragment in item.fragments
                ],
            }
            for name, item in sorted(config.profiles.items())
        },
        "rules": [
            {"kind": fragment.kind, "source": fragment.source, "path": str(fragment.path)}
            for fragment in config.rules
        ],
    }


def _text_show(config: EffectiveConfig) -> str:
    payload = show_payload(config)
    lines: list[str] = []
    for path, value in sorted(_flatten_leaves(payload["values"])):
        lines.append(f"{path} = {json.dumps(value, ensure_ascii=False)}")
        lines.append(f"  source: {config.origins[path]}")
    lines.append("prompts:")
    for name, prompt in payload["prompts"].items():
        lines.append(f"  {name} [{prompt['source']}]: {prompt['path']}")
    lines.append("active profiles:")
    for name, profile in payload["profiles"].items():
        lines.append(f"  {name}: {', '.join(profile['detected_from'])}")
    lines.append("selected agents:")
    for name in config.selected_agents:
        lines.append(f"  {name}: {config.agents[name].path}")
    lines.append("rules:")
    for rule in payload["rules"]:
        lines.append(f"  {rule['kind']} [{rule['source']}]: {rule['path']}")
    return "\n".join(lines) + "\n"


INIT_FILES = {
    "config.toml": """# Project overrides for Phasemill. Uncomment only values you need.\n# [review]\n# max_iterations = 3\n# [agents.review-quality]\n# model = \"gpt-5.6-sol\"\n# model_reasoning_effort = \"high\"\n# [profiles]\n# auto = true\n# enable = [\"go\"]\n# disable = []\n""",
    **{f"rules/{name}.md": f"# Add project-specific {name} rules here.\n" for name in RULE_KINDS},
    **{
        f"prompts/{name}.md": f"# Replace the complete {name} prompt here; comment-only files use the embedded default.\n"
        for name in (
            "make-plan",
            "task",
            "review-first",
            "review-second",
            "finalize",
            "pi-review",
            "learning",
            "lazy-discovery",
            "lazy-design",
            "lazy-plan",
            "lazy-plan-review",
            "lazy-plan-fix",
        )
    },
    "agents/domain.md": "# Define an optional project-specific domain review role here.\n",
    **{
        f"profiles/{name}.md": f"# Add project-specific {name} profile rules here.\n"
        for name in ("go", "python", "javascript-typescript", "java-kotlin", "php", "rust")
    },
}


def init_project(project_root: Path, *, confirmed: bool) -> list[Path]:
    if not confirmed:
        raise ConfigError("config init requires explicit --yes confirmation")
    root = project_root.resolve()
    if not root.is_dir():
        raise ConfigError(f"project root is not a directory: {root}")
    target = root / PROJECT_CONFIG_DIR
    created: list[Path] = []
    for relative, content in INIT_FILES.items():
        path = target / relative
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path)
    return created


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--plugin-data", type=Path)
    parser.add_argument("--set", dest="overrides", action="append", default=[], metavar="PATH=VALUE")
    parser.add_argument("--touched-file", action="append", default=[])
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show", help="show effective configuration and origins")
    show.add_argument("--format", choices=("text", "json"), default="text")
    commands.add_parser("validate", help="validate effective configuration")
    init = commands.add_parser("init", help="create commented project templates")
    init.add_argument("--yes", action="store_true", help="confirm creation")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            created = init_project(args.project_root, confirmed=args.yes)
            for path in created:
                print(path)
            return 0
        config = load_effective(
            project_root=args.project_root,
            plugin_data=args.plugin_data,
            overrides=args.overrides,
            touched_files=args.touched_file,
        )
        if args.command == "validate":
            print("configuration is valid")
        elif args.format == "json":
            print(json.dumps(show_payload(config), indent=2, ensure_ascii=False))
        else:
            print(_text_show(config), end="")
        return 0
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
