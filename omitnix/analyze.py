"""The core run: discover, analyze, count, and refuse to lie about the result.

The counting invariant is the product::

    discovered == analyzed + unresolved + unknown + unclaimed

``unknown`` and ``unclaimed`` are kept apart because only one of them is a failure: an
adapter claimed the extension and could not read the file, against no adapter claiming the
extension at all. They are kept in the same total because both are files the repository
contains, and a count that quietly drops the second is the silence this module exists to
refuse.

Nothing here knows about a language. Files are routed to adapters by extension, adapters
declare what they can produce, and this module turns their answers into records whose
every field states whether it holds a value, holds nothing that was observed, lies
outside the adapter's capabilities, or was never looked for because the repository did
not say what to look for.
"""

from __future__ import annotations

from pathlib import Path

from . import __version__
from .adapters.base import Adapter, AnalysisRequest, AnalysisResult
from .config import Config, unconfigured_capabilities
from .errors import AdapterContractError, CompletenessError
from .gitmeta import commit_of, working_tree_is_dirty
from .model import (
    CAPABILITY_KINDS,
    CAPABILITY_ORDER,
    Capability,
    Coverage,
    Field,
    FieldState,
    FileRecord,
    GeneratedMeta,
    Report,
    Status,
    TableGaps,
    TableRecord,
    Unresolved,
    ValueKind,
    extension_of,
)
from .reasons import hides_a_table_reference
from .registry import AdapterSet, build_adapter_set
from .scan import SelectionResult, discover_repository_files, select_files
from .schema import load_schema_tables

TOOL = f"omitnix {__version__}"

__all__ = ["build_report", "assemble_report", "analyze_file"]


