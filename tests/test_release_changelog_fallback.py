from __future__ import annotations

import unittest

from pipeline.release.changelog import extract_dry_run_section
from pipeline.release.errors import EmptyUnreleasedError, ReleaseError


class ExtractDryRunSectionTests(unittest.TestCase):
    def test_empty_unreleased_falls_back_to_newest_version(self) -> None:
        changelog = """# Changelog

## [Unreleased]

## [1.2.1] - 2026-11-12

### Added

- A released feature.

## [1.2.0] - 2026-11-03

### Fixed

- An older fix.
"""
        result = extract_dry_run_section(changelog, "CHANGELOG.md")
        self.assertIn("## [1.2.1]", result)
        self.assertIn("A released feature.", result)
        self.assertNotIn("1.2.0", result)

    def test_populated_unreleased_remains_authoritative(self) -> None:
        changelog = """# Changelog

## [Unreleased]

### Fixed

- An unreleased fix.

## [1.2.1] - 2026-11-12

### Added

- A released feature.
"""
        result = extract_dry_run_section(changelog, "CHANGELOG.md")
        self.assertIn("An unreleased fix.", result)
        self.assertNotIn("A released feature.", result)

    def test_empty_unreleased_without_versioned_section_still_fails(self) -> None:
        with self.assertRaisesRegex(EmptyUnreleasedError, "Unreleased section.*empty"):
            extract_dry_run_section("# Changelog\n\n## [Unreleased]\n", "CHANGELOG.md")

    def test_duplicate_unreleased_sections_still_fail_closed(self) -> None:
        changelog = """# Changelog

## [Unreleased]

## [Unreleased]

## [1.2.1] - 2026-11-12

- A released feature.
"""
        with self.assertRaisesRegex(ReleaseError, "exactly one"):
            extract_dry_run_section(changelog, "CHANGELOG.md")


if __name__ == "__main__":
    unittest.main()
