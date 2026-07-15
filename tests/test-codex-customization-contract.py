#!/usr/bin/env python3
"""Executable contract for Codex project and language customization."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests/fixtures/codex/customization"


def merge_fields(layers: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    result: dict[str, Any] = {}
    origins: dict[str, str] = {}

    def merge(target: dict[str, Any], source: dict[str, Any], origin: str, prefix: str = "") -> None:
        for key, value in source.items():
            dotted = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                child = target.setdefault(key, {})
                if not isinstance(child, dict):
                    child = {}
                    target[key] = child
                merge(child, value, origin, dotted)
            else:
                target[key] = copy.deepcopy(value)
                origins[dotted] = origin

    for layer in layers:
        merge(result, layer["values"], layer["name"])
    return result, origins


def meaningful_template(path: Path) -> bool:
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    nonblank = [line for line in lines if line.strip()]
    if not nonblank:
        return False
    return len(nonblank) == 1 or any(not line.lstrip().startswith("#") for line in nonblank)


def resolve_replacement(candidates: list[Path]) -> Path | None:
    return next((path for path in candidates if meaningful_template(path)), None)


def applicable_agents(repo: Path, touched: list[Path]) -> list[Path]:
    found: set[Path] = set()
    root = repo.resolve()
    for relative in touched:
        current = (root / relative).resolve().parent
        while current == root or root in current.parents:
            candidate = current / "AGENTS.md"
            if candidate.is_file():
                found.add(candidate)
            if current == root:
                break
            current = current.parent
    return sorted(found, key=lambda path: (len(path.relative_to(root).parts), str(path)))


SUFFIX_PROFILES = {
    ".go": "go",
    ".py": "python",
    ".js": "javascript-typescript",
    ".jsx": "javascript-typescript",
    ".ts": "javascript-typescript",
    ".tsx": "javascript-typescript",
    ".java": "java-kotlin",
    ".kt": "java-kotlin",
    ".php": "php",
    ".rs": "rust",
}
MARKER_PROFILES = {
    "go.mod": "go",
    "pyproject.toml": "python",
    "package.json": "javascript-typescript",
    "pom.xml": "java-kotlin",
    "build.gradle": "java-kotlin",
    "composer.json": "php",
    "Cargo.toml": "rust",
}


def detect_profiles(repo: Path, touched: list[Path], *, auto: bool, enable: list[str], disable: list[str]) -> list[str]:
    active: set[str] = set(enable)
    if auto:
        touched_profiles = {SUFFIX_PROFILES[path.suffix] for path in touched if path.suffix in SUFFIX_PROFILES}
        marker_profiles = {profile for marker, profile in MARKER_PROFILES.items() if (repo / marker).exists()}
        active.update(touched_profiles if touched_profiles else marker_profiles)
    active.difference_update(disable)
    return sorted(active)


class CustomizationContractTests(unittest.TestCase):
    def test_config_merges_per_field_and_preserves_explicit_zero_values(self) -> None:
        contract = json.loads((FIXTURE / "contract.json").read_text(encoding="utf-8"))
        values, origins = merge_fields(contract["config_layers_low_to_high"])
        self.assertEqual(contract["expected_config"], values)
        self.assertEqual(contract["expected_origins"], origins)

    def test_replacement_skips_comment_only_user_template(self) -> None:
        root = FIXTURE / "templates"
        resolved = resolve_replacement([
            root / "user/prompts/task.md",
            root / "embedded/prompts/task.md",
        ])
        self.assertEqual(root / "embedded/prompts/task.md", resolved)

    def test_project_prompt_replaces_user_and_embedded_as_a_whole_file(self) -> None:
        root = FIXTURE / "templates"
        resolved = resolve_replacement([
            root / "project/prompts/task.md",
            root / "user/prompts/task.md",
            root / "embedded/prompts/task.md",
        ])
        self.assertEqual(root / "project/prompts/task.md", resolved)

    def test_nested_agents_are_ordered_from_repo_to_subtree(self) -> None:
        repo = FIXTURE / "repo"
        self.assertEqual(
            [repo / "AGENTS.md", repo / "internal/AGENTS.md"],
            applicable_agents(repo, [Path("internal/store/store.go")]),
        )

    def test_polyglot_detection_uses_only_touched_language_when_scope_exists(self) -> None:
        repo = FIXTURE / "repo"
        self.assertEqual(
            ["go"],
            detect_profiles(repo, [Path("internal/store/store.go")], auto=True, enable=[], disable=[]),
        )

    def test_php_detection_uses_touched_file_over_other_project_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "composer.json").write_text("{}\n", encoding="utf-8")
            (repo / "package.json").write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                ["php"],
                detect_profiles(repo, [Path("src/Service.php")], auto=True, enable=[], disable=[]),
            )

    def test_explicit_profiles_override_auto_detection(self) -> None:
        repo = FIXTURE / "repo"
        self.assertEqual(
            ["go"],
            detect_profiles(
                repo,
                [Path("web/app.ts")],
                auto=True,
                enable=["go"],
                disable=["javascript-typescript"],
            ),
        )

    def test_rule_precedence_is_source_labelled_and_stable(self) -> None:
        contract = json.loads((FIXTURE / "contract.json").read_text(encoding="utf-8"))
        self.assertEqual(
            ["embedded", "language-profile", "user", "project", "AGENTS.md", "current-user-request"],
            contract["rule_order_low_to_high"],
        )

if __name__ == "__main__":
    unittest.main()
