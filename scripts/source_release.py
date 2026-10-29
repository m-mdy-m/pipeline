#!/usr/bin/env python3
"""Backward-compatible command entry point; logic lives in pipeline_release."""

from pipeline_release import *  # noqa: F401,F403
from pipeline_release.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
