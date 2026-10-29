from __future__ import annotations
import sys
import zipfile
from .errors import ReleaseError
from .logger import logger
from .package import package
from .prepare import prepare


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"prepare", "package"}:
        logger.error("Usage: scripts/source_release.py prepare|package", component="cli")
        return 2
    try:
        prepare() if sys.argv[1] == "prepare" else package()
    except ReleaseError as exc:
        message = str(exc).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=Source Release validation failed::{message}", file=sys.stderr)
        logger.error(str(exc), component="source-release")
        return 1
    except (OSError, zipfile.BadZipFile, UnicodeError) as exc:
        logger.error(f"Source Release failed safely: {type(exc).__name__}: {exc}", component="source-release")
        return 1
    return 0
