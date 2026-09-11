# Flow-Aware PDF-to-Markdown Benchmark

A PDF extractor can recover every word on a page and still produce text that is
hard to read. Interleave two columns, insert a sidebar halfway through a sentence,
or separate the beginning of a paragraph from its continuation, and the passage
loses its meaning. For RAG and other workflows that consume extracted text,
keeping those passages intact matters.

This benchmark asks: **does the tool preserve each passage as coherent, correctly
ordered text in its Markdown output?** Flow-Aware Text Accuracy (FATA) scores
reference passages against extracted Markdown. The dashboard lets you follow a
score down to the text difference and the original PDF, so you can see what went
wrong—and check whether the reference itself needs correcting.

## Latest leaderboard

Latest published run: **2026-09-10** (`all-tools-2026-09-10`). Overall FATA on
445 retained snippets across 121 pages; higher is better.

| Tool | Total FATA (%) |
| --- | ---: |
| Gemini 3.8 Flash (OpenRouter) | 92.15 |
| Datalab Accurate | 88.23 |
| Docling CPU with OCR | 86.66 |
| Reducto r-1 | 86.56 |
| LlamaParse Agentic | 86.55 |
| Docling CPU without OCR | 85.68 |
| PyMuPDF4LLM | 84.69 |

These are the same totals shown in the [dashboard](apps/dashboard/README.md).
The scoring and sample-selection rules below explain how to interpret them.

## What “flow-aware” means

A complex page can have several valid reading paths. Two independent articles
can appear in either order in the output; the sentences *within* each article
still need to stay together.

Consider a page with two independent columns:

| Left column | Right column |
| --- | --- |
| The pump stopped. | The sensor failed. |
| Replace the seal. | Check the cable. |

Both of these preserve the passages:

```text
The pump stopped. Replace the seal.
The sensor failed. Check the cable.
```

```text
The sensor failed. Check the cable.
The pump stopped. Replace the seal.
```

Reading across the rows breaks them:

```text
The pump stopped. The sensor failed. Replace the seal. Check the cable.
```

FATA matches each reference passage independently within the output. It therefore
allows independent passages to move while penalizing text errors and disruptions
inside a passage. The focus is **prose extraction and reading flow**. Table
structure, figure understanding, visual layout fidelity, and downstream RAG
quality need their own evaluations.

## What is measured

The current collection contains **127 single-page PDFs**. It includes DocLayNet
samples from financial reports, scientific articles, laws, government tenders,
manuals, and patents, plus OCR examples. Numbered highlights in annotated PDFs
identify passage segments in reading order; an OCR workbook supplies additional
references. The evaluator reads these as versioned JSON snippets with source IDs.

For every reference snippet and selected tool:

1. Find a candidate matching substring in that page's Markdown using RapidFuzz's
   `partial_ratio_alignment`.
2. Compute the character-level Levenshtein edit distance between the reference
   and that substring, normalized by the longer string's length.
3. Aggregate the retained snippet distances into category and overall accuracy.

```text
distance = edit_distance(reference, match) / max(len(reference), len(match))
FATA (%) = 100 × (1 − mean retained snippet distance)
```

A perfect match scores 100%. Each retained snippet has equal weight; the overall
score weights category means by their snippet counts, not by passage length.
Matching uses fuzzy alignment rather than an exhaustive search for the substring
with the lowest Levenshtein distance. Markdown syntax, HTML, and whitespace are
scored as written.

### Interpreting a score

By default, a snippet contributes to the final score only when every selected tool
has a score and at least one tool has a normalized distance **below 0.25**. This means missing or empty outputs and passages that all
tools struggle with can disappear from the summary. Changing the tool selection
can also change the scored sample. Compare the same tools, references, and filter
settings, and inspect conversion failures alongside the score.

The references contain known extraction and reading-order errors. A low score is
a starting point for investigation; use the PDF to distinguish a parser failure
from a reference problem. A high score means the retained reference passages were
preserved well. It does not establish that every part of the page was extracted
correctly, or penalize all extra text outside the matched passages.

## Start with the dashboard

The [React dashboard](apps/dashboard/README.md) opens the published comparison of
seven parser pipelines without running conversions. Use it to:

- Find a tool's weakest or strongest documents, filter by category, or find pages
  where any or every tool falls within a score range.
- Sort by tool disagreement to investigate where parsers behave differently.
- Diff a ground-truth snippet against the evaluator's exact selected match.
- Inspect the original **PDF + Markdown** side by side, switch tools, or diff two
  complete tool outputs. Share the current selection through its URL.

