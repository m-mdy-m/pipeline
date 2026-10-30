from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.common.hashing import sha256_file
from pipeline.common.io import atomic_write_json, atomic_write_text, write_output_variables
from pipeline.utils.paths import resolve_within


class CommonHelpersTests(unittest.TestCase):
    def test_atomic_text_and_json_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_path = atomic_write_text(root / "nested" / "value.txt", "complete\n")
            json_path = atomic_write_json(root / "nested" / "value.json", {"ready": True})
            self.assertEqual(text_path.read_text(encoding="utf-8"), "complete\n")
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), {"ready": True})
            self.assertFalse(list((root / "nested").glob("*.tmp")))

    def test_sha256_helper_matches_standard_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "asset.bin"
            path.write_bytes(b"pipeline-common")
            self.assertEqual(sha256_file(path), hashlib.sha256(b"pipeline-common").hexdigest())

    def test_output_file_rejects_multiline_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "output.txt"
            write_output_variables({"version": "1.2.3", "stable": True}, target)
            self.assertEqual(target.read_text(encoding="utf-8"), "version=1.2.3\nstable=true\n")
            with self.assertRaises(ValueError):
                write_output_variables({"notes": "first\nsecond"}, target)

    def test_workspace_path_helper_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(resolve_within(root, "inside/file.txt"), root / "inside" / "file.txt")
            with self.assertRaises(ValueError):
                resolve_within(root, "../outside")


if __name__ == "__main__":
    unittest.main(verbosity=2)
