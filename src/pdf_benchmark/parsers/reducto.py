"""Reducto r-1: standard async jobs and whole-document Markdown."""

import argparse
import asyncio
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

from ..artifacts import RunArtifacts
from ..execution import run_async
from ..models import ExecutionOptions, Metadata, ParsedDocument

if TYPE_CHECKING:
    import httpx
    from reducto import AsyncReducto


class ReductoParser:
    def __init__(
        self, client: "AsyncReducto", downloads: "httpx.AsyncClient", artifacts: RunArtifacts
    ):
        self.client = client
        self.downloads = downloads
        self.artifacts = artifacts

    @property
    def config(self) -> Metadata:
        return {
            "model": "r-1",
            "api": "v3",
            "sdk_version": version("reductoai"),
            "queue": "standard",
            "chunk_mode": "disabled",
            "table_output_format": "md",
        }

    async def convert(self, path: Path) -> ParsedDocument:
        uploaded = await self.client.upload(file=path)
        job = await self.client.parse.run_job(
            input=uploaded.file_id,
            settings={"model": "r-1"},
            retrieval={"chunking": {"chunk_mode": "disabled"}},
            formatting={"table_output_format": "md"},
            queue_priority="standard",
        )
        self.artifacts.submission(
            {"file": str(path), "job_id": job.job_id, "queue": "standard", "model": "r-1"}
        )
        while True:
            status = await self.client.job.get(job.job_id)
            if status.status == "Completed":
                if status.result is None:
                    raise RuntimeError("Completed job has no result")
                result = status.result
                return ParsedDocument(
                    await self._markdown(result),
                    {
                        "job_id": job.job_id,
                        "server_duration": result.duration,
                        "usage": result.usage.model_dump(mode="json"),
                    },
                )
            if status.status == "Failed":
                raise RuntimeError(
                    f"Reducto job {job.job_id} failed: {status.reason or status.error}"
                )
            await asyncio.sleep(2)

    async def _markdown(self, result) -> str:
        payload = result.result.model_dump(mode="json")
        if payload["type"] == "url":
            # Signed result URLs must not receive the API client's authorization.
            response = await self.downloads.get(payload["url"])
            response.raise_for_status()
            payload = response.json()
        # Even unchunked Markdown is wrapped in one item by the API.
        documents = payload if isinstance(payload, list) else payload["chunks"]
        if len(documents) != 1:
            raise ValueError("Expected one full-document Markdown result with chunking disabled")
        return documents[0]["content"]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """All supported settings are fixed or supplied by the common CLI."""


def run(options: argparse.Namespace, paths: list[Path], key: str) -> int:
    import httpx
    from reducto import AsyncReducto

    artifacts = RunArtifacts(options.output_dir)
    artifacts.prepare(options.overwrite)

    async def execute() -> int:
        async with (
            AsyncReducto(api_key=key, timeout=120) as client,
            httpx.AsyncClient(timeout=120) as downloads,
        ):
            return await run_async(
                ReductoParser(client, downloads, artifacts),
                paths,
                artifacts,
                ExecutionOptions(options.timeout, options.concurrency),
            )

    return asyncio.run(execute())
