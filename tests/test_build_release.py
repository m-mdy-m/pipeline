from __future__ import annotations

import hashlib
import json
import lzma
import re
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
    verify_release_assets,
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

    def test_dev_prerelease_tag_uses_its_exact_changelog_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changelog = self.write_changelog(
                root,
                "# Changelog\n\n"
                "## [0.1.0-dev] - 2026-11-07\n### Added\n- development snapshot\n",
            )
            result = prepare_release(
                changelog_path=changelog,
                output_directory=root / "out",
                ref_type="tag",
                ref_name="v0.1.0-dev",
                commit_sha="a" * 40,
            )
            notes = (root / "out" / "release-notes.md").read_text(encoding="utf-8")
            self.assertEqual(result["version"], "0.1.0-dev")
            self.assertEqual(result["release_tag"], "v0.1.0-dev")
            self.assertTrue(result["prerelease"])
            self.assertIn("- development snapshot", notes)

    def test_unapproved_prerelease_suffix_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changelog = self.write_changelog(root, "# Changelog\n\n## [0.1.0]\n- release\n")
            with self.assertRaises(BuildReleaseError):
                prepare_release(
                    changelog_path=changelog,
                    output_directory=root / "out",
                    ref_type="tag",
                    ref_name="v0.1.0-preview.1",
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

    def test_assemble_includes_root_metadata_alongside_target_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp) / "assets"
            target = assets / "release-build-linux-x86_64"
            target.mkdir(parents=True)
            (target / "frontend-core-linux.tar.gz").write_bytes(b"frontend package")
            metadata_names = (
                "frontend-core-1.1.1.json",
                "frontend-tui-1.1.1.json",
                "frontend-gui-sdl-1.1.1.json",
            )
            for name in metadata_names:
                (assets / name).write_text('{"schema_version":"1.2.0"}', encoding="utf-8")

            result = assemble_release_assets(assets)

            self.assertEqual(result["asset_count"], 1 + len(metadata_names))
            checksum_lines = (assets / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
            checksum_inventory = {line.split("  ", 1)[1] for line in checksum_lines}
            self.assertIn("frontend-core-linux.tar.gz", checksum_inventory)
            for name in metadata_names:
                self.assertTrue((assets / name).is_file())
                self.assertIn(name, checksum_inventory)
            self.assertFalse(target.exists())

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


    def test_gitea_profile_adds_xz_assets_sidecars_manifest_and_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            target = assets / "release-build-linux-amd64"
            target.mkdir(parents=True)
            binary = target / "pipeline-linux-amd64"
            binary.write_bytes(b"example release binary" * 1024)
            metadata = root / "release-meta.json"
            metadata.write_text(
                json.dumps({
                    "version": "1.2.3",
                    "release_tag": "v1.2.3",
                    "commit_sha": "a" * 40,
                    "prerelease": False,
                }),
                encoding="utf-8",
            )

            result = assemble_release_assets(assets, profile="gitea", metadata_path=metadata)

            original = assets / binary.name
            compressed = assets / (binary.name + ".xz")
            self.assertEqual(result["asset_profile"], "gitea")
            self.assertTrue(original.is_file())
            self.assertTrue(compressed.is_file())
            self.assertEqual(lzma.decompress(compressed.read_bytes()), original.read_bytes())
            self.assertEqual(
                (assets / (original.name + ".sha256")).read_text(encoding="ascii"),
                f"{hashlib.sha256(original.read_bytes()).hexdigest()}  {original.name}\n",
            )
            manifest = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], "1.2.3")
            self.assertEqual(manifest["tag"], "v1.2.3")
            self.assertEqual(manifest["assets"][0]["name"], original.name)
            self.assertEqual(manifest["assets"][0]["compressed"]["name"], compressed.name)

            verification = verify_release_assets(assets)
            self.assertGreaterEqual(verification["file_count"], 6)
            self.assertEqual(verification["asset_count"], 1)

    def test_release_verifier_rejects_modified_asset_or_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp) / "assets"
            target = assets / "release-build-linux-amd64"
            target.mkdir(parents=True)
            (target / "binary").write_bytes(b"original")
            assemble_release_assets(assets, profile="gitea")
            (assets / "binary").write_bytes(b"tampered")
            with self.assertRaises(BuildReleaseError):
                verify_release_assets(assets)

    def test_gitea_profile_rejects_conflicting_existing_xz_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            assets = Path(tmp) / "assets"
            target = assets / "release-build-linux-amd64"
            target.mkdir(parents=True)
            (target / "binary").write_bytes(b"original")
            (target / "binary.xz").write_bytes(b"not an xz stream")
            with self.assertRaises(BuildReleaseError):
                assemble_release_assets(assets, profile="gitea")



class ReleaseWorkflowContractTests(unittest.TestCase):
    def test_release_workflows_use_version_tags_not_commit_sha_pins(self) -> None:
        paths = (
            ROOT / ".github/workflows/release.yml",
            ROOT / ".github/workflows/release-on-tag.yml",
            ROOT / ".github/workflows/reusable-smoke.yml",
            ROOT / ".github/workflows/github-release-smoke.yml",
            ROOT / ".github/workflows/release-assets-smoke.yml",
            ROOT / ".github/actions/python-setup/action.yml",
            ROOT / ".github/actions/release-assets/action.yml",
        )
        for path in paths:
            workflow = path.read_text(encoding="utf-8")
            refs = re.findall(r"(?m)^\s*uses:\s*([^\s#]+)", workflow)
            for ref in refs:
                if ref.startswith("./"):
                    continue
                with self.subTest(path=path.relative_to(ROOT), action=ref):
                    self.assertIn("@", ref)
                    version = ref.rsplit("@", 1)[1]
                    self.assertRegex(
                        version,
                        r"^v\d+(?:\.\d+)*(?:[-+][A-Za-z0-9.-]+)?$",
                    )
                    self.assertNotRegex(version, r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
