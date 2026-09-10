"""Native PyMuPDF4LLM batch conversion with benchmark-compatible outputs."""

import argparse
import multiprocessing
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

try:
    from .local_common import (
        add_common_arguments, finish_run, input_files, positive_int,
        prepare_output, write_record,
    )
except ImportError:
    from local_common import (
        add_common_arguments, finish_run, input_files, positive_int,
        prepare_output, write_record,
    )


def logged_duration(log_path: Path) -> float | None:
    """Use native per-document timestamps, not time spent waiting for a result."""
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
        start = next(datetime.fromisoformat(line[7:]) for line in lines if line.startswith("Start: "))
        end = next(datetime.fromisoformat(line[5:]) for line in lines if line.startswith("End: "))
        return (end - start).total_seconds()
    except (OSError, StopIteration, ValueError):
        return None


def run_batch(files: list[Path], args) -> int:
    import pymupdf4llm

    pymupdf4llm.use_layout(args.layout)
    # The native pool does not propagate use_layout(False) to spawned workers.
    # Sequential native execution preserves that explicit mode on every platform.
    workers = args.workers if args.layout else 1
    if not args.layout and args.workers != 1:
        print("Layout disabled: using native sequential mode to preserve this setting.")
    config = {"api": "convert_batch", "workers": workers if workers is not None else "auto",
              "layout": args.layout, "ocr": args.layout and args.ocr,
              "persistent": args.persistent, "streaming": True}
    versions = {name.replace("-", "_") + "_version": version(name)
                for name in ("pymupdf4llm", "pymupdf", "pymupdf-layout")}
    native_dir = (args.output_dir / "native").resolve()
    # Explicit options retain the single-document API's header/footer behavior;
    # convert_batch's own defaults omit headers and footers.
    options = {"header": True, "footer": True, "use_ocr": args.layout and args.ocr}
    records = []
    started = time.perf_counter()
    try:
        results = pymupdf4llm.convert_batch(
            files, backend="md", workers=workers, persistent=args.persistent,
            streaming=True, out_dir=native_dir, options=options,
        )
        for result in results:
            path = Path(result.input).resolve()
            record = {"file": str(path), "success": False, "config": config, **versions}
            log_path = native_dir / path.stem / "run-log.txt"
            record.update(native_log=str(log_path), duration_seconds=logged_duration(log_path))
            try:
                if not result.success:
                    raise RuntimeError(str(result.error))
                if not isinstance(result.output, str) or not result.output.strip():
                    raise ValueError("Empty Markdown output")
                target = args.output_dir / "markdowns" / f"{path.stem}.md"
                target.write_text(result.output, encoding="utf-8")
                record.update(success=True, markdown_file=str(target))
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            write_record(args.output_dir, record)
            records.append(record)
    except Exception as exc:
        completed = {record["file"] for record in records}
        for path in files:
            if str(path) not in completed:
                record = {"file": str(path), "success": False, "config": config,
                          **versions, "error": f"{type(exc).__name__}: {exc}"}
                write_record(args.output_dir, record)
                records.append(record)
    return finish_run(args.output_dir, records, time.perf_counter() - started, config)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_arguments(parser, "pymupdflayout_results")
    parser.add_argument("--workers", type=positive_int, default=None,
                        help="Native worker count; default uses PyMuPDF4LLM automatic sizing")
    parser.add_argument("--persistent", action=argparse.BooleanOptionalAction, default=True,
                        help="Reuse native worker state across documents")
    parser.add_argument("--layout", action=argparse.BooleanOptionalAction, default=True,
                        help="Use bundled Layout; --no-layout runs sequentially")
    parser.add_argument("--ocr", action=argparse.BooleanOptionalAction, default=True,
                        help="Enable automatic OCR for scanned pages in Layout mode")
    args = parser.parse_args()
    try:
        files = input_files(args)
        prepare_output(args.output_dir, files, args.overwrite)
        return run_batch(files, args)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
