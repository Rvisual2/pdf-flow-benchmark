"""CLI and output handling for local conversion benchmarks."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def add_common_arguments(parser: argparse.ArgumentParser, output: str) -> None:
    parser.add_argument("--input-dir", type=Path, default=ROOT / "PDFs")
    parser.add_argument("--output-dir", type=Path, default=ROOT / output)
    parser.add_argument("--limit", type=positive_int, help="Convert a small sample")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing run outputs")


def input_files(args: argparse.Namespace) -> list[Path]:
    if not args.input_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {args.input_dir}")
    files = sorted(
        (p.resolve() for p in args.input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"),
        key=lambda p: (int(p.stem[5:]) if p.stem.startswith("page_") and p.stem[5:].isdigit() else float("inf"), p.name),
    )
    if not files:
        raise ValueError(f"No PDFs in {args.input_dir}")
    if len({p.stem for p in files}) != len(files):
        raise ValueError("PDF stems must be unique to avoid overwriting Markdown")
    return files[:args.limit]


def check_output(output: Path, overwrite: bool) -> None:
    if output.exists() and any(output.iterdir()) and not overwrite:
        raise ValueError(f"Output is not empty: {output}. Choose a new --output-dir or use --overwrite.")


def prepare_output(output: Path, files: list[Path], overwrite: bool) -> None:
    check_output(output, overwrite)
    markdowns = output / "markdowns"
    markdowns.mkdir(parents=True, exist_ok=True)
    # Clear old Markdown only when replacement was explicitly requested. Otherwise
    # a failed or limited rerun could silently reuse old successful results.
    if overwrite:
        for path in markdowns.glob("*.md"):
            path.unlink()
    (output / "results.jsonl").write_text("", encoding="utf-8")


def write_record(output: Path, record: dict) -> None:
    record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    with (output / "results.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{'OK' if record['success'] else 'FAILED'} {Path(record['file']).name}", flush=True)


def finish_run(output: Path, records: list[dict], elapsed: float, config: dict) -> int:
    failed = sum(not record["success"] for record in records)
    summary = {"timestamp": datetime.now(timezone.utc).isoformat(), "config": config,
               "total": len(records), "failed": failed, "wall_seconds": elapsed}
    (output / "run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output / "duration.txt").write_text(f"Total Duration: {elapsed:.2f}s\n", encoding="utf-8")
    print(f"{len(records) - failed}/{len(records)} succeeded in {elapsed:.2f}s")
    return int(failed > 0)
