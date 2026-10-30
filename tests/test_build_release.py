from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline_release.build import (  # noqa: E402
    BuildReleaseError,
    assemble_release_assets,
    prepare_release,
)


class BuildReleaseTests(unittest.TestCase):
    def write_changelog(self, root: Path, content: str) -> Path:
        path = root / "CHANGELOG.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_stable_tag_uses_its_exact_changelog_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changelog = self.write_changelog(
                root,
                "# Changelog\n\n"
                "## [Unreleased]\n- future\n\n"
                "## [1.2.3] - 2026-10-30\n### Added\n- feature\n\n"
                "## [1.2.2]\n- old\n",
            )
            result = prepare_release(
                changelog_path=changelog,
                output_directory=root / "out",
                ref_type="tag",
                ref_name="v1.2.3",
                commit_sha="a" * 40,
            )
            notes = (root / "out" / "release-notes.md").read_text(encoding="utf-8")
            self.assertEqual(result["version"], "1.2.3")
            self.assertFalse(result["prerelease"])
            self.assertIn("- feature", notes)
            self.assertNotIn("- future", notes)
            self.assertTrue((root / "out" / "release-meta.json").is_file())

    def test_stable_tag_without_matching_section_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changelog = self.write_changelog(root, "# Changelog\n\n## [Unreleased]\n- draft\n")
            with self.assertRaises(BuildReleaseError):
                prepare_release(
                    changelog_path=changelog,
                    output_directory=root / "out",
                    ref_type="tag",
                    ref_name="v1.2.3",
                    commit_sha="a" * 40,
                )

    def test_branch_dry_run_uses_unreleased_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changelog = self.write_changelog(root, "# Changelog\n\n## [Unreleased]\n- current work\n")
            result = prepare_release(
                changelog_path=changelog,
                output_directory=root / "out",
                ref_type="branch",
                ref_name="main",
                commit_sha="abcdef0123456789",
                dry_run=True,
            )
            notes = (root / "out" / "release-notes.md").read_text(encoding="utf-8")
            self.assertEqual(result["version"], "0.0.0-dev.abcdef0")
            self.assertTrue(result["prerelease"])
            self.assertIn("- current work", notes)

    def test_assemble_writes_checksums_for_all_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            nested = assets / "release-build-linux"
            nested.mkdir(parents=True)
            target = nested / "application.tar.gz"
            target.write_bytes(b"release artifact")
            result = assemble_release_assets(assets)
            expected = hashlib.sha256(target.read_bytes()).hexdigest()
            checksum = (assets / "SHA256SUMS").read_text(encoding="utf-8")
            self.assertEqual(result["asset_count"], 1)
            self.assertIn(f"{expected}  release-build-linux/application.tar.gz", checksum)

    def test_assemble_rejects_empty_and_symlinked_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty = root / "empty"
            empty.mkdir()
            with self.assertRaises(BuildReleaseError):
                assemble_release_assets(empty)

            assets = root / "assets"
            assets.mkdir()
            target = root / "outside.bin"
            target.write_bytes(b"outside")
            (assets / "linked.bin").symlink_to(target)
            with self.assertRaises(BuildReleaseError):
                assemble_release_assets(assets)


if __name__ == "__main__":
    unittest.main(verbosity=2)
