from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.release.identifiers import is_valid_target_id  # noqa: E402


class ReleaseTargetIdentifierTests(unittest.TestCase):
    def test_accepts_ids_for_supported_architectures(self) -> None:
        for value in (
            "linux-amd64",
            "android-x86_64",
            "ios-simulator-x86_64",
            "android-arm64-v8a",
        ):
            with self.subTest(value=value):
                self.assertTrue(is_valid_target_id(value))

    def test_rejects_path_like_or_invalid_ids(self) -> None:
        for value in ("", "_android", "../linux", "linux/amd64", "Linux-amd64", "a" * 65):
            with self.subTest(value=value):
                self.assertFalse(is_valid_target_id(value))


if __name__ == "__main__":
    unittest.main(verbosity=2)
