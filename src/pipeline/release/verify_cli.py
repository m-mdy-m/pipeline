"""CLI for verifying downloaded source-release bundles."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .verify import verify_bundle
from .errors import ReleaseError

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a downloaded pipeline source-release bundle.")
    parser.add_argument("directory", nargs="?", default=".")
    args = parser.parse_args(argv)
    try:
        result = verify_bundle(Path(args.directory))
    except (OSError, ReleaseError, ValueError) as exc:
        print(f"source release verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
