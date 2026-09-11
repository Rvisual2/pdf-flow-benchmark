"""Translate the historical PDF annotations and OCR workbook into reference pages."""

import logging
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .ground_truth import ReferencePage, ReferenceSnippet, validate_pages

LOGGER = logging.getLogger(__name__)


def extract_annotations(pdf_path: Path) -> list[dict]:
    import pymupdf

    if pdf_path.is_dir():
        # Preserve the historical page-to-file association for the existing dataset.
        paths = sorted(
            (path for path in pdf_path.iterdir() if path.suffix.lower() == ".pdf"),
            key=lambda path: int(path.stem.split("_")[-1]) if "_" in path.name else str(path),
        )
    else:
        paths = [pdf_path]
    annotations = []
    for page_number, path in enumerate(paths, start=1):
        LOGGER.debug("Extracting annotations %s/%s: %s", page_number, len(paths), path.name)
        with pymupdf.open(path) as document:
            page = document[0]
            page_annotations = list(page.annots() or [])
            source = next(
                (
                    annotation.info.get("content", "").strip()
                    for annotation in page_annotations
                    if "source" in annotation.info.get("content", "").lower()
                ),
                "",
            )
            for annotation in page_annotations:
                content = annotation.info.get("content", "").strip()
                match = re.match(r"^(\d+\.\d+)", content)
                if "source" in content.lower() or not match or annotation.type[1] != "Highlight":
                    continue
                text = " ".join(
                    page.get_text("text", clip=annotation.rect, sort=True).strip().split()
                )
                if text:
                    annotations.append(
                        {
                            "page_number": page_number,
                            "annotation": {"key": match.group(1), "text": text},
                            "source": source,
                        }
                    )
    annotations.sort(key=lambda entry: (entry["page_number"], float(entry["annotation"]["key"])))
    return annotations


def combine_sources(annotations: list[dict], workbook_path: Path) -> list[dict]:
    workbook = pd.read_excel(workbook_path)
    grouped = defaultdict(lambda: defaultdict(list))
    for entry in annotations:
        series, sequence = map(int, entry["annotation"]["key"].split("."))
        grouped[entry["page_number"]][series].append((sequence, entry["annotation"]["text"]))
    combined = {}
    for page_number, series_groups in grouped.items():
        combined[page_number] = {
            "page_number": page_number,
            "annotations": {
                f"reading_order_{series}": " ".join(
                    text for _, text in sorted(texts, key=lambda item: item[0])
                )
                for series, texts in series_groups.items()
            },
            "ocr_text": [],
        }
    for _, row in workbook.iterrows():
        page_number = row["Page No."]
        combined.setdefault(
            page_number, {"page_number": page_number, "annotations": {}, "ocr_text": []}
        )
        combined[page_number]["ocr_text"].append(row["Text"])
    return [combined[page_number] for page_number in sorted(combined)]


def build_reference_pages(combined: list[dict]) -> list[ReferencePage]:
    from cleantext import clean

    pages = []
    for page in combined:
        snippets = []
        for key, text in sorted(
            page["annotations"].items(),
            key=lambda item: int(item[0].removeprefix("reading_order_")),
        ):
            if isinstance(text, str) and text.strip():
                order = int(key.removeprefix("reading_order_"))
                snippets.append(
                    ReferenceSnippet(f"annotation:{order}", text.strip(), "annotation", order)
                )
        for index, text in enumerate(page["ocr_text"], start=1):
            if not isinstance(text, str) or not text.strip():
                continue
            cleaned = clean(
                text,
                lower=False,
                normalize_whitespace=True,
                fix_unicode=False,
                strip_lines=True,
                no_line_breaks=True,
                lang="en",
            )
            if cleaned.strip():
                snippets.append(ReferenceSnippet(f"ocr:{index}", cleaned.strip(), "ocr"))
        if snippets:
            pages.append(ReferencePage(int(page["page_number"]), tuple(snippets)))
    validate_pages(pages)
    return pages
