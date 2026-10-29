from __future__ import annotations

import os
import subprocess
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import source_release as sr


class ChangelogTests(unittest.TestCase):
    def test_common_heading_formats(self) -> None:
        for heading in (
            "## [1.2.3]",
            "## [1.2.3] - 2026-10-29",
            "## 1.2.3",
            "## v1.2.3",
            "## Version 1.2.3",
            "Version 1.2.3",
        ):
            with self.subTest(heading=heading):
                self.assertEqual(sr.heading_info(heading)[1], "1.2.3")

    def test_extracts_only_current_section(self) -> None:
        body = "# Changelog\n\n## [1.2.3] - date\n\n### Added\n- one\n\n## [1.1.0]\n- old\n"
        self.assertEqual(
            sr.extract_version_section(body, "1.2.3", "CHANGELOG.md"),
            "## [1.2.3] - date\n\n### Added\n- one\n",
        )

    def test_duplicate_or_missing_version_is_error(self) -> None:
        with self.assertRaises(sr.ReleaseError):
            sr.extract_version_section("## [1.2.3]\na\n## 1.2.3\nb\n", "1.2.3", "CHANGELOG")
        with self.assertRaises(sr.ReleaseError):
            sr.extract_version_section("## [Unreleased]\n- draft\n", "1.2.3", "CHANGELOG")

    def test_changelog_autodetection_is_strict_and_rejects_symlinks(self) -> None:
        root = Path("/tmp/source-release-test")
        one = sr.TreeEntry("100644", "blob", "a" * 40, "CHANGELOG.md", root)
        two = sr.TreeEntry("100644", "blob", "b" * 40, "docs/CHANGELOG", root)
        with self.assertRaises(sr.ReleaseError):
            sr.detect_changelog([one, two], "")
        link = sr.TreeEntry("120000", "blob", "c" * 40, "CHANGELOG.md", root)
        with self.assertRaises(sr.ReleaseError):
            sr.detect_changelog([link], "")
        self.assertIsNone(sr.detect_changelog([one], "docs/CHANGELOG"))


class PathPolicyTests(unittest.TestCase):
    def test_rejects_traversal_and_platform_paths(self) -> None:
        for path in ("../secret", "/etc/passwd", "a\\..\\b", "C:/secret", "a//b", "CON.txt"):
            with self.subTest(path=path), self.assertRaises(sr.ReleaseError):
                sr.safe_repo_path(path)

    def test_exclusion_globs_and_no_negation(self) -> None:
        self.assertTrue(sr.glob_match("dist/bin/app", "dist/"))
        self.assertTrue(sr.glob_match("docs/CHANGELOG.md", "*.md"))
        self.assertFalse(sr.glob_match("src/main.c", "dist/"))
        with self.assertRaises(sr.ReleaseError):
            sr.glob_match(".env", "!.env")

    def test_safe_symlink_and_escape_detection(self) -> None:
        sr.validate_symlinks({"docs/current": "../CHANGELOG.md"}, {"CHANGELOG.md"}, {"CHANGELOG.md"})
        with self.assertRaises(sr.ReleaseError):
            sr.validate_symlinks({"docs/current": "../../outside"}, {"docs/file"}, {"docs/file"})
        with self.assertRaises(sr.ReleaseError):
            sr.validate_symlinks({"a": "b", "b": "a"}, set(), set())

    def test_zip_casefold_collisions_fail_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "case.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("project/README.md", "one")
                archive.writestr("project/readme.md", "two")
            with self.assertRaises(sr.ReleaseError):
                sr.validate_zip(
                    archive_path, "project", "project-source.zip", None,
                    {"project/README.md", "project/readme.md"},
                )


