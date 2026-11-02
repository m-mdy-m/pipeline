"""Benchmark parsing, comparison and the ``pipeline bench`` command."""
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

from pipeline.benchmark import compare as cmp  # noqa: E402
from pipeline.core.cli import main as cli_main  # noqa: E402
from pipeline.utils.commands import split_command_line  # noqa: E402

GOBENCH = """goos: linux
pkg: example.com/demo
BenchmarkAdd-8   1000000   10.0 ns/op   0 B/op   0 allocs/op
BenchmarkAdd-8   1000000   30.0 ns/op   0 B/op   0 allocs/op
BenchmarkAdd-8   1000000   20.0 ns/op   0 B/op   0 allocs/op
BenchmarkMul     500       1,5 ns/op
PASS
"""


def run_cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cli_main(list(argv))
    return code, out.getvalue()


class ParseTests(unittest.TestCase):
    def test_gobench_median_and_package_prefix(self) -> None:
        values = cmp.parse_gobench(GOBENCH)
        self.assertEqual(values["example.com/demo.BenchmarkAdd"], 20.0)

    def test_gobench_without_package_and_noise(self) -> None:
        self.assertEqual(cmp.parse_gobench("BenchmarkX 10 5 ns/op\nnoise\n"), {"BenchmarkX": 5.0})
        self.assertEqual(cmp.parse_gobench(""), {})

    def test_split_command(self) -> None:
        self.assertEqual(cmp.split_command("python -c 'print(1)'"), ("python", "-c", "print(1)"))

    def test_windows_command_preserves_backslashes_and_quoted_spaces(self) -> None:
        command = r'"C:\Program Files\Python\python.exe" C:\repo\bench.py'
        self.assertEqual(
            split_command_line(command, windows=True),
            (r"C:\Program Files\Python\python.exe", r"C:\repo\bench.py"),
        )


class CompareTests(unittest.TestCase):
    def test_thresholds(self) -> None:
        rows = {r.name: r for r in cmp.compare({"a": 100, "b": 100, "c": 100, "gone": 1}, {"a": 130, "b": 110, "c": 50, "new": 1}, 25)}
        self.assertEqual(rows["a"].status, "regression")
        self.assertEqual(rows["b"].status, "ok")
        self.assertEqual(rows["c"].status, "improved")
        self.assertEqual(rows["gone"].status, "removed")
        self.assertEqual(rows["new"].status, "new")

    def test_exactly_on_threshold_is_not_a_regression(self) -> None:
        self.assertEqual(cmp.compare({"a": 100}, {"a": 125}, 25)[0].status, "ok")

    def test_zero_baseline_does_not_divide_by_zero(self) -> None:
        self.assertEqual(cmp.compare({"a": 0}, {"a": 5}, 25)[0].status, "ok")

    def test_markdown_mentions_regression(self) -> None:
        text = cmp.render_markdown(cmp.compare({"a": 100}, {"a": 200}, 25), 25, note="hello")
        self.assertIn("a", text)
        self.assertIn("hello", text)

    def test_baseline_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b" / "base.json"
            cmp.save_baseline(path, {"x": 1.5})
            self.assertEqual(cmp.load_baseline(path), {"x": 1.5})
            path.write_text("[1]")
            with self.assertRaises(cmp.BenchmarkError):
                cmp.load_baseline(path)


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=cwd, check=True, capture_output=True)


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class BenchCliTests(unittest.TestCase):
    """A tiny repo whose benchmark prints the number stored in value.txt."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "repo"
        self.root.mkdir()
        (self.root / "bench.py").write_text(
            "import pathlib\nprint('BenchmarkDemo 1 %s ns/op' % pathlib.Path('value.txt').read_text().strip())\n"
        )
        (self.root / "value.txt").write_text("100\n")
        git(self.root, "init", "-q")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "base")

    def bench(self, *extra: str) -> tuple[int, dict]:
        result = self.tmp / "out.json"
        code, _ = run_cli("bench", "--root", str(self.root), "--command", f"{sys.executable} bench.py", "--parser", "gobench",
                          "--count", "1", "--result", str(result), *extra)
        return code, (json.loads(result.read_text()) if result.exists() else {})

    def test_regression_against_a_git_ref_fails(self) -> None:
        (self.root / "value.txt").write_text("400\n")
        code, report = self.bench("--against", "HEAD")
        self.assertEqual(code, 1)
        self.assertEqual(report["regressions"], 1)
        self.assertTrue(report["compared"])
        self.assertEqual(report["results"][0]["status"], "regression")

    def test_report_only_never_fails(self) -> None:
        (self.root / "value.txt").write_text("400\n")
        code, report = self.bench("--against", "HEAD", "--report-only")
        self.assertEqual(code, 0)
        self.assertEqual(report["regressions"], 1)

    def test_unchanged_code_passes_and_worktree_is_cleaned_up(self) -> None:
        code, report = self.bench("--against", "HEAD")
        self.assertEqual(code, 0)
        self.assertEqual(report["regressions"], 0)
        listing = subprocess.run(["git", "worktree", "list"], cwd=self.root, capture_output=True, text=True, check=True).stdout
        self.assertEqual(len(listing.strip().splitlines()), 1)

    def test_bad_ref_is_skipped_unless_strict(self) -> None:
        code, report = self.bench("--against", "no-such-ref")
        self.assertEqual(code, 0)
        self.assertFalse(report["compared"])
        code, _ = self.bench("--against", "no-such-ref", "--strict")
        self.assertEqual(code, 2)

    def test_baseline_file_workflow(self) -> None:
        baseline = self.tmp / "baseline.json"
        code, _ = self.bench("--baseline", str(baseline), "--update-baseline")
        self.assertEqual(code, 0)
        self.assertEqual(cmp.load_baseline(baseline), {"BenchmarkDemo": 100.0})
        (self.root / "value.txt").write_text("500\n")
        code, report = self.bench("--baseline", str(baseline))
        self.assertEqual(code, 1)
        code, _ = self.bench("--baseline", str(baseline), "--threshold", "1000")
        self.assertEqual(code, 0)

    def test_missing_baseline_file(self) -> None:
        code, report = self.bench("--baseline", str(self.tmp / "nope.json"))
        self.assertEqual(code, 0)
        self.assertFalse(report["compared"])
        code, _ = self.bench("--baseline", str(self.tmp / "nope.json"), "--strict")
        self.assertEqual(code, 2)

    def test_no_results_is_an_error(self) -> None:
        code, _ = run_cli("bench", "--root", str(self.root), "--command", f"{sys.executable} -c pass", "--parser", "gobench")
        self.assertEqual(code, 2)

    def test_language_without_default_command_needs_one(self) -> None:
        (self.root / "pipeline.toml").write_text('[ci]\nlanguage = "python"\n')
        code, _ = run_cli("bench", "--root", str(self.root))
        self.assertNotEqual(code, 0)

    def test_config_table_supplies_command_and_threshold(self) -> None:
        (self.root / "pipeline.toml").write_text(
            f'[ci.bench]\ncommand = {json.dumps(sys.executable + " bench.py")}\nparser = "gobench"\ncount = 1\nthreshold_percent = 1000\n'
        )
        (self.root / "value.txt").write_text("400\n")
        code, _ = run_cli("bench", "--root", str(self.root), "--against", "HEAD")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