With Node.js 22.12+ (or 24+) and npm, run from the repository root:

```bash
cd apps/dashboard
npm ci
npm run dev
```

Open the URL printed by Vite. The dashboard reads published artifacts anonymously;
no Python environment or provider API keys are needed. `npm run build` creates a
static build. To display your own evaluated runs, follow the dashboard guide's
[publish and export workflow](apps/dashboard/README.md#refresh-the-published-snapshot).

## Set up the benchmark

Use Python 3.13 or newer and `uv`. Run these commands from the repository root:

```bash
uv sync --frozen
uv run pdf-benchmark data download
uv run pdf-benchmark parsers list
```

This installs the package and CLI, restores the input PDFs and reference sources,
and lists the available tools and credential presence. Downloads and inspection
commands require no provider keys. Local converters download models on first use;
`uv.lock` pins the dependency set.

### Run a local smoke check

Generate Markdown for two PDFs with PyMuPDF4LLM, then score it:

```bash
uv run pdf-benchmark convert pymupdf4llm \
  --limit 2 --output-dir results/runs/smoke
uv run pdf-benchmark evaluate \
  --markdown-source pymupdf4llm=results/runs/smoke/markdowns \
  --output-dir results/runs/smoke-evaluation
uv run pdf-benchmark results scores results/runs/smoke-evaluation
```

This uses no paid API. It checks the conversion-to-report workflow on a small
sample; remove `--limit 2` and choose a fresh output directory for a full run.
The filtering rules above still apply to a single-tool evaluation.

To inspect an existing published run without invoking a parser:

```bash
uv run pdf-benchmark results releases
uv run pdf-benchmark results download --release all-tools-2026-09-10 \
  --directory results/runs/published
```

## Run and compare tools

Every parser uses the same command structure:

```bash
uv run pdf-benchmark convert llamaparse --output-dir results/runs/llamaparse
uv run pdf-benchmark convert datalab --output-dir results/runs/datalab
uv run pdf-benchmark convert reducto --output-dir results/runs/reducto
uv run pdf-benchmark convert gemini --output-dir results/runs/gemini
uv run pdf-benchmark convert pymupdf4llm --workers 2 --output-dir results/runs/pymupdf4llm
uv run pdf-benchmark convert docling --ocr both --workers 2 --output-dir results/runs/docling
```

Download inputs first with `uv run pdf-benchmark data download`.
The first four commands invoke paid services. Set credentials in your environment
or an ignored root `.env` file:

| Parser | Default configuration | Credential |
| --- | --- | --- |
| LlamaParse | v2 `agentic`, latest published date for that tier | `LLAMA_CLOUD_API_KEY` |
| Datalab | `accurate` | `DATALAB_API_KEY` |
| Reducto | V3 `r-1`, standard queue, chunking disabled | `REDUCTO_API_KEY` |
| Gemini | OpenRouter `google/gemini-3.8-flash`, native PDF input | `OPENROUTER_API_KEY` |
| PyMuPDF4LLM | Native `convert_batch()`, bundled Layout and OCR | None |
| Docling | CPU, separate OCR and no-OCR pipelines | None |

Common options include `--input-dir data/pdfs`, `--limit 2` for a smoke check, and
`--overwrite` to replace an existing run. Use `<parser> --help` for all options.

LlamaParse, Datalab, and Reducto accept `--concurrency` (default 5). Gemini's
current runner processes one document at a time; execution policy is separate
from parsing. LlamaParse optionally supports `--server-batch` and an explicit
`--parser-version`; LlamaParse and Datalab support `--fresh` for timing runs.
Reducto uses immediate standard async jobs and saves whole-document Markdown,
including Markdown tables. Delayed discount queues are not used.

PyMuPDF4LLM supports `--no-layout`, `--no-ocr`, and `--no-persistent`.
Without Layout it uses one worker because the native worker pool does not
propagate that setting. Docling accepts `--ocr on`, `off`, or `both`, plus
`--batch-size`, `--page-batch-size`, and `--threads`.

A run contains `markdowns/page_<number>.md`, `results.jsonl`, `run.json`, and
`duration.txt`. PyMuPDF4LLM also retains native outputs under `native/`.
Docling's `--ocr both --output-dir results/runs/docling` creates `ocr/` and `no_ocr/`.
Nonempty destinations require `--overwrite`, which clears old Markdown and run
summaries. Remote submission IDs remain in `submissions.jsonl`. Failed or empty
conversions produce a nonzero exit code; successful documents are preserved.

Use `pdf-benchmark convert <parser>` for every provider; `python -m pdf_benchmark`
is also available after installation. New conversions default to `results/runs/<parser>/`.

## Evaluate results

Select the runs to evaluate with repeated `--markdown-source NAME=DIRECTORY`
arguments. At least one source is required:

```bash
uv run pdf-benchmark evaluate \
  --markdown-source llamaparse=results/runs/llamaparse/markdowns \
  --markdown-source reducto=results/runs/reducto/markdowns \
  --markdown-source docling_ocr=results/runs/docling/ocr/markdowns \
  --markdown-source docling_no_ocr=results/runs/docling/no_ocr/markdowns \
  --output-dir results/runs/evaluation
```

The output directory contains:

- `scores.csv`: a simple `tool,score_percent` table.
- `scores_by_category.csv`: category scores and the weighted mean.
- `granular.csv`: snippet distances and matched text after excluding missing scores,
  before the distance threshold.
- `filtered.csv`: the retained snippets used in the final score.
- `ground_truth.json`: versioned reference snippets with source IDs.

Evaluation reads `data/ground_truth/references.json` by default and scores only
the Markdown sources you select. To evaluate a separately reviewed reference file:

```bash
uv run pdf-benchmark evaluate \
  --ground-truth-input results/runs/evaluation/ground_truth.json \
  --markdown-source reducto=results/runs/reducto/markdowns \
  --output-dir results/runs/reviewed-evaluation
```

Use `--rebuild-ground-truth` to regenerate references from annotated PDFs and
`ocr.xlsx`. Reports default to `results/runs/evaluation/`; set `--output-dir` to choose
another directory. See [ground-truth editing](docs/ground-truth.md) for the schema
and provenance. Evaluation never overwrites the source references by default.

## Publish artifacts

PDFs and raw Markdown with provenance live in Google Cloud Storage. Downloads are
anonymous; publishing uses the owner's `gcloud auth login` credentials.

```bash
uv run pdf-benchmark data upload --label dataset-v1
uv run pdf-benchmark results upload results/runs/reducto --label reducto-v1
uv run pdf-benchmark results download --release all-tools-2026-09-10 \
  --directory results/runs/published-september
```

See [cloud artifacts](docs/cloud-artifacts.md) for manifests, integrity checks,
provenance, and access permissions. Public users cannot list or write objects.

## Code organization and extension

```text
src/pdf_benchmark/          Installable Python package
  parsers/                 Provider adapters and their options
  evaluation/              References, source loaders, matching, scoring
  resources/               Bundled PDF-to-Markdown prompt
  cli.py, registry.py       Commands and lazy parser registration
  execution.py, models.py   Execution policies and shared result contracts
  artifacts.py, compare.py  Run output and directory comparison
data/
  pdfs/                    Converter inputs
  ground_truth/             References, annotated PDFs, OCR workbook
  page_categories.csv      Page-to-category mapping
results/
  runs/                    Ignored experiments and new generated output
apps/dashboard/            React score overview and document comparison workspace
tests/                     Essential offline integration tests
docs/                      Parser, dataset, and CLI guides
```

Adapters contain SDK clients and related configuration. Shared execution and
artifact handling keep polling limits, error reporting, and output conventions
out of individual providers. Plain functions handle matching and reporting.
Follow [Adding a parser](docs/adding-parsers.md) to register a new adapter without
changing the scorer.

## CLI and development

Every command group supports `--help`; inspection commands accept `--json` for
scripts. Explore a provider's settings, a reference page, or a saved run:

```bash
uv run pdf-benchmark parsers show reducto
uv run pdf-benchmark data page 12
uv run pdf-benchmark results list
uv run pdf-benchmark results show results/runs/reducto
```

See [CLI usage](docs/cli.md) for workflows and the
[converter audit](docs/converter-upgrade.md) for reviewed SDK versions and provider
details. `uv sync` installs the project in editable mode. `uv build` creates a
wheel containing code and bundled resources; datasets and runs stay outside the
wheel. When using a wheel elsewhere, set `PDF_BENCHMARK_ROOT` to the checkout or
provide explicit input and output paths.

Run the offline checks from the repository root:

```bash
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
uv run pdf-benchmark compare before/ after/ differences.txt
```

The small offline suite checks paid request contracts, failure handling, async
execution limits, native batch identity mapping, and evaluation from reference
JSON. It makes no paid requests. For scoring changes, compare full-corpus reports
before and after a change; for local adapter changes, compare real sample Markdown.
Keep generated experiments under ignored `results/runs/`. Publish artifacts explicitly; generated Markdown and PDFs are not tracked.
