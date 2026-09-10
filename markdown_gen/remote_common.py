"""Shared reporting for hosted document parsers (no automatic resubmission)."""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

try:
    from .local_common import ROOT, add_common_arguments, finish_run, input_files, positive_int, prepare_output, write_record
except ImportError:
    from local_common import ROOT, add_common_arguments, finish_run, input_files, positive_int, prepare_output, write_record


def configure(parser, output, *, concurrent=True):
    add_common_arguments(parser, output)
    parser.add_argument("--timeout", type=positive_int, default=7200, help="Per-document deadline in seconds")
    if concurrent:
        parser.add_argument("--concurrency", type=positive_int, default=5)
    return parser


def require_key(name):
    load_dotenv(ROOT / ".env")
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Set {name} in the environment or repository .env")
    return value


def save_submission(output, record):
    """Retain remote IDs immediately, even when polling is interrupted."""
    record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    with (output / "submissions.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")


def save_markdown(output, path, markdown):
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("Empty Markdown output")
    target = output / "markdowns" / f"{path.stem}.md"
    target.write_text(markdown, encoding="utf-8")
    return str(target)


async def run_documents(files, args, convert, config):
    started = time.perf_counter()
    semaphore = asyncio.Semaphore(args.concurrency)

    async def one(path):
        async with semaphore:
            document_start = time.perf_counter()
            record = {"file": str(path), "success": False, "config": config}
            try:
                async with asyncio.timeout(args.timeout):
                    markdown, metadata = await convert(path)
                record.update(metadata)
                record["markdown_file"] = save_markdown(args.output_dir, path, markdown)
                record["success"] = True
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            record["duration_seconds"] = time.perf_counter() - document_start
            write_record(args.output_dir, record)
            return record

    records = await asyncio.gather(*(one(path) for path in files))
    return finish_run(args.output_dir, records, time.perf_counter() - started, config)
