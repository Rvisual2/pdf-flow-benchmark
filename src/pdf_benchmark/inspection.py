"""Read-only discovery of parsers, reference data, and saved results."""

import csv
import json
import os
from collections import Counter
from pathlib import Path

from .files import ROOT, RUNS_DIRECTORY
from .registry import PARSERS


def print_table(headers: list[str], rows: list[list[object]]) -> None:
    values = [["—" if value is None else str(value) for value in row] for row in rows]
    widths = [
        max([len(header), *(len(row[index]) for row in values)])
        for index, header in enumerate(headers)
    ]
    for row in [headers, ["-" * width for width in widths], *values]:
        print("  ".join(value.ljust(width) for value, width in zip(row, widths)).rstrip())


def print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def parser_details(name: str) -> dict:
    from dotenv import dotenv_values

    spec = PARSERS[name]
    configured = None
    if spec.api_key:
        value = os.environ.get(spec.api_key)
        if value is None:
            value = dotenv_values(ROOT / ".env").get(spec.api_key)
        configured = bool(value)
    return {
        "name": name,
        "description": spec.description,
        "service": "paid" if spec.api_key else "local",
        "credential_variable": spec.api_key,
        "credential_configured": configured,
        "output_directory": str(RUNS_DIRECTORY / spec.output_directory),
        "options_command": f"pdf-benchmark convert {name} --help",
    }


def list_parsers(as_json: bool = False) -> int:
    records = [parser_details(name) for name in PARSERS]
    if as_json:
        print_json(records)
    else:
        print_table(
            ["Parser", "Service", "Credential", "Description"],
            [
                [
                    record["name"],
                    record["service"],
                    "not needed"
                    if record["service"] == "local"
                    else "configured"
                    if record["credential_configured"]
                    else "missing",
                    record["description"],
                ]
                for record in records
            ],
        )
        print("\nConfigured means a key is present; no API request is made.")
        print("Next: pdf-benchmark parsers show <name>")
    return 0


def show_parser(name: str, as_json: bool = False) -> int:
    record = parser_details(name)
    if as_json:
        print_json(record)
    else:
        print(record["description"])
        print(f"Default output: {record['output_directory']}")
        if record["credential_variable"]:
            status = "configured (not verified)" if record["credential_configured"] else "missing"
            print(f"Credential: {record['credential_variable']} — {status}")
        from .cli import conversion_parser

        print()
        conversion_parser(name).print_help()
    return 0


def inspect_data(directory: Path, page_number: int | None = None, as_json: bool = False) -> int:
    from .evaluation.ground_truth import read_ground_truth

    pages = read_ground_truth(directory / "ground_truth/references.json")
    with (directory / "page_categories.csv").open(encoding="utf-8", newline="") as stream:
        mapping = {int(row["Page"]): row["Folder"] for row in csv.DictReader(stream)}
    if page_number is not None:
        page = next((page for page in pages if page.page_number == page_number), None)
        if page is None:
            raise ValueError(
                f"No reference snippets for page {page_number}. Use 'data show' to inspect the dataset."
            )
        from dataclasses import asdict

        record = {
            **asdict(page),
            "category": mapping.get(page_number),
            "pdf": str(directory / "pdfs" / f"page_{page_number}.pdf"),
        }
        if as_json:
            print_json(record)
        else:
            print(
                f"Page {page_number} — {record['category'] or 'uncategorized'}\nPDF: {record['pdf']}"
            )
            for snippet in page.snippets:
                print(f"\n[{snippet.id}] {snippet.text}")
        return 0
    pdf_count = sum(
        path.is_file() and path.suffix.lower() == ".pdf" for path in (directory / "pdfs").iterdir()
    )
    categories = Counter(mapping.get(page.page_number, "uncategorized") for page in pages)
    record = {
        "directory": str(directory),
        "pdfs": pdf_count,
        "reference_pages": len(pages),
        "snippets": sum(len(page.snippets) for page in pages),
        "categories": dict(sorted(categories.items())),
    }
    if as_json:
        print_json(record)
    else:
        print(
            f"Dataset: {directory}\nPDFs: {pdf_count}  Reference pages: {len(pages)}  Snippets: {record['snippets']}"
        )
        print_table(
            ["Category", "Reference pages"],
            [[name, count] for name, count in sorted(categories.items())],
        )
        print(
            "\nCounts are before evaluation filters. Inspect text with: pdf-benchmark data page <number>"
        )
    return 0


