from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline_release.logger import PipelineLogger  # noqa: E402


class PipelineLoggerTests(unittest.TestCase):
    def test_stderr_fallback_is_readable_and_component_scoped(self) -> None:
        stream = io.StringIO()
        instance = PipelineLogger(library_path="", fallback_stream=stream, use_environment=False)
        instance.info("built source snapshot", component="prepare")
        instance.warning("one file was excluded", component="archive")
        output = stream.getvalue()
        self.assertIn("[INFO] [prepare] built source snapshot", output)
        self.assertIn("[WARN] [archive] one file was excluded", output)

    def test_missing_explicit_native_library_fails_loudly(self) -> None:
        with self.assertRaises(RuntimeError):
            PipelineLogger(library_path="/definitely/not/a/logger.so", use_environment=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
