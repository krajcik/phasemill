#!/usr/bin/env python3
"""Contract tests for Codex marketplace and plugin manifests."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = REPO / "scripts/validate-codex-plugins.py"
SPEC = importlib.util.spec_from_file_location("validate_codex_plugins", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class CodexManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)
        shutil.copytree(REPO / ".agents", self.repo / ".agents")
        shutil.copytree(REPO / "plugins", self.repo / "plugins")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def marketplace_path(self) -> Path:
        return self.repo / ".agents/plugins/marketplace.json"

    def load_marketplace(self) -> dict:
        return json.loads(self.marketplace_path().read_text(encoding="utf-8"))

    def write_marketplace(self, data: dict) -> None:
        self.marketplace_path().write_text(json.dumps(data), encoding="utf-8")

    def manifest_path(self, name: str) -> Path:
        return self.repo / f"plugins/{name}/.codex-plugin/plugin.json"

    def load_manifest(self, name: str) -> dict:
        return json.loads(self.manifest_path(name).read_text(encoding="utf-8"))

    def write_manifest(self, name: str, data: dict) -> None:
        self.manifest_path(name).write_text(json.dumps(data), encoding="utf-8")

    def errors(self) -> list[str]:
        return VALIDATOR.validate_repository(self.repo)

    def assert_error_contains(self, text: str) -> None:
        self.assertTrue(any(text in error for error in self.errors()), self.errors())

    def test_repository_manifests_are_valid(self) -> None:
        self.assertEqual([], self.errors())

    def test_rejects_malformed_json(self) -> None:
        self.manifest_path("phasemill").write_text("{", encoding="utf-8")
        self.assert_error_contains("invalid JSON")

    def test_rejects_missing_plugin_path(self) -> None:
        data = self.load_marketplace()
        data["plugins"][0]["source"]["path"] = "./plugins/missing"
        self.write_marketplace(data)
        self.assert_error_contains("plugin directory does not exist")

    def test_rejects_duplicate_marketplace_name(self) -> None:
        data = self.load_marketplace()
        duplicate = dict(data["plugins"][0])
        duplicate["source"] = dict(data["plugins"][0]["source"])
        data["plugins"].append(duplicate)
        self.write_marketplace(data)
        self.assert_error_contains("duplicate marketplace plugin name")

    def test_rejects_manifest_name_mismatch(self) -> None:
        data = self.load_manifest("phasemill")
        data["name"] = "other"
        self.write_manifest("phasemill", data)
        self.assert_error_contains("manifest name mismatch")

    def test_rejects_non_semantic_version(self) -> None:
        data = self.load_manifest("phasemill")
        data["version"] = "next"
        self.write_manifest("phasemill", data)
        self.assert_error_contains("manifest version is not semantic")

    def test_rejects_marketplace_path_escape(self) -> None:
        data = self.load_marketplace()
        data["plugins"][0]["source"]["path"] = "./plugins/../../outside"
        self.write_marketplace(data)
        self.assert_error_contains("escapes plugins directory")

    def test_rejects_missing_optional_component_path(self) -> None:
        data = self.load_manifest("phasemill")
        data["skills"] = "./missing-skills"
        self.write_manifest("phasemill", data)
        self.assert_error_contains("skills path does not exist")

    def test_rejects_missing_interface_asset_path(self) -> None:
        data = self.load_manifest("phasemill")
        data["interface"]["logo"] = "./assets/missing.svg"
        self.write_manifest("phasemill", data)
        self.assert_error_contains("interface.logo path does not exist")


if __name__ == "__main__":
    unittest.main()
