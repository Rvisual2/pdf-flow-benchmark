# Adding a parser

A parser converts documents into `ParsedDocument(markdown, metadata)`. It does not
need a base class. Protocols in `src/pdf_benchmark/models.py` describe the supported
interfaces; use a class when an SDK client, model, or configuration needs reuse.

## Adapter and execution policy

Create `src/pdf_benchmark/parsers/example.py`. A minimal synchronous adapter looks like:

```python
from pathlib import Path

from pdf_benchmark.models import ParsedDocument


class ExampleParser:
    def __init__(self, client):
        self.client = client

    @property
    def config(self) -> dict:
        return {"provider": "example", "mode": "accurate"}

    def convert(self, path: Path) -> ParsedDocument:
        markdown = self.client.parse(path)  # Replace with the provider's API.
        return ParsedDocument(markdown)
```

Choose the shared executor matching the adapter:

| Adapter interface | Executor | Use |
| --- | --- | --- |
| `convert(path)` | `run_sequential` | One synchronous document at a time |
| `async convert(path)` | `run_async` | Bounded concurrent requests with document deadlines |
| `convert_many(paths)` yielding `DocumentOutcome` | `run_batch` | Native local batches |
| Async `convert_many(paths)` yielding `DocumentOutcome` | `run_async_batch` | Native hosted batches with a batch deadline |

Every adapter exposes `config`. Batch outcomes identify the original input path;
never pair returned results with inputs by completion order. Raise conversion
errors or yield failed outcomes rather than returning empty successful results.
The executor persists successes, records failures, and returns a nonzero status
when documents fail. Execution policy can change independently of request parsing.

## Command integration

Provide these two module functions:

- `add_arguments(parser)`: add only provider-specific CLI options.
- `run(options, paths, key) -> int`: create `RunArtifacts(options.output_dir)`,
  call `prepare(options.overwrite)`, open the SDK client, and return the chosen
  executor's status. Use `asyncio.run()` around an async executor.

`cli.py` supplies common input/output, limit, and overwrite options. Register one
`ParserSpec` in `registry.py`, including its module name, description, default
output directory under `results/runs/`, optional API-key variable, and whether to expose concurrency.
Hosted entries also receive a timeout. See the Datalab adapter for a complete
async implementation and OpenRouter for a synchronous one.

Keep optional or heavyweight SDK imports inside `run()` or adapter methods so
listing commands does not load models. Record SDK/model versions, relevant
settings, and returned usage in metadata; never include credentials. Persist
remote job IDs through `artifacts.submission()` before polling.

## Evaluation and verification

The scorer discovers no providers: it accepts named Markdown directories. A new
parser can immediately be evaluated with:

```bash
uv run pdf-benchmark convert example --limit 2 --output-dir results/runs/example
uv run pdf-benchmark evaluate \
  --markdown-source example=results/runs/example/markdowns --output-dir results/runs/example-report
```

Use a complete corpus for comparisons. Add only essential tests for the new API
contract or a substantive failure case; do not test trivial helpers or freeze an
execution preference unnecessarily. Run a real local sample where possible;
paid live checks are separate from the offline suite.
