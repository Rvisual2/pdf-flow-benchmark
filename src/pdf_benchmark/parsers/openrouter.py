"""Native PDF requests through OpenRouter with a sequential CLI runner."""

import argparse
import base64
import hashlib
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from ..artifacts import RunArtifacts
from ..execution import run_sequential
from ..models import Metadata, ParsedDocument

if TYPE_CHECKING:
    import httpx

MODEL_ID = "google/gemini-3.8-flash"
API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterParser:
    def __init__(self, client: "httpx.Client", prompt: str, model: str = MODEL_ID):
        self.client = client
        self.prompt = prompt
        self.model = model

    @property
    def config(self) -> Metadata:
        return {
            "model": self.model,
            "gateway": "openrouter",
            "pdf_engine": "native",
            "prompt_sha256": hashlib.sha256(self.prompt.encode()).hexdigest(),
        }

    def convert(self, path: Path) -> ParsedDocument:
        encoded_pdf = base64.b64encode(path.read_bytes()).decode("ascii")
        response = self.client.post(
            API_URL,
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.prompt},
                            {
                                "type": "file",
                                "file": {
                                    "filename": path.name,
                                    "file_data": f"data:application/pdf;base64,{encoded_pdf}",
                                },
                            },
                        ],
                    }
                ],
                "plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}],
                "provider": {"require_parameters": True},
                "stream": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise RuntimeError(str(payload["error"]))
        choice = payload["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError(f"Incomplete generation: {choice.get('finish_reason')}")
        return ParsedDocument(
            choice["message"]["content"],
            {
                "generation_id": payload.get("id"),
                "model": payload.get("model"),
                "provider": payload.get("provider"),
                "usage": payload.get("usage"),
            },
        )


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model", default=MODEL_ID, help="OpenRouter model ID with native PDF support"
    )
    parser.add_argument("--prompt", type=Path, help="Override the bundled PDF-to-Markdown prompt")


def run(options: argparse.Namespace, paths: list[Path], key: str) -> int:
    import httpx

    prompt = (
        options.prompt.read_text(encoding="utf-8")
        if options.prompt
        else files("pdf_benchmark")
        .joinpath("resources/pdf_to_markdown.md")
        .read_text(encoding="utf-8")
    )
    artifacts = RunArtifacts(options.output_dir)
    artifacts.prepare(options.overwrite)
    with httpx.Client(
        headers={"Authorization": f"Bearer {key}"}, timeout=options.timeout
    ) as client:
        return run_sequential(OpenRouterParser(client, prompt, options.model), paths, artifacts)
