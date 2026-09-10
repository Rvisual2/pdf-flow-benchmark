"""Docling CPU benchmark using reusable converters and native convert_all batches."""

import argparse
import gc
import multiprocessing
import os
import time
from importlib.metadata import version
from pathlib import Path

try:
    from .local_common import (ROOT, add_common_arguments, check_output, finish_run, input_files,
                               positive_int, prepare_output, write_record)
except ImportError:
    from local_common import (ROOT, add_common_arguments, check_output, finish_run, input_files,
                              positive_int, prepare_output, write_record)

_CONVERTER = None
_CONFIG = None


def get_converter(config: dict):
    """Load models once per process; set thread limits before native imports."""
    global _CONVERTER, _CONFIG
    if _CONVERTER is not None and _CONFIG == config:
        return _CONVERTER
    _CONVERTER = None
    gc.collect()
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[key] = str(config["threads"])

    import torch
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.settings import settings
    from docling.document_converter import DocumentConverter, PdfFormatOption

    torch.set_num_threads(config["threads"])
    settings.debug.profile_pipeline_timings = True
    settings.perf.doc_batch_size = config["batch_size"]
    # Docling labels cross-document threading experimental. Use process workers
    # on CPU; each pipeline batches pages.
    settings.perf.doc_batch_concurrency = 1
    options = PdfPipelineOptions(
        do_ocr=config["ocr"],
        do_table_structure=config["tables"],
        accelerator_options=AcceleratorOptions(
            device=AcceleratorDevice.CPU, num_threads=config["threads"]),
        ocr_batch_size=config["page_batch_size"],
        layout_batch_size=config["page_batch_size"],
        table_batch_size=config["page_batch_size"],
    )
    _CONVERTER = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )
    _CONFIG = config.copy()
    return _CONVERTER


def process_batch(task: tuple) -> list[dict]:
    """Associate results by source path, including partial and failed conversions."""
    files, output, config = task
    records = {}
    started = time.perf_counter()
    versions = {"docling_version": version("docling"), "torch_version": version("torch")}
    try:
        converter = get_converter(config)
        from docling.datamodel.base_models import ConversionStatus
        for result in converter.convert_all(files, raises_on_error=False):
            path = Path(result.input.file).resolve()
            record = {"file": str(path), **versions, "config": config, "success": False,
                      "status": result.status.value}
            try:
                if result.status != ConversionStatus.SUCCESS:
                    raise RuntimeError(f"Conversion status: {result.status.value}; {result.errors}")
                markdown = result.document.export_to_markdown()
                if not markdown.strip():
                    raise ValueError("Empty Markdown output")
                md_path = output / "markdowns" / f"{path.stem}.md"
                md_path.write_text(markdown, encoding="utf-8")
                timing = result.timings.get("pipeline_total")
                record.update(success=True, markdown_file=str(md_path),
                              pages_processed=len(result.document.pages),
                              duration=sum(timing.times) if timing else None)
            except Exception as exc:
                record["error"] = str(exc)
            records[path] = record
    except Exception as exc:
        for path in files:
            records.setdefault(path, {"file": str(path), **versions, "config": config,
                                      "success": False, "error": str(exc)})
    elapsed = time.perf_counter() - started
    for path in files:
        records.setdefault(path, {"file": str(path), **versions, "config": config,
                                  "success": False, "error": "No conversion result returned"})
        records[path]["batch_wall_seconds"] = elapsed
    return [records[path] for path in files]


def run_pipeline(files: list[Path], output: Path, config: dict, overwrite: bool) -> int:
    prepare_output(output, files, overwrite)
    tasks = [(files[i:i + config["batch_size"]], output, config)
             for i in range(0, len(files), config["batch_size"])]
    started = time.perf_counter()
    records = []
    if config["workers"] == 1:
        batches = map(process_batch, tasks)
        for batch in batches:
            for record in batch:
                write_record(output, record)
                records.append(record)
    else:
        with multiprocessing.get_context("spawn").Pool(
            processes=min(config["workers"], len(tasks))
        ) as pool:
            for batch in pool.imap_unordered(process_batch, tasks):
                for record in batch:
                    write_record(output, record)
                    records.append(record)
            pool.close()
            pool.join()
    return finish_run(output, records, time.perf_counter() - started, config)


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch Docling conversion on CPU")
    add_common_arguments(parser, "docling_results")
    parser.set_defaults(output_dir=None)
    parser.add_argument("--ocr", choices=("on", "off", "both"), default="both")
    parser.add_argument("--workers", type=positive_int, default=1,
                        help="CPU model processes; each consumes additional memory")
    parser.add_argument("--threads", type=positive_int, default=4)
    parser.add_argument("--batch-size", type=positive_int, default=8, help="Documents per convert_all call")
    parser.add_argument("--page-batch-size", type=positive_int, default=4, help="OCR/layout/table stage batch size")
    parser.add_argument("--no-tables", action="store_true")
    args = parser.parse_args()
    try:
        files = input_files(args)
        modes = (True, False) if args.ocr == "both" else (args.ocr == "on",)
        if args.output_dir is None:
            outputs = [ROOT / ("docling_ocr_results" if mode else "docling_wocr_results") for mode in modes]
        else:
            base = args.output_dir
            outputs = [base / ("ocr" if mode else "no_ocr") if args.ocr == "both" else base for mode in modes]
        for output in outputs:
            check_output(output, args.overwrite)
        exit_code = 0
        for mode, output in zip(modes, outputs):
            config = {"device": "cpu", "workers": args.workers, "threads": args.threads,
                      "batch_size": args.batch_size, "page_batch_size": args.page_batch_size,
                      "ocr": mode, "tables": not args.no_tables}
            exit_code |= run_pipeline(files, output, config, args.overwrite)
        return exit_code
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
