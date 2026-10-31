"""CLI for the provider-neutral build-target catalogue and matrix validation."""
from __future__ import annotations

import argparse
import json
import sys

from .matrix import BuildMatrixError, target_catalog, validate_build_matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect supported release target profiles.")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="list built-in desktop, mobile and PWA profiles")
    listing.add_argument("--format", choices=("json", "table"), default="table")
    validate = commands.add_parser("validate", help="validate a GitHub-style build matrix JSON object")
    validate.add_argument("matrix_json")
    validate.add_argument("--default-e2e-test-command", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            catalog = target_catalog()
            if args.format == "json":
                print(json.dumps(catalog, indent=2, sort_keys=True))
            else:
                print("| Target | Platform | OS | Architecture | ABI |")
                print("| --- | --- | --- | --- | --- |")
                for target, data in catalog.items():
                    print(f"| {target} | {data['platform']} | {data['target_os']} | {data['architecture']} | {data['abi'] or '—'} |")
            return 0
        normalized = validate_build_matrix(
            args.matrix_json, default_e2e_test_command=args.default_e2e_test_command
        )
    except BuildMatrixError as exc:
        print(f"build target configuration: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"valid": True, "targets": normalized}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
