"""Command line interface.

Exit codes are the interface a hook or CI job actually consumes:

===  ==========================================================================
0    the run finished; anything unreadable was reported rather than hidden
1    a discovered file is ``unknown`` **and** the repository asked to fail on that
2    usage, configuration, or adapter-contract error
3    ``--check`` found the generated document out of date
4    ``--gate`` refused a newly added file
===  ==========================================================================

1 answers for ``unknown`` only -- a file whose extension an adapter claims and could not
read. A file no adapter claims is ``unclaimed``: counted, reported by extension, and never
a reason to fail, because there is nothing there to have gone wrong. A repository full of
prose and configuration is not a repository with a problem.

1 is opt-in (``fail_on_unknown`` in the configuration, off by default) and 4 is not.
That asymmetry is the point. A refused new file is being added right now by the person
reading the message, who can supply what is missing. A file this tool cannot read is
usually somebody else's, and sometimes nobody's fault at all -- a grammar that chokes on
valid source has no fix the repository can apply. Failing a build over it only converts
a reported gap into a chore, which is how a check gets switched off. What keeps the gap
visible is that the generated documents name it, and they do that either way.

``--workspace`` reuses the same codes across many repositories: 1 when any repository
that ran holds an unknown file, and 2 when a repository could not be run at all. The
second takes precedence, because a repository nothing could run is a hole of unknown
size, and it must not be reported as the smaller, well-understood failure.
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
from .render import payload_for_check, render_json, to_payload
from .scan import discover_files
from .schema import load_schema_tables
from .workspace import (
    WORKSPACE_OUTPUT_DIR,
    DeploymentStatus,
    default_jobs,
    discover_repositories,
    run_workspace,
    survey_workspace,
    write_workspace_documents,
)

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
            "with --files, write the generated document anyway. Off by default because "
            "a partial run would overwrite the full index with a subset."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; compare the generated document on disk with a fresh run",
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
        "--since",
        metavar="REF",
        default=None,
        help=(
            "with --gate, treat as new whatever this branch added since REF instead of "
            "reading the working tree. This is the form CI can use: it holds for work "
            "anyone committed, whether or not their machine had the hook installed."
        ),
    )
    parser.add_argument(
        "--print",
        dest="print_path",
        metavar="PATH",
        help="print the record for one file as JSON and exit",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help=(
            "walk the working directory instead of analyzing what git tracks. Includes "
            "untracked files, and with them whatever local scratch the working directory "
            "happens to hold. Applies to a single repository the same way it does inside "
            "--workspace; the default either way is what git tracks."
        ),
    )

    workspace = parser.add_argument_group(
        "workspace mode",
        "Run across every git repository under a directory. Records are keyed "
        "<repository>/<path> and reverse indexes stay inside their repository.",
    )
    workspace.add_argument(
        "--workspace",
        type=Path,
        metavar="DIR",
        help="analyze every repository under DIR instead of a single repository",
    )
    workspace.add_argument(
        "--out",
        type=Path,
        metavar="DIR",
        default=None,
        help=(
            "where a workspace run writes "
            f"(default: ./{WORKSPACE_OUTPUT_DIR}). Scanned repositories are not "
            "written to unless --write-per-repo says so."
        ),
    )
    workspace.add_argument(
        "--exclude-repo",
        action="append",
        default=None,
        metavar="GLOB",
        help=(
            "skip repositories whose workspace-relative path matches GLOB, or that sit "
            "under a directory matching it. Repeatable. Skipped repositories are "
            "reported, not dropped."
        ),
    )
    workspace.add_argument(
        "--write-per-repo",
        action="store_true",
        help="also write .omitnix/ inside each scanned repository (off by default)",
    )
    workspace.add_argument(
        "--no-workspace-excludes",
        action="store_true",
        help=(
            "do not add the workspace default exclusions to each repository. Everything "
            "a repository contains is discovered, and most of it will be unknown."
        ),
    )
    workspace.add_argument(
        "--jobs",
        type=int,
        default=None,
        metavar="N",
        help=(
            "worker processes for a workspace run (default: one per core, at most 8). "
            "There is no cache: identical bytes in two places can analyze to different "
            "results, so repeated work is answered with parallelism instead."
        ),
    )
    workspace.add_argument(
        "--dry-run",
        action="store_true",
        help="with --workspace, list the repositories that would be analyzed and stop",
    )
    workspace.add_argument(
        "--status",
        action="store_true",
        help=(
            "with --workspace, report where this tool is deployed and whether what it "
            "generated has gone stale, instead of analyzing everything. Writes nothing. "
            "A repository with no committed index is reported as such and is not "
            "analyzed."
        ),
    )
    return parser



def _status_line(status: DeploymentStatus) -> str:
    """One repository as one line. Absent is a state, not a blank."""
    state = {
        "current": "current",
        "stale": "STALE",
        "unverified": "UNVERIFIED",
        "absent": "-",
        "unreadable": "UNREADABLE",
    }[status.state]
    applied = status.applied or "-"
    if status.state == "absent":
        applied = "-"
    pointers = "+".join(status.pointed_at_by) if status.pointed_at_by else "-"
    if not status.has_index:
        pointers = "-"
    coverage = "-"
    if status.coverage is not None:
        coverage = f"{status.coverage.analyzed}/{status.coverage.discovered}"
    mark = " (worktree)" if status.is_worktree else ""
    return f"{status.repo + mark:<38} {state:<11} {applied:<11} {coverage:<11} {pointers}"


def _run_workspace_status(args, root: Path, exclude_repos, out, err) -> int:
    """Report the deployment, rather than analyzing the code.

    Exits 3 when any committed index is out of date, for the same reason --check does:
    a stale generated document is read as the current state by whoever finds it. It
    exits 3 for an index this run was not equipped to check as well, which is a different
    sentence on stderr and the same refusal to call it fine.
    """

    def progress(position: int, total: int, repo: str) -> None:
        print(f"omitnix: [{position}/{total}] {repo}", file=err)

    statuses = survey_workspace(
        root,
        exclude_repos=exclude_repos,
        tracked_only=not args.all_files,
        progress=progress,
    )

    header = f"{'repository':<38} {'index':<11} {'applied':<11} {'analyzed':<11} pointed at by"
    print(header, file=out)
    print("-" * len(header), file=out)
    for status in statuses:
        print(_status_line(status), file=out)

    deployed = [s for s in statuses if s.has_index]
    stale = [s for s in deployed if s.state == "stale"]
    unverified = [s for s in deployed if s.state == "unverified"]
    unreadable = [s for s in deployed if s.state == "unreadable"]
    unpointed = [s for s in deployed if s.state != "absent" and not s.pointed_at_by]

    # "Could not be checked" belongs in the same sentence as "out of date", not in a
    # footnote. A summary that says only "0 out of date" while nine repositories were
    # never compared reads as an all-clear.
    unchecked = (
        f", {len(unverified)} could not be checked here" if unverified else ""
    )
    print("", file=out)
    print(
        f"omitnix: {len(statuses)} repositor(y/ies) surveyed, {len(deployed)} with a "
        f"committed index, {len(stale)} out of date{unchecked}. Nothing was written.",
        file=out,
    )

    for status in stale:
        print(f"omitnix: out of date: {status.repo}", file=err)
        if status.is_worktree:
            # Telling somebody to regenerate here would point the fix at a branch whose
            # contents usually arrive by merge. Say where the tree actually comes from.
            print(
                f"  this is a linked worktree of {status.main_worktree}; regenerating "
                "here commits to whatever branch it has checked out",
                file=err,
            )
        else:
            print(f"  regenerate with: omitnix --root {status.root}", file=err)

    for status in unverified:
        # Deliberately not "regenerate": following that advice here would replace a good
        # index with the near-empty one this machine is able to produce.
        print(f"omitnix: could not be checked: {status.repo}", file=err)
        print(f"  {status.detail}", file=err)

    for status in unreadable:
        print(f"omitnix: could not be surveyed: {status.repo}: {status.detail}", file=err)

    for status in unpointed:
        # An index that no instruction file names is found by luck. Saying so is the
        # whole point of reporting coverage rather than a file count.
        print(
            f"omitnix: {status.repo} has an index that neither CLAUDE.md nor AGENTS.md "
            "names, so a reader is not told to look at it",
            file=err,
        )

    # Unverified is not a pass. "I could not check" and "I checked and it is fine" are
    # the same exit code only in a survey nobody should wire into anything.
    if stale or unverified or unreadable:
        return EXIT_STALE
    return EXIT_OK


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

    # --print exists to explain one line of the index, so it has to be held to the same
    # scope the index was built under. Analyzing the file on its own terms would let it
    # follow a reference the full run refuses, and print an answer the index never shows.
    in_scope = frozenset(discover_files(config))

    record = analyze_file(rel, adapter_set, config, schema_tables, in_scope)
    print(json.dumps(record.to_json(), indent=2, ensure_ascii=False), file=out)
    if record.status is Status.UNKNOWN and config.fail_on_unknown:
        return EXIT_UNKNOWN
    return EXIT_OK


def _run_gate(args: argparse.Namespace, config: Config, out, err) -> int:
    selection = new_files(config, args.files, since=args.since)
    # Said on every run, pass or fail. "The gate passed" means nothing until you know
    # what it was asked about, and the two questions have very different coverage: the
    # working tree answers only for uncommitted work on this machine.
    basis = f"added since {args.since}" if args.since else "newly added in the working tree"

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
    # Printed whether or not the gate passes: a statement the analyzer could not follow,
    # or a file no adapter claims. Neither decides the outcome, and both have to stay
    # visible -- a gate that passes in silence says more than it checked.
    for notice in result.notices:
        print(f"omitnix: noted: {notice.line()}", file=err)
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
        print(f"omitnix: gate passed. checked {count} {subject} {basis}", file=out)
        return EXIT_OK

    failed = len(result.failed_paths)
    subject = "file" if failed == 1 else "files"
    print(f"omitnix: gate refused {failed} {subject} {basis}", file=err)
    for finding in result.findings:
        print(f"  {finding.line()}", file=err)
    return EXIT_GATE


_WORKSPACE_ONLY = (
    ("--out", "out"),
    ("--exclude-repo", "exclude_repo"),
    ("--write-per-repo", "write_per_repo"),
    ("--no-workspace-excludes", "no_workspace_excludes"),
    ("--jobs", "jobs"),
    ("--dry-run", "dry_run"),
)


def _reject_workspace_only_options(args: argparse.Namespace, err) -> int | None:
    # `is not None` rather than truthiness: `--jobs 0` is a value the user typed, and
    # refusing it here is better than accepting it and doing nothing with it.
    offered = [flag for flag, dest in _WORKSPACE_ONLY if getattr(args, dest) not in (None, False)]
    if not offered:
        return None
    print(
        f"omitnix: {', '.join(offered)} only applies with --workspace",
        file=err,
    )
    return EXIT_ERROR


def _run_workspace(args: argparse.Namespace, out, err) -> int:
    for flag, present in (
        ("--check", args.check),
        ("--gate", args.gate),
        ("--since", args.since is not None),
        ("--files", bool(args.files)),
        ("--print", bool(args.print_path)),
        ("--write", args.write),
    ):
        if present:
            # Each of these answers a question about one repository: is this document
            # current, is this file new, what does this path contain. Silently applying
            # one to fifty repositories would give an answer to a question nobody asked.
            print(f"omitnix: {flag} cannot be combined with --workspace", file=err)
            return EXIT_ERROR

    root = args.workspace
    if not root.is_dir():
        print(f"omitnix: no such directory: {root}", file=err)
        return EXIT_ERROR

    exclude_repos = tuple(args.exclude_repo or ())

    if args.dry_run:
        discovery = discover_repositories(root.resolve(), exclude_repos)
        for repo in discovery.repositories:
            print(repo, file=out)
        print(
            f"omitnix: {len(discovery.repositories) + len(discovery.excluded)} "
            f"repositor(y/ies) found, {len(discovery.excluded)} excluded by request, "
            f"{len(discovery.repositories)} would be analyzed. Nothing was written.",
            file=out,
        )
        for repo in discovery.excluded:
            print(f"omitnix: excluded by request: {repo}", file=err)
        for entry in discovery.unreadable_directories:
            print(f"omitnix: could not list: {entry}", file=err)
        return EXIT_OK

    if args.status:
        return _run_workspace_status(args, root, exclude_repos, out, err)

    out_dir = (args.out or Path.cwd() / WORKSPACE_OUTPUT_DIR).resolve()
    jobs = args.jobs if args.jobs is not None else default_jobs()
    if jobs < 1:
        print("omitnix: --jobs must be at least 1", file=err)
        return EXIT_ERROR

    def progress(position: int, total: int, repo: str) -> None:
        print(f"omitnix: [{position}/{total}] {repo}", file=err)

    result = run_workspace(
        root,
        out_dir=out_dir,
        exclude_repos=exclude_repos,
        apply_workspace_excludes=not args.no_workspace_excludes,
        jobs=jobs,
        write_per_repo=args.write_per_repo,
        tracked_only=not args.all_files,
        progress=progress,
    )
    documents = write_workspace_documents(result, out_dir)

    coverage = result.coverage
    print(
        f"omitnix: {len(result.succeeded)} repositor(y/ies) analyzed, "
        f"{len(result.failed)} could not be run, "
        f"{len(result.excluded_repositories)} excluded by request",
        file=out,
    )
    print(coverage.headline(), file=out)
    for path in documents:
        print(f"wrote {path}", file=out)

    unconfigured = result.unconfigured_authorization
    if unconfigured:
        # Said out loud on every run. A column that reads "not configured" in a document
        # nobody opens is how "we did not check" turns into "there is nothing to check".
        print(
            f"omitnix: {len(unconfigured)} repositor(y/ies) name no authorization "
            "function, so no authorization check was made in them. This is not a "
            "finding that they have none.",
            file=err,
        )

    for run in result.succeeded:
        if run.discovery_note:
            print(f"omitnix: {run.repo}: {run.discovery_note}", file=err)
    for run in result.failed:
        print(f"omitnix: could not run {run.repo}: {run.error}", file=err)
    for entry in result.unreadable_directories:
        print(f"omitnix: could not list: {entry}", file=err)

    if coverage.unclaimed:
        # Printed whatever the outcome. The number is the whole point of counting them,
        # and it is not a failure: nothing tried to read these files.
        print(
            f"omitnix: {coverage.unclaimed} discovered file(s) are claimed by no adapter. "
            f"Each repository's entry in {documents[0]} counts them by extension.",
            file=err,
        )

    if result.failed:
        return EXIT_ERROR
    if coverage.unknown:
        print(
            f"omitnix: {coverage.unknown} discovered file(s) have an adapter that could "
            f"not read them. Each repository's entry in {documents[0]} names them.",
            file=err,
        )
        return EXIT_UNKNOWN
    return EXIT_OK


def _report_not_analyzed(report, config: Config, err) -> None:
    """Say what was not analyzed, in the two forms the two facts deserve.

    A failure is named: an adapter claims the extension and could not read the file, so
    there is one file to go and look at. An unclaimed extension is counted: nothing tried,
    the extension is the entire fact, and printing it once per file is how the one real
    failure ends up buried in ninety-five lines about Markdown.
    """
    _report_unknown(report, config, err)
    _report_unclaimed(report, err)


def _report_unknown(report, config: Config, err) -> None:
    """Name the files an adapter claimed and could not read. Truncated, never silently."""
    unknown = report.unknown_files
    if not unknown:
        return
    print(
        f"omitnix: {len(unknown)} discovered file(s) have an adapter that could not read "
        "them. Each one is a defect in this tool or in the file itself.",
        file=err,
    )
    for record in unknown[:20]:
        print(f"  {record.path}: {record.reason}", file=err)
    if len(unknown) > 20:
        print(f"  ... {len(unknown) - 20} more (see {config.json_path})", file=err)


def _report_unclaimed(report, err) -> None:
    """Count the files no adapter claims, by extension. Never one line per file."""
    counts = report.unclaimed_extensions
    if not counts:
        return
    listed = ", ".join(f"{extension} x{count}" for extension, count in counts.items())
    print(
        f"omitnix: {report.coverage.unclaimed} discovered file(s) are claimed by no "
        "adapter, so nothing tried to read them. They are counted, and each one is in "
        "the generated document by name:",
        file=err,
    )
    print(f"  {listed}", file=err)


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

    if differences:
        print("omitnix: generated document is out of date", file=err)
        for line in differences:
            print(f"  {line}", file=err)
        print("  regenerate with: omitnix", file=err)
        return EXIT_STALE

    # Being current is not the same as being complete, so whatever was not analyzed is
    # still said here even when the document matches. Whether an unreadable file also
    # fails the run is the repository's call: see Config.fail_on_unknown for why that is
    # not this tool's to decide by default.
    if report.coverage.unknown:
        print(f"omitnix: up to date, but {report.coverage.headline()}", file=out)
    else:
        print(f"omitnix: up to date. {report.coverage.headline()}", file=out)
    _report_not_analyzed(report, config, err)
    if report.coverage.unknown and config.fail_on_unknown:
        return EXIT_UNKNOWN
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
    stored_tracked = (stored.get("generated") or {}).get("tracked_only")
    fresh_tracked = (fresh.get("generated") or {}).get("tracked_only")
    if stored_tracked != fresh_tracked:
        # Named explicitly rather than left to read as ordinary added/removed noise: the
        # two runs asked discovery a different question, which is not the same defect as
        # the document being out of date.
        lines.append(f"discovery mode changed: tracked_only {stored_tracked} -> {fresh_tracked}")
    if not lines:
        lines.append("content differs")
    return lines


def main(argv: list[str] | None = None, out=None, err=None) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    args = _build_parser().parse_args(argv)

    if args.workspace is not None:
        try:
            return _run_workspace(args, out, err)
        except OmitnixError as exc:
            print(f"omitnix: {exc}", file=err)
            return EXIT_ERROR

    rejected = _reject_workspace_only_options(args, err)
    if rejected is not None:
        return rejected

    if args.gate and (args.check or args.write):
        # The gate reports on new files only. Letting it write or compare the document
        # would put a slice of the repository where the full index belongs.
        print("omitnix: --gate cannot be combined with --check or --write", file=err)
        return EXIT_ERROR

    if args.since is not None and not args.gate:
        # Refused rather than ignored. A CI job written as `omitnix --since <base>`, with
        # --gate left off by mistake, would otherwise do a full run and go green while
        # gating nothing -- which is the exact failure this flag exists to end.
        print("omitnix: --since only applies with --gate", file=err)
        return EXIT_ERROR

    if args.gate and args.all_files:
        # The gate never calls discovery at all -- it asks git directly which files are
        # new (see gate.new_files) -- so this flag has nothing to apply to there. Refused
        # rather than silently ignored, same reasoning as --since above.
        print("omitnix: --all-files cannot be combined with --gate", file=err)
        return EXIT_ERROR

    try:
        if args.print_path:
            return _run_print(args, out, err)

        config = load_config(args.root, args.config)
        if args.gate:
            return _run_gate(args, config, out, err)
        report = build_report(config, files=args.files, tracked_only=not args.all_files)
    except OmitnixError as exc:
        print(f"omitnix: {exc}", file=err)
        return EXIT_ERROR

    if report.generated.discovery_note:
        # "git could not list tracked files, so the working tree was walked instead" is a
        # different answer from "here is what git tracks", and the two must never look
        # alike to whoever reads the run.
        print(f"omitnix: {report.generated.discovery_note}", file=err)

    if report.table_gaps.note:
        # Said on the run, not only written into the document. The table list is the half
        # of the output people read without opening the file records, and "nothing reads
        # this table" is exactly the sentence it must not be allowed to imply.
        print(f"omitnix: {report.table_gaps.note}", file=err)

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
            "omitnix: partial run (--files); the document was not written. "
            "Pass --write to overwrite it with this subset.",
            file=err,
        )
    else:
        output_dir = config.root / config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        # newline="\n" on purpose: this document is meant to be committed, and the
        # platform that happened to run the tool must not show up as a whole-file diff.
        config.json_path.write_text(render_json(report), encoding="utf-8", newline="\n")
        wrote = [config.json_path]

    print(report.coverage.headline(), file=out)
    for path in wrote:
        print(f"wrote {path}", file=out)

    _report_not_analyzed(report, config, err)
    if report.coverage.unknown and config.fail_on_unknown:
        return EXIT_UNKNOWN

    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
