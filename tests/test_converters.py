"""Offline integration checks: API requests, failures, ordering, and output isolation."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from datalab_sdk.models import ConversionResult
from llama_cloud import AsyncLlamaCloud
from reducto import AsyncReducto

from pdf_benchmark.artifacts import RunArtifacts
from pdf_benchmark.execution import run_async, run_async_batch
from pdf_benchmark.models import ExecutionOptions, ParsedDocument
from pdf_benchmark.parsers import datalab, llamaparse, openrouter, reducto


class OpenRouterTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.input_directory = Path(self.temporary_directory.name)
        self.document_paths = [self.input_directory / f"page_{n}.pdf" for n in (1, 2)]
        for path in self.document_paths:
            path.write_bytes(b"%PDF-1.7 fixture")

    def test_openrouter_native_pdf_and_incomplete_response(self):
        def handler(request):
            body = json.loads(request.content)
            name = body["messages"][0]["content"][1]["file"]["filename"]
            self.assertEqual(body["model"], "google/gemini-3.8-flash")
            self.assertEqual(body["plugins"][0]["pdf"]["engine"], "native")
            self.assertTrue(
                body["messages"][0]["content"][1]["file"]["file_data"].startswith(
                    "data:application/pdf;base64,"
                )
            )
            return httpx.Response(
                200,
                json={
                    "id": name,
                    "model": body["model"],
                    "usage": {"cost": 0.001},
                    "choices": [
                        {
                            "finish_reason": "stop" if name == "page_1.pdf" else "length",
                            "message": {"content": "document text"},
                        }
                    ],
                },
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            adapter = openrouter.OpenRouterParser(client, "Convert faithfully")
            self.assertEqual(adapter.convert(self.document_paths[0]).markdown, "document text")
            with self.assertRaisesRegex(ValueError, "Incomplete generation"):
                adapter.convert(self.document_paths[1])


class HostedParserTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.input_directory = Path(self.temporary_directory.name)
        self.document_paths = [self.input_directory / f"page_{n}.pdf" for n in (1, 2, 3)]
        for path in self.document_paths:
            path.write_bytes(b"%PDF-1.7 fixture")
        self.artifacts = RunArtifacts(self.input_directory / "output")
        self.artifacts.prepare()

    async def test_concurrency_limit_and_per_file_failure(self):
        active = peak = 0

        async def convert(path):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            if path == self.document_paths[1]:
                raise RuntimeError("provider failure")
            return ParsedDocument(path.stem)

        code = await run_async(
            SimpleNamespace(convert=convert, config={}),
            self.document_paths,
            self.artifacts,
            ExecutionOptions(timeout=10, concurrency=2),
        )
        self.assertEqual(peak, 2)
        self.assertEqual(code, 1)
        records = [
            json.loads(s)
            for s in (self.artifacts.directory / "results.jsonl").read_text().splitlines()
        ]
        self.assertEqual(len(records), 3)
        self.assertEqual(sum(r["success"] for r in records), 2)

    async def test_llama_real_sdk_upload_and_v2_result(self):
        def handler(request):
            if request.url.path.endswith("/upload"):
                self.assertIn(b'"tier": "agentic"', request.content)
                self.assertIn(b'"version": "2026-08-19"', request.content)
                return httpx.Response(
                    200, json={"id": "job-1", "status": "PENDING", "project_id": "p"}
                )
            self.assertEqual(request.url.path, "/api/v2/parse/job-1")
            return httpx.Response(
                200,
                json={
                    "job": {"id": "job-1", "project_id": "p", "status": "COMPLETED"},
                    "markdown": {
                        "pages": [
                            {"page_number": 2, "success": True, "markdown": "second"},
                            {"page_number": 1, "success": True, "markdown": "first"},
                        ]
                    },
                },
            )

        async with AsyncLlamaCloud(
            api_key="test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        ) as client:
            document = await llamaparse.LlamaParseParser(
                client,
                self.artifacts,
                llamaparse.LlamaParseOptions(parser_version="2026-08-19", fresh=True),
            ).convert(self.document_paths[0])
        self.assertEqual(document.markdown, "first\n\nsecond")
        self.assertEqual(document.metadata["job_id"], "job-1")
        self.assertIn("job-1", (self.artifacts.directory / "submissions.jsonl").read_text())

    async def test_datalab_accurate_and_completed_failure(self):
        client = SimpleNamespace(
            convert=AsyncMock(
                return_value=ConversionResult(
                    success=False, output_format="markdown", error="page quota exceeded"
                )
            )
        )
        with self.assertRaisesRegex(RuntimeError, "page quota"):
            await datalab.DatalabParser(client, datalab.DatalabOptions(fresh=True)).convert(
                self.document_paths[0]
            )
        options = client.convert.call_args.kwargs["options"]
        self.assertEqual(options.mode, "accurate")
        self.assertTrue(options.skip_cache)
        client.convert.return_value = ConversionResult(
            success=True, output_format="markdown", markdown="text", page_count=1
        )
        document = await datalab.DatalabParser(client, datalab.DatalabOptions(fresh=True)).convert(
            self.document_paths[0]
        )
        self.assertEqual(document.markdown, "text")
        self.assertEqual(document.metadata["pages_processed"], 1)

    async def test_reducto_real_sdk_standard_queue_and_signed_result(self):
        def handler(request):
            if request.url.path == "/upload":
                return httpx.Response(200, json={"file_id": "reducto://fixture"})
            if request.url.path == "/parse_async":
                body = json.loads(request.content)
                self.assertEqual(body["input"], "reducto://fixture")
                self.assertEqual(body["settings"]["model"], "r-1")
                self.assertEqual(body["queue_priority"], "standard")
                self.assertEqual(body["retrieval"]["chunking"]["chunk_mode"], "disabled")
                self.assertEqual(body["formatting"]["table_output_format"], "md")
                return httpx.Response(200, json={"job_id": "job-1"})
            return httpx.Response(
                200,
                json={
                    "status": "Completed",
                    "result": {
                        "response_type": "parse",
                        "job_id": "job-1",
                        "duration": 1,
                        "usage": {"num_pages": 1},
                        "result": {
                            "type": "url",
                            "url": "https://download.example/result",
                            "result_id": "r",
                        },
                    },
                },
            )

        def download(request):
            self.assertNotIn("Authorization", request.headers)
            return httpx.Response(
                200, json={"type": "full", "chunks": [{"content": "parsed text"}]}
            )

        async with AsyncReducto(
            api_key="test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        ) as client:
            async with httpx.AsyncClient(transport=httpx.MockTransport(download)) as downloads:
                document = await reducto.ReductoParser(client, downloads, self.artifacts).convert(
                    self.document_paths[0]
                )
        self.assertEqual(document.markdown, "parsed text")
        self.assertEqual(document.metadata["usage"]["num_pages"], 1)

    async def test_llama_native_batch_maps_reordered_results(self):
        document_paths = self.document_paths[:2]
        client = SimpleNamespace(
            configurations=SimpleNamespace(
                create=AsyncMock(return_value=SimpleNamespace(id="config"))
            ),
            beta=SimpleNamespace(
                directories=SimpleNamespace(
                    create=AsyncMock(return_value=SimpleNamespace(id="directory")),
                    files=SimpleNamespace(
                        upload=AsyncMock(
                            side_effect=[SimpleNamespace(id="f1"), SimpleNamespace(id="f2")]
                        )
                    ),
                )
            ),
            batches=SimpleNamespace(
                create=AsyncMock(return_value=SimpleNamespace(id="batch")),
                get=AsyncMock(
                    return_value=SimpleNamespace(
                        id="batch",
                        status="COMPLETED",
                        results=[
                            SimpleNamespace(
                                source_directory_file_id="f2",
                                error_message=None,
                                job_reference=SimpleNamespace(id="j2"),
                            ),
                            SimpleNamespace(
                                source_directory_file_id="f1",
                                error_message="failed",
                                job_reference=None,
                            ),
                        ],
                    )
                ),
            ),
        )
        adapter = llamaparse.LlamaParseParser(
            client,
            self.artifacts,
            llamaparse.LlamaParseOptions(parser_version="2026-08-19", fresh=True),
        )
        with patch.object(
            adapter, "poll", AsyncMock(return_value=ParsedDocument("second", {"job_id": "j2"}))
        ):
            code = await run_async_batch(
                adapter, document_paths, self.artifacts, ExecutionOptions(timeout=10, concurrency=2)
            )
        self.assertEqual(code, 1)
        self.assertFalse((self.artifacts.directory / "markdowns/page_1.md").exists())
        self.assertEqual((self.artifacts.directory / "markdowns/page_2.md").read_text(), "second")
        config = client.configurations.create.call_args.kwargs["parameters"]
        self.assertEqual(config["tier"], "agentic")
        self.assertEqual(config["version"], "2026-08-19")


if __name__ == "__main__":
    unittest.main()
