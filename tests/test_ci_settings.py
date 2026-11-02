"""The repository-owned ``[ci]`` table and the portable toolchain checks."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline.core.cli import main as cli_main  # noqa: E402
from pipeline.core.ci_settings import CISettings, load_ci_settings, parse_ci_table  # noqa: E402
from pipeline.core.errors import PipelineConfigError  # noqa: E402
from pipeline.toolchains import checks  # noqa: E402


def run_cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = cli_main(list(argv))
        except SystemExit as exc:  # argparse errors
            code = int(exc.code or 0)
    return code, out.getvalue()


class ParseTests(unittest.TestCase):
    def test_full_table(self) -> None:
        s = parse_ci_table({
            "language": "go", "stages": ["lint", "test"], "skip": ["install"], "timeout_seconds": 90,
            "options": {"race": True, "tests": "t"}, "commands": {"build": "make"},
            "bench": {"command": "go test -bench .", "parser": "gobench", "count": 4, "threshold_percent": 10, "baseline": "b.json"},
        })
        self.assertEqual(s.language, "go")
        self.assertEqual(s.stages, ("lint", "test"))
        self.assertEqual(s.options, {"race": "true", "tests": "t"})
        self.assertEqual(s.bench.threshold_percent, 10.0)
        self.assertEqual(s.bench.baseline, "b.json")

    def test_rejects_bad_input(self) -> None:
        bad = [
            ("x", "must be a table"),
            ({"nope": 1}, "Unknown keys"),
            ({"stages": ["deploy"]}, "unknown stages"),
            ({"skip": "lint"}, "array"),
            ({"timeout_seconds": -1}, "timeout_seconds"),
            ({"timeout_seconds": True}, "timeout_seconds"),
            ({"options": {"a": [1]}}, "options"),
            ({"commands": {"lint": " "}}, "commands"),
            ({"commands": {"deploy": "x"}}, "unknown stages"),
            ({"bench": {"parser": "csv"}}, "parser"),
            ({"bench": {"extra": 1}}, "bench"),
            ({"bench": {"count": -1}}, "count"),
            ({"bench": {"threshold_percent": True}}, "threshold"),
        ]
        for raw, text in bad:
            with self.subTest(raw=raw), self.assertRaises(PipelineConfigError) as ctx:
                parse_ci_table(raw)
            self.assertIn(text, str(ctx.exception))

    def test_load_defaults_and_broken_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(load_ci_settings(root), CISettings())
            (root / "pipeline.toml").write_text("[tasks.a]\ncommand=['true']\n")
            self.assertEqual(load_ci_settings(root), CISettings())
            (root / "pipeline.toml").write_text("[ci\n")
            with self.assertRaises(PipelineConfigError):
                load_ci_settings(root)


class CIIntegrationTests(unittest.TestCase):
    def project(self, toml: str) -> Path:
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        root = Path(tmp)
        (root / "pipeline.toml").write_text(toml)
        (root / "go.mod").write_text("module demo\n\ngo 1.22\n")
        return root

    def plan(self, root: Path, *extra: str) -> dict:
        code, out = run_cli("ci", "--root", str(root), "--dry-run", *extra)
        self.assertEqual(code, 0)
        return json.loads(out)

    def test_config_only_file_without_tasks_is_valid(self) -> None:
        root = self.project('[ci]\nlanguage = "go"\nskip = ["install"]\n')
        data = self.plan(root)
        self.assertEqual(data["language"], "go")
        self.assertNotIn("install", [s["stage"] for s in data["steps"]])

    def test_ci_commands_override_and_cli_wins(self) -> None:
        root = self.project('[ci]\nlanguage = "go"\n[ci.commands]\ntest = "echo from-config"\n')
        text = json.dumps(self.plan(root))
        self.assertIn("from-config", text)
        text = json.dumps(self.plan(root, "--test-command", "echo from-cli"))
        self.assertIn("from-cli", text)
        self.assertNotIn("from-config", text)

    def test_invalid_ci_table_is_a_config_error(self) -> None:
        root = self.project('[ci]\nstages = ["deploy"]\n')
        code, _ = run_cli("ci", "--root", str(root), "--dry-run")
        self.assertNotEqual(code, 0)


@unittest.skipUnless(shutil.which("gofmt") and shutil.which("go"), "Go is not installed")
class GoChecksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / "go.mod").write_text("module demo\n\ngo 1.22\n", newline="\n")

    def test_gofmt(self) -> None:
        (self.tmp / "a.go").write_text("package a\n\nfunc F() int { return 1 }\n", newline="\n")
        self.assertEqual(checks.gofmt(self.tmp, []), 0)
        (self.tmp / "a.go").write_text("package a\nfunc F()   int{return 1}\n", newline="\n")
        self.assertEqual(checks.gofmt(self.tmp, []), 1)

    def test_go_mod_tidy_detects_and_restores(self) -> None:
        (self.tmp / "a.go").write_text("package a\n", newline="\n")
        self.assertEqual(checks.go_mod_tidy(self.tmp, []), 0)
        original = "module demo\n\ngo 1.22\n\nrequire example.invalid/x v1.0.0\n"
        (self.tmp / "go.mod").write_text(original, newline="\n")
        # offline: tidy may fail resolving the module; either way the file must be restored
        code = checks.go_mod_tidy(self.tmp, [])
        self.assertNotEqual(code, 0)
        self.assertEqual((self.tmp / "go.mod").read_text(), original)

    def test_go_mod_tidy_without_go_mod(self) -> None:
        (self.tmp / "go.mod").unlink()
        self.assertEqual(checks.go_mod_tidy(self.tmp, []), 2)


@unittest.skipUnless(shutil.which("vim"), "vim is not installed")
class VimChecksTests(unittest.TestCase):
    def test_vim_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "vim"
            shutil.copytree(ROOT / "examples" / "toolchains" / "vim", root)
            self.assertEqual(checks.vim_features(root, ["vim"]), 0)
            self.assertEqual(checks.vim_load(root, ["vim"]), 0)
            self.assertEqual(checks.vim_helptags(root, ["vim"]), 0)

    def test_vim_load_reports_a_broken_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plugin").mkdir()
            (root / "plugin" / "bad.vim").write_text("this is not a vim command !!\n")
            self.assertEqual(checks.vim_load(root, ["vim"]), 1)
            self.assertEqual(checks.vim_load(Path(tmp) / "empty", ["vim"]), 2)

    def test_vim_load_accepts_line_continuations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plugin").mkdir()
            (root / "plugin" / "ok.vim").write_text("let g:x = [\n  \\ 1,\n  \\ 2]\n")
            self.assertEqual(checks.vim_load(root, ["vim"]), 0)


class ChecksCliTests(unittest.TestCase):
    def test_unknown_check_is_rejected(self) -> None:
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            checks.main(["nope"])


if __name__ == "__main__":
    unittest.main()
