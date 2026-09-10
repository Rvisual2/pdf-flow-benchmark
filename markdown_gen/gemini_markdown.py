"""Sequential native PDF conversion with Gemini 3.8 Flash through OpenRouter."""

import argparse
import base64
import hashlib
import time
from pathlib import Path

import httpx

try:
    from .remote_common import (ROOT, configure, finish_run, input_files, prepare_output,
                                require_key, save_markdown, write_record)
except ImportError:
    from remote_common import (ROOT, configure, finish_run, input_files, prepare_output,
                               require_key, save_markdown, write_record)

MODEL_ID = "google/gemini-3.8-flash"
API_URL = "https://openrouter.ai/api/v1/chat/completions"


def request_body(path: Path, prompt: str, model: str) -> dict:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "file", "file": {"filename": path.name,
                "file_data": f"data:application/pdf;base64,{data}"}},
        ]}],
        "plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}],
        "provider": {"require_parameters": True},
        "stream": False,
    }


def convert_document(client, path, prompt, model):
    response = client.post(API_URL, json=request_body(path, prompt, model))
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    choice = data["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise ValueError(f"Incomplete generation: {choice.get('finish_reason')}")
    return choice["message"]["content"], {
        "generation_id": data.get("id"), "model": data.get("model"),
        "provider": data.get("provider"), "usage": data.get("usage"),
    }


def run_sequential(files, args, client, prompt):
    """Finish one document before sending the next; intentionally no task pool."""
    started = time.perf_counter()
    config = {"model": args.model, "gateway": "openrouter", "pdf_engine": "native",
              "concurrency": 1, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
    records = []
    for path in files:
        document_start = time.perf_counter()
        record = {"file": str(path), "success": False, "config": config}
        try:
            markdown, metadata = convert_document(client, path, prompt, args.model)
            record.update(metadata)
            record["markdown_file"] = save_markdown(args.output_dir, path, markdown)
            record["success"] = True
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        record["duration_seconds"] = time.perf_counter() - document_start
        write_record(args.output_dir, record)
        records.append(record)
    return finish_run(args.output_dir, records, time.perf_counter() - started, config)


def main():
    parser = configure(argparse.ArgumentParser(description=__doc__), "gemini_results", concurrent=False)
    parser.add_argument("--model", default=MODEL_ID, help="OpenRouter model ID with native PDF support")
    parser.add_argument("--prompt", type=Path, default=Path(__file__).with_name("ai_prompt.md"))
    args = parser.parse_args()
    try:
        key = require_key("OPENROUTER_API_KEY")
        files = input_files(args)
        prompt = args.prompt.read_text(encoding="utf-8")
        prepare_output(args.output_dir, files, args.overwrite)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=args.timeout) as client:
        return run_sequential(files, args, client, prompt)


if __name__ == "__main__":
    raise SystemExit(main())
