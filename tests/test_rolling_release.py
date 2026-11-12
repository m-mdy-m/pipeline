from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.release.rolling import (
    RollingReleaseError,
    prepare_rolling_assets,
    verify_rolling_assets,
)


SOURCE_SHA = "a" * 40
MATRIX = json.dumps([
    {"target": "linux-x86_64", "profile": "tui"},
    {"target": "windows-x86_64", "profile": "gui-sdl"},
])


class RollingReleasePreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="pipeline-rolling-test-")
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "downloaded"
        self.artifacts.mkdir()
        self.output = self.root / "prepared"
        self.write_artifact(
            "cdin-installed-product-linux-x86_64-tui",
            os_name="linux",
            architecture="x86_64",
            abi="gnu-glibc-2.35",
            profile="tui",
            payload=b"linux product archive",
        )
        self.write_artifact(
            "cdin-installed-product-windows-x86_64-gui-sdl",
            os_name="windows",
            architecture="x86_64",
            abi="windows-ucrt64",
            profile="gui-sdl",
            payload=b"windows product archive",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_artifact(
        self,
        directory_name: str,
        *,
        os_name: str,
        architecture: str,
        abi: str,
        profile: str,
        payload: bytes,
        source_sha: str = SOURCE_SHA,
        version: str = "0.2.0",
    ) -> Path:
        directory = self.artifacts / directory_name
        directory.mkdir()
        archive_name = f"cdin-{version}-{os_name}-{architecture}-{profile}.tar.gz"
        digest = hashlib.sha256(payload).hexdigest()
        (directory / archive_name).write_bytes(payload)
        (directory / f"{archive_name}.sha256").write_text(
            f"{digest}  {archive_name}\n", encoding="ascii"
        )
        package_manifest = {
            "schema_version": 1,
            "product": "com.cdin.editor",
            "version": version,
            "source_commit": source_sha,
            "target": {"os": os_name, "architecture": architecture, "abi": abi},
            "profile": profile,
            "registry_version": "0.2.0-dev.2",
            "registry_manifest_sha256": "b" * 64,
            "components": [],
            "environment_contracts": [],
            "build_dependencies": {},
            "archive": {
                "name": archive_name,
                "size_bytes": len(payload),
                "sha256": digest,
            },
        }
        (directory / f"cdin-{version}.manifest.json").write_text(
            json.dumps(package_manifest), encoding="utf-8"
        )
        return directory

    def prepare(
        self,
        *,
        source_sha: str = SOURCE_SHA,
        matrix: str = MATRIX,
        source_run_id: str = "123456",
        source_run_attempt: str = "2",
    ) -> dict:
        return prepare_rolling_assets(
            artifact_root=self.artifacts,
            output_directory=self.output,
            repository="cdin-editor/cdin",
            source_sha=source_sha,
            source_run_id=source_run_id,
            source_run_attempt=source_run_attempt,
            product_prefix="cdin",
            expected_target_profiles=matrix,
        )

    def refresh_rolling_manifest(self, result: dict) -> None:
        manifest_path = self.output / result["manifest_name"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for asset in manifest["assets"]:
            path = self.output / asset["name"]
            asset["size_bytes"] = path.stat().st_size
            asset["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        (self.output / (result["manifest_name"] + ".sha256")).write_text(
            f"{digest}  {result['manifest_name']}\n", encoding="ascii"
        )

    def test_prepares_exact_matrix_and_commit_qualified_assets(self) -> None:
        result = self.prepare()
        self.assertEqual(result["source_commit"], SOURCE_SHA)
        self.assertEqual(result["asset_count"], 8)
        self.assertTrue(result["manifest_name"].endswith(f"{SOURCE_SHA}.json"))
        self.assertEqual(len(result["packages"]), 2)
        self.assertEqual(
            {(item["target"], item["profile"]) for item in result["packages"]},
            {("linux-x86_64", "tui"), ("windows-x86_64", "gui-sdl")},
        )
        for asset in result["assets"]:
            path = self.output / asset["name"]
            self.assertEqual(path.stat().st_size, asset["size_bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), asset["sha256"])
            self.assertIn(SOURCE_SHA, path.name)
        report = verify_rolling_assets(
            output_directory=self.output,
            manifest_name=result["manifest_name"],
            source_sha=SOURCE_SHA,
            repository="cdin-editor/cdin",
            expected_target_profiles=MATRIX,
        )
        self.assertEqual(report["source_commit"], SOURCE_SHA)
        self.assertEqual(report["asset_count"], 8)

    def test_rejects_zero_or_nonpositive_workflow_run_identity(self) -> None:
        with self.assertRaisesRegex(RollingReleaseError, "positive decimal integers"):
            self.prepare(source_run_id="0")
        with self.assertRaisesRegex(RollingReleaseError, "positive decimal integers"):
            self.prepare(source_run_attempt="00")

    def test_rejects_artifact_built_from_another_commit(self) -> None:
        directory = next(self.artifacts.iterdir())
        manifest_path = next(directory.glob("*.manifest.json"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source_commit"] = "c" * 40
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(RollingReleaseError, "expected"):
            self.prepare()

    def test_rejects_missing_native_target_profile(self) -> None:
        directory = next(self.artifacts.glob("cdin-installed-product-windows-*"))
        for path in directory.iterdir():
            path.unlink()
        directory.rmdir()
        with self.assertRaisesRegex(RollingReleaseError, "expected 2 downloaded artifacts, found 1"):
            self.prepare()

    def test_rejects_archive_checksum_mismatch(self) -> None:
        directory = next(self.artifacts.iterdir())
        sidecar = next(directory.glob("*.sha256"))
        sidecar.write_text(f"{'0' * 64}  {sidecar.name[:-7]}\n", encoding="ascii")
        with self.assertRaisesRegex(RollingReleaseError, "checksum sidecar"):
            self.prepare()

    def test_rejects_duplicate_target_profile(self) -> None:
        original = next(self.artifacts.iterdir())
        duplicate = self.artifacts / "duplicate-artifact"
        duplicate.mkdir()
        for path in original.iterdir():
            (duplicate / path.name).write_bytes(path.read_bytes())
        with self.assertRaisesRegex(RollingReleaseError, "expected 2 downloaded artifacts, found 3"):
            self.prepare()

    def test_rejects_symlinked_artifact_members(self) -> None:
        directory = next(self.artifacts.iterdir())
        archive = next(path for path in directory.iterdir() if path.name.endswith(".tar.gz"))
        link = directory / "linked.tar.gz"
        try:
            link.symlink_to(archive)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable")
        with self.assertRaisesRegex(RollingReleaseError, "symlink"):
            self.prepare()

    def test_verifier_rejects_missing_package_pair_even_when_target_list_is_intact(self) -> None:
        result = self.prepare()
        manifest_path = self.output / result["manifest_name"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["packages"].pop()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(RollingReleaseError, "package inventory is incomplete"):
            verify_rolling_assets(
                output_directory=self.output,
                manifest_name=result["manifest_name"],
                source_sha=SOURCE_SHA,
                repository="cdin-editor/cdin",
                expected_target_profiles=MATRIX,
            )

    def test_verifier_rejects_checksum_sidecar_that_disagrees_with_archive(self) -> None:
        result = self.prepare()
        package = result["packages"][0]
        sidecar = self.output / package["checksum"]
        sidecar.write_text(f"{'0' * 64}  {package['archive']['name']}\n", encoding="ascii")
        self.refresh_rolling_manifest(result)
        with self.assertRaisesRegex(RollingReleaseError, "checksum sidecar is inconsistent"):
            verify_rolling_assets(
                output_directory=self.output,
                manifest_name=result["manifest_name"],
                source_sha=SOURCE_SHA,
                repository="cdin-editor/cdin",
                expected_target_profiles=MATRIX,
            )

    def test_verifier_rejects_package_manifest_from_another_commit(self) -> None:
        result = self.prepare()
        package = result["packages"][0]
        package_manifest_path = self.output / package["package_manifest"]
        package_manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
        package_manifest["source_commit"] = "c" * 40
        package_manifest_path.write_text(json.dumps(package_manifest), encoding="utf-8")
        self.refresh_rolling_manifest(result)
        with self.assertRaisesRegex(RollingReleaseError, "provenance/target/profile mismatch"):
            verify_rolling_assets(
                output_directory=self.output,
                manifest_name=result["manifest_name"],
                source_sha=SOURCE_SHA,
                repository="cdin-editor/cdin",
                expected_target_profiles=MATRIX,
            )

    def test_verifier_rejects_modified_prepared_asset(self) -> None:
        result = self.prepare()
        asset = self.output / result["assets"][0]["name"]
        asset.write_bytes(b"tampered")
        with self.assertRaisesRegex(RollingReleaseError, "digest/size mismatch"):
            verify_rolling_assets(
                output_directory=self.output,
                manifest_name=result["manifest_name"],
                source_sha=SOURCE_SHA,
                repository="cdin-editor/cdin",
                expected_target_profiles=MATRIX,
            )


if __name__ == "__main__":
    unittest.main()
