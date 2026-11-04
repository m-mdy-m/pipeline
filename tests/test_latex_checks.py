"""Tests for PDF artifact validation in the LaTeX preset."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline.toolchains.checks import latex_pdf


class LatexArtifactTests(unittest.TestCase):
    def test_accepts_a_pdf_with_header_and_eof_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "build"
            output.mkdir()
            (output / "document.pdf").write_bytes(b"%PDF-1.7\n1 0 obj\nendobj\n%%EOF\n")
            self.assertEqual(latex_pdf(root, ["build"]), 0)

    def test_rejects_empty_or_incomplete_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "build"
            output.mkdir()
            (output / "broken.pdf").write_bytes(b"%PDF-1.7\nunfinished")
            self.assertEqual(latex_pdf(root, ["build"]), 1)

    def test_rejects_missing_build_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(latex_pdf(Path(tmp), ["build"]), 1)

    def test_accepts_uppercase_pdf_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "build"
            output.mkdir()
            (output / "document.PDF").write_bytes(b"%PDF-1.7\\n1 0 obj\\nendobj\\n%%EOF\\n")
            self.assertEqual(latex_pdf(root, ["build"]), 0)

