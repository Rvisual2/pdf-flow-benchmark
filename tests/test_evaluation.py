"""Reference schema, scoring invariants, and evaluation from reviewed JSON."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pdf_benchmark.cli import main
from pdf_benchmark.evaluation.ground_truth import (
    ReferencePage,
    ReferenceSnippet,
    read_ground_truth,
    write_ground_truth,
)


class GroundTruthTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)

    def test_evaluation_from_json_requires_no_source_pdf_or_workbook(self):
        reference = self.directory / "reference.json"
        write_ground_truth(
            reference, [ReferencePage(1, (ReferenceSnippet("ocr:1", "Exact text", "ocr"),))]
        )
        markdown = self.directory / "markdowns"
        markdown.mkdir()
        (markdown / "page_1.md").write_text("Exact text")
        mapping = self.directory / "mapping.csv"
        pd.DataFrame([{"Page": 1, "Folder": "manuals"}]).to_csv(mapping, index=False)
        output = self.directory / "evaluation"
        result = main(
            [
                "evaluate",
                "--ground-truth-input",
                str(reference),
                "--pdf-path",
                "missing-pdfs",
                "--excel-path",
                "missing.xlsx",
                "--page-mapping",
                str(mapping),
                "--markdown-source",
                f"new_parser={markdown}",
                "--output-dir",
                str(output),
            ]
        )
        self.assertEqual(result, 0)
        scores = pd.read_csv(output / "scores.csv")
        self.assertEqual(
            scores.to_dict("records"), [{"tool": "new_parser", "score_percent": 100.0}]
        )
        captured_output = io.StringIO()
        with contextlib.redirect_stdout(captured_output):
            self.assertEqual(main(["results", "scores", str(output), "--json"]), 0)
        self.assertEqual(json.loads(captured_output.getvalue()), scores.to_dict("records"))
        self.assertEqual(
            read_ground_truth(output / "ground_truth.json"), read_ground_truth(reference)
        )
