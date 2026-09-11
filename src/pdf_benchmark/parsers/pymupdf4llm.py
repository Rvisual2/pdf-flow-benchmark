"""Native PyMuPDF4LLM batch conversion, preserving its worker and OCR controls."""

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Iterator

from ..artifacts import RunArtifacts
from ..execution import failure, run_batch
from ..files import positive_int
from ..models import DocumentOutcome, Metadata, ParsedDocument


@dataclass(frozen=True)
class PyMuPDF4LLMOptions:
    workers: int | None = None
    persistent: bool = True
    layout: bool = True
    ocr: bool = True


def logged_duration(path: Path) -> float | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        start = next(
            datetime.fromisoformat(line[7:]) for line in lines if line.startswith("Start: ")
        )
        end = next(datetime.fromisoformat(line[5:]) for line in lines if line.startswith("End: "))
        return (end - start).total_seconds()
    except (OSError, StopIteration, ValueError):
        return None


class PyMuPDF4LLMParser:
    def __init__(self, options: PyMuPDF4LLMOptions, native_directory: Path):
        self.options = options
        self.native_directory = native_directory.resolve()

    @property
    def workers(self) -> int | None:
        # The native process pool does not propagate use_layout(False).
        return self.options.workers if self.options.layout else 1

    @property
    def config(self) -> Metadata:
        return {
            **asdict(self.options),
            "api": "convert_batch",
            "workers": self.workers or "auto",
            "ocr": self.options.layout and self.options.ocr,
            "streaming": True,
        }

    def convert_many(self, paths: list[Path]) -> Iterator[DocumentOutcome]:
        import pymupdf4llm

        pymupdf4llm.use_layout(self.options.layout)
        versions = {
            name.replace("-", "_") + "_version": version(name)
            for name in ("pymupdf4llm", "pymupdf", "pymupdf-layout")
        }
        results = pymupdf4llm.convert_batch(
            paths,
            backend="md",
            workers=self.workers,
            persistent=self.options.persistent,
            streaming=True,
            out_dir=self.native_directory,
            options={
                "header": True,
                "footer": True,
                "use_ocr": self.options.layout and self.options.ocr,
            },
        )
        for result in results:
            path = Path(result.input).resolve()
            log_path = self.native_directory / path.stem / "run-log.txt"
            if not result.success:
                yield failure(path, RuntimeError(str(result.error)))
            else:
                yield DocumentOutcome(
                    path,
                    ParsedDocument(result.output, {**versions, "native_log": str(log_path)}),
                    duration_seconds=logged_duration(log_path),
                )


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workers", type=positive_int, help="Default: native automatic sizing")
    parser.add_argument("--persistent", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--layout",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Disabling Layout uses native sequential execution",
    )
    parser.add_argument("--ocr", action=argparse.BooleanOptionalAction, default=True)


def run(options: argparse.Namespace, paths: list[Path], key: str | None = None) -> int:
    artifacts = RunArtifacts(options.output_dir)
    artifacts.prepare(options.overwrite)
    settings = PyMuPDF4LLMOptions(options.workers, options.persistent, options.layout, options.ocr)
    return run_batch(PyMuPDF4LLMParser(settings, artifacts.directory / "native"), paths, artifacts)