def list_results(directory: Path, limit: int, as_json: bool = False) -> int:
    if not directory.is_dir():
        raise ValueError(f"Results directory does not exist: {directory}")
    files = set(directory.rglob("run.json")) | set(directory.rglob("scores.csv"))
    files |= {
        path
        for path in directory.rglob("scores_by_category.csv")
        if not (path.parent / "scores.csv").exists()
    }
    records = []
    for path in sorted(files, key=lambda path: (path.stat().st_mtime, str(path)), reverse=True)[
        :limit
    ]:
        record = {
            "directory": str(path.parent),
            "kind": "conversion" if path.name == "run.json" else "evaluation",
        }
        if path.name == "run.json":
            try:
                summary = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(summary, dict):
                    raise ValueError("Expected a JSON object")
                record.update(
                    total=summary.get("total"),
                    failed=summary.get("failed"),
                    timestamp=summary.get("timestamp"),
                )
            except ValueError:
                record.update(kind="invalid", error="Invalid run.json")
        records.append(record)
    if as_json:
        print_json(records)
    elif records:
        print_table(
            ["Kind", "Documents", "Failed", "Directory"],
            [
                [
                    record["kind"],
                    record.get("total"),
                    record.get("failed", "—"),
                    record["directory"],
                ]
                for record in records
            ],
        )
        print(f"\nShowing {len(records)} of {len(files)} saved records, newest files first.")
        print("Next: pdf-benchmark results show <directory>")
    else:
        print("No saved results found. Start with: pdf-benchmark convert <parser>")
    return 0


def read_scores(path: Path) -> list[dict]:
    if path.is_dir():
        path = next(
            (
                path / name
                for name in ("scores.csv", "scores_by_category.csv")
                if (path / name).is_file()
            ),
            path / "scores.csv",
        )
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if rows and {"tool", "score_percent"}.issubset(rows[0]):
        return [{"tool": row["tool"], "score_percent": float(row["score_percent"])} for row in rows]
    weighted = next(
        (
            row
            for row in rows
            if row.get("") == "Weighted_Mean" or row.get("Folder") == "Weighted_Mean"
        ),
        None,
    )
    if weighted is None:
        raise ValueError(f"No tool scores or Weighted_Mean row in {path}")
    return [
        {"tool": name, "score_percent": float(value)}
        for name, value in weighted.items()
        if name not in {"", "Folder", "Folder_Count"}
    ]


def show_scores(path: Path, as_json: bool = False) -> int:
    scores = sorted(read_scores(path), key=lambda row: row["score_percent"], reverse=True)
    if as_json:
        print_json(scores)
    else:
        print_table(
            ["Tool", "FATA (%)"],
            [[score["tool"], f"{score['score_percent']:.2f}"] for score in scores],
        )
    return 0


def show_result(directory: Path, as_json: bool = False) -> int:
    summary_path = directory / "run.json"
    if not summary_path.is_file():
        return show_scores(directory, as_json)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError(f"Expected a JSON object in {summary_path}")
    if as_json:
        print_json(summary)
    else:
        print(f"Run: {directory}")
        print(
            f"Documents: {summary.get('total', 'unknown')}  Failed: {summary.get('failed', 'unknown')}  Seconds: {summary.get('wall_seconds', 'unknown')}"
        )
        print("Configuration:")
        print_json(summary.get("config", {}))
        print(
            f"Markdown: {directory / 'markdowns'}\nPer-document details: {directory / 'results.jsonl'}"
        )
    return 0