def _read_text(path: Path) -> tuple[str | None, str | None]:
    """Return (text, failure reason)."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, f"file could not be read: {exc.strerror or exc}"
    try:
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return None, "file is not valid UTF-8 text"


def _empty_state(capability: Capability, unconfigured: frozenset[Capability]) -> FieldState:
    """What an empty value means for this capability.

    ``none_observed`` is a claim: the adapter was given something to look for and did not
    find it. It is only true where there *was* something to look for, which for
    authentication and authorization is a list the repository writes. With the list empty
    nothing was searched for, and saying "observed none" there turns an unasked question
    into an answer -- for every file at once, which is how it reads as a finding about the
    repository rather than about its configuration.
    """
    return FieldState.NOT_CONFIGURED if capability in unconfigured else FieldState.NONE_OBSERVED


def _normalize_values(
    adapter: Adapter,
    values: dict[Capability, object],
    path: str,
    unconfigured: frozenset[Capability] = frozenset(),
) -> dict[Capability, Field]:
    undeclared = sorted(str(cap) for cap in set(values) - set(adapter.capabilities))
    if undeclared:
        raise AdapterContractError(
            f"adapter '{adapter.name}' returned {', '.join(undeclared)} for {path} "
            "without declaring the capability"
        )

    fields: dict[Capability, Field] = {}
    for capability in CAPABILITY_ORDER:
        if capability not in adapter.capabilities:
            fields[capability] = Field(FieldState.OUT_OF_SCOPE)
            continue

        raw = values.get(capability)
        if CAPABILITY_KINDS[capability] is ValueKind.LIST:
            if raw is None:
                items: tuple[str, ...] = ()
            elif isinstance(raw, str) or not hasattr(raw, "__iter__"):
                raise AdapterContractError(
                    f"adapter '{adapter.name}' returned a non-list for {capability} on {path}"
                )
            else:
                items = tuple(sorted({str(item).strip() for item in raw if str(item).strip()}))
            state = FieldState.VALUE if items else _empty_state(capability, unconfigured)
            fields[capability] = Field(state, list(items))
        else:
            text = "" if raw is None else str(raw).strip()
            if text:
                fields[capability] = Field(FieldState.VALUE, text)
            else:
                fields[capability] = Field(_empty_state(capability, unconfigured), None)
    return fields


def analyze_file(
    rel: str,
    adapter_set: AdapterSet,
    config: Config,
    schema_tables: frozenset[str] = frozenset(),
    in_scope: frozenset[str] | None = None,
) -> FileRecord:
    """Analyze one file. Never raises for a file it cannot handle -- it reports it."""
    adapter = adapter_set.for_path(rel)
    if adapter is None:
        # Not a failure: nothing was attempted. Counted all the same, and the reason is
        # kept on the record so that one file printed on its own still explains itself.
        return FileRecord(
            path=rel,
            adapter=None,
            status=Status.UNCLAIMED,
            reason=f"no adapter claims '{extension_of(rel)}'",
        )

    absolute = config.root / rel
    text, failure = _read_text(absolute)
    if text is None:
        return FileRecord(
            path=rel, adapter=adapter.name, status=Status.UNKNOWN, reason=failure
        )

    request = AnalysisRequest(
        path=rel,
        absolute_path=absolute,
        text=text,
        authentication_functions=config.authentication_functions,
        authorization_functions=config.authorization_functions,
        schema_tables=schema_tables,
        in_scope=in_scope,
    )
    try:
        result = adapter.analyze(request)
    except AdapterContractError:
        raise
    except Exception as exc:  # noqa: BLE001 - an adapter defect must not stop the run
        return FileRecord(
            path=rel,
            adapter=adapter.name,
            status=Status.UNKNOWN,
            reason=f"adapter '{adapter.name}' raised {type(exc).__name__}: {exc}",
        )

    if not isinstance(result, AnalysisResult):
        raise AdapterContractError(
            f"adapter '{adapter.name}' returned {type(result).__name__} for {rel}, "
            "expected AnalysisResult"
        )

    if result.unknown_reason:
        return FileRecord(
            path=rel,
            adapter=adapter.name,
            status=Status.UNKNOWN,
            reason=result.unknown_reason,
        )

    unresolved = tuple(
        item if isinstance(item, Unresolved) else Unresolved(str(item))
        for item in result.unresolved
    )
    return FileRecord(
        path=rel,
        adapter=adapter.name,
        status=Status.UNRESOLVED if unresolved else Status.ANALYZED,
        fields=_normalize_values(
            adapter, result.values, rel, unconfigured_capabilities(config)
        ),
        unresolved=unresolved,
    )


def _reports_tables(record: FileRecord) -> bool:
    """Whether this record could have contributed to the reverse index at all.

    An adapter that does not declare ``reads`` or ``writes`` never puts a table anywhere,
    so nothing it failed to follow can be hiding one. Without this, an HTML page with a
    script the grammar could not read would mark tables it has no relationship with, and
    a mark that appears everywhere is a mark nobody acts on.
    """
    return any(
        (entry := record.fields.get(capability)) is not None
        and entry.state is not FieldState.OUT_OF_SCOPE
        for capability in (Capability.READS, Capability.WRITES)
    )


def _table_evidence_gaps(records: tuple[FileRecord, ...]) -> TableGaps:
    """The files holding a statement that could be touching a table nobody can see.

    Counted per file as well as named, because the two facts are needed in two places:
    the names mark the tables those files *were* observed to touch, and the total is the
    only place a table missing from the index entirely can be accounted for at all.
    """
    per_file = {
        record.path: count
        for record in records
        if _reports_tables(record)
        and (count := sum(1 for item in record.unresolved if hides_a_table_reference(item.code)))
    }
    return TableGaps(files=tuple(sorted(per_file)), unresolved_count=sum(per_file.values()))


def _table_index(
    records: tuple[FileRecord, ...],
    schema_tables: frozenset[str],
    gap_files: frozenset[str] = frozenset(),
) -> tuple[TableRecord, ...]:
    read_by: dict[str, set[str]] = {}
    written_by: dict[str, set[str]] = {}

    for record in records:
        for capability, bucket in (
            (Capability.READS, read_by),
            (Capability.WRITES, written_by),
        ):
            entry = record.fields.get(capability)
            if entry is None or entry.state is not FieldState.VALUE:
                continue
            for table in entry.value:
                bucket.setdefault(table, set()).add(record.path)

    names = sorted(set(read_by) | set(written_by) | set(schema_tables))
    return tuple(
        _table_record(name, read_by, written_by, schema_tables, gap_files) for name in names
    )


def _table_record(
    name: str,
    read_by: dict[str, set[str]],
    written_by: dict[str, set[str]],
    schema_tables: frozenset[str],
    gap_files: frozenset[str],
) -> TableRecord:
    touched_by = read_by.get(name, set()) | written_by.get(name, set())
    return TableRecord(
        name=name,
        read_by=tuple(sorted(read_by.get(name, ()))),
        written_by=tuple(sorted(written_by.get(name, ()))),
        in_schema_snapshot=name in schema_tables,
        # A file that touches this table and could not be read in full. Its two entries
        # above are what was legible, not what the file does.
        unresolved_in=tuple(sorted(touched_by & gap_files)),
    )


def build_report(
    config: Config,
    files: list[str] | None = None,
    adapter_set: AdapterSet | None = None,
    *,
    tracked_only: bool = True,
) -> Report:
    """Run the analysis and assemble the report.

    ``files`` restricts the run to an explicit list (what a pre-commit hook passes, or
    what ``--gate`` narrows to). The resulting report is marked partial, because its
    coverage describes those files only, and discovery is not consulted at all: an
    explicit list is a different question from "what does this repository contain", and
    ``tracked_only`` has no effect on it.

    Without ``files``, this is the question ``tracked_only`` answers. Default: what git
    tracks, not everything a full filesystem walk would turn up -- a working tree also
    holds local scratch nobody meant to include, and unlike committed content, it is not
    the same set on every machine that runs this. See
    :func:`omitnix.scan.discover_repository_files` for the measurement that made this the
    default rather than the walk it replaced. ``tracked_only=False`` (the CLI's
    ``--all-files``) asks for the walk on purpose.
    """
    adapter_set = adapter_set or build_adapter_set(config.adapters)

    schema_tables: frozenset[str] = frozenset()
    if config.schema_snapshot:
        schema_tables = load_schema_tables(config.root / config.schema_snapshot)

    partial = files is not None
    discovery_note = ""
    if files is None:
        discovery = discover_repository_files(config, tracked_only=tracked_only)
        selected: SelectionResult | list[str] = discovery.files
        discovery_note = discovery.note
        skipped = 0
    else:
        selection = select_files(config, files)
        selected = selection
        skipped = selection.skipped

    # The scope every adapter is held to. Built from the same selection the run analyzes,
    # so an adapter can never reach a file this report does not account for.
    in_scope = frozenset(selected)
    records = [
        analyze_file(rel, adapter_set, config, schema_tables, in_scope)
        for rel in sorted(selected)
    ]

    return assemble_report(
        config,
        records,
        adapter_set,
        schema_tables,
        partial=partial,
        skipped=skipped,
        tracked_only=tracked_only,
        discovery_note=discovery_note,
    )


def assemble_report(
    config: Config,
    records: list[FileRecord],
    adapter_set: AdapterSet,
    schema_tables: frozenset[str] = frozenset(),
    *,
    partial: bool = False,
    skipped: int = 0,
    tracked_only: bool = True,
    discovery_note: str = "",
) -> Report:
    """Turn analyzed records into a report, counting them and checking the invariant.

    Separate from :func:`build_report` because a caller may have produced the records
    some other way -- a workspace run analyzes a repository's files across several
    processes, over its own call to :func:`omitnix.scan.discover_repository_files`, and
    hands the results back here along with the ``tracked_only``/``discovery_note`` that
    discovery produced. The counting and the invariant must not have a second
    implementation, so there is only this one.
    """
    ordered = tuple(sorted(records, key=lambda record: record.path))

    # Counted by asking for each of the four statuses by name, and totalled against the
    # number of records rather than against the sum of what was asked for. A record whose
    # status is none of the four is then missing from the total, which is exactly what the
    # invariant below is for. Pre-filling a slot for every member of ``Status`` would make
    # the check unfailable -- a test of an assertion that cannot fire proves nothing, and
    # the day a fifth status is added it would be the count, not the check, that decided
    # whether the file was accounted for.
    counts: dict[object, int] = {}
    for record in ordered:
        counts[record.status] = counts.get(record.status, 0) + 1
    coverage = Coverage(
        discovered=len(ordered),
        analyzed=counts.get(Status.ANALYZED, 0),
        unresolved=counts.get(Status.UNRESOLVED, 0),
        unknown=counts.get(Status.UNKNOWN, 0),
        unclaimed=counts.get(Status.UNCLAIMED, 0),
        skipped_by_config=skipped,
    )
    if not coverage.holds:
        seen = ", ".join(f"{status}={count}" for status, count in sorted(counts.items(), key=str))
        raise CompletenessError(
            f"counting invariant broke: discovered={coverage.discovered} but "
            f"analyzed={coverage.analyzed} + unresolved={coverage.unresolved} + "
            f"unknown={coverage.unknown} + unclaimed={coverage.unclaimed}. "
            f"Statuses found: {seen}"
        )

    generated = GeneratedMeta(
        commit=commit_of(config.root),
        dirty=working_tree_is_dirty(config.root),
        tool=TOOL,
        partial=partial,
        adapters=adapter_set.info(),
        tracked_only=tracked_only,
        discovery_note=discovery_note,
    )
    table_gaps = _table_evidence_gaps(ordered)
    return Report(
        generated=generated,
        coverage=coverage,
        files=ordered,
        tables=_table_index(ordered, schema_tables, frozenset(table_gaps.files)),
        table_gaps=table_gaps,
    )
