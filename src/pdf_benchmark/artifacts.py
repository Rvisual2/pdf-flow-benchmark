"""Own all files and progress records for one conversion run."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import DocumentOutcome, Metadata


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunArtifacts:
    def __init__(self, directory: Path):
        self.directory = directory
        self.records: list[Metadata] = []

    def check_available(self, overwrite: bool = False) -> None:
        if self.directory.exists() and any(self.directory.iterdir()) and not overwrite:
            raise ValueError(
                f"Output is not empty: {self.directory}. Choose a new --output-dir or use --overwrite."
            )

    def prepare(self, overwrite: bool = False) -> None:
        self.check_available(overwrite)
        markdown_directory = self.directory / "markdowns"
        markdown_directory.mkdir(parents=True, exist_ok=True)
        if overwrite:
            for path in markdown_directory.glob("*.md"):
                path.unlink()
            # Retain remote IDs in submissions.jsonl for interrupted older runs.
            for filename in ("run.json", "duration.txt", "config.json"):
                (self.directory / filename).unlink(missing_ok=True)
        self.records.clear()
        (self.directory / "results.jsonl").write_text("", encoding="utf-8")

    def write_json(self, filename: str, data: Metadata) -> None:
        (self.directory / filename).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def append_json(self, filename: str, data: Metadata) -> None:
        with (self.directory / filename).open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps({**data, "timestamp": utc_timestamp()}, ensure_ascii=False) + "\n"
            )

    def submission(self, metadata: Metadata) -> None:
        """Persist remote IDs before polling, without resubmitting on failure."""
        self.append_json("submissions.jsonl", metadata)

    def record(self, outcome: DocumentOutcome, config: Metadata) -> None:
        metadata = outcome.document.metadata if outcome.document else {}
        record = {
            **metadata,
            "file": str(outcome.path),
            "config": config,
            "success": False,
            "duration_seconds": outcome.duration_seconds,
            "source_sha256": None,
        }
        try:
            record["source_sha256"] = hashlib.sha256(outcome.path.read_bytes()).hexdigest()
            if outcome.error:
                raise ValueError(outcome.error)
            if (
                outcome.document is None
                or not isinstance(outcome.document.markdown, str)
                or not outcome.document.markdown.strip()
            ):
                raise ValueError("Empty Markdown output")
            target = self.directory / "markdowns" / f"{outcome.path.stem}.md"
            target.write_text(outcome.document.markdown, encoding="utf-8")
            record.update(success=True, markdown_file=str(target))
        except (ValueError, OSError) as error:
            record["error"] = outcome.error or f"{type(error).__name__}: {error}"
        self.records.append(record)
        self.append_json("results.jsonl", record)
        print(f"{'OK' if record['success'] else 'FAILED'} {outcome.path.name}", flush=True)

    def finish(self, elapsed_seconds: float, config: Metadata) -> int:
        failures = sum(not record["success"] for record in self.records)
        from .provenance import repository_provenance

        self.write_json(
            "run.json",
            {
                "timestamp": utc_timestamp(),
                "provenance": repository_provenance(),
                "config": config,
                "total": len(self.records),
                "failed": failures,
                "wall_seconds": elapsed_seconds,
            },
        )
        (self.directory / "duration.txt").write_text(
            f"Total Duration: {elapsed_seconds:.2f}s\n", encoding="utf-8"
        )
        print(
            f"{len(self.records) - failures}/{len(self.records)} succeeded in {elapsed_seconds:.2f}s"
        )
        return int(failures > 0)
