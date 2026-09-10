"""Datalab Convert API, accurate mode, with bounded async directory conversion."""

import argparse
import asyncio
from importlib.metadata import version

from datalab_sdk import AsyncDatalabClient, ConvertOptions

try:
    from .remote_common import configure, input_files, prepare_output, require_key, run_documents
except ImportError:
    from remote_common import configure, input_files, prepare_output, require_key, run_documents


async def convert_document(client, path, args):
    result = await client.convert(path, options=ConvertOptions(
        output_format="markdown", mode=args.mode, skip_cache=args.fresh),
        max_polls=args.timeout, poll_interval=1)
    if not result.success:
        raise RuntimeError(result.error or "Datalab returned success=false")
    return result.markdown, {"pages_processed": result.page_count,
        "versions": result.versions, "metadata": result.metadata,
        "cost_breakdown": result.cost_breakdown, "server_runtime": result.runtime}


async def run(args, key, files):
    config = {"mode": args.mode, "sdk_version": version("datalab-python-sdk"),
              "api": "v1/convert", "skip_cache": args.fresh, "concurrency": args.concurrency}
    async with AsyncDatalabClient(api_key=key, timeout=args.timeout) as client:
        return await run_documents(files, args, lambda path: convert_document(client, path, args), config)


def main():
    parser = configure(argparse.ArgumentParser(description=__doc__), "datalab_results")
    parser.add_argument("--mode", choices=("fast", "balanced", "accurate"), default="accurate")
    parser.add_argument("--fresh", action="store_true", help="Bypass cached results for timing benchmarks")
    args = parser.parse_args()
    try:
        key = require_key("DATALAB_API_KEY")
        files = input_files(args)
        prepare_output(args.output_dir, files, args.overwrite)
        return asyncio.run(run(args, key, files))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
