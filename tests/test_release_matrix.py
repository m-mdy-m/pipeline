from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.release.matrix import BuildMatrixError, target_catalog, validate_build_matrix  # noqa: E402


class BuildMatrixTests(unittest.TestCase):
    def test_catalog_lists_desktop_and_mobile_architectures(self) -> None:
        catalog = target_catalog()
        self.assertEqual(catalog["windows-386"]["architecture"], "x86")
        self.assertEqual(catalog["windows-amd64"]["architecture"], "x86_64")
        self.assertEqual(catalog["android-arm64-v8a"]["abi"], "arm64-v8a")
        self.assertEqual(catalog["ios-arm64"]["target_os"], "ios")
        self.assertEqual(catalog["ios-simulator-x86_64"]["abi"], "simulator")
        self.assertEqual(catalog["pwa-web"]["platform"], "pwa")

    def test_matrix_infers_known_target_metadata_and_accepts_custom_targets(self) -> None:
        rows = validate_build_matrix({
            "include": [
                {"id": "android-arm64-v8a", "os": "ubuntu-24.04"},
                {"id": "custom-runtime", "os": "ubuntu-24.04", "target_os": "customos", "architecture": "riscv64"},
            ]
        })
        self.assertEqual(rows[0]["architecture"], "arm64")
        self.assertEqual(rows[0]["abi"], "arm64-v8a")
        self.assertEqual(rows[1]["architecture"], "riscv64")

    def test_matrix_rejects_duplicate_ids_bad_commands_and_orphan_setup(self) -> None:
        cases = [
            {"include": [{"id": "x", "os": "ubuntu"}, {"id": "x", "os": "ubuntu"}]},
            {"include": [{"id": "x", "os": "ubuntu", "build_command": ["make"]}]},
            {"include": [{"id": "x", "os": "ubuntu", "e2e_setup_command": "setup"}]},
            {"include": []},
        ]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(BuildMatrixError):
                validate_build_matrix(value)

    def test_matrix_target_setup_can_use_a_workflow_level_e2e_test_default(self) -> None:
        rows = validate_build_matrix(
            {"include": [{"id": "ios-simulator-arm64", "os": "macos-15", "e2e_setup_command": "boot-simulator"}]},
            default_e2e_test_command="run-e2e",
        )
        self.assertEqual(rows[0]["e2e_setup_command"], "boot-simulator")


if __name__ == "__main__":
    unittest.main(verbosity=2)
