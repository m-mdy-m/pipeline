from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import benchmark  # noqa: E402


class BenchmarkRunnerTests(unittest.TestCase):
    def test_repeated_command_writes_portable_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = benchmark.run_benchmark(
                command=f"{sys.executable} -c \"print('benchmark-ok')\"",
                category="startup",
                repetitions=3,
                working_directory=root,
                output_directory="results",
            )

            output = root / "results"
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["runs"], 3)
            self.assertTrue((output / "summary.md").is_file())
            self.assertTrue((output / "environment.txt").is_file())
            with (output / "iterations.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row["exit_code"] == "0" for row in rows))

    def test_failed_command_is_recorded_and_returned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = benchmark.run_benchmark(
                command=f"{sys.executable} -c \"raise SystemExit(7)\"",
                category="micro",
                repetitions=5,
                working_directory=root,
                output_directory="results",
            )
            self.assertEqual(result["exit_code"], 7)
            self.assertEqual(result["runs"], 1)
            self.assertIn("7", (root / "results" / "iterations.csv").read_text(encoding="utf-8"))

    def test_invalid_category_and_repetition_count_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                benchmark.run_benchmark(
                    command="echo ok",
                    category="unknown",
                    repetitions=1,
                    working_directory=root,
                )
            with self.assertRaises(ValueError):
                benchmark.run_benchmark(
                    command="echo ok",
                    category="micro",
                    repetitions=0,
                    working_directory=root,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
