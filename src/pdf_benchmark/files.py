"""Repository paths, deterministic input discovery, and credentials."""

import argparse
import os
from pathlib import Path


def workspace_root() -> Path:
    """Find the checkout for editable installs; installed wheels use the working directory."""
    configured_root = os.getenv("PDF_BENCHMARK_ROOT")
    if configured_root:
        return Path(configured_root).expanduser().resolve()
    working_directory = Path.cwd()
    for directory in (
        working_directory,
        *working_directory.parents,
        *Path(__file__).resolve().parents,
    ):
        if (directory / "pyproject.toml").is_file() and (directory / "src/pdf_benchmark").is_dir():
            return directory
    return working_directory


ROOT = workspace_root()
DATA_DIRECTORY = ROOT / "data"
BASELINE_DIRECTORY = ROOT / "results/baseline"
RUNS_DIRECTORY = ROOT / "results/runs"


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def document_sort_key(path: Path) -> tuple[float, str]:
    suffix = path.stem.removeprefix("page_")
    number = int(suffix) if path.stem.startswith("page_") and suffix.isdigit() else float("inf")
    return number, path.name


def discover_pdfs(directory: Path, limit: int | None = None) -> list[Path]:
    if not directory.is_dir():
        raise ValueError(
            f"Input directory does not exist: {directory}. Run 'pdf-benchmark data download' first."
        )
    paths = sorted(
        (
            path.resolve()
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        ),
        key=document_sort_key,
    )
    if not paths:
        raise ValueError(f"No PDFs in {directory}")
    if len({path.stem for path in paths}) != len(paths):
        raise ValueError("PDF stems must be unique to avoid overwriting Markdown")
    return paths[:limit]


def require_api_key(name: str) -> str:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Set {name} in the environment or repository .env")
    return value
