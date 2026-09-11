# Command-line guide

Install with `uv sync --frozen`, then prefix the commands below with `uv run`.
Running `pdf-benchmark` without arguments shows the command groups and examples.
A group without an action shows its available actions. Every level has `--help`.

## Discover tools and data

```bash
pdf-benchmark parsers list
pdf-benchmark parsers show llamaparse
pdf-benchmark convert docling --help
pdf-benchmark data download
pdf-benchmark data show
pdf-benchmark data page 12
```

`parsers list` shows local/paid tools and whether credentials are configured.
Presence is not authentication: discovery does not call providers or print keys.
`parsers show` includes defaults and all provider options. `data show` summarizes
PDFs, reference snippets, and categories before scoring filters. `data page`
prints the original reference text, source IDs, category, and input PDF path.
Use `--directory` on data commands to inspect another dataset with the same layout.

## Convert and evaluate

```bash
pdf-benchmark convert pymupdf4llm --limit 2 --output-dir results/runs/smoke
pdf-benchmark convert docling --ocr both --output-dir results/runs/docling
pdf-benchmark evaluate \
  --markdown-source docling_ocr=results/runs/docling/ocr/markdowns \
  --markdown-source docling_no_ocr=results/runs/docling/no_ocr/markdowns \
  --output-dir results/runs/docling-evaluation
```

`convert <parser>` exposes shared input/output options and options specific to that
parser. Paid commands require their credential. Nonempty output directories need
`--overwrite`; prefer a fresh directory to retain earlier results.

Evaluation requires at least one `--markdown-source NAME=DIRECTORY`.
Without `--ground-truth-input`, it reads the bundled dataset's reference JSON.
Use `--rebuild-ground-truth` to re-extract source annotations and OCR text.
`--verbose` enables per-page evaluation logs. Normal evaluation prints a summary.

## Browse results

```bash
pdf-benchmark results list --limit 10
pdf-benchmark results show results/runs/smoke
pdf-benchmark results scores results/runs/docling-evaluation
pdf-benchmark compare results/runs/before/markdowns results/runs/after/markdowns differences.txt
```

`results list` discovers conversion `run.json` files and evaluation score CSVs,
ordered by file modification time. `results show` displays saved configuration,
failures, duration, and output locations, or the score table for an evaluation.
`results scores` accepts a report directory, `scores.csv`, or the current
`scores_by_category.csv` report.

## Scripting and exit codes

Inspection commands support `--json`:

```bash
pdf-benchmark parsers list --json
pdf-benchmark data page 12 --json
pdf-benchmark results scores results/runs/docling-evaluation --json
```

JSON output contains only the requested data. Conversion/evaluation already write
structured results to disk. Exit 0 indicates completion, 1 indicates a conversion,
evaluation, or inspection failure, and 2 indicates invalid CLI usage or conversion
preflight configuration. Directory comparison exits 0 when the comparison completes,
even if files differ; inspect its report for differences.

Redirect both streams when retaining a complete log:

```bash
mkdir -p results/runs/logs
pdf-benchmark convert reducto --output-dir results/runs/reducto \
  > results/runs/logs/reducto.log 2>&1
```

## Cloud artifact commands

`data upload` publishes the dataset; `data download` restores it.
`results upload DIRECTORY --label NAME` publishes raw Markdown with provenance.
`results releases` lists curated release manifests without listing the bucket.
`results download --release NAME --directory results/runs/NAME` restores a release.
Use `--manifest` instead of `--release` to select a manifest URL or local upload
receipt. An explicit destination directory is required. Uploads need gcloud login; downloads do not.
See [cloud artifacts](cloud-artifacts.md) for publication and download details.

## Export dashboard data

```bash
uv run pdf-benchmark dashboard export \
  --evaluation-dir results/runs/evaluation \
  --run-dir results/runs/published-september \
  --release all-tools-2026-09-10 --publish
```

Exports report scores, matched snippets, and public artifact references for the
[React dashboard](../apps/dashboard/README.md). The run must match the published
release. Omit `--publish` for a local snapshot; publishing updates the frontend's
data pointer using gcloud credentials. This command never invokes paid parsers.
