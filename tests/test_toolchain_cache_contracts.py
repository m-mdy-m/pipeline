"""Contracts for dependency caches and pre-provisioned toolchains."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / ".github" / "actions" / "toolchain-quality" / "action.yml"
REUSABLE = ROOT / ".github" / "workflows" / "ci.yml"
GUIDE = ROOT / "docs" / "toolchains.md"


class ToolchainCacheContractTests(unittest.TestCase):
    def test_composite_action_has_lock_scoped_python_and_tex_caches(self) -> None:
        action = ACTION.read_text(encoding="utf-8")
        self.assertIn("python-cache-dependency-path:", action)
        self.assertIn("hashFiles(inputs.python-cache-dependency-path)", action)
        self.assertIn("latex-packages-file:", action)
        self.assertIn("hashFiles(inputs.latex-packages-file)", action)
        self.assertIn("uses: actions/cache@v4", action)
        self.assertIn("path: /var/cache/apt/archives", action)

    def test_preinstalled_latex_mode_verifies_without_installing(self) -> None:
        action = ACTION.read_text(encoding="utf-8")
        setup = action.split("    - name: Set up LaTeX (English and Persian)", 1)[1]
        setup = setup.split("    - name: Set up Rust", 1)[0]
        self.assertIn("verify)", setup)
        self.assertIn("install)", setup)
        self.assertIn("command -v \"latexmk\"", setup)
        self.assertIn("kpsewhich chicago-notes.bbx", setup)

    def test_reusable_workflow_exposes_the_same_latex_cache_contract(self) -> None:
        workflow = REUSABLE.read_text(encoding="utf-8")
        self.assertIn("latex-setup-mode:", workflow)
        self.assertIn("latex-packages-file:", workflow)
        self.assertIn("hashFiles(inputs.latex-packages-file)", workflow)
        self.assertIn("cache-dependency-path: ${{ inputs.python-cache-dependency-path }}", workflow)

    def test_documentation_distinguishes_hosted_cache_from_persistent_runners(self) -> None:
        guide = GUIDE.read_text(encoding="utf-8")
        self.assertIn("GitHub-hosted runners are fresh machines", guide)
        self.assertIn("latex-setup-mode: verify", guide)
        self.assertIn("untrusted public pull-request code", guide)


if __name__ == "__main__":
    unittest.main()
