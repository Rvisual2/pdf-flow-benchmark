"""Offline integration checks: API requests, failures, ordering, and output isolation."""

import argparse
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
from llama_cloud.types.parsing_get_response import ParsingGetResponse
from reducto import AsyncReducto

from markdown_gen import datalab_markdown, gemini_markdown, llamaprse_markdown, reducto_markdown
from markdown_gen.local_common import input_files, prepare_output
from markdown_gen.remote_common import run_documents


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = [self.root / f"page_{n}.pdf" for n in (1, 2)]
        for path in self.files:
            path.write_bytes(b"%PDF-1.7 fixture")
        self.output = self.root / "output"
        prepare_output(self.output, self.files, False)

    def test_existing_output_requires_explicit_overwrite(self):
        stale = self.output / "markdowns/page_99.md"
        stale.write_text("old result")
        with self.assertRaises(ValueError):
            prepare_output(self.output, self.files, False)
        prepare_output(self.output, self.files, True)
        self.assertFalse(stale.exists())

    def test_numeric_document_order(self):
        (self.root / "page_10.pdf").write_bytes(b"PDF")
        files = input_files(argparse.Namespace(input_dir=self.root, limit=None))
        self.assertEqual([p.stem for p in files], ["page_1", "page_2", "page_10"])

    def test_openrouter_sequential_native_pdf_and_continue_after_failure(self):
        seen = []
        def handler(request):
            body = json.loads(request.content)
            name = body["messages"][0]["content"][1]["file"]["filename"]
            seen.append(name)
            self.assertEqual(body["model"], "google/gemini-3.8-flash")
            self.assertEqual(body["plugins"][0]["pdf"]["engine"], "native")
            self.assertTrue(body["messages"][0]["content"][1]["file"]["file_data"].startswith("data:application/pdf;base64,"))
            if name == "page_2.pdf":
                # First output is persisted before document two is submitted.
                self.assertTrue((self.output / "markdowns/page_1.md").exists())
            return httpx.Response(200, json={"id": name, "model": body["model"], "usage": {"cost": .001},
                "choices": [{"finish_reason": "stop" if name == "page_1.pdf" else "length",
                             "message": {"content": "document text"}}]})
        args = argparse.Namespace(model=gemini_markdown.MODEL_ID, output_dir=self.output)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            code = gemini_markdown.run_sequential(self.files, args, client, "Convert faithfully")
        self.assertEqual(code, 1)
        self.assertEqual(seen, ["page_1.pdf", "page_2.pdf"])
        self.assertFalse((self.output / "markdowns/page_2.md").exists())


class RemoteTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = [self.root / f"page_{n}.pdf" for n in (1, 2, 3)]
        for path in self.files:
            path.write_bytes(b"%PDF-1.7 fixture")
        self.args = argparse.Namespace(output_dir=self.root / "out", timeout=10, concurrency=2,
            tier="agentic", mode="accurate", fresh=True)
        prepare_output(self.args.output_dir, self.files, False)

    async def test_concurrency_limit_and_per_file_failure(self):
        active = peak = 0
        async def convert(path):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(.01)
            active -= 1
            if path == self.files[1]:
                raise RuntimeError("provider failure")
            return path.stem, {}
        code = await run_documents(self.files, self.args, convert, {})
        self.assertEqual(peak, 2)
        self.assertEqual(code, 1)
        records = [json.loads(s) for s in (self.args.output_dir / "results.jsonl").read_text().splitlines()]
        self.assertEqual(len(records), 3)
        self.assertEqual(sum(r["success"] for r in records), 2)

    async def test_llama_real_sdk_upload_and_v2_result(self):
        def handler(request):
            if request.url.path.endswith("/upload"):
                self.assertIn(b'"tier": "agentic"', request.content)
                self.assertIn(b'"version": "2026-08-19"', request.content)
                return httpx.Response(200, json={"id": "job-1", "status": "PENDING", "project_id": "p"})
            self.assertEqual(request.url.path, "/api/v2/parse/job-1")
            return httpx.Response(200, json={"job": {"id": "job-1", "project_id": "p", "status": "COMPLETED"},
                "markdown": {"pages": [{"page_number": 2, "success": True, "markdown": "second"},
                                        {"page_number": 1, "success": True, "markdown": "first"}]}})
        async with AsyncLlamaCloud(api_key="test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))) as client:
            markdown, metadata = await llamaprse_markdown.convert_document(client, self.files[0], self.args, "2026-08-19")
        self.assertEqual(markdown, "first\n\nsecond")
        self.assertEqual(metadata["job_id"], "job-1")
        self.assertIn("job-1", (self.args.output_dir / "submissions.jsonl").read_text())

    def test_llama_rejects_partial_pages(self):
        result = ParsingGetResponse.model_validate({"job": {"id": "j", "project_id": "p", "status": "COMPLETED"},
            "markdown": {"pages": [{"page_number": 1, "success": False, "error": "OCR failed"}]}})
        with self.assertRaises(ValueError):
            llamaprse_markdown.extract_markdown(result)

    async def test_datalab_accurate_and_completed_failure(self):
        client = SimpleNamespace(convert=AsyncMock(return_value=ConversionResult(
            success=False, output_format="markdown", error="page quota exceeded")))
        with self.assertRaisesRegex(RuntimeError, "page quota"):
            await datalab_markdown.convert_document(client, self.files[0], self.args)
        options = client.convert.call_args.kwargs["options"]
        self.assertEqual(options.mode, "accurate")
        self.assertTrue(options.skip_cache)
        client.convert.return_value = ConversionResult(success=True, output_format="markdown", markdown="text", page_count=1)
        markdown, metadata = await datalab_markdown.convert_document(client, self.files[0], self.args)
        self.assertEqual(markdown, "text")
        self.assertEqual(metadata["pages_processed"], 1)

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
            return httpx.Response(200, json={"status": "Completed", "result": {
                "response_type": "parse", "job_id": "job-1", "duration": 1,
                "usage": {"num_pages": 1}, "result": {"type": "url", "url": "https://download.example/result", "result_id": "r"}}})
        def download(request):
            self.assertNotIn("Authorization", request.headers)
            return httpx.Response(200, json={"type": "full", "chunks": [{"content": "parsed text"}]})
        async with AsyncReducto(api_key="test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))) as client:
            async with httpx.AsyncClient(transport=httpx.MockTransport(download)) as downloads:
                markdown, metadata = await reducto_markdown.convert_document(client, downloads, self.files[0], self.args)
        self.assertEqual(markdown, "parsed text")
        self.assertEqual(metadata["usage"]["num_pages"], 1)

    async def test_llama_native_batch_maps_reordered_results(self):
        args = self.args
        files = self.files[:2]
        parse_result = lambda text: (text, {"job_id": text})
        client = SimpleNamespace(
            configurations=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(id="config"))),
            beta=SimpleNamespace(directories=SimpleNamespace(
                create=AsyncMock(return_value=SimpleNamespace(id="directory")),
                files=SimpleNamespace(upload=AsyncMock(side_effect=[SimpleNamespace(id="f1"), SimpleNamespace(id="f2")])))),
            batches=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(id="batch")),
                get=AsyncMock(return_value=SimpleNamespace(id="batch", status="COMPLETED", results=[
                    SimpleNamespace(source_directory_file_id="f2", error_message=None, job_reference=SimpleNamespace(id="j2")),
                    SimpleNamespace(source_directory_file_id="f1", error_message="failed", job_reference=None)]))))
        with patch.object(llamaprse_markdown, "poll_parse", AsyncMock(return_value=parse_result("second"))):
            code = await llamaprse_markdown.run_server_batch(client, files, args, {"parser_version": "2026-08-19"})
        self.assertEqual(code, 1)
        self.assertFalse((args.output_dir / "markdowns/page_1.md").exists())
        self.assertEqual((args.output_dir / "markdowns/page_2.md").read_text(), "second")
        config = client.configurations.create.call_args.kwargs["parameters"]
        self.assertEqual(config["tier"], "agentic")
        self.assertEqual(config["version"], "2026-08-19")


if __name__ == "__main__":
    unittest.main()
