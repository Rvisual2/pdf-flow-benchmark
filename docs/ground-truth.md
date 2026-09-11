# Ground-truth format and editing

Evaluation uses versioned reference data independently of its original PDF and
spreadsheet sources. Every evaluation exports `ground_truth.json`. Pass that file
back with `--ground-truth-input` to bypass annotation extraction and the workbook.
The default reference file is `data/ground_truth/references.json`. The category
mapping is `data/page_categories.csv`, with `Page` and `Folder` columns. Use
`--rebuild-ground-truth` to import PDF/workbook sources instead of JSON.

## Schema version 1

```json
{
  "schema_version": 1,
  "pages": [
    {
      "page_number": 1,
      "snippets": [
        {
          "id": "annotation:1",
          "text": "A complete passage in its intended reading order.",
          "source": "annotation",
          "reading_order": 1
        },
        {
          "id": "ocr:1",
          "text": "Another independently readable passage.",
          "source": "ocr",
          "reading_order": null
        }
      ]
    }
  ]
}
```

Page numbers are positive integers corresponding to `page_<number>.md`. Pages
must be unique and contain at least one snippet. Snippet IDs must be unique within
a page; IDs and text cannot be empty. `source` records the original source
(`annotation` or `ocr`), including after a correction. Optional `reading_order`
is a nonnegative integer identifying an annotation series, not an ordering
constraint between otherwise independent snippets. List order determines the
report's `needle_index`.

## Preparing and reviewing references

1. Evaluate the original sources with `--markdown-source TOOL=RUN/markdowns --rebuild-ground-truth --output-dir results/runs/reference-review`.
2. Copy its `ground_truth.json` into a separate review directory.
3. Check suspicious snippets against the original PDF. Correct the text while
   preserving its ID and origin; record the reason in a companion review note.
4. Evaluate the edited file with `--ground-truth-input` and a new output directory.
5. Compare granular and summary CSVs before and after the edits using identical parser
   selections and filter settings. Explain reference edits separately from parser
   improvements.

The original files in `data/ground_truth/annotated_pdfs/` and `ocr.xlsx` remain the
provenance archive. The
annotation importer uses numeric file ordering and assigns
page numbers by position; do not rename or subset that archive when rebuilding
existing references. For a new or partial dataset, explicit JSON page numbers
avoid that positional convention.

Annotation snippets join highlight segments by series and sequence. Workbook
snippets undergo the existing text cleanup. JSON imports are scored as written,
without repeating cleanup. The `ground_truth.json` export retains snippet IDs and
source metadata. Evaluation writes this versioned reference file and the four CSV
reports; annotation/workbook intermediate data stays in memory.
