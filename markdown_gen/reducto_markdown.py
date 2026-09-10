"""Reducto V3 r-1 parsing with concurrent, immediate-processing async jobs."""

import argparse
import asyncio
from importlib.metadata import version

import httpx
from reducto import AsyncReducto

try:
    from .remote_common import configure, input_files, prepare_output, require_key, run_documents, save_submission
except ImportError:
    from remote_common import configure, input_files, prepare_output, require_key, run_documents, save_submission


async def result_markdown(result, download_client):
    payload = result.result.model_dump(mode="json")
    if payload["type"] == "url":
        response = await download_client.get(payload["url"])
        response.raise_for_status()
        payload = response.json()
    # Reducto wraps whole-document Markdown in one item even with chunking disabled.
    chunks = payload if isinstance(payload, list) else payload["chunks"]
    if len(chunks) != 1:
        raise ValueError("Expected one full-document Markdown result with chunking disabled")
    return chunks[0]["content"]


async def convert_document(client, download_client, path, args):
    uploaded = await client.upload(file=path)
    job = await client.parse.run_job(
        input=uploaded.file_id, settings={"model": "r-1"},
        retrieval={"chunking": {"chunk_mode": "disabled"}},
        formatting={"table_output_format": "md"}, queue_priority="standard")
    save_submission(args.output_dir, {"file": str(path), "job_id": job.job_id,
                                     "queue": "standard", "model": "r-1"})
    while True:
        status = await client.job.get(job.job_id)
        if status.status == "Completed":
            if status.result is None:
                raise RuntimeError("Completed job has no result")
            result = status.result
            return await result_markdown(result, download_client), {
                "job_id": job.job_id, "server_duration": result.duration,
                "usage": result.usage.model_dump(mode="json"),
            }
        if status.status == "Failed":
            raise RuntimeError(f"Reducto job {job.job_id} failed: {status.reason or status.error}")
        await asyncio.sleep(2)


async def run(args, key, files):
    config = {"model": "r-1", "api": "v3", "sdk_version": version("reductoai"),
              "queue": "standard", "chunk_mode": "disabled",
              "table_output_format": "md", "concurrency": args.concurrency}
    async with AsyncReducto(api_key=key, timeout=120) as client, httpx.AsyncClient(timeout=120) as download:
        return await run_documents(files, args, lambda path: convert_document(client, download, path, args), config)


def main():
    parser = configure(argparse.ArgumentParser(description=__doc__), "reducto_results")
    args = parser.parse_args()
    try:
        key = require_key("REDUCTO_API_KEY")
        files = input_files(args)
        prepare_output(args.output_dir, files, args.overwrite)
        return asyncio.run(run(args, key, files))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
