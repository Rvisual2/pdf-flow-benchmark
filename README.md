# Flow-Aware PDF-to-Markdown Benchmark

Compare PDF extraction tools by how well their Markdown preserves coherent reading
flow. Flow-Aware Text Accuracy (FATA) matches reference snippets against each
parser's output and reports character-level similarity as a percentage.

## Setup

Use Python 3.13 or newer. From the repository root:

```bash
uv sync --frozen
uv run pdf-benchmark --help
uv run pdf-benchmark data download
```

`uv sync` installs the project in editable mode and exposes `pdf-benchmark`.
Build a distributable wheel with `uv build`; the wheel contains code and the LLM
prompt, while datasets and results remain in the checkout. Local converters
download models on first use. The
[converter audit](docs/converter-upgrade.md) records reviewed SDK versions and
provider API details; `uv.lock` fixes the dependency set. Commands locate this
checkout in editable installs. When using a wheel elsewhere, set
`PDF_BENCHMARK_ROOT` to the checkout or provide explicit input and output paths.
The [layout migration guide](docs/repository-layout.md) maps all former paths.

## Explore the CLI

```bash
uv run pdf-benchmark                       # Show command groups and examples
uv run pdf-benchmark parsers list          # Available tools and credential presence
uv run pdf-benchmark parsers show reducto  # Defaults and every provider option
uv run pdf-benchmark data show             # Dataset size and categories
uv run pdf-benchmark results releases       # Published cloud releases
uv run pdf-benchmark results download       # Restore baseline Markdown
uv run pdf-benchmark data page 12          # Inspect reference snippets
uv run pdf-benchmark results list          # Browse recent runs and evaluations
uv run pdf-benchmark results show results/runs/reducto
uv run pdf-benchmark results scores results/runs/evaluation
```

Every group supports `--help`; inspection commands accept `--json` for scripts.
Discovery makes no paid requests. See [CLI usage](docs/cli.md) for workflows.

## Browse the dashboard

The [React dashboard](apps/dashboard/README.md) compares all seven parser pipelines
across 129 PDFs. Filter the document score matrix by tool, category, low/high scores,
or tool disagreements. Open a score to compare ground-truth snippets with the
evaluator's closest matches. The PDF + Markdown tab shows the original PDF beside
rendered or raw tool output, and the tool comparison view diffs complete outputs.
Document previews, reference matches, and artifact provenance connect scores to evidence.

```bash
cd apps/dashboard
npm ci
npm run dev
```

The dashboard reads published artifacts anonymously; no Python environment or API
keys are needed to view it. Build a static deployment with `npm run build`.
Refresh its data from evaluated, published runs with `pdf-benchmark dashboard export`;
see the dashboard guide for the complete workflow.

## Generate Markdown

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

The old standalone runners have been removed. Use `pdf-benchmark convert <parser>`
for every provider; `python -m pdf_benchmark` is also available after installation.
New conversions default to `results/runs/<parser>/`, leaving archived baselines
under `results/baseline/` intact.

## Evaluate results

Restore the archived baseline with `uv run pdf-benchmark results download`, or
select complete runs with repeated `--markdown-source NAME=DIRECTORY` arguments:

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
- `granular.csv` and `filtered.csv`: snippet distances and matched text.
- `ground_truth.json`: versioned reference snippets with source IDs.
- Legacy intermediate JSON exports for existing analysis scripts.

By default, evaluation reads `data/ground_truth/references.json` and the downloaded
Markdown under `results/baseline/`. To evaluate a separately reviewed reference file:

```bash
uv run pdf-benchmark evaluate \
  --ground-truth-input results/runs/evaluation/ground_truth.json \
  --markdown-source reducto=results/runs/reducto/markdowns \
  --output-dir results/runs/reviewed-evaluation
```

Use `--rebuild-ground-truth` to regenerate references from annotated PDFs and
`ocr.xlsx`. Reports default to `results/runs/evaluation/`; individual output flags
remain available. See [ground-truth editing](docs/ground-truth.md) for the schema
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

## How scoring works

The source collection includes documents sampled from DocLayNet across financial
reports, scientific articles, laws, tenders, manuals, and patents. Numbered PDF
highlights form reference snippets in reading order; the workbook supplies
additional OCR references. Each snippet represents a coherent passage, without
requiring unrelated passages on a page to have a single total order.

The scorer uses fuzzy substring alignment, then normalized Levenshtein distance.
A perfect match has distance 0. Category accuracy is `(1 - mean distance) * 100`;
the overall score weights categories by their retained snippet counts.

The historical filters remain unchanged: missing scores from any selected parser
exclude that snippet, the `test` category is excluded, and at least one parser
must achieve distance below 0.25. Consequently, changing the selected parsers can
change the evaluation sample. Compare the same providers and inspect filtered
rows when interpreting differences.

References contain known extraction and reading-order errors. Raw HTML, Markdown
formatting, and whitespace can also affect distances. This refactor preserves
existing scoring behavior; it does not apply the experimental ground-truth or
HTML normalization corrections from earlier analyses.

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
  baseline/                Downloaded provider outputs and historical reports
  runs/                    Ignored experiments and new generated output
apps/dashboard/            React score overview and document comparison workspace
tests/                     Essential offline integration tests
docs/                      Parser, dataset, and migration guides
```

Adapters contain SDK clients and related configuration. Shared execution and
artifact handling keep polling limits, error reporting, and output conventions
out of individual providers. Plain functions handle matching and reporting.
Follow [Adding a parser](docs/adding-parsers.md) to register a new adapter without
changing the scorer.

## Development

```bash
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
uv run pdf-benchmark compare before/ after/ differences.txt
```

The small offline suite checks paid request contracts, failure handling, async
execution limits, native batch identity mapping, and evaluation from reference
JSON. It makes no paid requests. For scoring changes, compare full-corpus reports
against a baseline; for local adapter changes, compare real sample Markdown.
Keep generated experiments under ignored `results/runs/`. Publish artifacts explicitly; generated Markdown and PDFs are no longer tracked.
