"""Shared validation for release target identifiers."""
from __future__ import annotations

import re


# Target IDs are portable artifact identifiers, not language identifiers.
# Keep this rule shared by matrix parsing and target-stage execution.
TARGET_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def is_valid_target_id(value: object) -> bool:
    """Return whether value is a safe, portable target ID."""
    return isinstance(value, str) and TARGET_ID_PATTERN.fullmatch(value) is not None
