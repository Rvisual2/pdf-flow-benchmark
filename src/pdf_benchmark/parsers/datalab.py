"""Datalab SDK adapter, independent of execution and artifact storage."""

import argparse
import asyncio
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

from ..artifacts import RunArtifacts
from ..execution import run_async
from ..models import ExecutionOptions, Metadata, ParsedDocument

if TYPE_CHECKING:
    from datalab_sdk import AsyncDatalabClient


@dataclass(frozen=True)
class DatalabOptions:
    mode: str = "accurate"
    fresh: bool = False
    timeout: int = 7200


class DatalabParser:
    def __init__(self, client: "AsyncDatalabClient", options: DatalabOptions):
        self.client = client
        self.options = options

    @property
    def config(self) -> Metadata:
        return {
            "mode": self.options.mode,
            "sdk_version": version("datalab-python-sdk"),
            "api": "v1/convert",
            "skip_cache": self.options.fresh,
        }

    async def convert(self, path: Path) -> ParsedDocument:
        from datalab_sdk import ConvertOptions

        result = await self.client.convert(
            path,
            options=ConvertOptions(
                output_format="markdown", mode=self.options.mode, skip_cache=self.options.fresh
            ),
            max_polls=self.options.timeout,
            poll_interval=1,
        )
        if not result.success:
            raise RuntimeError(result.error or "Datalab returned success=false")
        return ParsedDocument(
            result.markdown,
            {
                "pages_processed": result.page_count,
                "versions": result.versions,
                "metadata": result.metadata,
                "cost_breakdown": result.cost_breakdown,
                "server_runtime": result.runtime,
            },
        )


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=("fast", "balanced", "accurate"), default="accurate")
    parser.add_argument(
        "--fresh", action="store_true", help="Bypass cached results for timing runs"
    )


def run(options: argparse.Namespace, paths: list[Path], key: str) -> int:
    from datalab_sdk import AsyncDatalabClient

    artifacts = RunArtifacts(options.output_dir)
    artifacts.prepare(options.overwrite)

    async def execute() -> int:
        async with AsyncDatalabClient(api_key=key, timeout=options.timeout) as client:
            adapter = DatalabParser(
                client, DatalabOptions(options.mode, options.fresh, options.timeout)
            )
            return await run_async(
                adapter, paths, artifacts, ExecutionOptions(options.timeout, options.concurrency)
            )

    return asyncio.run(execute())
