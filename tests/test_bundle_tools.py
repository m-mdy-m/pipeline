from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.release.errors import ReleaseError  # noqa: E402
from pipeline.release.verify import verify_bundle  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BundleVerifierTests(unittest.TestCase):
    def create_bundle(self, directory: Path) -> None:
        archive_path = directory / "demo-v1.2.3-source.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("demo-v1.2.3/README.md", "demo source\n")
            archive.writestr("demo-v1.2.3/src/main.c", "int main(void) { return 0; }\n")
        manifest = {
            "schema_version": 1,
            "project": "demo/project",
            "version": "1.2.3",
            "tag": "v1.2.3",
            "prerelease": False,
            "archive": {
                "name": archive_path.name,
                "root_directory": "demo-v1.2.3",
                "sha256": digest(archive_path),
                "file_count": 2,
                "files": ["README.md", "src/main.c"],
            },
        }
        manifest_path = directory / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        targets = [archive_path, manifest_path]
        lines = [f"{digest(path)}  {path.name}" for path in sorted(targets, key=lambda item: item.name)]
        (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_valid_bundle_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_bundle(root)
            result = verify_bundle(root)
            self.assertEqual(result["archive"], "demo-v1.2.3-source.zip")
            self.assertEqual(result["archive_file_count"], 2)
            self.assertEqual(result["verified_assets"], 2)

    def test_checksum_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_bundle(root)
            (root / "demo-v1.2.3-source.zip").write_bytes(b"modified")
            with self.assertRaises(ReleaseError):
                verify_bundle(root)

    def test_unlisted_asset_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.create_bundle(root)
            (root / "unverified.bin").write_bytes(b"not checksummed")
            with self.assertRaises(ReleaseError):
                verify_bundle(root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
