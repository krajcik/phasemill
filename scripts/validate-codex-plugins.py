#!/usr/bin/env python3
"""Validate the repository-local Codex marketplace and plugin manifests."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$")
REQUIRED_MANIFEST_FIELDS = (
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
)
OPTIONAL_PATH_FIELDS = ("skills", "hooks", "mcpServers", "apps")
INTERFACE_PATH_FIELDS = ("composerIcon", "logo", "screenshots")


def load_json(path: Path, errors: list[str]) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing JSON file: {path}")
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON in {path}: {exc.msg} at line {exc.lineno}, column {exc.colno}")
    return None


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_component_path(
    plugin_root: Path,
    field: str,
    value: object,
    errors: list[str],
) -> None:
    values = value if isinstance(value, list) else [value]
    if not values or not all(isinstance(item, str) and item for item in values):
        errors.append(f"{plugin_root.name}: {field} must be a path or non-empty path list")
        return

    for item in values:
        assert isinstance(item, str)
        if not item.startswith("./"):
            errors.append(f"{plugin_root.name}: {field} path must start with './': {item}")
            continue
        target = (plugin_root / item).resolve()
        if not is_within(target, plugin_root.resolve()):
            errors.append(f"{plugin_root.name}: {field} path escapes plugin root: {item}")
        elif not target.exists():
            errors.append(f"{plugin_root.name}: {field} path does not exist: {item}")


def validate_repository(repo: Path) -> list[str]:
    repo = repo.resolve()
    errors: list[str] = []
    marketplace_path = repo / ".agents/plugins/marketplace.json"
    marketplace = load_json(marketplace_path, errors)
    if not isinstance(marketplace, dict):
        if marketplace is not None:
            errors.append(f"{marketplace_path}: top level must be an object")
        return errors

    entries = marketplace.get("plugins")
    if not isinstance(entries, list):
        errors.append(f"{marketplace_path}: plugins must be an array")
        return errors

    names: list[str] = []
    marketplace_roots: set[Path] = set()
    for index, entry in enumerate(entries):
        label = f"marketplace plugin[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label}: entry must be an object")
            continue

        name = entry.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{label}: name must be a non-empty string")
            continue
        names.append(name)
        label = f"marketplace plugin {name!r}"

        source = entry.get("source")
        if not isinstance(source, dict) or source.get("source") != "local":
            errors.append(f"{label}: source.source must be 'local'")
            continue
        source_path = source.get("path")
        if not isinstance(source_path, str) or not source_path.startswith("./plugins/"):
            errors.append(f"{label}: local source path must start with './plugins/'")
            continue
        plugin_root = (repo / source_path).resolve()
        if not is_within(plugin_root, (repo / "plugins").resolve()):
            errors.append(f"{label}: local source path escapes plugins directory: {source_path}")
            continue
        if not plugin_root.is_dir():
            errors.append(f"{label}: plugin directory does not exist: {source_path}")
            continue
        marketplace_roots.add(plugin_root)

        policy = entry.get("policy")
        if not isinstance(policy, dict) or not policy.get("installation") or not policy.get("authentication"):
            errors.append(f"{label}: policy requires installation and authentication")
        if not isinstance(entry.get("category"), str) or not entry["category"]:
            errors.append(f"{label}: category must be a non-empty string")

        manifest_path = plugin_root / ".codex-plugin/plugin.json"
        manifest = load_json(manifest_path, errors)
        if not isinstance(manifest, dict):
            if manifest is not None:
                errors.append(f"{manifest_path}: top level must be an object")
            continue

        for field in REQUIRED_MANIFEST_FIELDS:
            if field not in manifest or manifest[field] in (None, "", {}):
                errors.append(f"{name}: manifest field {field!r} is required")
        if manifest.get("name") != name:
            errors.append(f"{name}: manifest name mismatch: {manifest.get('name')!r}")
        version = manifest.get("version")
        if not isinstance(version, str) or not SEMVER.fullmatch(version):
            errors.append(f"{name}: manifest version is not semantic: {version!r}")

        for field in OPTIONAL_PATH_FIELDS:
            if field in manifest:
                validate_component_path(plugin_root, field, manifest[field], errors)

        interface = manifest.get("interface")
        if interface is not None and not isinstance(interface, dict):
            errors.append(f"{name}: manifest interface must be an object")
        elif isinstance(interface, dict):
            for field in INTERFACE_PATH_FIELDS:
                if field in interface:
                    validate_component_path(
                        plugin_root,
                        f"interface.{field}",
                        interface[field],
                        errors,
                    )

    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    for name in duplicate_names:
        errors.append(f"duplicate marketplace plugin name: {name}")

    discovered_roots = {
        path.parent.parent.resolve()
        for path in (repo / "plugins").glob("*/.codex-plugin/plugin.json")
    }
    for root in sorted(discovered_roots - marketplace_roots):
        errors.append(f"Codex manifest missing from marketplace: {root.relative_to(repo)}")
    for root in sorted(marketplace_roots - discovered_roots):
        errors.append(f"marketplace plugin missing Codex manifest: {root.relative_to(repo)}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = validate_repository(args.repo)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Codex marketplace and plugin manifests are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
