from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "rolling-release.yml"


class RollingReleaseWorkflowContractTests(unittest.TestCase):
    def test_channel_is_reusable_separate_from_semver_release(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_call:", workflow)
        self.assertIn("pipeline-ref:", workflow)
        self.assertIn("source-run-id:", workflow)
        self.assertIn("source-run-attempt:", workflow)
        self.assertIn("source-commit:", workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn('group: pipeline-rolling-latest-${{ github.repository }}', workflow)
        self.assertIn('name: Rolling development GitHub Release', workflow)

    def test_exact_upstream_artifacts_are_downloaded_only_from_a_successful_run(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        verify = workflow.index("Verify the exact upstream CI run")
        download = workflow.index("Download product bundles from the exact successful CI run")
        self.assertLess(verify, download)
        download_block = workflow[download:workflow.index("Validate all six native product bundles", download)]
        self.assertIn("run-id: ${{ inputs.source-run-id }}", download_block)
        self.assertIn("repository: ${{ github.repository }}", download_block)
        self.assertIn("github-token:", download_block)
        self.assertIn("steps.source.outputs.publish == 'true'", workflow)

    def test_product_artifacts_and_remote_inventory_are_verified_before_promotion(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        validate = workflow.index("Validate all six native product bundles")
        upload = workflow.index("Upload uniquely named candidate assets")
        verify_remote = workflow.index("Verify the complete remote asset inventory before moving latest")
        promote = workflow.index("Recheck freshness, move latest and publish the verified release")
        self.assertLess(validate, upload)
        self.assertLess(upload, verify_remote)
        self.assertLess(verify_remote, promote)
        self.assertIn("pipeline.release.rolling prepare", workflow)
        self.assertIn("pipeline.release.rolling verify-remote", workflow)
        self.assertIn('"prerelease": True', workflow)
        self.assertIn('"tag_name": "latest"', workflow)
        self.assertIn('"draft": False', workflow)
        self.assertIn('"make_latest": "false"', workflow)

    def test_delayed_runs_are_checked_before_and_after_upload_and_old_assets_prune_last(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        source = workflow.index("Verify the exact upstream CI run")
        before = workflow.index("Check source ancestry and current latest pointer")
        upload = workflow.index("Upload uniquely named candidate assets")
        after = workflow.index("Recheck freshness, move latest and publish the verified release")
        prune = workflow.index("Prune superseded rolling assets only after tag + Release metadata are live")
        self.assertLess(source, before)
        self.assertLess(before, upload)
        self.assertLess(upload, after)
        self.assertLess(after, prune)
        self.assertIn("latest_successful_run_id", workflow)
        self.assertIn("latest_successful_run_attempt", workflow)
        self.assertIn("old-assets-to-prune.txt", workflow)
        self.assertNotIn("make_latest: true", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
