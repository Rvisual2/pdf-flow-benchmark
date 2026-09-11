"""Artifact publication and anonymous retrieval must preserve data and provenance."""

import base64
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

import httpx

from pdf_benchmark.cli import build_parser
from pdf_benchmark.storage.publication import download, publish
from pdf_benchmark.storage.transfer import BucketPublisher, digest, json_bytes, validated_targets


class ArtifactTransferTests(unittest.TestCase):
    def test_result_download_requires_selection_and_destination(self):
        parser = build_parser()
        for flags in ([], ["--release", "example"], ["--directory", "results/runs/example"]):
            with self.subTest(flags=flags), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    parser.parse_args(["results", "download", *flags])
                self.assertEqual(raised.exception.code, 2)
        for selector in ("--release", "--manifest"):
            options = parser.parse_args(
                ["results", "download", selector, "example", "--directory", "results/runs/example"]
            )
            self.assertEqual(options.directory, Path("results/runs/example"))
            self.assertEqual(getattr(options, selector.removeprefix("--")), "example")

    def test_publish_and_anonymous_restore_with_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "inputs"
            source.mkdir()
            (source / "page_1.pdf").write_bytes(b"%PDF fixture")
            run = root / "run"
            (run / "markdowns").mkdir(parents=True)
            (run / "markdowns/page_1.md").write_text("# Raw Markdown\n")
            (run / "results.jsonl").write_text(
                json.dumps(
                    {
                        "file": "/old/location/page_1.pdf",
                        "model": "test-model",
                        "source_sha256": digest(b"%PDF fixture"),
                        "api_key": "must-not-publish",
                        "full_result": {"secret": "must-not-publish"},
                    }
                )
                + "\n"
            )
            objects = {}

            def handle(request):
                if request.method == "POST":
                    self.assertEqual(request.headers["Authorization"], "Bearer test-token")
                    self.assertEqual(request.url.params["ifGenerationMatch"], "0")
                    name = request.url.params["name"]
                    if name in objects:
                        return httpx.Response(412)
                    objects[name] = request.content
                    return httpx.Response(
                        200,
                        json={
                            "md5Hash": base64.b64encode(
                                hashlib.md5(request.content).digest()
                            ).decode()
                        },
                    )
                self.assertNotIn("Authorization", request.headers)
                name = unquote(request.url.path).removeprefix("/test-bucket/")
                return httpx.Response(200, content=objects[name])

            with httpx.Client(transport=httpx.MockTransport(handle)) as client:
                publisher = BucketPublisher("test-bucket", client, "test-token")
                receipt = root / "receipt.json"
                publish(
                    "results",
                    run,
                    publisher,
                    input_directory=source,
                    label="test",
                    workers=2,
                    receipt=receipt,
                )
                # Publishing the same content must reuse immutable objects safely.
                publish(
                    "results",
                    run,
                    publisher,
                    input_directory=source,
                    label="test",
                    workers=2,
                    receipt=receipt,
                )
                output = root / "restored"
                manifest = download(str(receipt), output, client, kind="results", workers=2)
                self.assertEqual(
                    (output / "markdowns/page_1.md").read_bytes(),
                    (run / "markdowns/page_1.md").read_bytes(),
                )
                raw_manifest = json_bytes(manifest)
                self.assertNotIn(b"must-not-publish", raw_manifest)
                self.assertNotIn(b"must-not-publish", (output / "results.jsonl").read_bytes())
                entry = next(entry for entry in manifest["files"] if entry["path"].endswith(".md"))
                self.assertEqual(entry["provenance"]["input_sha256"], digest(b"%PDF fixture"))
                self.assertEqual(entry["provenance"]["input_hash_origin"], "conversion")
                (output / "markdowns/page_1.md").write_text("local edits")
                with self.assertRaisesRegex(ValueError, "Local file differs"):
                    download(str(receipt), output, client, kind="results")
                self.assertEqual((output / "markdowns/page_1.md").read_text(), "local edits")

    def test_untrusted_manifest_cannot_escape_or_replace_with_corrupt_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entry = {
                "path": "../escape.md",
                "sha256": digest(b"good"),
                "size": 4,
                "url": "https://storage.googleapis.com/test-bucket/file",
            }
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                validated_targets({"files": [entry]}, root)
            entry["path"] = "page_1.md"
            manifest = root / "manifest.json"
            manifest.write_bytes(
                json_bytes({"schema_version": 1, "kind": "results", "files": [entry]})
            )
            target = root / "output"
            target.mkdir()
            (target / "page_1.md").write_text("local original")
            with httpx.Client(
                transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"oops"))
            ) as client:
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    download(str(manifest), target, client, kind="results", overwrite=True)
            self.assertEqual((target / "page_1.md").read_text(), "local original")
            self.assertEqual(len(list(target.iterdir())), 1)
