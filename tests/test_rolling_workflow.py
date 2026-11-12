from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "rolling-release.yml"
PUBLISHER = ROOT / "scripts" / "publish_rolling_release.sh"


class RollingReleaseWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.publisher = PUBLISHER.read_text(encoding="utf-8")

    def test_reusable_workflow_is_serialized_per_repository(self) -> None:
        self.assertIn("workflow_call:", self.workflow)
        self.assertIn("group: rolling-product-${{ inputs.repository }}", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_source_run_is_bound_to_the_exact_artifact_producing_workflow(self) -> None:
        self.assertIn("source-workflow-path:", self.workflow)
        self.assertIn("SOURCE_WORKFLOW_PATH: ${{ inputs.source-workflow-path }}", self.workflow)
        self.assertIn('(.path == $workflow)', self.workflow)
        self.assertIn('SOURCE_WORKFLOW_PATH', self.publisher)
        self.assertIn('--arg workflow "$SOURCE_WORKFLOW_PATH"', self.publisher)

    def test_publisher_preserves_inherited_pythonpath(self) -> None:
        self.assertIn('PYTHONPATH=".pipeline/src:src${PYTHONPATH:+:$PYTHONPATH}"', self.publisher)

    def test_only_a_successful_exact_main_push_can_be_promoted(self) -> None:
        for expression in (
            "(.event == \"push\")",
            "(.conclusion == \"success\")",
            "(.head_branch == $branch)",
            "(.head_sha == $sha)",
            "(.repository.full_name == $repository)",
        ):
            self.assertIn(expression, self.workflow)
        self.assertIn('[[ "$SOURCE_BRANCH" == "main" ]]', self.workflow)
        self.assertIn('assert_fresh_main()', self.publisher)

    def test_artifacts_are_downloaded_from_the_exact_source_workflow_run(self) -> None:
        download = self.workflow.split(
            "      - name: Download target/profile artifacts from the verified source run",
            1,
        )[1].split("      - name:", 1)[0]
        self.assertIn("pattern: ${{ inputs.artifact-pattern }}", download)
        self.assertIn("repository: ${{ inputs.repository }}", download)
        self.assertIn("run-id: ${{ inputs.source-run-id }}", download)
        self.assertIn("github-token: ${{ github.token }}", download)
        self.assertIn("merge-multiple: false", download)

    def test_prepare_verify_promote_and_audit_steps_are_ordered(self) -> None:
        names = (
            "Download target/profile artifacts",
            "Verify and prepare commit-qualified rolling assets",
            "Independently verify the complete candidate inventory",
            "Promote the verified rolling release",
            "Retain the exact promotion inventory",
        )
        positions = [self.workflow.index(name) for name in names]
        self.assertEqual(positions, sorted(positions))

    def test_publisher_never_overwrites_immutable_same_sha_assets(self) -> None:
        self.assertNotIn("--clobber", self.publisher)
        self.assertNotIn("head -n 1", self.publisher)
        self.assertNotIn("awk -F", self.publisher)
        self.assertIn("pipeline.release.rolling verify", self.publisher)
        self.assertIn('line.split("\\t")', self.publisher)
        self.assertIn("immutable rolling asset collision", self.publisher)
        self.assertIn('remote_digest != f"sha256:{expected_digest}"', self.publisher)
        self.assertNotIn("gh release upload", self.publisher)
        self.assertIn("upload_release_asset", self.publisher)
        self.assertIn("upload_url?name=$encoded_name", self.publisher)
        self.assertIn("expected_size", self.publisher)

    def test_draft_release_retry_resolves_by_id_and_uploads_to_the_release_upload_url(self) -> None:
        self.assertIn('releases?per_page=100', self.publisher)
        self.assertIn('gh api "repos/$REPOSITORY/releases/$RELEASE_ID"', self.publisher)
        self.assertNotIn('releases/tags/latest', self.publisher)
        self.assertIn(".tag_name == \"latest\"", self.publisher)
        self.assertIn(".prerelease == true", self.publisher)
        self.assertIn("https://uploads.github.com/repos/$REPOSITORY/releases/$RELEASE_ID/assets", self.publisher)
        self.assertIn("upload_url_template", self.publisher)

    def test_remote_asset_names_are_parsed_without_shell_or_jq_interpolation(self) -> None:
        self.assertNotIn("select(.name ==", self.publisher)
        self.assertNotIn("awk -F", self.publisher)
        self.assertIn("fields = line.split", self.publisher)
        self.assertIn("remote_asset_state", self.publisher)

    def test_manifest_is_uploaded_after_packages_and_before_promotion(self) -> None:
        package_upload = self.publisher.index("# Upload commit-qualified package assets")
        manifest_upload = self.publisher.index("# Upload the authoritative manifest and its checksum only after package assets.")
        remote_verify = self.publisher.index("# Compare every local package/checksum/manifest byte")
        promote = self.publisher.index("# Recheck source identity immediately before moving the mutable tag")
        self.assertLess(package_upload, manifest_upload)
        self.assertLess(manifest_upload, remote_verify)
        self.assertLess(remote_verify, promote)

    def test_prerelease_is_verified_before_obsolete_assets_are_pruned(self) -> None:
        update_release = self.publisher.index('gh api --method PATCH "repos/$REPOSITORY/releases/$RELEASE_ID"')
        verify_flags = self.publisher.index("(.draft == false) and (.prerelease == true)", update_release)
        prune = self.publisher.index("# Prune old assets only after the new inventory")
        self.assertLess(update_release, verify_flags)
        self.assertLess(verify_flags, prune)
        self.assertIn('prefix = f"rolling-{product}-"', self.publisher)
        self.assertIn('name.startswith(prefix)', self.publisher)


    def test_publisher_script_has_valid_bash_syntax(self) -> None:
        if shutil.which("bash") is None:
            self.skipTest("bash is not installed")
        result = subprocess.run(
            ["bash", "-n", str(PUBLISHER)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_tag_move_is_guarded_by_latest_main_and_verified_release_assets(self) -> None:
        assert_main = self.publisher.index("assert_fresh_main", self.publisher.index("# Recheck source identity immediately before moving the mutable tag"))
        ref_update = self.publisher.index('gh api --method PATCH "repos/$REPOSITORY/git/refs/tags/latest"', assert_main)
        self.assertLess(assert_main, ref_update)
        self.assertIn('repos/$REPOSITORY/git/ref/tags/latest', self.publisher)


if __name__ == "__main__":
    unittest.main()
