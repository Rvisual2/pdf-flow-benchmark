# Flow-Aware PDF-to-Markdown Benchmark

This repository provides a benchmark for evaluating the accuracy of PDF-to-Markdown extraction tools. The main goal is to measure how well a tool can convert a complex, 2D PDF document into a 1D (text/markdown) format that **preserves the logical reading flow** of the content.

---

## The Core Problem

Large Language Models (LLMs) operate on a 1D sequence of tokens. They cannot natively understand the 2D spatial layout of a PDF. This "2D-to-1D" gap is a major bottleneck.

Existing benchmarks are often inadequate:
1.  **They focus on layout detection:** Datasets like DocLayNet are excellent for identifying *bounding boxes* (e.g., "this is a paragraph"), but not for connecting text blocks that form a single, logical flow (e.g., "this paragraph continues in the next column").
2.  **They assume a "total order":** Some benchmarks incorrectly assume a single, linear reading path for an entire document. In reality, complex documents have a **partial order**. For example, a main article and a sidebar can be read independently; neither logically precedes the other.

This benchmark is designed to measure a tool's ability to extract and correctly sequence these logically coherent "threads" of text.

---

## Benchmark Methodology

### 1. Dataset
The benchmark uses **127 PDF documents** sampled from the [DocLayNet dataset](https://github.com/DS4SD/DocLayNet), ensuring a diverse mix of challenging, real-world layouts. The documents are sourced from six distinct categories:
* Financial Reports
* Scientific Articles
* Laws & Regulations
* Government Tenders
* Manuals
* Patents

### 2. Ground Truth
To create a "ground truth" for evaluating text flow, for each document, we **manually copied multiple, random pieces of text in their correct logical reading order** to create "ground truth snippets" for each PDF. An evaluation metric can then check if a tool's output contains these snippets, in order, without being jumbled with text from other columns or sections. This method effectively tests the preservation of reading flow.

### 3. Evaluation Metric: FATA Score
We evaluate tools using a **Flow-Aware Text Accuracy (FATA) Score**. 

1.  For each ground truth text snippet (`truth_i`), we search the tool's entire markdown output to find the substring that is its "best match" (`best_match_i`).
2.  This "best match" is determined using the **Normalized Levenshtein distance** (a measure of character-level similarity).
3.  The final FATA score is a weighted average of the similarity scores for all snippets.
4.  A high FATA score (max 1.0) indicates the tool successfully extracted the text snippets with their internal order intact. A low score indicates the text was "mangled" (e.g., columns interleaved, text garbled), making it impossible to find a clean match for the ground truth snippets. These are converted to percentages, 100% being perfect.

---

## Initial Tools Evaluated

This benchmark was used to generate a comparative analysis of modern PDF extraction tools that produce markdown directly. The initial set of tools evaluated includes:

* LlamaParse
* Docling
* PyMuPDF4LLM
* Marker
* Reducto
* Google Gemini (multimodal)
---


# How to run this benchmark

```bash
uv sync
uv run prod_benchmark.py
```

## Updated converter runners

See the [2026-09-10 upgrade audit](docs/converter-upgrade.md) for versions,
API migrations, batch options, and official sources. Install the reviewed
versions with `uv sync --frozen`. Run `--help` on any generator for its options.

Local examples (new output folders preserve the committed baseline):

```bash
uv run markdown_gen/pymupdf4llm_markdown.py --output-dir runs/pymupdf4llm
uv run markdown_gen/docling_cpu.py --ocr both --workers 2 --batch-size 8 --output-dir runs/docling
```

Docling CPU's default paths remain `docling_ocr_results/` and
`docling_wocr_results/`. With `--ocr both --output-dir runs/docling`, outputs
instead go to `runs/docling/ocr/` and `runs/docling/no_ocr/`. Models download on
first use. PyMuPDF remains an internal dependency for extracting annotated
ground truth. PyMuPDF4LLM is a separate benchmark provider; the Docling GPU
runner is removed. PyMuPDF4LLM uses the current bundled Layout default, with
`--no-layout` available to disable it and `--no-ocr` to disable automatic OCR.
Automatic OCR is available in Layout mode. The runner uses native
`convert_batch()` with automatic worker sizing, streaming results, and persistent
workers. Override with `--workers 4` or `--no-persistent`. Native per-document
logs and outputs are retained under `native/`; flat Markdown for scoring is under
`markdowns/`. `--no-layout` uses native sequential execution because the library
does not propagate that setting to spawned worker processes.
Its default output directory remains `pymupdflayout_results/` for compatibility
with the committed dataset; its benchmark column is named `pymupdf4llm`.

Store the relevant API key in your environment or an ignored root `.env`:
`OPENROUTER_API_KEY`, `LLAMA_CLOUD_API_KEY`, `REDUCTO_API_KEY`, or
`DATALAB_API_KEY`. These commands invoke paid services:

```bash
uv run markdown_gen/gemini_markdown.py --output-dir runs/gemini
uv run markdown_gen/llamaprse_markdown.py --concurrency 5 --output-dir runs/llama
uv run markdown_gen/reducto_markdown.py --concurrency 5 --output-dir runs/reducto
uv run markdown_gen/datalab_markdown.py --concurrency 5 --output-dir runs/datalab
```

Gemini uses `google/gemini-3.8-flash` through OpenRouter, **one document at a
time**, with native PDF input. The same sequential runner supports other
native-PDF LLMs through `--model`. No Google Gemini API key is needed.
LlamaParse defaults to `agentic`; Datalab defaults to `accurate`; Reducto
uses `r-1`. LlamaParse supports `--server-batch` on Pro/Enterprise plans.
Reducto uses concurrent standard async jobs for immediate processing and saves
each result as it completes. Delayed discount queues are excluded.
Chunking is explicitly disabled: each PDF produces one full-document Markdown
string, with tables formatted as Markdown.
Use `--fresh` on LlamaParse or Datalab to bypass cached results for timing runs.

All runners support `--limit 2` for smoke checks. A run writes Markdown,
per-document `results.jsonl`, `run.json`, and total wall time in `duration.txt`.
Nonempty outputs require `--overwrite`; that option clears prior Markdown.
Failed/empty results are reported and cause a nonzero exit code.

## Evaluate custom runs

Repeat `--markdown-source NAME=DIRECTORY` to select the outputs to compare.
Each directory must contain `page_<number>.md` files. Both Docling pipelines
can appear as separate columns:

```bash
mkdir -p runs/reports
uv run prod_benchmark.py \
  --markdown-source docling_ocr=runs/docling/ocr/markdowns \
  --markdown-source docling_no_ocr=runs/docling/no_ocr/markdowns \
  --markdown-source pymupdf4llm=runs/pymupdf4llm/markdowns \
  --annotations-output runs/reports/annotations.json \
  --combined-output runs/reports/combined.json \
  --cleaned-output runs/reports/cleaned.json \
  --granular-output runs/reports/granular.csv \
  --filtered-output runs/reports/filtered.csv \
  --benchmark-output runs/reports/final.csv
```

The original scoring/filtering methodology is unchanged: rows missing a score
from any selected provider are excluded. Use complete conversion runs for
comparisons and inspect failures before interpreting scores.

## Offline validation

```bash
uv run python -m unittest discover -s tests -v
```

Tests exercise real SDK request serialization with mocked HTTP responses,
sequential LLM processing, bounded parser concurrency, partial failures, and
batch result mapping. They do not submit paid requests.
