"""Score reference snippets and summarize the same filtered sample for all parsers."""

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .ground_truth import ReferencePage
from .matching import find_best_match_and_normalized_distance

LOGGER = logging.getLogger(__name__)
RESERVED_COLUMNS = {
    "page_number",
    "needle_index",
    "needle",
    "OCR",
    "Page",
    "Folder",
    "Folder_Count",
}


@dataclass(frozen=True)
class MarkdownSource:
    name: str
    directory: Path


@dataclass(frozen=True)
class EvaluationReports:
    granular: pd.DataFrame
    filtered: pd.DataFrame
    summary: pd.DataFrame


def validate_sources(sources: list[MarkdownSource]) -> None:
    names = [source.name for source in sources]
    if not names or len(set(names)) != len(names):
        raise ValueError("Provide at least one source with unique names")
    occupied = set(RESERVED_COLUMNS)
    for source in sources:
        if (
            not source.name.strip()
            or source.name in occupied
            or f"{source.name}_best_match" in occupied
        ):
            raise ValueError(f"Duplicate or reserved source name: {source.name}")
        occupied.update((source.name, f"{source.name}_best_match"))
        if not source.directory.is_dir():
            raise ValueError(
                f"Markdown directory does not exist: {source.directory}. Download a named results release or convert your own inputs."
            )


def generate_raw_scores(pages: list[ReferencePage], sources: list[MarkdownSource]) -> pd.DataFrame:
    validate_sources(sources)
    rows = []
    for page_index, page in enumerate(pages, start=1):
        LOGGER.debug("Processing page group %s/%s", page_index, len(pages))
        markdown_by_source = {}
        for source in sources:
            path = source.directory / f"page_{page.page_number}.md"
            try:
                markdown_by_source[source.name] = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                markdown_by_source[source.name] = None
        for snippet_index, snippet in enumerate(page.snippets):
            row = {
                "page_number": page.page_number,
                "needle_index": snippet_index,
                "needle": snippet.text,
                "OCR": snippet.source == "ocr",
            }
            for source in sources:
                markdown = markdown_by_source[source.name]
                match, score = (
                    find_best_match_and_normalized_distance(snippet.text, markdown)
                    if markdown
                    else (None, None)
                )
                row[source.name] = score
                row[f"{source.name}_best_match"] = match
            rows.append(row)
    return pd.DataFrame(rows)


def analyze_results(
    raw_scores: pd.DataFrame,
    page_mapping: pd.DataFrame,
    score_columns: list[str],
    threshold: float = 0.25,
) -> EvaluationReports:
    if not {"Page", "Folder"}.issubset(page_mapping.columns):
        raise ValueError("Page mapping requires Page and Folder columns")
    if page_mapping.Page.duplicated().any():
        raise ValueError("Page mapping contains duplicate pages")
    merged = raw_scores.merge(page_mapping, left_on="page_number", right_on="Page")
    granular = merged.dropna(subset=score_columns).copy()
    filtered = granular[granular[score_columns].min(axis=1) < threshold]
    if filtered.empty:
        return EvaluationReports(granular, filtered, pd.DataFrame())
    mean_distances = filtered.groupby("Folder")[score_columns].mean()
    counts = filtered.groupby("Folder").size()
    summary = ((1 - mean_distances) * 100).round(2)
    summary["Folder_Count"] = counts.astype(int)
    weighted_scores = {
        column: ((1 - (mean_distances[column] * counts).sum() / counts.sum()) * 100).round(2)
        for column in score_columns
    }
    weighted_row = pd.Series(weighted_scores, name="Weighted_Mean")
    weighted_row["Folder_Count"] = int(counts.sum())
    summary = pd.concat([summary, weighted_row.to_frame().T])
    ranked_columns = (
        summary.loc["Weighted_Mean", score_columns].sort_values(ascending=False).index.tolist()
    )
    return EvaluationReports(granular, filtered, summary[ranked_columns + ["Folder_Count"]])


def simple_scores(summary: pd.DataFrame) -> pd.DataFrame:
    return (
        summary.loc["Weighted_Mean"]
        .drop("Folder_Count")
        .rename_axis("tool")
        .reset_index(name="score_percent")
    )
