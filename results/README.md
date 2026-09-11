# Benchmark results

`baseline/` contains downloaded provider Markdown and historical evaluation
reports. Restore provider files with `uv run pdf-benchmark results download`.
Raw Markdown bytes are preserved; published metadata is curated for provenance. Each provider retains its
`markdowns/` directory and available metadata. Docling variants are under
`baseline/docling/ocr/` and `baseline/docling/no_ocr/`.

`baseline/evaluation/` preserves historical CSVs and intermediate extraction JSON;
these are archival snapshots, not automatically regenerated current scores. Both
original filtered reports are retained under distinct names.

`runs/` is ignored by Git. New conversions and evaluation reports go here by
default. Existing local experiments were moved here as well, including the full
2026-09-10 run. Their logs and metadata preserve original recorded paths.

Use a distinct run directory for comparisons. Publish a run with `pdf-benchmark results upload DIRECTORY --label NAME`; promote
its manifest pointer to the release catalog only after verification. Provider
Markdown and metadata are ignored locally; historical evaluation CSVs stay tracked.
