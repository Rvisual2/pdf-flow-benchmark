"""Evaluation CLI and orchestration; extraction and scoring stay independently usable."""

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from ..files import BASELINE_DIRECTORY, DATA_DIRECTORY, RUNS_DIRECTORY
from .ground_truth import legacy_cleaned_data, read_ground_truth, write_ground_truth
from .scoring import (
    MarkdownSource,
    analyze_results,
    generate_raw_scores,
    simple_scores,
    validate_sources,
)

DEFAULT_SOURCES = [
    MarkdownSource("reducto", BASELINE_DIRECTORY / "reducto/markdowns"),
    MarkdownSource("datalab", BASELINE_DIRECTORY / "datalab/markdowns"),
    MarkdownSource("gemini", BASELINE_DIRECTORY / "gemini/markdowns"),
    MarkdownSource("llama_parse", BASELINE_DIRECTORY / "llamaparse/markdowns"),
    MarkdownSource("pymupdf4llm", BASELINE_DIRECTORY / "pymupdf4llm/markdowns"),
    MarkdownSource("docling_cpu_without_ocr", BASELINE_DIRECTORY / "docling/no_ocr/markdowns"),
    MarkdownSource("docling_cpu_with_ocr", BASELINE_DIRECTORY / "docling/ocr/markdowns"),
]
OUTPUT_FILES = {
    "annotations_output": "annotations.json",
    "combined_output": "combined.json",
    "cleaned_output": "cleaned.json",
    "ground_truth_output": "ground_truth.json",
    "benchmark_output": "scores_by_category.csv",
    "granular_output": "granular.csv",
    "filtered_output": "filtered.csv",
}


def source_argument(value: str) -> MarkdownSource:
    name, separator, directory = value.partition("=")
    if not separator or not name.strip() or not directory:
        raise argparse.ArgumentTypeError("use NAME=DIRECTORY")
    return MarkdownSource(name, Path(directory))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-benchmark evaluate",
        description="Score Markdown against reference snippets. Defaults to the committed baseline.",
        epilog="Example: pdf-benchmark evaluate --markdown-source reducto=results/runs/reducto/markdowns --output-dir results/runs/evaluation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--pdf-path", type=Path, default=DATA_DIRECTORY / "ground_truth/annotated_pdfs"
    )
    parser.add_argument("--excel-path", type=Path, default=DATA_DIRECTORY / "ground_truth/ocr.xlsx")
    parser.add_argument("--page-mapping", type=Path, default=DATA_DIRECTORY / "page_categories.csv")
    reference_options = parser.add_mutually_exclusive_group()
    reference_options.add_argument(
        "--ground-truth-input",
        type=Path,
        help="Versioned JSON; defaults to data/ground_truth/references.json",
    )
    reference_options.add_argument(
        "--rebuild-ground-truth",
        action="store_true",
        help="Extract reference snippets from the annotated PDFs and OCR workbook",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=RUNS_DIRECTORY / "evaluation",
        help="Report directory (default: results/runs/evaluation)",
    )
    for name in OUTPUT_FILES:
        parser.add_argument("--" + name.replace("_", "-"), type=Path)
    parser.add_argument(
        "--scores-output",
        type=Path,
        help="Simple tool/score CSV; defaults to output-dir/scores.csv",
    )
    parser.add_argument(
        "--markdown-source",
        action="append",
        type=source_argument,
        metavar="NAME=DIRECTORY",
        help="Select a Markdown directory; repeat to compare parsers",
    )
    parser.add_argument(
        "--min-score-threshold",
        type=float,
        default=0.25,
        help="Retain snippets where at least one distance is below this value",
    )
    parser.add_argument(
        "--excluded-folders", nargs="+", default=["test"], help="Categories to exclude"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main(arguments: list[str] | None = None) -> int:
    parser = build_parser()
    options = parser.parse_args(arguments)
    logging.basicConfig(
        level=logging.DEBUG if options.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)
    try:
        if not 0 < options.min_score_threshold <= 1:
            raise ValueError("Score threshold must be greater than zero and at most one")
        sources = options.markdown_source or DEFAULT_SOURCES
        validate_sources(sources)
        outputs = {
            name: getattr(options, name) or options.output_dir / filename
            for name, filename in OUTPUT_FILES.items()
        }
        scores_path = options.scores_output or options.output_dir / "scores.csv"
        for path in [*outputs.values(), *([scores_path] if scores_path else [])]:
            path.parent.mkdir(parents=True, exist_ok=True)
        if not options.rebuild_ground_truth:
            reference_path = (
                options.ground_truth_input or DATA_DIRECTORY / "ground_truth/references.json"
            )
            pages = read_ground_truth(reference_path)
        else:
            from .sources import build_reference_pages, combine_sources, extract_annotations

            annotations = extract_annotations(options.pdf_path)
            combined = combine_sources(annotations, options.excel_path)
            pages = build_reference_pages(combined)
            write_json(outputs["annotations_output"], annotations)
            write_json(outputs["combined_output"], combined)
        write_json(outputs["cleaned_output"], legacy_cleaned_data(pages))
        write_ground_truth(outputs["ground_truth_output"], pages)
        raw_scores = generate_raw_scores(pages, sources)
        reports = analyze_results(
            raw_scores,
            pd.read_csv(options.page_mapping),
            [source.name for source in sources],
            options.min_score_threshold,
            tuple(options.excluded_folders),
        )
        reports.granular.to_csv(outputs["granular_output"], index=False)
        reports.filtered.to_csv(outputs["filtered_output"], index=False)
        if reports.summary.empty:
            outputs["benchmark_output"].unlink(missing_ok=True)
            if scores_path:
                scores_path.unlink(missing_ok=True)
            raise ValueError("No scored snippets remain after filtering")
        reports.summary.to_csv(outputs["benchmark_output"])
        if scores_path:
            simple_scores(reports.summary).to_csv(scores_path, index=False, float_format="%.2f")
        logger.info(
            "Scored %s snippets across %s pages",
            len(reports.filtered),
            reports.filtered.page_number.nunique(),
        )
        logger.info("Saved benchmark results: %s", outputs["benchmark_output"])
        return 0
    except (OSError, ValueError, KeyError) as error:
        logger.error("Evaluation failed: %s", error, exc_info=options.verbose)
        return 1
