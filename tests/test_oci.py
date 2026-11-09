from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.oci.artifacts import (  # noqa: E402
    OciArtifactError,
    build_publication_receipt,
    prepare_package_artifact,
    validate_target_matrix,
    verify_package_artifact,
)


class OciPackageArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.payload = self.root / "kernel-1.2.1-linux-amd64.tar.gz"
        self.payload.write_bytes(b"deterministic package payload\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prepare(self, *, output: str = "metadata", **overrides: str) -> dict:
        values = {
            "artifact_pattern": str(self.payload),
            "output_directory": self.root / output,
            "package_name": "kernel",
            "component_id": "kernel",
            "version": "1.2.1",
            "source_repository": "https://github.com/cdin-editor/kernel",
            "source_revision": "a" * 40,
            "target_id": "linux-amd64",
            "target_os": "linux",
            "architecture": "amd64",
            "abi": "gnu",
        }
        values.update(overrides)
        return prepare_package_artifact(**values)

    def test_prepare_writes_target_and_payload_identity(self) -> None:
        result = self.prepare()
        metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual(metadata["artifact_type"], "application/vnd.pipeline.package.v1")
        self.assertEqual(metadata["component"], {"id": "kernel", "variant": "default"})
        self.assertEqual(metadata["package"]["tag"], "1.2.1-linux-amd64")
        self.assertEqual(metadata["target"], {
            "id": "linux-amd64", "os": "linux", "architecture": "x86_64", "abi": "gnu"
        })
        self.assertEqual(metadata["artifact"]["size"], self.payload.stat().st_size)
        self.assertEqual(len(metadata["artifact"]["sha256"]), 64)
        self.assertEqual(result["artifact_path"], str(self.payload.resolve()))

    def test_metadata_is_deterministic_for_the_same_inputs(self) -> None:
        first = self.prepare(output="first")
        second = self.prepare(output="second")
        first_bytes = Path(first["metadata_path"]).read_bytes()
        second_bytes = Path(second["metadata_path"]).read_bytes()
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(first["metadata_sha256"], second["metadata_sha256"])

    def test_verify_accepts_an_unchanged_package(self) -> None:
        prepared = self.prepare()
        result = verify_package_artifact(prepared["metadata_path"], self.payload)
        self.assertTrue(result["verified"])
        self.assertEqual(result["sha256"], prepared["artifact_sha256"])
        self.assertEqual(result["target_id"], "linux-amd64")

    def test_verify_rejects_tampered_payload(self) -> None:
        prepared = self.prepare()
        self.payload.write_bytes(b"modified package payload\n")
        with self.assertRaisesRegex(OciArtifactError, "size mismatch|SHA-256 mismatch"):
            verify_package_artifact(prepared["metadata_path"], self.payload)

    def test_prepare_requires_exactly_one_artifact(self) -> None:
        second = self.root / "second.tar.gz"
        second.write_bytes(b"second")
        with self.assertRaisesRegex(OciArtifactError, "exactly one file"):
            self.prepare(artifact_pattern=str(self.root / "*.tar.gz"))

    def test_prepare_rejects_symlink_artifacts(self) -> None:
        link = self.root / "linked.tar.gz"
        try:
            link.symlink_to(self.payload)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links are unavailable on this runner")
        with self.assertRaisesRegex(OciArtifactError, "symbolic link"):
            self.prepare(artifact_pattern=str(link))

    def test_prepare_rejects_bad_version_and_source_identity(self) -> None:
        with self.assertRaisesRegex(OciArtifactError, "SemVer"):
            self.prepare(version="latest")
        with self.assertRaisesRegex(OciArtifactError, "full 40- or 64-character"):
            self.prepare(source_revision="main")
        with self.assertRaisesRegex(OciArtifactError, "HTTPS URL"):
            self.prepare(source_repository="http://github.com/cdin-editor/kernel")

    def test_target_matrix_requires_unique_platform_identity(self) -> None:
        value = json.dumps({"include": [
            {"id": "linux-amd64", "os": "ubuntu-24.04", "target_os": "linux",
             "architecture": "x86_64", "abi": "gnu"},
            {"id": "windows-amd64", "os": "windows-2025", "target_os": "windows",
             "architecture": "x86_64", "abi": "ucrt64"},
        ]})
        result = validate_target_matrix(value)
        self.assertEqual([entry["id"] for entry in result], ["linux-amd64", "windows-amd64"])

        duplicate = json.dumps({"include": [
            {"id": "linux-amd64", "os": "ubuntu-24.04", "target_os": "linux",
             "architecture": "amd64", "abi": "gnu"},
            {"id": "linux-amd64", "os": "ubuntu-24.04", "target_os": "linux",
             "architecture": "x86_64", "abi": "musl"},
        ]})
        with self.assertRaisesRegex(OciArtifactError, "duplicate target matrix id"):
            validate_target_matrix(duplicate)

    def test_universal_package_uses_version_only_tag(self) -> None:
        result = self.prepare(
            output="universal",
            target_id="any",
            target_os="any",
            architecture="any",
            abi="none",
            version="1.0.0-rc.2+build.7",
        )
        self.assertEqual(result["tag"], "1.0.0-rc.2_build.7")

    def test_metadata_output_never_overwrites_existing_descriptor(self) -> None:
        self.prepare()
        with self.assertRaisesRegex(OciArtifactError, "refusing to overwrite"):
            self.prepare()

    def test_publication_receipt_uses_the_immutable_manifest_digest(self) -> None:
        prepared = self.prepare()
        digest = "sha256:" + ("b" * 64)
        push_result = self.root / "push.json"
        push_result.write_text(json.dumps({
            "artifactType": "application/vnd.pipeline.package.v1",
            "digest": digest,
            "reference": f"ghcr.io/example/kernel@{digest}",
            "referenceAsTags": ["ghcr.io/example/kernel:1.2.1-linux-amd64"],
        }), encoding="utf-8")
        receipt = build_publication_receipt(
            metadata_path=prepared["metadata_path"],
            push_result_path=push_result,
            registry="ghcr.io",
            owner="Example",
        )
        self.assertEqual(receipt["oci"]["reference"], "ghcr.io/example/kernel:1.2.1-linux-amd64")
        self.assertEqual(receipt["oci"]["immutable_reference"], f"ghcr.io/example/kernel@{digest}")

    def test_publication_receipt_rejects_reference_digest_drift(self) -> None:
        prepared = self.prepare()
        push_result = self.root / "push.json"
        push_result.write_text(json.dumps({
            "artifactType": "application/vnd.pipeline.package.v1",
            "digest": "sha256:" + ("b" * 64),
            "reference": "ghcr.io/example/kernel@sha256:" + ("c" * 64),
            "referenceAsTags": ["ghcr.io/example/kernel:1.2.1-linux-amd64"],
        }), encoding="utf-8")
        with self.assertRaisesRegex(OciArtifactError, "does not match its digest"):
            build_publication_receipt(
                metadata_path=prepared["metadata_path"],
                push_result_path=push_result,
                registry="ghcr.io",
                owner="example",
            )


if __name__ == "__main__":
    unittest.main()
