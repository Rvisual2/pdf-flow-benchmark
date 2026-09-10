# Converter upgrade audit — 2026-09-10

The last repository commit is dated 2026-04-23. SDK versions below were checked against PyPI and current official documentation. Pins record the reviewed release; a newer release should be reviewed before changing them. Provider accuracy claims have not been measured on this corpus.

| Tool | Updated integration | Bulk processing |
| --- | --- | --- |
| PyMuPDF4LLM | `pymupdf4llm==1.28.2`, native `convert_batch()` with bundled Layout | Automatic worker sizing, persistent workers, and streaming results; configurable `--workers` and `--no-persistent`. |
| Docling | `docling==2.126.0`; `PdfPipelineOptions`, current accelerator module, `DocumentConverter.convert_all()` | Converter/model reuse per worker; document batches and OCR/layout/table page batches. CPU processes are configurable; OCR-enabled and OCR-disabled runs remain separate. |
| Gemini / direct LLMs | OpenRouter `/api/v1/chat/completions`, `google/gemini-3.8-flash`, native PDF input | Strictly sequential, as requested. No concurrency or server batch mode. HTTPX replaces the Google SDK. |
| LlamaParse | `llama-cloud==2.16.0`, Parse v2, `agentic` | Bounded async documents, or native directory batches with `--server-batch` (Pro/Enterprise). |
| Reducto | `reductoai==0.24.0`, V3, `settings.model="r-1"` (preview) | Standard async jobs with bounded concurrency; chunking disabled, full-document Markdown saved as each job completes. |
| Datalab / Marker | `datalab-python-sdk==0.5.0`, `/api/v1/convert`, `mode="accurate"` | SDK async conversion with bounded concurrency; the documented bulk recipe uses concurrent requests, not a separate batch endpoint. |

## Compatibility and reproducibility

The legacy `llama-cloud-services` packages constrain `llama-cloud` to 0.1.x. The migration replaces `llama-cloud-services` and `llama-parse` with the current SDK. The new dependency set resolves in `uv.lock`.

PyMuPDF4LLM is included as one benchmark provider, using the current bundled Layout default. `--no-layout` disables Layout explicitly and uses native sequential execution to preserve this setting across platforms: the current batch pool does not propagate it to spawned workers. The `pymupdf4llm` score column reads the existing `pymupdflayout_results/markdowns` directory by default. PyMuPDF 1.28.2 also remains an internal dependency for reading ground-truth annotations. The Docling GPU runner is removed.

LlamaParse resolves the service's `latest` version **for the selected tier** once before submission, validates it against published versions, and records the dated version. `--parser-version` can select a published date explicitly. Native directory batches create a saved configuration using those same settings; remote configuration, directory, file, and batch IDs are written to `submissions.jsonl`.

Reducto r-1 and Datalab's hosted models can change independently of their Python SDKs. Datalab documents model pinning only for enterprise plans; Reducto's general version pinning has limited rollout windows. Record actual run settings and returned version/usage metadata. No fixed per-file prices or historical Gemini token-price tables are used: costs are recorded only when the service returns them, and absent usage remains unknown.

## Execution behavior

Both Docling OCR modes remain available on CPU, with separate output folders; the default runs both. Select `--ocr on`, `off`, or `both`. Tables remain enabled by default. CPU defaults to one process to bound memory; increase `--workers` after measuring the target machine. Docling labels cross-document threading experimental, so this runner uses process parallelism instead.

Standard concurrent execution is the default for hosted document parsers. Reducto's documented immediate batch workflow submits individual requests concurrently; there is no documented multi-document immediate parse endpoint. The runner uses `/parse_async` with `queue_priority="standard"`, polls job status, and saves each completed result. Delayed discount queues are excluded per the real-time requirement. LlamaParse's native directory batch API is distinct from discounted queue processing.

Runs refuse nonempty output folders unless `--overwrite` is supplied. Overwriting clears old Markdown so stale successes cannot contaminate a partial or failed rerun. Preserve baseline results by using new output folders. LlamaParse and Reducto job IDs are saved before polling; an interrupted local process does not cancel the hosted job. There is no automatic resume/resubmit workflow.

## Sources

- [PyMuPDF4LLM API and Layout switch](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/api.html), [native batch API implementation](https://github.com/pymupdf/pymupdf4llm/blob/main/src/batch_converter.py).

- [Docling converter](https://docling-project.github.io/docling/reference/document_converter/), [pipeline options](https://docling-project.github.io/docling/reference/pipeline_options/), [2.126.0 implementation](https://github.com/docling-project/docling/blob/v2.126.0/docling/document_converter.py).
- [OpenRouter Gemini 3.8 Flash](https://openrouter.ai/google/gemini-3.8-flash), [native PDF requests](https://openrouter.ai/docs/guides/overview/multimodal/pdfs).
- [LlamaParse v2](https://developers.llamaindex.ai/llamaparse/parse/guides/api-reference/), [tiers and versions](https://developers.llamaindex.ai/llamaparse/parse/guides/tiers/), [native batches](https://developers.llamaindex.ai/llamaparse/batches/getting_started/).
- [Reducto r-1](https://docs.reducto.ai/parse/r-1), [async jobs](https://docs.reducto.ai/workflows/async-overview), [immediate batch processing](https://docs.reducto.ai/workflows/batch-processing), [whole-document Markdown](https://docs.reducto.ai/reference/faq), [version pinning](https://docs.reducto.ai/reference/version-pinning).
- [Datalab SDK](https://documentation.datalab.to/docs/welcome/sdk/conversion), [batch conversion](https://documentation.datalab.to/docs/recipes/conversion/batch-documents), [version policy](https://documentation.datalab.to/platform/versioning).

## Validation

- Native PyMuPDF4LLM batch conversion passed two-document checks with Layout enabled and disabled. Its Markdown matched the single-document API byte for byte on the sample and passed through the scorer. A mixed valid/corrupt batch preserved the valid output, reported the corrupt file, and returned a failure exit code.

- Nine offline converter tests pass, including actual SDK request serialization against mocked HTTP transports.
- Both Docling CPU modes converted a two-document sample using spawned workers and the locked dependencies (CPU PyTorch wheel variant).
- With the same six selected providers, the original and updated scoring implementations produced byte-identical granular, filtered, and final CSVs on the existing dataset.
- The lockfile validates, and the installed validation environment passes dependency compatibility checks.
- On 2026-09-10, authorized live conversions of `PDFs/page_1.pdf` succeeded for LlamaParse `agentic_plus` (2026-08-19), Datalab `accurate`, Reducto `r-1` (standard queue, chunking disabled), and Gemini `google/gemini-3.8-flash` through OpenRouter. Each returned nonempty Markdown containing source-document text. Artifacts are in `runs/paid-live-20260910T102327Z/`. This single-document smoke check does not establish corpus accuracy or comparative throughput.