class ArchiveIntegrationTests(unittest.TestCase):
    def create_repo(self, root: Path) -> str:
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Pipeline Test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "pipeline-test@example.invalid"], cwd=root, check=True)
        (root / "CHANGELOG.md").write_text("# Changelog\n\n## [1.2.3]\n\n### Added\n- source release\n", encoding="utf-8")
        (root / ".editorconfig").write_text("root = true\n", encoding="utf-8")
        (root / ".env.example").write_text("TOKEN=replace-me\n", encoding="utf-8")
        (root / "app.sh").write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
        (root / "app.sh").chmod(0o755)
        (root / "generated.txt").write_text("excluded\n", encoding="utf-8")
        (root / "untracked.txt").write_text("not tracked\n", encoding="utf-8")
        subprocess.run(["git", "add", "CHANGELOG.md", ".editorconfig", ".env.example", "app.sh", "generated.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "test snapshot"], cwd=root, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        subprocess.run(["git", "tag", "v1.2.3", commit], cwd=root, check=True)
        # Leave an untracked file to prove it is absent from the snapshot archive.
        return commit

    def run_flow(self, mode: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commit = self.create_repo(root)
            script_dest = root / "scripts" / "source_release.py"
            script_dest.parent.mkdir(parents=True, exist_ok=True)
            scripts_root = Path(__file__).resolve().parents[1] / "scripts"
            script_dest.write_bytes((scripts_root / "source_release.py").read_bytes())
            shutil.copytree(scripts_root / "pipeline_release", root / "scripts" / "pipeline_release")
            shutil.copytree(scripts_root / "pipeline_core", root / "scripts" / "pipeline_core")
            subprocess.run(["git", "add", "scripts"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "add modular helper"], cwd=root, check=True)
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            subprocess.run(["git", "tag", "-f", "v1.2.3", commit], cwd=root, check=True, stdout=subprocess.DEVNULL)
            outputs = root / "outputs.txt"
            env = os.environ.copy()
            env.update({
                "PIPELINE_REF_TYPE": "tag", "PIPELINE_REF_NAME": "v1.2.3", "PIPELINE_SHA": commit,
                "PIPELINE_REPOSITORY": "demo/project", "PIPELINE_WORKSPACE": str(root), "PIPELINE_OUTPUT_FILE": str(outputs), "SOURCE_WORK_DIR": str(root / "work"),
                "SOURCE_DRY_RUN": "false", "SOURCE_CHANGELOG_PATH": "",
                "SOURCE_CHANGELOG_MISSING_POLICY": "fail", "SOURCE_CHANGELOG_ASSET_MODE": mode,
                "SOURCE_ARCHIVE_NAME": "{repository}-{tag}-source.zip", "SOURCE_SUBMODULES": "fail-if-present",
                "SOURCE_EXCLUDE_PATTERNS": "generated.txt\n", "SOURCE_SENSITIVE_PATH_PATTERNS": "",
                "SOURCE_SENSITIVE_ALLOWLIST_PATTERNS": "", "SOURCE_GITLEAKS_ALLOWLIST_PATH": "",
                "SOURCE_RELEASE_NOTES_MODE": "section", "SOURCE_RELEASE_NOTES_PATH": "",
            })
            subprocess.run([sys.executable, "scripts/source_release.py", "prepare"], cwd=root, env=env, check=True)
            resolved = ""
            excluded_count = "0"
            for line in outputs.read_text(encoding="utf-8").splitlines():
                key, value = line.split("=", 1)
                if key == "changelog_path": resolved = value
                if key == "excluded_path_count": excluded_count = value
            env["SOURCE_CHANGELOG_PATH"] = resolved
            env["SOURCE_EXCLUDED_PATH_COUNT"] = excluded_count
            # In asset-only mode, the changelog stays outside the ZIP but must still be scanned.
            scan_changelog = root / "work" / "secret-scan" / "CHANGELOG.md"
            self.assertTrue(scan_changelog.is_file())
            self.assertIn("source release", scan_changelog.read_text(encoding="utf-8"))
            subprocess.run([sys.executable, "scripts/source_release.py", "package"], cwd=root, env=env, check=True)

            archive_path = root / "work" / "release-assets" / "project-v1.2.3-source.zip"
            self.assertTrue(archive_path.is_file())
            with zipfile.ZipFile(archive_path) as zf:
                names = zf.namelist()
                self.assertIn("project-v1.2.3/.editorconfig", names)
                self.assertIn("project-v1.2.3/.env.example", names)
                self.assertIn("project-v1.2.3/app.sh", names)
                self.assertNotIn("project-v1.2.3/generated.txt", names)
                self.assertNotIn("project-v1.2.3/untracked.txt", names)
                has_changelog = "project-v1.2.3/CHANGELOG.md" in names
                self.assertEqual(has_changelog, mode != "asset-only")
            separate = root / "work" / "release-assets" / "CHANGELOG.md"
            self.assertEqual(separate.is_file(), mode in {"archive-and-asset", "asset-only"})
            self.assertTrue((root / "work" / "release-assets" / "manifest.json").is_file())
            checksum_lines = (root / "work" / "release-assets" / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
            self.assertTrue(checksum_lines)
            self.assertTrue(all(len(line.split("  ", 1)[0]) == 64 for line in checksum_lines))

    def test_archive_only(self) -> None:
        self.run_flow("archive-only")

    def test_archive_and_asset(self) -> None:
        self.run_flow("archive-and-asset")

    def test_asset_only(self) -> None:
        self.run_flow("asset-only")


if __name__ == "__main__":
    unittest.main()
