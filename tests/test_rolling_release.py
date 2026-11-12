from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.release.rolling import (  # noqa: E402
    RollingReleaseError,
    latest_action,
    prepare_rolling_assets,
    verify_remote_assets,
)


SOURCE_SHA = "a" * 40
RUN_ID = "43170000001"
RUN_ATTEMPT = "1"


def write_group(root: Path, runner_os: str, profile: str) -> None:
    os_name = {"Linux": "linux", "macOS": "darwin", "Windows": "windows"}[runner_os]
    architecture = "arm64" if runner_os == "macOS" else "x86_64"
    target = {
        "os": os_name,
        "architecture": architecture,
        "abi": "windows-ucrt64" if os_name == "windows" else (
            "macos-15" if os_name == "darwin" else "gnu-glibc-2.39"
        ),
    }
    extension = ".zip" if runner_os == "Windows" else ".tar.gz"
    slug = f"{os_name}-{architecture}-{profile}"
    archive_name = f"cdin-0.2.0-{slug}{extension}"
    archive = root / f"cdin-installed-product-{runner_os}-{profile}" / archive_name
    archive.parent.mkdir(parents=True)
    archive.write_bytes(f"{runner_os}:{profile}".encode("ascii"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (archive.parent / (archive.name + ".sha256")).write_text(
        f"{digest}  {archive.name}\n", encoding="ascii"
    )
    manifest = {
        "schema_version": 1,
        "product": "com.cdin.editor",
        "version": "0.2.0",
        "source_commit": SOURCE_SHA,
        "target": target,
        "profile": profile,
        "registry_manifest_sha256": "b" * 64,
        "components": [
            {"component_id": "backend", "variant": "default", "version": "1.2.1"}
        ],
        "archive": {
            "name": archive.name,
            "size_bytes": archive.stat().st_size,
            "sha256": digest,
        },
        "workflow": {"run_id": RUN_ID, "run_attempt": RUN_ATTEMPT},
    }
    (archive.parent / f"cdin-0.2.0-{slug}.manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )


class RollingReleasePreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="pipeline-rolling-")
        self.root = Path(self.temporary.name)
        self.downloaded = self.root / "downloaded"
        self.output = self.root / "output"
        self.downloaded.mkdir()
        for runner_os in ("Linux", "macOS", "Windows"):
            for profile in ("tui", "gui-sdl"):
                write_group(self.downloaded, runner_os, profile)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prepare(self) -> dict:
        return prepare_rolling_assets(
            downloaded_root=self.downloaded,
            output_root=self.output,
            source_commit=SOURCE_SHA,
            source_run_id=RUN_ID,
            source_run_attempt=RUN_ATTEMPT,
        )

    def test_requires_complete_six_job_product_matrix_and_prepares_manifest(self) -> None:
        inventory = self.prepare()
        self.assertEqual(len(inventory["assets"]), 14)
        manifest_path = self.output / inventory["manifest"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["channel"], "latest")
        self.assertTrue(manifest["prerelease"])
        self.assertEqual(manifest["source_commit"], SOURCE_SHA)
        self.assertEqual(len(manifest["artifacts"]), 6)
        self.assertEqual(
            {(row["runner_os"], row["profile"]) for row in manifest["artifacts"]},
            {
                (os_name, profile)
                for os_name in ("Linux", "macOS", "Windows")
                for profile in ("tui", "gui-sdl")
            },
        )
        self.assertTrue((self.output / inventory["checksums"]).is_file())

    def test_rejects_missing_platform_profile_artifact(self) -> None:
        missing = self.downloaded / "cdin-installed-product-Windows-gui-sdl"
        for path in missing.iterdir():
            path.unlink()
        missing.rmdir()
        with self.assertRaisesRegex(RollingReleaseError, "matrix is incomplete"):
            self.prepare()

    def test_rejects_wrong_source_revision_or_run_identity(self) -> None:
        manifest_path = next(self.downloaded.glob("cdin-installed-product-Linux-tui/*.manifest.json"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source_commit"] = "c" * 40
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(RollingReleaseError, "source commit mismatch"):
            self.prepare()

    def test_rejects_corrupt_archive_checksum(self) -> None:
        archive = next(self.downloaded.glob("cdin-installed-product-Linux-tui/*.tar.gz"))
        archive.write_bytes(b"tampered")
        with self.assertRaisesRegex(RollingReleaseError, "byte size mismatch|SHA-256 mismatch"):
            self.prepare()

    def test_rejects_symlinked_artifact(self) -> None:
        group = self.downloaded / "cdin-installed-product-Linux-tui"
        linked = group / "escape.tar.gz"
        linked.symlink_to(next(group.glob("*.tar.gz")))
        with self.assertRaisesRegex(RollingReleaseError, "symlink"):
            self.prepare()

    def test_refuses_to_overwrite_a_prepared_candidate_directory(self) -> None:
        self.prepare()
        with self.assertRaisesRegex(RollingReleaseError, "output already exists"):
            self.prepare()

    def test_remote_verification_requires_exact_digest_and_size_for_all_assets(self) -> None:
        inventory = self.prepare()
        remote = [
            {
                "name": item["name"],
                "size": item["size"],
                "digest": f"sha256:{item['sha256']}",
            }
            for item in inventory["assets"]
        ]
        verify_remote_assets(inventory, remote)
        remote[0]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(RollingReleaseError, "digest/size mismatch"):
            verify_remote_assets(inventory, remote)

    def test_latest_guard_rejects_a_delayed_older_successful_run(self) -> None:
        ancestry = {
            (SOURCE_SHA, "b" * 40): True,
            (SOURCE_SHA, "c" * 40): True,
            ("b" * 40, "c" * 40): True,
        }

        def is_ancestor(parent: str, child: str) -> bool:
            return parent == child or ancestry.get((parent, child), False)

        self.assertEqual(
            latest_action(
                current_latest="b" * 40,
                candidate=SOURCE_SHA,
                main_head="c" * 40,
                is_ancestor=is_ancestor,
            ),
            "stale",
        )
        self.assertEqual(
            latest_action(
                current_latest=SOURCE_SHA,
                candidate="b" * 40,
                main_head="c" * 40,
                is_ancestor=is_ancestor,
            ),
            "publish",
        )

    def test_latest_guard_rejects_diverged_candidate(self) -> None:
        with self.assertRaisesRegex(RollingReleaseError, "not on the same mainline"):
            latest_action(
                current_latest="b" * 40,
                candidate="c" * 40,
                main_head="d" * 40,
                is_ancestor=lambda parent, child: parent == child or (parent, child) == ("c" * 40, "d" * 40),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
