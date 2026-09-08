"""Command line interface.

Exit codes are the interface a hook or CI job actually consumes:

===  ==========================================================================
0    every discovered file was analyzed
1    at least one discovered file is ``unknown``
2    usage, configuration, or adapter-contract error
3    ``--check`` found the generated documents out of date
4    ``--gate`` refused a newly added file
===  ==========================================================================

4 is separate from 1 on purpose: a hook that blocks a commit wants to distinguish "the
file you are adding is not acceptable" from "the repository contains something this tool
cannot read", because the second is usually somebody else's file and a different fix.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .analyze import analyze_file, build_report
from .config import Config, load_config
from .errors import OmitnixError
from .gate import new_files, run_gate
from .globs import normalize
from .model import Status
from .registry import build_adapter_set
from .render import (
    PROVENANCE_PREFIXES,
    payload_for_check,
    render_json,
    render_markdown,
    to_payload,
)
from .schema import load_schema_tables

EXIT_OK = 0
EXIT_UNKNOWN = 1
EXIT_ERROR = 2
EXIT_STALE = 3
EXIT_GATE = 4


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omitnix",
        description=(
            "Generate a per-file code inventory and a table reverse index, and fail when "
            "a discovered file could not be analyzed."
        ),
    )
    parser.add_argument("--version", action="version", version=f"omitnix {__version__}")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository to scan (default: current directory)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="path to .omitnix.yaml (default: the one at the root, if any)",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        metavar="PATH",
        help="analyze only these files, as a pre-commit hook would pass them",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "with --files, write the generated documents anyway. Off by default because "
            "a partial run would overwrite the full index with a subset."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; compare the generated documents on disk with a fresh run",
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help=(
            "check only the files git reports as newly added, and refuse one that lacks "
            "what its adapter is able to report. Writes nothing."
        ),
    )
    parser.add_argument(
        "--print",
        dest="print_path",
        metavar="PATH",
        help="print the record for one file as JSON and exit",
    )
    return parser


def _run_print(args: argparse.Namespace, out, err) -> int:
    config = load_config(args.root, args.config)
    adapter_set = build_adapter_set(config.adapters)
    schema_tables = frozenset()
    if config.schema_snapshot:
        schema_tables = load_schema_tables(config.root / config.schema_snapshot)

    candidate = Path(args.print_path)
    absolute = candidate if candidate.is_absolute() else config.root / candidate
    try:
        rel = normalize(str(absolute.resolve().relative_to(config.root)))
    except ValueError:
        print(f"omitnix: {args.print_path} is outside {config.root}", file=err)
        return EXIT_ERROR
    if not absolute.is_file():
        print(f"omitnix: no such file: {args.print_path}", file=err)
        return EXIT_ERROR

    record = analyze_file(rel, adapter_set, config, schema_tables)
    print(json.dumps(record.to_json(), indent=2, ensure_ascii=False), file=out)
    return EXIT_UNKNOWN if record.status is Status.UNKNOWN else EXIT_OK


def _run_gate(args: argparse.Namespace, config: Config, out, err) -> int:
    selection = new_files(config, args.files)

    for path in selection.missing:
        print(f"omitnix: no such file under {config.root}: {path}", file=err)
    if selection.excluded_by_config:
        print(
            f"omitnix: {selection.excluded_by_config} path(s) excluded by the "
            "configuration and therefore not gated",
            file=err,
        )

    report = build_report(config, files=list(selection.paths))
    result = run_gate(report, config)

    for exemption in result.exemptions:
        print(f"omitnix: exemption applied: {exemption.line()}", file=err)
    # Printed whether or not the gate passes: these are things the analyzer could not
    # follow, and they have to stay visible without deciding the outcome.
    for notice in result.notices:
        print(f"omitnix: not followed: {notice.line()}", file=err)
    # A check that applied but could not be made. Said out loud rather than passed over,
    # so that "we did not look" is never mistaken for "we looked and it was fine".
    for capability in result.unconfigured:
        print(
            f"omitnix: {capability} not checked: {capability}_functions is empty in the "
            "configuration, so there is nothing to look for",
            file=err,
        )

    if result.passed:
        count = len(result.checked)
        subject = "file" if count == 1 else "files"
        print(f"omitnix: gate passed. {count} newly added {subject} checked", file=out)
        return EXIT_OK

    failed = len(result.failed_paths)
    subject = "file" if failed == 1 else "files"
    print(f"omitnix: gate refused {failed} newly added {subject}", file=err)
    for finding in result.findings:
        print(f"  {finding.line()}", file=err)
    return EXIT_GATE


def _strip_commit_line(text: str) -> str:
    """Drop the provenance line before comparing.

    It names the commit and whether the tree was dirty, which differ on every run for
    reasons that have nothing to do with whether the inventory is current.
    """
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.startswith(PROVENANCE_PREFIXES)
    )


def _run_check(report, config, out, err) -> int:
    fresh_payload = payload_for_check(to_payload(report))
    differences: list[str] = []

    json_path = config.json_path
    if not json_path.is_file():
        differences.append(f"{json_path} does not exist")
    else:
        try:
            stored = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            differences.append(f"{json_path} could not be read: {exc}")
        else:
            stored_payload = payload_for_check(stored)
            if stored_payload != fresh_payload:
                differences.extend(_describe_json_difference(stored_payload, fresh_payload))

    markdown_path = config.markdown_path
    if not markdown_path.is_file():
        differences.append(f"{markdown_path} does not exist")
    elif _strip_commit_line(markdown_path.read_text(encoding="utf-8")) != _strip_commit_line(
        render_markdown(report)
    ):
        differences.append(f"{markdown_path} differs from a fresh run")

    if differences:
        print("omitnix: generated documents are out of date", file=err)
        for line in differences:
            print(f"  {line}", file=err)
        print("  regenerate with: omitnix", file=err)
        return EXIT_STALE

    print(f"omitnix: up to date. {report.coverage.headline()}", file=out)
    return EXIT_OK


def _describe_json_difference(stored: dict, fresh: dict) -> list[str]:
    stored_files = {entry["path"]: entry for entry in stored.get("files", [])}
    fresh_files = {entry["path"]: entry for entry in fresh.get("files", [])}
    added = sorted(set(fresh_files) - set(stored_files))
    removed = sorted(set(stored_files) - set(fresh_files))
    changed = sorted(
        path
        for path in set(stored_files) & set(fresh_files)
        if stored_files[path] != fresh_files[path]
    )

    lines: list[str] = []
    for label, paths in (("added", added), ("removed", removed), ("changed", changed)):
        if paths:
            shown = ", ".join(paths[:5])
            more = f" (+{len(paths) - 5} more)" if len(paths) > 5 else ""
            lines.append(f"{len(paths)} file(s) {label}: {shown}{more}")
    if stored.get("coverage") != fresh.get("coverage"):
        lines.append(f"coverage {stored.get('coverage')} -> {fresh.get('coverage')}")
    if stored.get("tables") != fresh.get("tables"):
        lines.append("the table reverse index differs")
    if not lines:
        lines.append("content differs")
    return lines


def main(argv: list[str] | None = None, out=None, err=None) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    args = _build_parser().parse_args(argv)

    if args.gate and (args.check or args.write):
        # The gate reports on new files only. Letting it write or compare the documents
        # would put a slice of the repository where the full index belongs.
        print("omitnix: --gate cannot be combined with --check or --write", file=err)
        return EXIT_ERROR

    try:
        if args.print_path:
            return _run_print(args, out, err)

        config = load_config(args.root, args.config)
        if args.gate:
            return _run_gate(args, config, out, err)
        report = build_report(config, files=args.files)
    except OmitnixError as exc:
        print(f"omitnix: {exc}", file=err)
        return EXIT_ERROR

    if args.files:
        selection_note = report.coverage.skipped_by_config
        if selection_note:
            print(
                f"omitnix: {selection_note} requested path(s) excluded by the configuration",
                file=err,
            )

    if args.check:
        return _run_check(report, config, out, err)

    wrote: list[Path] = []
    if args.files and not args.write:
        print(
            "omitnix: partial run (--files); documents were not written. "
            "Pass --write to overwrite them with this subset.",
            file=err,
        )
    else:
        output_dir = config.root / config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        # newline="\n" on purpose: these documents are meant to be committed, and the
        # platform that happened to run the tool must not show up as a whole-file diff.
        config.json_path.write_text(render_json(report), encoding="utf-8", newline="\n")
        config.markdown_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
        wrote = [config.json_path, config.markdown_path]

    print(report.coverage.headline(), file=out)
    for path in wrote:
        print(f"wrote {path}", file=out)

    if report.coverage.unknown:
        print(
            f"omitnix: {report.coverage.unknown} discovered file(s) could not be analyzed. "
            "Give the extension an adapter, or exclude it explicitly in .omitnix.yaml.",
            file=err,
        )
        unknown = [record for record in report.files if record.status is Status.UNKNOWN]
        for record in unknown[:20]:
            print(f"  {record.path}: {record.unknown_reason}", file=err)
        if len(unknown) > 20:
            print(f"  ... {len(unknown) - 20} more (see {config.markdown_path})", file=err)
        return EXIT_UNKNOWN

    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
