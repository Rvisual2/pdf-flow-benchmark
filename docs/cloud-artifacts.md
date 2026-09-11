# Public benchmark artifacts

PDFs and raw Markdown are stored in the Google Cloud Storage bucket
`pdf-flow-benchmark-hashiromer-20260910`, in project
`pypi-download-analysis-457820` (`us-east1`, Standard storage).

## Download before an experiment

```bash
uv run pdf-benchmark data download
uv run pdf-benchmark results releases
uv run pdf-benchmark results download
uv run pdf-benchmark evaluate
```

Data download restores input PDFs, annotated PDFs, OCR workbook, reference JSON,
and category mapping. Results download defaults to the archived baseline. To
retrieve the full seven-tool September run separately:

```bash
uv run pdf-benchmark results download --release all-tools-2026-09-10 \
  --directory results/runs/published-september
```

Downloads require no Google account or SDK. Releases are pinned by manifest URL
and SHA-256 in `src/pdf_benchmark/resources/artifacts.json`, which ships in the
wheel. The manifest identifies exact files; no bucket-list request is needed.
Each file is checked against its expected size and SHA-256 before replacing a
local file. Matching files are reused. Conflicting local files require
`--overwrite`; malformed paths and writes outside the destination are rejected.

## Publish a dataset or conversion run

The maintainer needs Google Cloud CLI authentication:

```bash
gcloud auth login
uv run pdf-benchmark data upload --label dataset-2026-09-10 \
  --account maintainer@example.com --receipt results/runs/publications/dataset.json
uv run pdf-benchmark results upload results/runs/reducto \
  --label reducto-experiment-01 --account maintainer@example.com \
  --receipt results/runs/publications/reducto.json
```

`results upload` accepts one run or a directory containing several runs. Use
`--input-dir` when the source PDFs are elsewhere. `--bucket` overrides the default
bucket. Transfers use bounded concurrency (`--workers`, default 8), independent
of parser execution settings.

Objects use `objects/<sha256>/<filename>` names. Conditional creation prevents
replacement; a repeated upload verifies and reuses existing content. A release
manifest is uploaded only after all its files succeed. The local receipt contains
the public manifest URL and checksum; it can be passed to `--manifest` when
retrieving an unpublished-to-the-catalog experiment. The upload command does not
change the release catalog automatically. Promote a verified receipt's manifest
pointer into the catalog through code review.

## Provenance

Raw Markdown bytes are preserved. Every Markdown entry records the source PDF
filename and SHA-256, plus available conversion records: provider/model, parser
settings, SDK versions, timestamps, job IDs, duration, and document counts.
Selected run summaries and per-document metadata are included; credentials,
free-form logs, and full provider response bodies are not publication inputs.
Historical records may lack configuration or source hashes. The manifest labels
hashes computed at publication as `publication_time`; it does not claim the
current code or inputs generated an older result.

New local runs record input hashes and available Git revision/dirty-state and
lockfile hashes. The manifest separately records the publishing code state.
Unknown provenance stays unknown; publication does not fabricate model versions
or hardware information. Failed documents remain represented by available
per-document records, while only existing Markdown files are uploaded.

## Public access

The bucket uses uniform bucket-level access. Its explicit IAM bindings are:

- `allUsers`: `roles/storage.legacyObjectReader` (`storage.objects.get` only).
- Publishing maintainer: `roles/storage.admin`.

Anonymous object reads succeeded in live checks; anonymous JSON/XML listings and
writes were rejected. This uses Google's documented
[read-without-listing role](https://docs.cloud.google.com/storage/docs/access-control/making-data-public).
Public manifests intentionally disclose the files belonging to their release,
while the bucket API does not expose an object inventory.

## Git policy

PDFs, the OCR workbook, and provider baseline directories are ignored local
caches. The release catalog, source code, reference JSON, category mapping,
documentation, and historical evaluation reports remain reviewable in Git.
Artifacts were removed from the index after successful publication and verified
anonymous restoration. Older Git history still contains historical artifacts;
this migration does not rewrite history.

## Dashboard thumbnails

Low-resolution PDF covers live in the separate
`pdf-flow-thumbnails-hashiromer-20260910` bucket in the same project and region.
It uses the same public-read-without-listing policy and read-only browser CORS.

`uv run pdf-benchmark dashboard thumbnails --publish` generates JPEG covers capped
at 320 pixels on the longest edge (quality 70). The catalog pins a manifest with
image hashes, dimensions, source PDF hashes, page numbers, and renderer settings.
Generated images remain under ignored `results/runs/thumbnails/`. Re-export the
dashboard snapshot after publishing to attach covers to their matching PDFs.
