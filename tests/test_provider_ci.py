"""The language presets must behave the same through every provider, and providers must stay thin."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from pipeline.providers.github.adapter import render_annotations, render_step_summary  # noqa: E402

REPORT = {
    "language": "go",
    "succeeded": False,
    "requested_tasks": ["test"],
    "tasks": [
        {"name": "build", "status": "succeeded", "return_code": 0, "duration_seconds": 1.5, "error": ""},
        {"name": "test", "status": "failed", "return_code": 3, "duration_seconds": 0.25, "error": "Command exited with 3\nsecond line"},
        {"name": "extra", "status": "skipped", "return_code": None, "duration_seconds": 0, "error": "Dependency test did not succeed"},
    ],
}


class GitHubPresentationTests(unittest.TestCase):
    def test_step_summary_lists_every_task(self) -> None:
        text = render_step_summary(REPORT)
        self.assertIn("pipeline: go — failed", text)
        for name in ("build", "test", "extra"):
            self.assertIn(f"`{name}`", text)
        self.assertIn("❌ failed", text)

    def test_annotations_escape_newlines_and_only_cover_failures(self) -> None:
        lines = render_annotations(REPORT)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("::error title=pipeline task test failed::"))
        self.assertNotIn("\n", lines[0])
        self.assertIn("%0A", lines[0])


class SameCommandAllProvidersTests(unittest.TestCase):
    ENTRYPOINTS = {"local": "pipeline.providers.local", "github": "pipeline.providers.github", "gitlab": "pipeline.providers.gitlab"}

    def env_for(self, provider: str, root: Path) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PIPELINE_", "GITHUB_", "CI_"))}
        env.update({"PYTHONPATH": str(SRC), "PWD": str(root)})
        if provider == "github":
            env.update({"GITHUB_WORKSPACE": str(root), "GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/feature/x", "GITHUB_SHA": "a" * 40,
                        "GITHUB_STEP_SUMMARY": str(root / "summary.md"), "GITHUB_OUTPUT": str(root / "github-output.txt")})
        elif provider == "gitlab":
            env.update({"CI_PROJECT_DIR": str(root), "CI_PIPELINE_SOURCE": "push", "CI_COMMIT_BRANCH": "feature/x", "CI_COMMIT_REF_NAME": "feature/x", "CI_COMMIT_SHA": "b" * 40})
        else:
            env["PIPELINE_WORKSPACE"] = str(root)
        return env

    def run_ci(self, provider: str, root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, "-m", self.ENTRYPOINTS[provider]]
        command += ["ci"] if provider == "github" else ["ci"]
        command += ["--root", str(root), "--language", "custom", *extra]
        return subprocess.run(command, cwd=ROOT, env=self.env_for(provider, root), capture_output=True, text=True, check=False)

    def test_a_passing_preset_run_succeeds_everywhere(self) -> None:
        for provider in self.ENTRYPOINTS:
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                report = root / "report.json"
                proc = self.run_ci(provider, root, "--build-command", "python -c pass", "--test-command",
                                   "python -c \"import os; assert os.environ['PIPELINE_PROVIDER'] == '%s'\"" % provider, "--result", str(report))
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                data = json.loads(report.read_text(encoding="utf-8"))
                self.assertEqual((data["provider"], data["succeeded"], data["language"]), (provider, True, "custom"))

    def test_a_failing_preset_run_fails_everywhere(self) -> None:
        for provider in self.ENTRYPOINTS:
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as tmp:
                proc = self.run_ci(provider, Path(tmp), "--test-command", "python -c 'raise SystemExit(4)'")
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)

    def test_github_adds_summary_annotation_and_outputs_without_changing_core_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.run_ci("github", root, "--test-command", "python -c 'raise SystemExit(4)'")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("::error title=pipeline task test failed::", proc.stdout)
            summary = (root / "summary.md").read_text(encoding="utf-8")
            self.assertIn("pipeline: custom — failed", summary)
            output = (root / "github-output.txt").read_text(encoding="utf-8")
            self.assertIn("language=custom", output)
            self.assertIn("succeeded=false", output)

    def test_github_does_not_leave_temporary_reports_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = self.env_for("github", root)
            env["TMPDIR"] = str(root / "tmp")
            (root / "tmp").mkdir()
            subprocess.run([sys.executable, "-m", "pipeline.providers.github", "ci", "--root", str(root), "--language", "custom", "--test-command", "python -c pass"],
                           cwd=ROOT, env=env, capture_output=True, text=True, check=True)
            self.assertEqual(list((root / "tmp").iterdir()), [])


class ProvidersStayThinTests(unittest.TestCase):
    """Language knowledge lives in src/pipeline/toolchains, never in a provider."""

    TOOL_COMMANDS = re.compile(
        r"\b(npm (?:ci|install|test|run)|pnpm install|yarn install|go (?:test|vet|build|mod)|cargo (?:test|build|clippy|fetch)|"
        r"mvn\b|gradle\b|dotnet (?:test|build|restore)|pytest|unittest discover|compileall|pip install|cmake --build|ctest)"
    )

    def provider_files(self) -> list[Path]:
        files = list((SRC / "pipeline" / "providers").rglob("*.py"))
        files += list((SRC / "pipeline" / "providers").rglob("*.yml"))
        files += list((ROOT / ".github" / "actions").rglob("action.yml"))
        files.append(ROOT / ".github" / "workflows" / "ci.yml")
        files.append(ROOT / ".gitlab-ci.yml")
        return files

    def test_provider_files_do_not_hardcode_toolchain_commands(self) -> None:
        for path in self.provider_files():
            text = path.read_text(encoding="utf-8")
            # Descriptions and comments may mention commands; executable lines may not.
            code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(("#", "description:")))
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertIsNone(self.TOOL_COMMANDS.search(code), self.TOOL_COMMANDS.search(code))

    def test_toolchains_package_has_no_provider_references(self) -> None:
        for path in (SRC / "pipeline" / "toolchains").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                for needle in ("GITHUB_", "GITLAB_", "CI_PROJECT", "::error", ".providers", "import providers"):
                    self.assertNotIn(needle, text)

    def test_every_provider_exposes_the_ci_command_through_the_core(self) -> None:
        from pipeline.core.cli import build_parser

        parsed = build_parser().parse_args(["ci", "--language", "node", "--skip", "lint"])
        self.assertEqual((parsed.command, parsed.language, parsed.skip), ("ci", "node", "lint"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
