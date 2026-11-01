from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.release.build import (  # noqa: E402
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
            self.assertEqual(result["release_tag"], "v1.2.3")
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
            self.assertEqual(result["release_tag"], "v0.0.0-dev.abcdef0")
            self.assertTrue(result["prerelease"])
            self.assertIn("- current work", notes)

    def test_assemble_flattens_assets_and_writes_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            target_dir = assets / "release-build-linux"
            target_dir.mkdir(parents=True)
            source = target_dir / "application.tar.gz"
            source.write_bytes(b"release artifact")

            result = assemble_release_assets(assets)

            published = assets / "application.tar.gz"
            expected = hashlib.sha256(published.read_bytes()).hexdigest()
            checksum = (assets / "SHA256SUMS").read_text(encoding="utf-8")
            self.assertEqual(result["asset_count"], 1)
            self.assertTrue(published.is_file())
            self.assertFalse(target_dir.exists())
            self.assertEqual(checksum, f"{expected}  application.tar.gz\n")

    def test_assemble_skips_directory_represented_by_sibling_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp) / "assets"
            target = assets / "release-build-windows-x86_64-ucrt64"
            package_dir = target / "cdin-kernel-1.2.0-windows-x86_64"
            (package_dir / "include").mkdir(parents=True)
            (package_dir / "README.md").write_text("unpacked copy", encoding="utf-8")
            (package_dir / "include" / "kernel.h").write_text("header", encoding="utf-8")
            archive = target / "cdin-kernel-1.2.0-windows-x86_64.zip"
            archive.write_bytes(b"already packaged")
            sidecar = target / (archive.name + ".sha256")
            sidecar.write_text("abc  " + archive.name + "\n", encoding="utf-8")

            result = assemble_release_assets(assets)

            self.assertEqual(result["asset_count"], 2)
            self.assertTrue((assets / archive.name).is_file())
            self.assertTrue((assets / sidecar.name).is_file())
            self.assertFalse((assets / "README.md").exists())
            self.assertFalse((assets / target.name).exists())
            published_names = {path.name for path in assets.iterdir()}
            self.assertEqual(
                published_names,
                {archive.name, sidecar.name, "SHA256SUMS"},
            )

    def test_assemble_archives_selected_directories(self) -> None:
        import tarfile

        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp) / "assets"
            package_dir = assets / "release-build-linux-x86_64" / "my-package"
            (package_dir / "bin").mkdir(parents=True)
            (package_dir / "include").mkdir()
            (package_dir / "bin" / "app").write_bytes(b"binary")
            (package_dir / "include" / "app.h").write_text("header", encoding="utf-8")

            result = assemble_release_assets(assets)

            archive_path = assets / "linux-x86_64-my-package.tar.gz"
            self.assertEqual(result["asset_count"], 1)
            self.assertTrue(archive_path.is_file())
            with tarfile.open(archive_path, "r:gz") as archive:
                members = set(archive.getnames())
            self.assertIn("my-package/bin/app", members)
            self.assertIn("my-package/include/app.h", members)
            self.assertEqual(
                {path.name for path in assets.iterdir()},
                {archive_path.name, "SHA256SUMS"},
            )

    def test_assemble_disambiguates_duplicate_asset_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp) / "assets"
            for target_name in ("linux-x86_64", "windows-x86_64"):
                target = assets / f"release-build-{target_name}"
                target.mkdir(parents=True)
                archive = target / "application.zip"
                archive.write_bytes(target_name.encode("ascii"))
                (target / "application.zip.sha256").write_text(
                    "abc  application.zip\n", encoding="utf-8"
                )

            result = assemble_release_assets(assets)

            self.assertEqual(result["asset_count"], 4)
            for target_name in ("linux-x86_64", "windows-x86_64"):
                renamed = f"{target_name}-application.zip"
                self.assertTrue((assets / renamed).is_file())
                sidecar = (assets / (renamed + ".sha256")).read_text(encoding="utf-8")
                self.assertIn(renamed, sidecar)
            self.assertEqual(len(list(assets.iterdir())), 5)

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
