# Repository layout migration

The project now uses an installable `src/` package. Run `uv sync --frozen` after
updating a checkout; the `pdf-benchmark` command replaces standalone scripts.

## Files and directories

| Former location | Current location |
| --- | --- |
| `pdf_benchmark/` | `src/pdf_benchmark/` |
| `PDFs/` | `data/pdfs/` |
| `benchmark_data/PDFs/` | `data/ground_truth/annotated_pdfs/` |
| `benchmark_data/Pictures.xlsx` | `data/ground_truth/ocr.xlsx` |
| `benchmark_data/page_folder_mapping.csv` | `data/page_categories.csv` |
| `benchmark_data/{annotations,combined_output,cleaned_output}.json` | `results/baseline/evaluation/intermediate/{annotations,combined,cleaned}.json` |
| `datalab_results/` | `results/baseline/datalab/` |
| `gemini_results/` | `results/baseline/gemini/` |
| `llama_parse_results/` | `results/baseline/llamaparse/` |
| `reducto_results/` | `results/baseline/reducto/` |
| `pymupdflayout_results/` | `results/baseline/pymupdf4llm/` |
| `docling_ocr_results/`, `docling_wocr_results/` | `results/baseline/docling/{ocr,no_ocr}/` |
| `benchmark_granular.csv`, `benchmark_results_final.csv` | `results/baseline/evaluation/{granular,scores_by_category}.csv` |
| `benchmark_data/benchmark_filtered.csv` | `results/baseline/evaluation/filtered.csv` |
| Root `benchmark_filtered.csv` | `results/baseline/evaluation/legacy_filtered.csv` |
| `runs/` | `results/runs/` (still ignored) |
| `markdown_gen/ai_prompt.md` | `src/pdf_benchmark/resources/pdf_to_markdown.md` |

Dataset and archived result contents are preserved. The two original filtered
reports are retained separately because they represent separate historical files.
Archived logs and metadata keep their original paths as provenance; those strings
may refer to locations before migration.

`data/ground_truth/references.json` is the versioned export of the existing
references, without experimental corrections. Evaluation reads it by default;
`--rebuild-ground-truth` reconstructs it from source annotations and OCR, writing
the export to the report directory. Provider outputs and PDFs are now ignored caches restored from public storage;
see [cloud artifacts](cloud-artifacts.md). New conversions and evaluations default to
`results/runs/` so they do not overwrite committed baselines.

## Commands and imports

| Removed entry point | Replacement |
| --- | --- |
| `markdown_gen/<provider>_markdown.py` | `pdf-benchmark convert <provider>` |
| `markdown_gen/docling_cpu.py` | `pdf-benchmark convert docling` |
| `markdown_gen/llamaprse_markdown.py` | `pdf-benchmark convert llamaparse` |
| `prod_benchmark.py` | `pdf-benchmark evaluate` |
| `compare_folders.sh` or `compare_folders.py` | `pdf-benchmark compare` |
| `benchmark_data.utils` imports | `pdf_benchmark.evaluation.matching` |

Prefix commands with `uv run` in the checkout. The module entry point
`python -m pdf_benchmark` also works after installation. Update external scripts
and notebooks to the new imports and paths; compatibility wrappers are removed.

The wheel includes Python code and the default LLM prompt, not the corpus or
outputs. Editable installs locate the checkout automatically. For an installed
wheel, set `PDF_BENCHMARK_ROOT=/path/to/checkout`, or run from the checkout.
Explicit path flags also support datasets stored elsewhere.

## Clean-checkout validation — 2026-09-11

The staged repository builds an installable wheel and passes all 10 offline
Python integration tests. Ruff checks and lockfile validation pass. The installed
CLI anonymously restored 261 dataset files (including 129 input PDFs), read the
reference inventory, and exposed the dashboard export command.

Full-corpus evaluation of the existing baseline Markdown retained 445 snippets
across 120 pages. After mapping the historical `pymupdflayout` column to
`pymupdf4llm`, all retained snippet distances and final category/weighted scores
match the archived reports exactly. The versioned reference export differs from
the archived granular report in two snippets: a moved `p` on page 8, reference 0,
and a moved combining slash on page 18, reference 0. The latter changes two raw
distances by less than 0.0007, on a snippet excluded from the scored set. Archived
reports remain unchanged for comparison.

Validation used an isolated Python 3.13 environment with the evaluation and hosted
SDK test dependencies. It did not rerun paid conversions or local model inference.
Generated validation outputs are temporary and are not committed.
