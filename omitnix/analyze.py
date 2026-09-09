"""The core run: discover, analyze, count, and refuse to lie about the result.

The counting invariant is the product::

    discovered == analyzed + unresolved + unknown

Nothing here knows about a language. Files are routed to adapters by extension, adapters
declare what they can produce, and this module turns their answers into records whose
every field states whether it holds a value, holds nothing that was observed, or lies
outside the adapter's capabilities.
"""

from __future__ import annotations

from pathlib import Path

from . import __version__
from .adapters.base import Adapter, AnalysisRequest, AnalysisResult
from .config import Config
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
    TableRecord,
    Unresolved,
    ValueKind,
)
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


def _normalize_values(
    adapter: Adapter, values: dict[Capability, object], path: str
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
            state = FieldState.VALUE if items else FieldState.NONE_OBSERVED
            fields[capability] = Field(state, list(items))
        else:
            text = "" if raw is None else str(raw).strip()
            if text:
                fields[capability] = Field(FieldState.VALUE, text)
            else:
                fields[capability] = Field(FieldState.NONE_OBSERVED, None)
    return fields


def analyze_file(
    rel: str,
    adapter_set: AdapterSet,
    config: Config,
    schema_tables: frozenset[str] = frozenset(),
) -> FileRecord:
    """Analyze one file. Never raises for a file it cannot handle -- it reports it."""
    adapter = adapter_set.for_path(rel)
    if adapter is None:
        extension = Path(rel).suffix.lower() or "(no extension)"
        return FileRecord(
            path=rel,
            adapter=None,
            status=Status.UNKNOWN,
            unknown_reason=f"no adapter claims '{extension}'",
        )

    absolute = config.root / rel
    text, failure = _read_text(absolute)
    if text is None:
        return FileRecord(
            path=rel, adapter=adapter.name, status=Status.UNKNOWN, unknown_reason=failure
        )

    request = AnalysisRequest(
        path=rel,
        absolute_path=absolute,
        text=text,
        authentication_functions=config.authentication_functions,
        authorization_functions=config.authorization_functions,
        schema_tables=schema_tables,
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
            unknown_reason=f"adapter '{adapter.name}' raised {type(exc).__name__}: {exc}",
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
            unknown_reason=result.unknown_reason,
        )

    unresolved = tuple(
        item if isinstance(item, Unresolved) else Unresolved(str(item))
        for item in result.unresolved
    )
    return FileRecord(
        path=rel,
        adapter=adapter.name,
        status=Status.UNRESOLVED if unresolved else Status.ANALYZED,
        fields=_normalize_values(adapter, result.values, rel),
        unresolved=unresolved,
    )


def _table_index(
    records: tuple[FileRecord, ...], schema_tables: frozenset[str]
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
        TableRecord(
            name=name,
            read_by=tuple(sorted(read_by.get(name, ()))),
            written_by=tuple(sorted(written_by.get(name, ()))),
            in_schema_snapshot=name in schema_tables,
        )
        for name in names
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

    records = [analyze_file(rel, adapter_set, config, schema_tables) for rel in sorted(selected)]

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

    counts = {status: 0 for status in Status}
    for record in ordered:
        counts[record.status] += 1
    coverage = Coverage(
        discovered=len(ordered),
        analyzed=counts[Status.ANALYZED],
        unresolved=counts[Status.UNRESOLVED],
        unknown=counts[Status.UNKNOWN],
        skipped_by_config=skipped,
    )
    if not coverage.holds:
        raise CompletenessError(
            f"counting invariant broke: discovered={coverage.discovered} but "
            f"analyzed={coverage.analyzed} + unresolved={coverage.unresolved} + "
            f"unknown={coverage.unknown}"
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
    return Report(
        generated=generated,
        coverage=coverage,
        files=ordered,
        tables=_table_index(ordered, schema_tables),
    )
