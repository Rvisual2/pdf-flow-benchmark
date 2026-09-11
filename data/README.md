# Benchmark dataset

- `pdfs/`: unannotated conversion inputs, identified by `page_<number>.pdf`.
- `ground_truth/references.json`: versioned snippets used by default evaluation.
- `ground_truth/annotated_pdfs/`: source highlight annotations.
- `ground_truth/ocr.xlsx`: supplemental reference text, formerly `Pictures.xlsx`.
- `page_categories.csv`: `Page` and `Folder` labels used for category scores.

Run `uv run pdf-benchmark data download` to restore PDFs and the workbook from
public storage. These large files are ignored local caches. Reference JSON and
category mapping remain tracked for review. Reference JSON preserves the
existing benchmark text and known limitations; it is not a corrected dataset.
See [reference editing](../docs/ground-truth.md) for review and regeneration.
