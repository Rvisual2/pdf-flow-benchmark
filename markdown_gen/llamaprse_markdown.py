"""LlamaParse v2 Agentic; async documents or native directory batches."""

import argparse
import asyncio
import json
import time
from importlib.metadata import version

from llama_cloud import AsyncLlamaCloud

try:
    from .remote_common import (configure, finish_run, input_files, prepare_output, require_key,
                                run_documents, save_markdown, save_submission, write_record)
except ImportError:
    from remote_common import (configure, finish_run, input_files, prepare_output, require_key,
                               run_documents, save_markdown, save_submission, write_record)


def extract_markdown(result):
    if result.job.status != "COMPLETED":
        raise RuntimeError(f"LlamaParse job {result.job.id}: {result.job.status}")
    pages = result.markdown.pages if result.markdown else []
    if not pages or any(not page.success for page in pages):
        raise ValueError("Missing Markdown pages or partial page failure")
    markdown = "\n\n".join(page.markdown for page in sorted(pages, key=lambda page: page.page_number))
    return markdown, {"job_id": result.job.id, "pages_processed": len(pages),
        "usage": result.job.usage.model_dump(mode="json") if result.job.usage else None,
        "job_metadata": result.job_metadata}


async def poll_parse(client, job_id):
    while True:
        result = await client.parsing.get(job_id, expand=["markdown", "job_metadata"])
        if result.job.status in {"COMPLETED", "FAILED", "CANCELLED"}:
            return extract_markdown(result)
        await asyncio.sleep(2)


async def convert_document(client, path, args, parser_version):
    job = await client.parsing.create(upload_file=path, tier=args.tier,
                                     version=parser_version, disable_cache=args.fresh)
    save_submission(args.output_dir, {"file": str(path), "job_id": job.id,
                                     "tier": args.tier, "version": parser_version})
    return await poll_parse(client, job.id)


async def run_server_batch(client, files, args, config):
    """Use the current directory/configuration batch API (Pro/Enterprise plans)."""
    started = time.perf_counter()
    records = []
    paths_by_id = {}
    try:
        async with asyncio.timeout(args.timeout):
            configuration = await client.configurations.create(
                name=f"pdf-benchmark-{int(time.time())}",
                parameters={"product_type": "parse_v2", "tier": args.tier,
                            "version": config["parser_version"], "disable_cache": args.fresh})
            directory = await client.beta.directories.create(name="pdf-benchmark", type="ephemeral")
            save_submission(args.output_dir, {"configuration_id": configuration.id, "directory_id": directory.id})
            # Uploads are sequential; the service schedules the directory's parse jobs.
            for path in files:
                uploaded = await client.beta.directories.files.upload(directory.id, upload_file=path, display_name=path.name)
                paths_by_id[uploaded.id] = path
                save_submission(args.output_dir, {"file": str(path), "directory_file_id": uploaded.id})
            batch = await client.batches.create(source_directory_id=directory.id, config={
                "job": {"type": "parse_v2", "configuration_id": configuration.id}})
            save_submission(args.output_dir, {"batch_id": batch.id})
            while True:
                batch = await client.batches.get(batch.id, expand=["results"])
                if batch.status in {"COMPLETED", "FAILED", "CANCELLED"}:
                    break
                await asyncio.sleep(5)
            # Match by directory file ID; never rely on API result ordering.
            outcomes = {item.source_directory_file_id: item for item in batch.results or []}
            for file_id, path in paths_by_id.items():
                record = {"file": str(path), "success": False, "config": config, "batch_id": batch.id}
                try:
                    item = outcomes.get(file_id)
                    if item is None or item.error_message or item.job_reference is None:
                        raise RuntimeError(item.error_message if item and item.error_message else f"No parse result; batch {batch.status}")
                    markdown, metadata = await poll_parse(client, item.job_reference.id)
                    record.update(metadata)
                    record["markdown_file"] = save_markdown(args.output_dir, path, markdown)
                    record["success"] = True
                except Exception as exc:
                    record["error"] = str(exc)
                write_record(args.output_dir, record)
                records.append(record)
    except Exception as exc:
        completed = {record["file"] for record in records}
        for path in files:
            if str(path) not in completed:
                record = {"file": str(path), "success": False, "config": config,
                          "error": f"{type(exc).__name__}: {exc}; remote IDs are in submissions.jsonl"}
                write_record(args.output_dir, record)
                records.append(record)
    return finish_run(args.output_dir, records, time.perf_counter() - started, config)


async def run(args, key, files):
    async with AsyncLlamaCloud(api_key=key, timeout=120) as client:
        versions = await client.parsing.list_versions()
        parser_version = getattr(versions.latest, args.tier) if args.parser_version == "latest" else args.parser_version
        if parser_version not in getattr(versions, args.tier):
            raise ValueError(f"Version {parser_version} is unavailable for {args.tier}; available: {getattr(versions, args.tier)}")
        config = {"api": "v2", "tier": args.tier, "parser_version": parser_version,
                  "sdk_version": version("llama-cloud"), "disable_cache": args.fresh,
                  "execution": "server_batch" if args.server_batch else "concurrent",
                  "concurrency": args.concurrency}
        (args.output_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        if args.server_batch:
            return await run_server_batch(client, files, args, config)
        return await run_documents(files, args, lambda path: convert_document(client, path, args, parser_version), config)


def main():
    parser = configure(argparse.ArgumentParser(description=__doc__), "llama_parse_results")
    parser.add_argument("--tier", choices=("fast", "cost_effective", "agentic", "agentic_plus"), default="agentic")
    parser.add_argument("--parser-version", default="latest", help="Resolve latest to a published date once per run")
    parser.add_argument("--fresh", action="store_true", help="Bypass the parser cache")
    parser.add_argument("--server-batch", action="store_true", help="Native directory batch API; requires Pro/Enterprise")
    args = parser.parse_args()
    try:
        key = require_key("LLAMA_CLOUD_API_KEY")
        files = input_files(args)
        prepare_output(args.output_dir, files, args.overwrite)
        return asyncio.run(run(args, key, files))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
