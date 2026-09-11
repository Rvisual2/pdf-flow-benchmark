"""Execution policies independent of SDKs and parser-specific configuration."""

import asyncio
import time
from pathlib import Path

from .artifacts import RunArtifacts
from .models import (
    AsyncBatchParser,
    AsyncParser,
    BatchParser,
    DocumentOutcome,
    ExecutionOptions,
    SequentialParser,
)


def failure(path: Path, error: Exception, started: float | None = None) -> DocumentOutcome:
    return DocumentOutcome(
        path,
        error=f"{type(error).__name__}: {error}",
        duration_seconds=time.perf_counter() - started if started is not None else None,
    )


async def run_async(
    parser: AsyncParser, paths: list[Path], artifacts: RunArtifacts, options: ExecutionOptions
) -> int:
    started = time.perf_counter()
    semaphore = asyncio.Semaphore(options.concurrency)
    config = {**parser.config, "concurrency": options.concurrency}

    async def convert_one(path: Path) -> None:
        async with semaphore:
            document_started = time.perf_counter()
            try:
                async with asyncio.timeout(options.timeout):
                    document = await parser.convert(path)
                outcome = DocumentOutcome(
                    path, document, duration_seconds=time.perf_counter() - document_started
                )
            except Exception as error:
                outcome = failure(path, error, document_started)
            artifacts.record(outcome, config)

    await asyncio.gather(*(convert_one(path) for path in paths))
    return artifacts.finish(time.perf_counter() - started, config)


def run_sequential(parser: SequentialParser, paths: list[Path], artifacts: RunArtifacts) -> int:
    """Persist one document before submitting the next."""
    started = time.perf_counter()
    config = {**parser.config, "concurrency": 1}
    for path in paths:
        document_started = time.perf_counter()
        try:
            document = parser.convert(path)
            outcome = DocumentOutcome(
                path, document, duration_seconds=time.perf_counter() - document_started
            )
        except Exception as error:
            outcome = failure(path, error, document_started)
        artifacts.record(outcome, config)
    return artifacts.finish(time.perf_counter() - started, config)


def run_batch(parser: BatchParser, paths: list[Path], artifacts: RunArtifacts) -> int:
    started = time.perf_counter()
    remaining = set(paths)
    config = parser.config
    batch_error = "No conversion result returned"
    try:
        for outcome in parser.convert_many(paths):
            if outcome.path not in remaining:
                raise ValueError(f"Unexpected or duplicate parser result: {outcome.path}")
            artifacts.record(outcome, config)
            remaining.remove(outcome.path)
    except Exception as error:
        batch_error = f"{type(error).__name__}: {error}"
    for path in paths:
        if path in remaining:
            artifacts.record(DocumentOutcome(path, error=batch_error), config)
    if not remaining and batch_error != "No conversion result returned":
        # A protocol error after the final document must not become a success.
        raise ValueError(batch_error)
    return artifacts.finish(time.perf_counter() - started, config)


async def run_async_batch(
    parser: AsyncBatchParser, paths: list[Path], artifacts: RunArtifacts, options: ExecutionOptions
) -> int:
    """A native server batch has one deadline; retain all partial outcomes and IDs."""
    started = time.perf_counter()
    remaining = set(paths)
    config = {**parser.config, "execution": "server_batch", "concurrency": options.concurrency}
    batch_error = "No conversion result returned"
    try:
        async with asyncio.timeout(options.timeout):
            async for outcome in parser.convert_many(paths):
                if outcome.path not in remaining:
                    raise ValueError(f"Unexpected or duplicate parser result: {outcome.path}")
                artifacts.record(outcome, config)
                remaining.remove(outcome.path)
    except Exception as error:
        batch_error = f"{type(error).__name__}: {error}; remote IDs are in submissions.jsonl"
    for path in paths:
        if path in remaining:
            artifacts.record(DocumentOutcome(path, error=batch_error), config)
    if not remaining and batch_error != "No conversion result returned":
        raise ValueError(batch_error)
    return artifacts.finish(time.perf_counter() - started, config)
