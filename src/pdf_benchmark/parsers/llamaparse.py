"""LlamaParse v2 adapter with optional native directory submission."""

import argparse
import asyncio
import time
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator

from ..artifacts import RunArtifacts
from ..execution import failure, run_async, run_async_batch
from ..models import DocumentOutcome, ExecutionOptions, Metadata, ParsedDocument

if TYPE_CHECKING:
    from llama_cloud import AsyncLlamaCloud
    from llama_cloud.types.parsing_get_response import ParsingGetResponse


@dataclass(frozen=True)
class LlamaParseOptions:
    tier: str = "agentic"
    parser_version: str = "latest"
    fresh: bool = False


def extract_markdown(result: "ParsingGetResponse") -> ParsedDocument:
    if result.job.status != "COMPLETED":
        raise RuntimeError(f"LlamaParse job {result.job.id}: {result.job.status}")
    pages = result.markdown.pages if result.markdown else []
    if not pages or any(not page.success for page in pages):
        raise ValueError("Missing Markdown pages or partial page failure")
    return ParsedDocument(
        "\n\n".join(page.markdown for page in sorted(pages, key=lambda page: page.page_number)),
        {
            "job_id": result.job.id,
            "pages_processed": len(pages),
            "usage": result.job.usage.model_dump(mode="json") if result.job.usage else None,
            "job_metadata": result.job_metadata,
        },
    )


class LlamaParseParser:
    def __init__(
        self, client: "AsyncLlamaCloud", artifacts: RunArtifacts, options: LlamaParseOptions
    ):
        self.client = client
        self.artifacts = artifacts
        self.options = options
        self.parser_version = options.parser_version

    async def prepare(self) -> None:
        versions = await self.client.parsing.list_versions()
        if self.parser_version == "latest":
            self.parser_version = getattr(versions.latest, self.options.tier)
        available = getattr(versions, self.options.tier)
        if self.parser_version not in available:
            raise ValueError(
                f"Version {self.parser_version} is unavailable for {self.options.tier}; available: {available}"
            )

    @property
    def config(self) -> Metadata:
        return {
            "api": "v2",
            "tier": self.options.tier,
            "parser_version": self.parser_version,
            "sdk_version": version("llama-cloud"),
            "disable_cache": self.options.fresh,
            "execution": "concurrent",
        }

    async def poll(self, job_id: str) -> ParsedDocument:
        while True:
            result = await self.client.parsing.get(job_id, expand=["markdown", "job_metadata"])
            if result.job.status in {"COMPLETED", "FAILED", "CANCELLED"}:
                return extract_markdown(result)
            await asyncio.sleep(2)

    async def convert(self, path: Path) -> ParsedDocument:
        job = await self.client.parsing.create(
            upload_file=path,
            tier=self.options.tier,
            version=self.parser_version,
            disable_cache=self.options.fresh,
        )
        self.artifacts.submission(
            {
                "file": str(path),
                "job_id": job.id,
                "tier": self.options.tier,
                "version": self.parser_version,
            }
        )
        return await self.poll(job.id)

    async def convert_many(self, paths: list[Path]) -> AsyncIterator[DocumentOutcome]:
        configuration = await self.client.configurations.create(
            name=f"pdf-benchmark-{int(time.time())}",
            parameters={
                "product_type": "parse_v2",
                "tier": self.options.tier,
                "version": self.parser_version,
                "disable_cache": self.options.fresh,
            },
        )
        directory = await self.client.beta.directories.create(
            name="pdf-benchmark", type="ephemeral"
        )
        self.artifacts.submission(
            {"configuration_id": configuration.id, "directory_id": directory.id}
        )
        paths_by_id = {}
        for path in paths:
            uploaded = await self.client.beta.directories.files.upload(
                directory.id, upload_file=path, display_name=path.name
            )
            paths_by_id[uploaded.id] = path
            self.artifacts.submission({"file": str(path), "directory_file_id": uploaded.id})
        batch = await self.client.batches.create(
            source_directory_id=directory.id,
            config={"job": {"type": "parse_v2", "configuration_id": configuration.id}},
        )
        self.artifacts.submission({"batch_id": batch.id})
        while True:
            batch = await self.client.batches.get(batch.id, expand=["results"])
            if batch.status in {"COMPLETED", "FAILED", "CANCELLED"}:
                break
            await asyncio.sleep(5)
        outcomes = {item.source_directory_file_id: item for item in batch.results or []}
        for file_id, path in paths_by_id.items():
            try:
                result = outcomes.get(file_id)
                if result is None or result.error_message or result.job_reference is None:
                    raise RuntimeError(
                        result.error_message
                        if result and result.error_message
                        else f"No parse result; batch {batch.status}"
                    )
                document = await self.poll(result.job_reference.id)
                yield DocumentOutcome(
                    path,
                    ParsedDocument(document.markdown, {**document.metadata, "batch_id": batch.id}),
                )
            except Exception as error:
                yield failure(path, error)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--tier", choices=("fast", "cost_effective", "agentic", "agentic_plus"), default="agentic"
    )
    parser.add_argument(
        "--parser-version", default="latest", help="Resolve latest once for the selected tier"
    )
    parser.add_argument("--fresh", action="store_true", help="Bypass the parser cache")
    parser.add_argument(
        "--server-batch",
        action="store_true",
        help="Native directory batches; requires Pro/Enterprise",
    )


def run(options: argparse.Namespace, paths: list[Path], key: str) -> int:
    from llama_cloud import AsyncLlamaCloud

    artifacts = RunArtifacts(options.output_dir)
    artifacts.prepare(options.overwrite)

    async def execute() -> int:
        async with AsyncLlamaCloud(api_key=key, timeout=120) as client:
            adapter = LlamaParseParser(
                client,
                artifacts,
                LlamaParseOptions(options.tier, options.parser_version, options.fresh),
            )
            await adapter.prepare()
            execution = ExecutionOptions(options.timeout, options.concurrency)
            artifacts.write_json(
                "config.json",
                {
                    **adapter.config,
                    "concurrency": execution.concurrency,
                    "execution": "server_batch" if options.server_batch else "concurrent",
                },
            )
            runner = run_async_batch if options.server_batch else run_async
            return await runner(adapter, paths, artifacts, execution)

    return asyncio.run(execute())
