"""Validated, versioned reference data independent of PDF and spreadsheet loaders."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ReferenceSnippet:
    id: str
    text: str
    source: Literal["annotation", "ocr"]
    reading_order: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Snippet IDs must be nonempty strings")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError(f"Snippet {self.id} has empty text")
        if self.source not in {"annotation", "ocr"}:
            raise ValueError(f"Unknown reference source: {self.source}")
        if self.reading_order is not None and (
            type(self.reading_order) is not int or self.reading_order < 0
        ):
            raise ValueError("Reading order must be a nonnegative integer or null")


@dataclass(frozen=True)
class ReferencePage:
    page_number: int
    snippets: tuple[ReferenceSnippet, ...]

    def __post_init__(self) -> None:
        if type(self.page_number) is not int or self.page_number < 1:
            raise ValueError("Page numbers must be positive integers")
        if not self.snippets:
            raise ValueError(f"Page {self.page_number} has no snippets")
        if len({snippet.id for snippet in self.snippets}) != len(self.snippets):
            raise ValueError(f"Duplicate snippet IDs on page {self.page_number}")


def validate_pages(pages: list[ReferencePage]) -> None:
    if not pages:
        raise ValueError("Ground truth contains no pages")
    if len({page.page_number for page in pages}) != len(pages):
        raise ValueError("Ground truth contains duplicate page numbers")


def write_ground_truth(path: Path, pages: list[ReferencePage]) -> None:
    validate_pages(pages)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"schema_version": SCHEMA_VERSION, "pages": [asdict(page) for page in pages]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def read_ground_truth(path: Path) -> list[ReferencePage]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported ground-truth schema; expected version {SCHEMA_VERSION}")
    try:
        pages = [
            ReferencePage(
                page["page_number"],
                tuple(ReferenceSnippet(**snippet) for snippet in page["snippets"]),
            )
            for page in data["pages"]
        ]
    except (KeyError, TypeError) as error:
        raise ValueError(f"Malformed ground-truth document: {error}") from error
    validate_pages(pages)
    return pages


def legacy_cleaned_data(pages: list[ReferencePage]) -> list[dict]:
    """Keep the historical cleaned.json export available for old analyses."""
    return [
        {
            "page_number": page.page_number,
            "texts": [snippet.text for snippet in page.snippets],
            "is_ocr": [snippet.source == "ocr" for snippet in page.snippets],
        }
        for page in pages
    ]
