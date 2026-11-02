"""Command-line parsing shared by benchmark and toolchain configuration."""
from __future__ import annotations

import os
import shlex


def split_command_line(text: str, *, windows: bool | None = None) -> tuple[str, ...]:
    """Split a configured command without losing Windows path separators.

    POSIX shlex treats backslashes as escape characters. On Windows they are
    normally path separators, so disable shlex escaping while retaining
    whitespace splitting and single/double quote grouping.
    """
    use_windows_rules = os.name == "nt" if windows is None else windows
    if not use_windows_rules:
        return tuple(shlex.split(text))

    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    return tuple(lexer)
