# Repository layout

The project is an installable Python package plus an independent React dashboard.
Use `uv sync --frozen` from the repository root to install the `pdf-benchmark` CLI.

| Directory | Contents |
| --- | --- |
| `src/pdf_benchmark/parsers/` | Provider adapters registered in `registry.py` |
| `src/pdf_benchmark/evaluation/` | Reference schema, source extraction, matching, and scoring |
| `src/pdf_benchmark/storage/` | Anonymous downloads and authenticated artifact publication |
| `src/pdf_benchmark/resources/` | Bundled LLM prompt and published artifact catalog |
| `data/pdfs/` | Downloaded converter input PDFs |
| `data/ground_truth/` | Versioned reference JSON and downloaded PDF/workbook sources |
| `data/page_categories.csv` | Document-to-category mapping |
| `results/runs/` | Ignored conversion runs, downloaded outputs, and evaluation reports |
| `apps/dashboard/` | React document inspection and parser comparison UI |
| `tests/` | API-contract, execution, evaluation, and storage tests |

Run `pdf-benchmark data download` to restore PDFs and the OCR workbook. Result
downloads require a release or manifest and a destination directory. Evaluation
requires one or more `--markdown-source NAME=DIRECTORY` arguments, so each report
identifies the parser outputs selected for that experiment.

Evaluation exports four CSV reports and versioned `ground_truth.json`. The source
reference file is `data/ground_truth/references.json`; generated reports belong in
`results/runs/` and are not tracked in Git.

The wheel contains Python code, the LLM prompt, and the artifact catalog. Data and
outputs remain separate. Editable installs locate the checkout automatically.
For a wheel installed elsewhere, set `PDF_BENCHMARK_ROOT=/path/to/checkout` or
provide explicit input and output paths. `python -m pdf_benchmark` also works after
installation.
