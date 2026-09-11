"""Export scored evidence and public artifact links for the read-only dashboard."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

from .files import DATA_DIRECTORY, ROOT
from .storage.cli import catalog
from .storage.transfer import BucketPublisher, digest, json_bytes, read_manifest

LABELS = {
    "gemini": ("Gemini 3.8 Flash", "OpenRouter", "LLM"),
    "reducto": ("Reducto r-1", "Reducto", "API"),
    "datalab": ("Datalab Accurate", "Datalab", "API"),
    "llamaparse": ("LlamaParse Agentic", "LlamaParse", "API"),
    "docling_ocr": ("Docling · OCR", "Docling", "Local"),
    "docling_no_ocr": ("Docling · no OCR", "Docling", "Local"),
    "pymupdf4llm": ("PyMuPDF4LLM", "PyMuPDF", "Local"),
}
CATEGORY_NAMES = {
    "finance_samples": "Finance",
    "govt tenders": "Government",
    "laws_sample": "Law",
    "manuals_sample": "Manuals",
    "patents": "Patents",
    "science_sample": "Science",
    "test": "Test set",
}


def export_dashboard(evaluation: Path, run: Path, release: str, client: httpx.Client) -> dict:
    configuration = catalog()
    dataset = read_manifest(configuration["dataset"], client)
    thumbnails = {}
    if configuration.get("thumbnails"):
        thumbnail_manifest = read_manifest(configuration["thumbnails"], client)
        if thumbnail_manifest["kind"] != "thumbnails":
            raise ValueError("Expected a thumbnail manifest")
        thumbnails = {entry["source_sha256"]: entry for entry in thumbnail_manifest["files"]}
    result_manifest = read_manifest(configuration["releases"][release], client)
    entries = {entry["path"]: entry for entry in result_manifest["files"]}
    pdfs = {
        int(Path(entry["path"]).stem.removeprefix("page_")): entry
        for entry in dataset["files"]
        if entry["path"].startswith("pdfs/")
    }
    mapping = pd.read_csv(DATA_DIRECTORY / "page_categories.csv")
    categories = dict(zip(mapping.Page, mapping.Folder))
    granular = pd.read_csv(evaluation / "granular.csv", keep_default_na=False)
    filtered = pd.read_csv(evaluation / "filtered.csv", keep_default_na=False)
    summary = pd.read_csv(evaluation / "scores_by_category.csv", index_col=0)
    provider_ids = [name for name in summary.columns if name != "Folder_Count"]
    retained = {(int(row.page_number), int(row.needle_index)) for row in filtered.itertuples()}
    if not retained or len(retained) != len(filtered):
        raise ValueError("Evaluation must contain unique, retained reference snippets")
    providers = []
    for name in provider_ids:
        if (
            abs(float(summary.loc["Weighted_Mean", name]) - (1 - filtered[name].mean()) * 100)
            > 0.011
        ):
            raise ValueError(f"Summary and filtered scores disagree for {name}")
        display, vendor, service = LABELS.get(
            name, (name.replace("_", " ").title(), name, "Unknown")
        )
        metadata_path = run / name / "run.json"
        metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
        providers.append(
            {
                "id": name,
                "name": display,
                "vendor": vendor,
                "service": service,
                "score": float(summary.loc["Weighted_Mean", name]),
                "config": metadata.get("config", {}),
                "wallSeconds": metadata.get("wall_seconds"),
                "failed": metadata.get("failed"),
                "categories": {
                    key: float(summary.loc[key, name])
                    for key in summary.index
                    if key != "Weighted_Mean"
                },
            }
        )
    documents = []
    for number, pdf in sorted(pdfs.items()):
        rows = granular[granular.page_number == number]
        kept = filtered[filtered.page_number == number]
        outputs = {}
        for name in provider_ids:
            path = f"{name}/markdowns/page_{number}.md"
            if path in entries:
                entry = entries[path]
                local = run / path
                if not local.is_file() or digest(local.read_bytes()) != entry["sha256"]:
                    raise ValueError(f"Local output does not match the published release: {path}")
                provenance = entry.get("provenance", {})
                if provenance.get("input_sha256") not in (None, pdf["sha256"]):
                    raise ValueError(f"Output provenance refers to a different PDF: {path}")
                outputs[name] = {
                    **{key: entry[key] for key in ("url", "sha256", "size")},
                    "provenance": provenance,
                }
        scores = {
            name: float((1 - kept[name].astype(float).mean()) * 100) if len(kept) else None
            for name in provider_ids
        }
        snippets = [
            {
                "index": int(row["needle_index"]),
                "text": row["needle"],
                "ocr": bool(row["OCR"]),
                "retained": (number, int(row["needle_index"])) in retained,
                "matches": {
                    name: {"distance": float(row[name]), "text": row[f"{name}_best_match"]}
                    for name in provider_ids
                },
            }
            for row in rows.to_dict("records")
        ]
        documents.append(
            {
                "page": number,
                "category": categories.get(number, "unmapped"),
                "pdf": {key: pdf[key] for key in ("url", "sha256", "size")},
                "outputs": outputs,
                "thumbnail": thumbnails.get(pdf["sha256"]),
                "scores": scores,
                "snippets": snippets,
                "scoredSnippets": len(kept),
            }
        )
    if any(len(document["outputs"]) != len(providers) for document in documents):
        raise ValueError(
            "The selected release does not contain matching outputs for every PDF/provider"
        )
    return {
        "schemaVersion": 1,
        "release": release,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "datasetManifest": configuration["dataset"],
        "resultManifest": configuration["releases"][release],
        "providers": providers,
        "documents": documents,
        "categories": CATEGORY_NAMES,
        "scoredDocuments": int(filtered.page_number.nunique()),
        "scoredSnippets": len(filtered),
        "methodology": "FATA measures character similarity within coherent reading-flow snippets. Scores use the same retained snippets for every parser; test pages and rows missing any parser are excluded. A snippet is retained when at least one parser has distance below 0.25. Rendered HTML is a viewing aid; the evaluator scores original Markdown. Ground truth contains known extraction errors.",
    }


def main(arguments: list[str] | None = None) -> int:
    if arguments and arguments[0] == "thumbnails":
        from .thumbnails import main as thumbnails_main

        return thumbnails_main(arguments[1:])
    parser = argparse.ArgumentParser(
        prog="pdf-benchmark dashboard",
        description="Export verified report data for the React dashboard",
    )
    commands = parser.add_subparsers(dest="action")
    commands.add_parser("thumbnails", help="Generate and publish small PDF cover images")
    export = commands.add_parser(
        "export", help="Build a dashboard snapshot from evaluation reports and published artifacts"
    )
    export.add_argument("--evaluation-dir", type=Path, required=True)
    export.add_argument("--run-dir", type=Path, required=True)
    export.add_argument("--release", default="all-tools-2026-09-10")
    export.add_argument(
        "--output", type=Path, default=ROOT / "results/runs/dashboard/benchmark.json"
    )
    export.add_argument(
        "--publish",
        action="store_true",
        help="Upload the snapshot and update the dashboard's public data pointer",
    )
    export.add_argument("--account")
    options = parser.parse_args(arguments)
    if options.action is None:
        parser.print_help()
        return 0
    try:
        with httpx.Client(timeout=120) as client:
            snapshot = export_dashboard(
                options.evaluation_dir, options.run_dir, options.release, client
            )
            content = json_bytes(snapshot)
            options.output.parent.mkdir(parents=True, exist_ok=True)
            options.output.write_bytes(content)
            print(
                f"Exported {len(snapshot['documents'])} PDFs, {len(snapshot['providers'])} parsers, {snapshot['scoredSnippets']} scored snippets"
            )
            if options.publish:
                publisher = BucketPublisher.from_gcloud(
                    catalog()["bucket"], client, options.account
                )
                reference = publisher.upload("dashboard.json", content)
                target = ROOT / "apps/dashboard/public/data-source.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(json_bytes(reference))
                print(f"Published dashboard snapshot: {reference['url']}")
        return 0
    except (OSError, ValueError, KeyError, httpx.HTTPError) as error:
        parser.exit(1, f"Dashboard export failed: {error}\n")
