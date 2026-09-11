"""Small PDF cover images, with source hashes and immutable cloud publication."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .files import DATA_DIRECTORY, ROOT, positive_int
from .storage.cli import catalog
from .storage.transfer import BucketPublisher, digest, json_bytes, read_manifest


def generate_thumbnails(
    input_directory: Path,
    output_directory: Path,
    client: httpx.Client,
    long_edge: int = 320,
    quality: int = 70,
    publisher: BucketPublisher | None = None,
) -> dict:
    import pymupdf

    dataset_reference = catalog()["dataset"]
    dataset = read_manifest(dataset_reference, client)
    inputs = [entry for entry in dataset["files"] if entry["path"].startswith("pdfs/")]
    output_directory.mkdir(parents=True, exist_ok=True)
    images = []
    for entry in inputs:
        source = input_directory / Path(entry["path"]).name
        source_bytes = source.read_bytes()
        if digest(source_bytes) != entry["sha256"]:
            raise ValueError(f"PDF does not match the published dataset: {source.name}")
        with pymupdf.open(stream=source_bytes, filetype="pdf") as document:
            page = document[0]
            scale = (long_edge - 1) / max(page.rect.width, page.rect.height)
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False
            )
            content = pixmap.tobytes("jpeg", jpg_quality=quality)
            name = f"{source.stem}.jpg"
            (output_directory / name).write_bytes(content)
            reference = (
                publisher.upload(name, content)
                if publisher
                else {
                    "sha256": digest(content),
                    "size": len(content),
                }
            )
            images.append(
                {
                    **reference,
                    "path": name,
                    "source_sha256": entry["sha256"],
                    "source_file": source.name,
                    "pdf_page": 1,
                    "page_count": document.page_count,
                    "width": pixmap.width,
                    "height": pixmap.height,
                }
            )
    manifest = {
        "schema_version": 1,
        "kind": "thumbnails",
        "files": images,
        "dataset": dataset_reference,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "renderer": {
            "name": "PyMuPDF",
            "version": pymupdf.VersionBind,
            "long_edge": long_edge,
            "jpeg_quality": quality,
        },
    }
    (output_directory / "manifest.json").write_bytes(json_bytes(manifest))
    return manifest


def main(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="pdf-benchmark dashboard thumbnails",
        description="Generate low-resolution PDF thumbnails",
    )
    parser.add_argument("--input-dir", type=Path, default=DATA_DIRECTORY / "pdfs")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/runs/thumbnails")
    parser.add_argument("--long-edge", type=positive_int, default=320)
    parser.add_argument("--quality", type=int, choices=range(1, 101), metavar="1-100", default=70)
    parser.add_argument(
        "--publish", action="store_true", help="Upload thumbnails and update the catalog"
    )
    parser.add_argument("--bucket", help="Override the configured thumbnail bucket")
    parser.add_argument("--account")
    options = parser.parse_args(arguments)
    if not 32 <= options.long_edge <= 1024:
        parser.error("--long-edge must be between 32 and 1024 pixels for thumbnails")
    try:
        configuration = catalog()
        with httpx.Client(timeout=120) as client:
            publisher = None
            if options.publish:
                bucket = options.bucket or configuration.get("thumbnail_bucket")
                if not bucket:
                    raise ValueError("Provide --bucket when first publishing thumbnails")
                publisher = BucketPublisher.from_gcloud(bucket, client, options.account)
            manifest = generate_thumbnails(
                options.input_dir,
                options.output_dir,
                client,
                options.long_edge,
                options.quality,
                publisher,
            )
            if publisher:
                reference = publisher.upload("thumbnails.json", json_bytes(manifest))
                configuration.update(thumbnail_bucket=publisher.bucket, thumbnails=reference)
                (ROOT / "src/pdf_benchmark/resources/artifacts.json").write_bytes(
                    json_bytes(configuration)
                )
            total_bytes = sum(image["size"] for image in manifest["files"])
            print(
                f"Generated {len(manifest['files'])} thumbnails, {total_bytes / 1024:.1f} KB total"
            )
            if publisher:
                print(f"Published to gs://{publisher.bucket}; catalog updated")
        return 0
    except (OSError, ValueError, KeyError, httpx.HTTPError) as error:
        parser.exit(1, f"Thumbnail generation failed: {error}\n")
