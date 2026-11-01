from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
ACTIONS = ROOT / ".github" / "actions"

NEW_WORKFLOWS = (
    "codeql.yml",
    "dependency-review.yml",
    "typos.yml",
    "yamllint.yml",
    "zizmor.yml",
    "pr-title.yml",
    "python-compatibility.yml",
    "scorecard.yml",
)
EXTERNAL_USES = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)


class WorkflowInventoryTests(unittest.TestCase):
    def test_required_repository_workflows_exist(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        for name in NEW_WORKFLOWS:
            with self.subTest(workflow=name):
                self.assertTrue((WORKFLOWS / name).is_file())
                self.assertIn(f"'{name}'", makefile)

    def test_python_quality_action_is_used_by_compatibility_matrix(self) -> None:
        workflow = (WORKFLOWS / "python-compatibility.yml").read_text(encoding="utf-8")
        action = ACTIONS / "python-quality" / "action.yml"
        self.assertTrue(action.is_file())
        self.assertIn("uses: ./.github/actions/python-quality", workflow)

    def test_python_matrix_covers_all_supported_minors(self) -> None:
        workflow = (WORKFLOWS / "python-compatibility.yml").read_text(encoding="utf-8")
        for version in ('"3.11"', '"3.12"', '"3.13"'):
            with self.subTest(version=version):
                self.assertIn(version, workflow)

    def test_dependabot_tracks_action_and_python_updates(self) -> None:
        config = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        self.assertIn("package-ecosystem: github-actions", config)
        self.assertIn("package-ecosystem: pip", config)
        self.assertIn("interval: weekly", config)


class WorkflowSecurityContractTests(unittest.TestCase):
    def test_new_external_action_references_are_version_tags_not_hashes(self) -> None:
        candidates = [WORKFLOWS / name for name in NEW_WORKFLOWS]
        candidates.append(ACTIONS / "python-quality" / "action.yml")
        for path in candidates:
            content = path.read_text(encoding="utf-8")
            for target in EXTERNAL_USES.findall(content):
                if target.startswith("./"):
                    continue
                with self.subTest(path=path.relative_to(ROOT), target=target):
                    self.assertIn("@", target, "External Actions must use an explicit version tag")
                    ref = target.rsplit("@", 1)[1]
                    self.assertRegex(ref, r"^v\d+(?:\.\d+)*(?:[-+][A-Za-z0-9.-]+)?$")
                    self.assertNotRegex(ref, r"^[0-9a-f]{40}$")

    def test_zizmor_explicitly_allows_tag_pinning(self) -> None:
        config = (ROOT / "zizmor.yml").read_text(encoding="utf-8")
        self.assertIn('"*": ref-pin', config)
        workflow = (WORKFLOWS / "zizmor.yml").read_text(encoding="utf-8")
        self.assertIn("config: zizmor.yml", workflow)

    def test_dependency_review_is_gated_by_repository_capability(self) -> None:
        workflow = (WORKFLOWS / "dependency-review.yml").read_text(encoding="utf-8")
        self.assertIn("vars.PIPELINE_DEPENDENCY_REVIEW_ENABLED == 'true'", workflow)
        self.assertIn("actions/dependency-review-action@v5.0.0", workflow)
        self.assertIn("dependency-review-prerequisite:", workflow)

    def test_read_only_default_permissions_are_declared(self) -> None:
        for name in NEW_WORKFLOWS:
            workflow = (WORKFLOWS / name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assertRegex(workflow, r"(?m)^permissions:\n  contents: read(?:\n|$)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
