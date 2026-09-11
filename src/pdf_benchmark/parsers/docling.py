"""Reusable CPU Docling converters with native page/document batching."""

import argparse
import multiprocessing
import os
import time
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Iterator

from ..artifacts import RunArtifacts
from ..execution import failure, run_batch
from ..files import positive_int
from ..models import DocumentOutcome, Metadata, ParsedDocument


@dataclass(frozen=True)
class DoclingOptions:
    ocr: bool = True
    workers: int = 1
    threads: int = 4
    batch_size: int = 8
    page_batch_size: int = 4
    tables: bool = True


class DoclingParser:
    def __init__(self, options: DoclingOptions):
        self.options = options
        self._converter = None

    @property
    def config(self) -> Metadata:
        return {**asdict(self.options), "device": "cpu"}

    def _get_converter(self):
        if self._converter is not None:
            return self._converter
        for variable in (
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ):
            os.environ[variable] = str(self.options.threads)

        import torch
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.settings import settings
        from docling.document_converter import DocumentConverter, PdfFormatOption

        torch.set_num_threads(self.options.threads)
        settings.debug.profile_pipeline_timings = True
        settings.perf.doc_batch_size = self.options.batch_size
        # Cross-document threading is experimental; CPU processes own their models.
        settings.perf.doc_batch_concurrency = 1
        pipeline = PdfPipelineOptions(
            do_ocr=self.options.ocr,
            do_table_structure=self.options.tables,
            accelerator_options=AcceleratorOptions(
                device=AcceleratorDevice.CPU, num_threads=self.options.threads
            ),
            ocr_batch_size=self.options.page_batch_size,
            layout_batch_size=self.options.page_batch_size,
            table_batch_size=self.options.page_batch_size,
        )
        self._converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline)},
        )
        return self._converter

    def convert_batch(self, paths: list[Path]) -> list[DocumentOutcome]:
        started = time.perf_counter()
        outcomes = {}
        versions = {"docling_version": version("docling"), "torch_version": version("torch")}
        try:
            from docling.datamodel.base_models import ConversionStatus

            for result in self._get_converter().convert_all(paths, raises_on_error=False):
                path = Path(result.input.file).resolve()
                try:
                    if result.status != ConversionStatus.SUCCESS:
                        raise RuntimeError(
                            f"Conversion status: {result.status.value}; {result.errors}"
                        )
                    timing = result.timings.get("pipeline_total")
                    duration = sum(timing.times) if timing else None
                    metadata = {
                        **versions,
                        "status": result.status.value,
                        "pages_processed": len(result.document.pages),
                    }
                    outcomes[path] = DocumentOutcome(
                        path,
                        ParsedDocument(result.document.export_to_markdown(), metadata),
                        duration_seconds=duration,
                    )
                except Exception as error:
                    outcomes[path] = failure(path, error)
        except Exception as error:
            for path in paths:
                outcomes.setdefault(path, failure(path, error))
        elapsed = time.perf_counter() - started
        results = []
        for path in paths:
            outcome = outcomes.get(
                path, DocumentOutcome(path, error="No conversion result returned")
            )
            if outcome.document:
                document = ParsedDocument(
                    outcome.document.markdown,
                    {**outcome.document.metadata, "batch_wall_seconds": elapsed},
                )
                outcome = DocumentOutcome(path, document, duration_seconds=outcome.duration_seconds)
            results.append(outcome)
        return results

    def convert_many(self, paths: list[Path]) -> Iterator[DocumentOutcome]:
        batches = [
            paths[index : index + self.options.batch_size]
            for index in range(0, len(paths), self.options.batch_size)
        ]
        if self.options.workers == 1:
            for batch in batches:
                yield from self.convert_batch(batch)
            return
        with multiprocessing.get_context("spawn").Pool(
            processes=min(self.options.workers, len(batches)),
            initializer=_initialize_worker,
            initargs=(self.options,),
        ) as pool:
            for outcomes in pool.imap_unordered(_convert_in_worker, batches):
                yield from outcomes
            pool.close()
            pool.join()


_worker_parser: DoclingParser | None = None


def _initialize_worker(options: DoclingOptions) -> None:
    global _worker_parser
    _worker_parser = DoclingParser(options)


def _convert_in_worker(paths: list[Path]) -> list[DocumentOutcome]:
    assert _worker_parser is not None
    return _worker_parser.convert_batch(paths)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ocr", choices=("on", "off", "both"), default="both")
    parser.add_argument(
        "--workers", type=positive_int, default=1, help="CPU processes; each holds its own models"
    )
    parser.add_argument("--threads", type=positive_int, default=4)
    parser.add_argument("--batch-size", type=positive_int, default=8)
    parser.add_argument("--page-batch-size", type=positive_int, default=4)
    parser.add_argument("--no-tables", action="store_true")


def run(options: argparse.Namespace, paths: list[Path], key: str | None = None) -> int:
    modes = (True, False) if options.ocr == "both" else (options.ocr == "on",)
    runs = []
    for ocr in modes:
        if options.ocr == "both":
            directory = options.output_dir / ("ocr" if ocr else "no_ocr")
        else:
            directory = options.output_dir
        artifacts = RunArtifacts(directory)
        artifacts.check_available(options.overwrite)
        runs.append((ocr, artifacts))
    exit_code = 0
    for ocr, artifacts in runs:
        artifacts.prepare(options.overwrite)
        settings = DoclingOptions(
            ocr,
            options.workers,
            options.threads,
            options.batch_size,
            options.page_batch_size,
            not options.no_tables,
        )
        exit_code |= run_batch(DoclingParser(settings), paths, artifacts)
    return exit_code
