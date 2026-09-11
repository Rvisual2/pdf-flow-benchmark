"""Compare directory contents, optionally saving the same report to disk."""

import argparse
import difflib
from collections import Counter
from pathlib import Path
from typing import Iterator


def compare_directories(before: Path, after: Path, excluded: Path | None = None) -> Iterator[str]:
    for directory in (before, after):
        if not directory.is_dir():
            raise ValueError(f"Directory does not exist: {directory}")
    relative_paths = sorted(
        {
            path.relative_to(directory)
            for directory in (before, after)
            for path in directory.rglob("*")
            if path.is_file() and path.resolve() != excluded
        }
    )
    counts = Counter()
    for relative_path in relative_paths:
        left, right = before / relative_path, after / relative_path
        if not left.is_file() or not right.is_file():
            status = "MISSING IN BEFORE" if not left.is_file() else "MISSING IN AFTER"
            counts[status] += 1
            yield f"[{status}] {relative_path}\n"
            continue
        left_bytes, right_bytes = left.read_bytes(), right.read_bytes()
        status = "IDENTICAL" if left_bytes == right_bytes else "DIFFERENT"
        counts[status] += 1
        yield f"[{status}] {relative_path}\n"
        if status == "DIFFERENT":
            try:
                left_lines = left_bytes.decode("utf-8").splitlines(keepends=True)
                right_lines = right_bytes.decode("utf-8").splitlines(keepends=True)
            except UnicodeDecodeError:
                yield "Binary files differ\n"
            else:
                yield from difflib.unified_diff(
                    left_lines, right_lines, fromfile=str(left), tofile=str(right)
                )
                yield "\n"
    yield (
        "\n"
        + ", ".join(
            f"{name.lower()}: {counts[name]}"
            for name in ("IDENTICAL", "DIFFERENT", "MISSING IN BEFORE", "MISSING IN AFTER")
        )
        + "\n"
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdf-benchmark compare", description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("report", type=Path, nargs="?")
    options = parser.parse_args(arguments)
    try:
        # Discover/compare before opening a report that may live inside an input directory.
        report = "".join(
            compare_directories(
                options.before, options.after, options.report.resolve() if options.report else None
            )
        )
        print(report, end="")
        if options.report:
            options.report.write_text(report, encoding="utf-8")
        return 0
    except (ValueError, OSError) as error:
        parser.error(str(error))
