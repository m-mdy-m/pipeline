from __future__ import annotations

from pathlib import Path
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
        self.assertIn("Immutable rolling asset collision", self.publisher)
        self.assertIn("sha256:$expected_sha", self.publisher)
        self.assertIn("expected_size", self.publisher)

    def test_manifest_is_uploaded_after_packages_and_before_promotion(self) -> None:
        package_upload = self.publisher.index("# Upload all commit-qualified assets")
        manifest_upload = self.publisher.index("# The manifest and its sidecar")
        remote_verify = self.publisher.index("# Re-read the Release inventory")
        promote = self.publisher.index("# Recheck immediately before moving the mutable ref")
        self.assertLess(package_upload, manifest_upload)
        self.assertLess(manifest_upload, remote_verify)
        self.assertLess(remote_verify, promote)

    def test_prerelease_is_verified_before_obsolete_assets_are_pruned(self) -> None:
        update_release = self.publisher.index('gh api --method PATCH "repos/$REPOSITORY/releases/$release_id"')
        verify_flags = self.publisher.index("(.draft == false) and (.prerelease == true)", update_release)
        prune = self.publisher.index("# Do not prune if main advanced")
        self.assertLess(update_release, verify_flags)
        self.assertLess(verify_flags, prune)
        self.assertIn('[[ "$name" == "rolling-$PRODUCT_PREFIX-"* ]]', self.publisher)

    def test_tag_move_is_guarded_by_latest_main_and_verified_release_assets(self) -> None:
        assert_main = self.publisher.index("assert_fresh_main", self.publisher.index("# Recheck immediately"))
        ref_update = self.publisher.index('gh api --method PATCH "repos/$REPOSITORY/git/refs/tags/latest"', assert_main)
        self.assertLess(assert_main, ref_update)
        self.assertIn('resolved_ref="$(gh api "repos/$REPOSITORY/commits/latest" --jq .sha)"', self.publisher)


if __name__ == "__main__":
    unittest.main()
