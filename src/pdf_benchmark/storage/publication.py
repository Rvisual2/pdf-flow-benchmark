"""Select explicit public artifacts and record their source and conversion provenance."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..provenance import repository_provenance
from .transfer import (
    BucketPublisher,
    digest,
    download_file,
    json_bytes,
    read_manifest,
    validated_targets,
)

# Provider response bodies and free-form logs are deliberately not publication inputs.
CONFIG_FIELDS = {
    "model",
    "gateway",
    "pdf_engine",
    "prompt_sha256",
    "api",
    "tier",
    "parser_version",
    "sdk_version",
    "mode",
    "skip_cache",
    "disable_cache",
    "execution",
    "concurrency",
    "queue",
    "chunk_mode",
    "table_output_format",
    "device",
    "workers",
    "threads",
    "batch_size",
    "page_batch_size",
    "ocr",
    "tables",
    "layout",
    "persistent",
    "streaming",
}
RECORD_FIELDS = {
    "success",
    "status",
    "timestamp",
    "duration",
    "duration_seconds",
    "model",
    "provider",
    "service",
    "pages",
    "pages_processed",
    "polls_required",
    "attempts",
    "request_id",
    "job_id",
    "batch_id",
    "generation_id",
    "credits_used",
    "input_tokens",
    "output_tokens",
    "estimated_cost_usd",
    "source_sha256",
    "docling_version",
    "torch_version",
    "pymupdf4llm_version",
    "pymupdf_layout_version",
    "pymupdf_version",
    "reducto_version",
    "batch_wall_seconds",
    "server_runtime",
}


def clean_record(record: dict) -> dict:
    cleaned = {name: value for name, value in record.items() if name in RECORD_FIELDS}
    if record.get("file"):
        cleaned["file"] = Path(record["file"]).name
    if record.get("markdown_file"):
        cleaned["markdown_file"] = "markdowns/" + Path(record["markdown_file"]).name
    if "config" in record:
        cleaned["config"] = {
            key: value for key, value in record["config"].items() if key in CONFIG_FIELDS
        }
    return cleaned


def dataset_files(directory: Path) -> list[tuple[str, bytes, dict]]:
    paths = list((directory / "pdfs").glob("*.pdf"))
    paths += list((directory / "ground_truth/annotated_pdfs").glob("*.pdf"))
    paths += [
        directory / name
        for name in ("ground_truth/references.json", "ground_truth/ocr.xlsx", "page_categories.csv")
    ]
    if not any(path.parent == directory / "pdfs" for path in paths):
        raise ValueError(f"No input PDFs found in {directory / 'pdfs'}")
    return [
        (path.relative_to(directory).as_posix(), path.read_bytes(), {}) for path in sorted(paths)
    ]


def result_files(directory: Path, input_directory: Path) -> list[tuple[str, bytes, dict]]:
    markdowns = sorted(directory.rglob("markdowns/page_*.md"))
    if not markdowns:
        raise ValueError(f"No markdowns/page_*.md files under {directory}")
    artifacts = []
    for run_directory in sorted({path.parent.parent for path in markdowns}):
        records = []
        record_path = run_directory / "results.jsonl"
        if record_path.is_file():
            records = [
                clean_record(json.loads(line))
                for line in record_path.read_text().splitlines()
                if line.strip()
            ]
            content = b"".join(
                json_bytes(record).replace(b"\n", b" ").rstrip() + b"\n" for record in records
            )
            artifacts.append((record_path.relative_to(directory).as_posix(), content, {}))
        summary_path = run_directory / "run.json"
        if summary_path.is_file():
            summary = json.loads(summary_path.read_text())
            summary = {
                key: value
                for key, value in summary.items()
                if key in {"timestamp", "total", "failed", "wall_seconds", "config", "provenance"}
            }
            summary["config"] = {
                key: value
                for key, value in summary.get("config", {}).items()
                if key in CONFIG_FIELDS
            }
            artifacts.append(
                (summary_path.relative_to(directory).as_posix(), json_bytes(summary), {})
            )
        for path in (run_directory / "markdowns").glob("page_*.md"):
            source = input_directory / (path.stem + ".pdf")
            if not source.is_file():
                raise ValueError(f"Missing source PDF needed for provenance: {source}")
            source_hash = digest(source.read_bytes())
            matching = [
                record for record in records if Path(record.get("file", "")).stem == path.stem
            ]
            # Older runners did not hash inputs during conversion: label this explicitly.
            recorded_hash = matching[-1].get("source_sha256") if matching else None
            if recorded_hash and recorded_hash != source_hash:
                raise ValueError(f"Source PDF has changed since conversion: {source.name}")
            provenance = {
                "input_file": source.name,
                "input_sha256": source_hash,
                "input_hash_origin": "conversion" if recorded_hash else "publication_time",
                "conversion_records": matching,
            }
            artifacts.append(
                (path.relative_to(directory).as_posix(), path.read_bytes(), provenance)
            )
    return artifacts


def publish(
    kind: str,
    directory: Path,
    publisher: BucketPublisher,
    *,
    input_directory: Path,
    label: str,
    workers: int,
    receipt: Path,
) -> dict:
    artifacts = (
        dataset_files(directory) if kind == "dataset" else result_files(directory, input_directory)
    )

    def upload(item: tuple[str, bytes, dict]) -> dict:
        path, content, provenance = item
        return {
            "path": path,
            **publisher.upload(Path(path).name, content),
            **({"provenance": provenance} if provenance else {}),
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        entries = list(pool.map(upload, artifacts))
    manifest = {
        "schema_version": 1,
        "kind": kind,
        "label": label,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "publication_code": repository_provenance(),
        "files": sorted(entries, key=lambda entry: entry["path"]),
    }
    reference = publisher.upload("manifest.json", json_bytes(manifest))
    result = {
        "schema_version": 1,
        "kind": kind,
        "label": label,
        "files": len(entries),
        "manifest": reference,
    }
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_bytes(json_bytes(result))
    print(f"Published {len(entries)} files. Manifest: {reference['url']}\nReceipt: {receipt}")
    return result


def download(
    reference: dict | str,
    directory: Path,
    client: httpx.Client,
    *,
    kind: str,
    workers: int = 8,
    overwrite: bool = False,
) -> dict:
    manifest = read_manifest(reference, client)
    if manifest["kind"] != kind:
        raise ValueError(f"Expected {kind} manifest, got {manifest['kind']}")
    targets = validated_targets(manifest, directory)
    # Refuse conflicting local changes before writing any files.
    for entry, target in targets:
        if (
            target.exists()
            and (not target.is_file() or digest(target.read_bytes()) != entry["sha256"])
            and not overwrite
        ):
            raise ValueError(
                f"Local file differs: {target}. Choose another directory or use --overwrite."
            )
    with ThreadPoolExecutor(max_workers=workers) as pool:
        downloaded = sum(pool.map(lambda item: download_file(*item, client), targets))
    print(
        f"Verified {len(targets)} files; downloaded {downloaded}, reused {len(targets) - downloaded}.\nSaved to: {directory}"
    )
    return manifest
