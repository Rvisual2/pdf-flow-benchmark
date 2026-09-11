"""Evaluation CLI and orchestration; extraction and scoring stay independently usable."""

import argparse
import logging
from pathlib import Path

import pandas as pd

from ..files import DATA_DIRECTORY, RUNS_DIRECTORY
from .ground_truth import read_ground_truth, write_ground_truth
from .scoring import (
    MarkdownSource,
    analyze_results,
    generate_raw_scores,
    simple_scores,
    validate_sources,
)


def source_argument(value: str) -> MarkdownSource:
    name, separator, directory = value.partition("=")
    if not separator or not name.strip() or not directory:
        raise argparse.ArgumentTypeError("use NAME=DIRECTORY")
    return MarkdownSource(name, Path(directory))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-benchmark evaluate",
        description="Score explicitly selected Markdown outputs against reference snippets.",
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
    parser.add_argument(
        "--markdown-source",
        action="append",
        required=True,
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
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


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
        sources = options.markdown_source
        validate_sources(sources)
        options.output_dir.mkdir(parents=True, exist_ok=True)
        scores_path = options.output_dir / "scores.csv"
        summary_path = options.output_dir / "scores_by_category.csv"
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
        write_ground_truth(options.output_dir / "ground_truth.json", pages)
        raw_scores = generate_raw_scores(pages, sources)
        reports = analyze_results(
            raw_scores,
            pd.read_csv(options.page_mapping),
            [source.name for source in sources],
            options.min_score_threshold,
        )
        reports.granular.to_csv(options.output_dir / "granular.csv", index=False)
        reports.filtered.to_csv(options.output_dir / "filtered.csv", index=False)
        if reports.summary.empty:
            summary_path.unlink(missing_ok=True)
            scores_path.unlink(missing_ok=True)
            raise ValueError("No scored snippets remain after filtering")
        reports.summary.to_csv(summary_path)
        simple_scores(reports.summary).to_csv(scores_path, index=False, float_format="%.2f")
        logger.info(
            "Scored %s snippets across %s pages",
            len(reports.filtered),
            reports.filtered.page_number.nunique(),
        )
        logger.info("Saved benchmark results: %s", summary_path)
        return 0
    except (OSError, ValueError, KeyError) as error:
        logger.error("Evaluation failed: %s", error, exc_info=options.verbose)
        return 1
