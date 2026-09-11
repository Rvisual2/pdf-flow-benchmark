"""The single list of available conversion commands."""

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType


@dataclass(frozen=True)
class ParserSpec:
    module: str
    description: str
    output_directory: str
    api_key: str | None = None
    concurrent: bool = False

    def load(self) -> ModuleType:
        return import_module(f"pdf_benchmark.parsers.{self.module}")


PARSERS = {
    "llamaparse": ParserSpec(
        "llamaparse",
        "LlamaParse v2 Agentic",
        "llamaparse",
        "LLAMA_CLOUD_API_KEY",
        concurrent=True,
    ),
    "datalab": ParserSpec(
        "datalab",
        "Datalab accurate conversion",
        "datalab",
        "DATALAB_API_KEY",
        concurrent=True,
    ),
    "reducto": ParserSpec(
        "reducto",
        "Reducto r-1 standard async parsing",
        "reducto",
        "REDUCTO_API_KEY",
        concurrent=True,
    ),
    "gemini": ParserSpec(
        "openrouter",
        "Sequential Gemini through OpenRouter",
        "gemini",
        "OPENROUTER_API_KEY",
    ),
    "pymupdf4llm": ParserSpec("pymupdf4llm", "Native PyMuPDF4LLM batches", "pymupdf4llm"),
    "docling": ParserSpec("docling", "Docling CPU with and without OCR", "docling"),
}
