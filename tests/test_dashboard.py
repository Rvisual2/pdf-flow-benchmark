"""Dashboard scores must be associated with the exact published parser outputs."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import pandas as pd

from pdf_benchmark.dashboard import export_dashboard
from pdf_benchmark.storage.transfer import digest, json_bytes


class DashboardExportTests(unittest.TestCase):
    def test_published_evidence_and_unscored_documents_reject_mismatched_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            markdowns = root / "parser/markdowns"
            markdowns.mkdir(parents=True)
            rows = [
                {
                    "page_number": 1,
                    "needle_index": 1,
                    "needle": "reference",
                    "OCR": False,
                    "parser": 0.1,
                    "parser_best_match": "referenc",
                }
            ]
            pd.DataFrame(rows).to_csv(root / "granular.csv", index=False)
            pd.DataFrame(rows).to_csv(root / "filtered.csv", index=False)
            pd.DataFrame(
                {"parser": [90.0, 90.0], "Folder_Count": [1, 1]},
                index=["science_sample", "Weighted_Mean"],
            ).to_csv(root / "scores_by_category.csv")
            (root / "page_categories.csv").write_text(
                "Page,Folder\n1,science_sample\n2,science_sample\n"
            )
            dataset, results = [], []
            for page in (1, 2):
                content = f"Markdown {page}".encode()
                (markdowns / f"page_{page}.md").write_bytes(content)
                reference = {
                    "url": f"https://storage.googleapis.com/test/{page}",
                    "size": len(content),
                    "sha256": digest(content),
                }
                dataset.append({**reference, "path": f"pdfs/page_{page}.pdf"})
                results.append(
                    {
                        **reference,
                        "path": f"parser/markdowns/page_{page}.md",
                        "provenance": {"input_sha256": reference["sha256"]},
                    }
                )
            manifests = {
                "/dataset": {"schema_version": 1, "kind": "dataset", "files": dataset},
                "/results": {"schema_version": 1, "kind": "results", "files": results},
                "/thumbnails": {
                    "schema_version": 1,
                    "kind": "thumbnails",
                    "files": [
                        {
                            "source_sha256": dataset[0]["sha256"],
                            "url": "https://storage.googleapis.com/test/cover.jpg",
                        }
                    ],
                },
            }
            configuration = {
                "dataset": "https://storage.googleapis.com/dataset",
                "releases": {"fixture": "https://storage.googleapis.com/results"},
                "thumbnails": "https://storage.googleapis.com/thumbnails",
            }
            transport = httpx.MockTransport(
                lambda request: httpx.Response(200, content=json_bytes(manifests[request.url.path]))
            )
            with (
                httpx.Client(transport=transport) as client,
                patch("pdf_benchmark.dashboard.catalog", return_value=configuration),
                patch("pdf_benchmark.dashboard.DATA_DIRECTORY", root),
            ):
                snapshot = export_dashboard(root, root, "fixture", client)
                self.assertEqual(snapshot["providers"][0]["score"], 90)
                self.assertEqual(
                    snapshot["documents"][0]["snippets"][0]["matches"]["parser"]["text"], "referenc"
                )
                self.assertIsNone(snapshot["documents"][1]["scores"]["parser"])
                self.assertEqual(
                    snapshot["documents"][0]["thumbnail"]["source_sha256"], dataset[0]["sha256"]
                )
                self.assertIsNone(snapshot["documents"][1]["thumbnail"])
                self.assertFalse(snapshot["documents"][0]["snippets"][0]["ocr"])
                (markdowns / "page_1.md").write_text("different run")
                with self.assertRaisesRegex(ValueError, "does not match the published release"):
                    export_dashboard(root, root, "fixture", client)
