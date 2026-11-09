"""Command-line interface for provider-neutral OCI package preparation."""
from __future__ import annotations

import argparse
import json
import sys

from .artifacts import (
    OciArtifactError,
    build_publication_receipt,
    prepare_package_artifact,
    stage_package_artifact,
    validate_target_matrix,
    validate_version,
    verify_package_artifact,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare and verify immutable package metadata for OCI artifacts."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="describe one package archive for OCI publication")
    prepare.add_argument("--artifact", required=True, help="path or glob that must resolve to exactly one regular file")
    prepare.add_argument("--output-directory", default=".pipeline/oci")
    prepare.add_argument("--package-name", required=True)
    prepare.add_argument("--component-id", required=True)
    prepare.add_argument("--variant", default="default")
    prepare.add_argument("--version", required=True)
    prepare.add_argument("--source-repository", required=True)
    prepare.add_argument("--source-revision", required=True)
    prepare.add_argument("--target-id", required=True)
    prepare.add_argument("--target-os", required=True)
    prepare.add_argument("--architecture", required=True)
    prepare.add_argument("--abi", required=True)
    prepare.add_argument("--media-type", default="application/vnd.pipeline.package.layer.v1.tar+gzip")

    verify = commands.add_parser("verify", help="verify one package file against its metadata")
    verify.add_argument("--metadata", required=True)
    verify.add_argument("--artifact", required=True)

    stage = commands.add_parser("stage", help="copy and re-verify immutable package bytes")
    stage.add_argument("--metadata", required=True)
    stage.add_argument("--artifact", required=True)
    stage.add_argument("--output-directory", required=True)
    stage.add_argument("--expected-metadata-sha256", required=True)

    matrix = commands.add_parser("validate-matrix", help="validate a JSON target matrix")
    matrix.add_argument("--value", required=True)

    version = commands.add_parser("validate-version", help="validate a SemVer package version")
    version.add_argument("--value", required=True)

    receipt = commands.add_parser("receipt", help="bind an ORAS result to a package digest")
    receipt.add_argument("--metadata", required=True)
    receipt.add_argument("--push-result", required=True)
    receipt.add_argument("--registry", default="ghcr.io")
    receipt.add_argument("--owner", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_package_artifact(
                artifact_pattern=args.artifact,
                output_directory=args.output_directory,
                package_name=args.package_name,
                component_id=args.component_id,
                variant=args.variant,
                version=args.version,
                source_repository=args.source_repository,
                source_revision=args.source_revision,
                target_id=args.target_id,
                target_os=args.target_os,
                architecture=args.architecture,
                abi=args.abi,
                media_type=args.media_type,
            )
        elif args.command == "verify":
            result = verify_package_artifact(args.metadata, args.artifact)
        elif args.command == "stage":
            result = stage_package_artifact(
                metadata_path=args.metadata,
                artifact_path=args.artifact,
                output_directory=args.output_directory,
                expected_metadata_sha256=args.expected_metadata_sha256,
            )
        elif args.command == "validate-matrix":
            result = {"targets": validate_target_matrix(args.value)}
        elif args.command == "validate-version":
            result = {"version": validate_version(args.value), "valid": True}
        else:
            result = build_publication_receipt(
                metadata_path=args.metadata,
                push_result_path=args.push_result,
                registry=args.registry,
                owner=args.owner,
            )
    except (OciArtifactError, OSError) as exc:
        print(f"OCI package validation failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
