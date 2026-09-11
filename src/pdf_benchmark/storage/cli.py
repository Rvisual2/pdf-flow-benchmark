"""Artifact publication and download commands for the data/results groups."""

import argparse
import json
from importlib.resources import files
from pathlib import Path

from ..files import DATA_DIRECTORY, RUNS_DIRECTORY, positive_int


def catalog() -> dict:
    return json.loads(files("pdf_benchmark").joinpath("resources/artifacts.json").read_text())


def add_commands(commands, group: str) -> None:
    upload = commands.add_parser(
        "upload", help="Publish immutable files and provenance (owner login required)"
    )
    if group == "results":
        upload.add_argument(
            "directory", type=Path, help="A conversion directory or collection of runs"
        )
        upload.add_argument(
            "--input-dir",
            type=Path,
            default=DATA_DIRECTORY / "pdfs",
            help="Source PDFs for provenance hashes",
        )
    else:
        upload.add_argument("--directory", type=Path, default=DATA_DIRECTORY)
    upload.add_argument("--label", required=True, help="Descriptive release or experiment name")
    upload.add_argument("--bucket", help="Override the configured bucket name")
    upload.add_argument("--account", help="gcloud account to use for publication")
    upload.add_argument("--receipt", type=Path, help="Write the public manifest pointer here")
    upload.add_argument(
        "--workers", type=positive_int, default=8, help="Concurrent file transfers (default: 8)"
    )
    download = commands.add_parser(
        "download", help="Download a known release without login or bucket listing"
    )
    if group == "results":
        selection = download.add_mutually_exclusive_group(required=True)
        selection.add_argument("--release", help="Published release name (see results releases)")
        selection.add_argument("--manifest", help="Manifest URL or local upload receipt")
        download.add_argument(
            "--directory", type=Path, required=True, help="Destination run directory"
        )
        releases = commands.add_parser(
            "releases", help="List published release manifests without listing the bucket"
        )
        releases.add_argument("--json", action="store_true")
    else:
        download.add_argument("--manifest", help="Manifest URL or local upload receipt")
        download.add_argument("--directory", type=Path, default=DATA_DIRECTORY)
    download.add_argument(
        "--overwrite", action="store_true", help="Replace local files with different hashes"
    )
    download.add_argument("--workers", type=positive_int, default=8)


def _run(options: argparse.Namespace) -> int:
    import httpx

    from .publication import download, publish
    from .transfer import BucketPublisher

    kind = "dataset" if options.command == "data" else "results"
    configuration = catalog()
    if options.action == "releases":
        from ..inspection import print_json, print_table

        releases = configuration.get("releases", {})
        if options.json:
            print_json(releases)
        else:
            print_table(
                ["Release", "Manifest URL"],
                [[name, reference["url"]] for name, reference in releases.items()],
            )
        return 0
    with httpx.Client(timeout=120, follow_redirects=False) as client:
        if options.action == "download":
            reference = options.manifest or (
                configuration.get("dataset")
                if kind == "dataset"
                else configuration.get("releases", {}).get(options.release)
            )
            if not reference:
                raise ValueError(
                    "No default release configured. Supply --manifest URL or receipt.json."
                )
            download(
                reference,
                options.directory,
                client,
                kind=kind,
                workers=options.workers,
                overwrite=options.overwrite,
            )
        else:
            publisher = BucketPublisher.from_gcloud(
                options.bucket or configuration["bucket"], client, options.account
            )
            receipt = options.receipt or RUNS_DIRECTORY / "publications" / f"{kind}.json"
            publish(
                kind,
                options.directory,
                publisher,
                input_directory=getattr(options, "input_dir", DATA_DIRECTORY / "pdfs"),
                label=options.label,
                workers=options.workers,
                receipt=receipt,
            )
    return 0


def run(options: argparse.Namespace) -> int:
    import httpx

    try:
        return _run(options)
    except httpx.HTTPError as error:
        raise ValueError(f"Cloud transfer failed: {error}") from error
