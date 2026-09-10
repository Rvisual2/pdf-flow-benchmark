# Repository Guidelines

## Project Structure & Module Organization

This Python repository benchmarks PDF-to-Markdown tools using Flow-Aware Text Accuracy (FATA).

- `prod_benchmark.py` extracts annotations, combines OCR ground truth, scores Markdown, and writes reports.
- `benchmark_data/utils.py` implements fuzzy matching and normalized Levenshtein distance. Other files in `benchmark_data/` contain annotated PDFs, `Pictures.xlsx`, page mappings, and intermediate JSON.
- `PDFs/` contains converter inputs; `markdown_gen/` contains provider-specific generation scripts and `ai_prompt.md`.
- Provider directories such as `docling_ocr_results/` contain `markdowns/page_<number>.md` and run metadata. Root CSV files contain benchmark reports.

## Build, Test, and Development Commands

Use Python 3.13 or newer and run commands from the repository root:

- `uv sync` installs project and development dependencies.
- `uv run prod_benchmark.py --help` lists input, output, filtering, and logging options.
- `uv run prod_benchmark.py --verbose` evaluates existing provider Markdown against ground truth and rewrites reports and intermediate files.
- `uv run markdown_gen/docling_cpu.py --ocr both --output-dir runs/docling` generates both Docling CPU variants from `PDFs/`.
- `bash compare_folders.sh <before_dir> <after_dir> differences.txt` compares generated files and saves a diff report.

There is no separate build step. Use `--output-dir runs/<tool>` to preserve baseline results and `--limit 2` for smoke checks. Both Docling OCR modes and the PyMuPDF4LLM benchmark remain available. See `docs/converter-upgrade.md` for API versions and batch behavior.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` functions and variables, and `UPPER_SNAKE_CASE` configuration constants. Follow nearby code, add type hints and concise docstrings for reusable functions, and write text outputs as UTF-8. Preserve `page_<number>` identifiers across PDFs, Markdown, and mappings. No formatter or linter is configured.

## Testing Guidelines

Run `uv run python -m unittest discover -s tests -v` for offline converter tests; no coverage threshold is configured. For scoring changes, rerun against existing Markdown and compare granular, filtered, and final reports. Explain score changes and inspect failures. Use `--markdown-source NAME=DIRECTORY` for custom runs. Keep unrelated regenerated artifacts out of commits.

## Commit & Pull Request Guidelines

History uses short descriptive subjects, with occasional `feat:` prefixes; no consistent prefix convention exists. Use a concise imperative subject. Pull requests should describe the change, link relevant issues, list validation commands, and explain benchmark differences. For regenerated results, record tool versions, model, OCR settings, and hardware.

## Configuration & Credentials

Keep API keys in environment variables or ignored `.env` files. Provider scripts use `OPENROUTER_API_KEY`, `LLAMA_CLOUD_API_KEY`, `REDUCTO_API_KEY`, and `DATALAB_API_KEY`. Gemini and other direct LLMs must process one document at a time. Never commit credentials.
