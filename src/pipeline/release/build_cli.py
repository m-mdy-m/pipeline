#!/usr/bin/env python3
"""CLI for provider-neutral build-release helpers."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .build import (
    BuildReleaseError,
    assemble_release_assets,
    prepare_release,
    verify_release_assets,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare release notes and verify build-release assets."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="validate the ref and prepare release notes")
    prepare.add_argument("--changelog", default="CHANGELOG.md")
    prepare.add_argument("--output-directory", default="release-preparation")
    prepare.add_argument("--ref-type", default=os.environ.get("PIPELINE_REF_TYPE", ""))
    prepare.add_argument("--ref-name", default=os.environ.get("PIPELINE_REF_NAME", ""))
    prepare.add_argument("--commit-sha", default=os.environ.get("PIPELINE_SHA", ""))
    prepare.add_argument("--dry-run", default="false")

    assemble = commands.add_parser("assemble", help="create checksums for downloaded artifacts")
    assemble.add_argument("--assets-directory", default="release-assets")
    assemble.add_argument("--profile", choices=("standard", "gitea"), default="standard")
    assemble.add_argument("--metadata", default="", help="optional release-meta.json from the prepare stage")

    verify = commands.add_parser("verify", help="verify release checksums and the optional asset manifest")
    verify.add_argument("--assets-directory", default="release-assets")

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_release(
                changelog_path=args.changelog,
                output_directory=args.output_directory,
                ref_type=args.ref_type,
                ref_name=args.ref_name,
                commit_sha=args.commit_sha,
                dry_run=args.dry_run,
            )
        elif args.command == "assemble":
            result = assemble_release_assets(
                args.assets_directory,
                profile=args.profile,
                metadata_path=args.metadata or None,
            )
        else:
            result = verify_release_assets(args.assets_directory)
    except (BuildReleaseError, OSError) as exc:
        print(f"build release failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
