"""Discover, convert, and evaluate documents through one command-line interface."""

import argparse
import sys
from importlib.metadata import version
from pathlib import Path

from .artifacts import RunArtifacts
from .files import (
    DATA_DIRECTORY,
    ROOT,
    RUNS_DIRECTORY,
    discover_pdfs,
    positive_int,
    require_api_key,
)
from .registry import PARSERS

EXAMPLES = """Start here:
  pdf-benchmark parsers list
  pdf-benchmark data download
  pdf-benchmark data show
  pdf-benchmark convert docling --limit 2
  pdf-benchmark evaluate --output-dir results/runs/evaluation
  pdf-benchmark results scores results/runs/evaluation

Use '<command> --help' or 'parsers show <name>' for options and defaults.
"""


def conversion_parser(name: str) -> argparse.ArgumentParser:
    spec = PARSERS[name]
    parser = argparse.ArgumentParser(
        prog=f"pdf-benchmark convert {name}",
        description=spec.description,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=f"Example: pdf-benchmark convert {name} --limit 2 --output-dir results/runs/{name}-smoke",
    )
    parser.add_argument(
        "--input-dir", type=Path, default=DATA_DIRECTORY / "pdfs", help="Directory containing PDFs"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=RUNS_DIRECTORY / spec.output_directory,
        help="Save Markdown and run metadata here",
    )
    parser.add_argument(
        "--limit", type=positive_int, help="Convert only the first N PDFs in numeric page order"
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace existing Markdown and run summaries"
    )
    if spec.api_key:
        parser.add_argument(
            "--timeout",
            type=positive_int,
            default=7200,
            help="Deadline in seconds per document, or per native server batch",
        )
    if spec.concurrent:
        parser.add_argument(
            "--concurrency",
            type=positive_int,
            default=5,
            help="Maximum in-flight document requests",
        )
    spec.load().add_arguments(parser)
    return parser


def conversion_main(arguments: list[str]) -> int:
    selector = argparse.ArgumentParser(
        prog="pdf-benchmark convert",
        description="Convert PDFs with a local or paid parser.",
        epilog="Inspect options: pdf-benchmark convert <parser> --help",
    )
    providers = selector.add_subparsers(dest="parser", title="available parsers")
    for name, spec in PARSERS.items():
        providers.add_parser(name, help=spec.description, add_help=False)
    if not arguments or arguments[0] in {"-h", "--help"}:
        selector.print_help()
        return 0
    # Provider flags belong to the selected adapter, not the selector.
    selected = selector.parse_args(arguments[:1])
    spec = PARSERS[selected.parser]
    parser = conversion_parser(selected.parser)
    options = parser.parse_args(arguments[1:])
    try:
        paths = discover_pdfs(options.input_dir, options.limit)
        key = require_api_key(spec.api_key) if spec.api_key else None
        RunArtifacts(options.output_dir).check_available(options.overwrite)
        return spec.load().run(options, paths, key)
    except (ValueError, OSError) as error:
        parser.error(str(error))


def add_json_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Write machine-readable JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-benchmark",
        description="Explore PDF parsers, generate Markdown, and evaluate reading-flow accuracy.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {version('prod-pdfbenchmark')}"
    )
    commands = parser.add_subparsers(dest="command", title="commands")
    parsers = commands.add_parser("parsers", help="Discover available parsers and configuration")
    parser_commands = parsers.add_subparsers(dest="action")
    parser_list = parser_commands.add_parser(
        "list", help="List parsers and credential presence (no API calls)"
    )
    add_json_option(parser_list)
    parser_show = parser_commands.add_parser(
        "show", help="Show a parser's options, defaults, and credential status"
    )
    parser_show.add_argument("name", choices=PARSERS)
    add_json_option(parser_show)
    data = commands.add_parser("data", help="Inspect the dataset and ground-truth snippets")
    data_commands = data.add_subparsers(dest="action")
    for action, description in (
        ("show", "Show document, reference, and category counts"),
        ("page", "Show reference snippets for one page"),
    ):
        command = data_commands.add_parser(action, help=description)
        if action == "page":
            command.add_argument("number", type=positive_int)
        command.add_argument(
            "--directory",
            type=Path,
            default=DATA_DIRECTORY,
            help="Dataset directory (default: data/)",
        )
        add_json_option(command)
    results = commands.add_parser("results", help="Browse saved runs and display scores")
    result_commands = results.add_subparsers(dest="action")
    from .storage.cli import add_commands

    add_commands(data_commands, "data")
    add_commands(result_commands, "results")
    result_list = result_commands.add_parser(
        "list", help="List saved conversion runs and evaluations"
    )
    result_list.add_argument(
        "--directory", type=Path, default=ROOT / "results", help="Search this results directory"
    )
    result_list.add_argument(
        "--limit", type=positive_int, default=20, help="Maximum records to display (default: 20)"
    )
    add_json_option(result_list)
    for action, description in (
        ("show", "Show a conversion summary or evaluation scores"),
        ("scores", "Display a ranked score table from a report directory or CSV"),
    ):
        command = result_commands.add_parser(action, help=description)
        command.add_argument("path", type=Path)
        add_json_option(command)
    for name, description in (
        ("convert", "Generate Markdown with a selected parser"),
        ("evaluate", "Score Markdown against reference snippets"),
        ("compare", "Compare files in two output directories"),
        ("dashboard", "Export scores and document evidence for the React dashboard"),
    ):
        commands.add_parser(name, help=description, add_help=False)
    parser.set_defaults(group_parsers={"parsers": parsers, "data": data, "results": results})
    return parser


def main(arguments: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if arguments and arguments[0] == "convert":
        return conversion_main(arguments[1:])
    if arguments and arguments[0] == "evaluate":
        from .evaluation.cli import main as evaluate

        return evaluate(arguments[1:])
    if arguments and arguments[0] == "dashboard":
        from .dashboard import main as dashboard

        return dashboard(arguments[1:])
    if arguments and arguments[0] == "compare":
        from .compare import main as compare

        return compare(arguments[1:])
    parser = build_parser()
    options = parser.parse_args(arguments)
    if options.command is None:
        parser.print_help()
        return 0
    if options.action is None:
        options.group_parsers[options.command].print_help()
        return 0
    from . import inspection

    try:
        if options.action in {"upload", "download", "releases"}:
            from .storage.cli import run

            return run(options)
        if options.command == "parsers":
            return (
                inspection.list_parsers(options.json)
                if options.action == "list"
                else inspection.show_parser(options.name, options.json)
            )
        if options.command == "data":
            return inspection.inspect_data(
                options.directory, getattr(options, "number", None), options.json
            )
        if options.action == "list":
            return inspection.list_results(options.directory, options.limit, options.json)
        if options.action == "scores":
            return inspection.show_scores(options.path, options.json)
        return inspection.show_result(options.path, options.json)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")
