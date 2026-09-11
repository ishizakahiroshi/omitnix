"""The data model.

Two ideas carry the whole design.

1. Every discovered file lands in exactly one of four statuses, and the four counts
   must add up to the number discovered.
2. Every field of every record carries a *state*, so that "this adapter cannot produce
   this field" is never rendered the same way as "this adapter produced nothing".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

#: What a path with no extension is counted under. A name, not an empty string, because
#: this appears in output a person reads.
NO_EXTENSION = "(no extension)"


def extension_of(path: str) -> str:
    """The lowercased extension of a POSIX path, or :data:`NO_EXTENSION`.

    One definition, used by the analyzer to say which extension nothing claims and by both
    the single-repository and the workspace report to group unclaimed files. A second copy
    would be a second answer to "which extension is this", and the two would disagree
    first on the awkward names -- ``.gitignore``, ``archive.tar.gz``, ``dir.d/run``.
    """
    name = path.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    return name[dot:].lower() if dot > 0 else NO_EXTENSION


class Capability(StrEnum):
    """A thing an adapter may be able to extract.

    An adapter declares the subset it can produce. The core asks for nothing else, and
    the renderer marks everything else as out of scope rather than as missing.
    """

    SUMMARY = "summary"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    READS = "reads"
    WRITES = "writes"
    SCREEN_TO_API = "screen_to_api"


class ValueKind(StrEnum):
    SCALAR = "scalar"
    LIST = "list"


#: The shape of each capability's value. This is capability metadata, not a per-adapter
#: or per-language table: adding a language must never require touching it.
CAPABILITY_KINDS: dict[Capability, ValueKind] = {
    Capability.SUMMARY: ValueKind.SCALAR,
    Capability.AUTHENTICATION: ValueKind.LIST,
    Capability.AUTHORIZATION: ValueKind.LIST,
    Capability.READS: ValueKind.LIST,
    Capability.WRITES: ValueKind.LIST,
    Capability.SCREEN_TO_API: ValueKind.LIST,
}

#: Stable order used by both renderers.
CAPABILITY_ORDER: tuple[Capability, ...] = (
    Capability.SUMMARY,
    Capability.AUTHENTICATION,
    Capability.AUTHORIZATION,
    Capability.READS,
    Capability.WRITES,
    Capability.SCREEN_TO_API,
)


#: What the new-file gate is allowed to demand of a newly added file.
#:
#: This is capability metadata, like the two tables above, and for the same reason: the
#: gate must not grow a list of languages. A capability is in here when its absence in a
#: brand new file is a defect rather than a fact about the file.
#:
#: ``READS`` / ``WRITES`` / ``SCREEN_TO_API`` are deliberately absent. A file that
#: touches no table is ordinary, so "observed none" there is an observation, not an
#: omission -- demanding them would turn every new file that happens to touch no table
#: into a failure.
GATE_REQUIRED_CAPABILITIES: tuple[Capability, ...] = (
    Capability.SUMMARY,
    Capability.AUTHENTICATION,
    Capability.AUTHORIZATION,
)


#: Capabilities that only mean something once the repository has said what to look for,
#: and the ``Config`` attribute that says it.
#:
#: Capability metadata again, and here for the same reason the two tables above are: two
#: different parts of the tool ask this question -- the gate, deciding whether a check can
#: be made at all, and the analyzer, deciding which state a field carries -- and a second
#: copy of the table is how the two would come to disagree about which checks the
#: repository configured. :func:`omitnix.config.unconfigured_capabilities` applies it.
CONFIGURED_BY: dict[Capability, str] = {
    Capability.AUTHENTICATION: "authentication_functions",
    Capability.AUTHORIZATION: "authorization_functions",
}


class FieldState(StrEnum):
    """Why a field looks the way it does."""

    VALUE = "value"
    #: The adapter declares this capability but observed nothing. Not "unused".
    NONE_OBSERVED = "none_observed"
    #: The adapter does not declare this capability. Not a missing value.
    OUT_OF_SCOPE = "out_of_scope"
    #: The adapter declares this capability, and the repository never said what to look
    #: for, so nothing was searched for. Not the same fact as having searched and found
    #: nothing, and the difference is not academic: pointed at a repository with no
    #: ``.omitnix.yaml`` on 2026-09-11, this tool reported ``authorization:
    #: none_observed`` for all 618 of its files, which reads as "618 files were checked
    #: and none holds an authorization call". Nothing had been checked at all.
    NOT_CONFIGURED = "not_configured"


#: States rendered without a ``value`` key. Both of them mean nothing was ever looked for
#: -- the adapter cannot report this, or the repository never said what to look for -- and
#: an empty list beside either would read as an observation that was never made.
_NO_VALUE_STATES: frozenset[FieldState] = frozenset(
    {FieldState.OUT_OF_SCOPE, FieldState.NOT_CONFIGURED}
)


class Status(StrEnum):
    """Where one discovered file ended up. Exactly one of these, always counted."""

    ANALYZED = "analyzed"
    #: Read, and something in it could not be followed. The record holds what was legible
    #: and an :class:`Unresolved` entry per gap.
    UNRESOLVED = "unresolved"
    #: An adapter claims this file's extension and could not produce a record from it:
    #: unreadable bytes, not UTF-8, a grammar that refused it, or a defect in the adapter.
    #: Somebody's bug, in this tool or in the file. ``reason`` says which.
    UNKNOWN = "unknown"
    #: No adapter claims this extension, so nothing ever tried to read it. Ordinary in any
    #: repository: prose, configuration, images and archives all land here, and so does a
    #: language whose adapter has not been written yet.
    #:
    #: Split off from ``UNKNOWN`` on 2026-09-11. Pointed at a real repository, this tool
    #: named 192 files one by one as unanalyzable -- 95 ``.md``, 45 ``.json``, 7 ``.png``
    #: -- and a genuine failure would have been a single line somewhere in that list. The
    #: two facts need different treatment in every place they appear: a failure is named,
    #: an unclaimed extension is counted by extension, and only a failure can fail a run.
    #: What is *not* different is that both are counted. An unclaimed file that vanished
    #: from the totals would be the exact silence this tool exists to break.
    UNCLAIMED = "unclaimed"


@dataclass(frozen=True, slots=True)
class Unresolved:
    """Something the analyzer looked at and could not follow.

    ``code`` is a short machine-readable reason (``dynamic_sql``, ``indirect_call``);
    ``detail`` is free text for a human. A blank cell is never an acceptable substitute.
    """

    code: str
    detail: str = ""

    def to_json(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class Field:
    state: FieldState
    value: Any = None

    def to_json(self) -> dict[str, Any]:
        if self.state in _NO_VALUE_STATES:
            return {"state": str(self.state)}
        return {"state": str(self.state), "value": self.value}


@dataclass(frozen=True, slots=True)
class FileRecord:
    path: str
    adapter: str | None
    status: Status
    fields: dict[Capability, Field] = field(default_factory=dict)
    unresolved: tuple[Unresolved, ...] = ()
    #: Why this file was not analyzed, in one sentence. Set on every record whose status
    #: is :attr:`Status.UNKNOWN` or :attr:`Status.UNCLAIMED`, absent on every other.
    #:
    #: It was called ``unknown_reason`` until the two were separated (2026-09-11), which
    #: left the name claiming the file was unknown on records that say ``unclaimed``. The
    #: whole point of the split is that those are different facts, and a field name is not
    #: exempt from that.
    reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "adapter": self.adapter,
            "status": str(self.status),
            "fields": {
                str(cap): self.fields[cap].to_json()
                for cap in CAPABILITY_ORDER
                if cap in self.fields
            },
            "unresolved": [item.to_json() for item in self.unresolved],
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True, slots=True)
class Coverage:
    """The count of a run, and the product it has to satisfy.

    ``unclaimed`` is here rather than folded into ``unknown`` because the two are acted on
    differently everywhere else -- but it is *here*, in the same total as the rest, because
    the alternative is a number that quietly excludes whatever the tool decided not to look
    at. A file no adapter claims is still a file this repository contains.
    """

    discovered: int
    analyzed: int
    unresolved: int
    unknown: int
    unclaimed: int = 0
    skipped_by_config: int = 0

    @property
    def holds(self) -> bool:
        return (
            self.discovered
            == self.analyzed + self.unresolved + self.unknown + self.unclaimed
        )

    def to_json(self) -> dict[str, int]:
        return {
            "discovered": self.discovered,
            "analyzed": self.analyzed,
            "unresolved": self.unresolved,
            "unknown": self.unknown,
            "unclaimed": self.unclaimed,
            "skipped_by_config": self.skipped_by_config,
        }

    def headline(self) -> str:
        """The line printed at the top of every generated document."""
        return (
            f"Coverage: {self.analyzed}/{self.discovered} analyzed, "
            f"{self.unresolved} unresolved, {self.unknown} unknown, "
            f"{self.unclaimed} unclaimed"
        )


@dataclass(frozen=True, slots=True)
class TableRecord:
    name: str
    read_by: tuple[str, ...] = ()
    written_by: tuple[str, ...] = ()
    #: True when the name came from a schema snapshot rather than only from source.
    in_schema_snapshot: bool = False
    #: Files that touch this table **and** hold a statement the analyzer could not read,
    #: so their entry for it may be only part of what they do with it. Named rather than
    #: counted, because the only use for this mark is going and looking.
    #:
    #: The two lists above are otherwise read as complete, and that reading is wrong
    #: exactly here: a file whose one unreadable statement is the one that touches this
    #: table appears in neither list, and nothing in this record would say so.
    unresolved_in: tuple[str, ...] = ()

    @property
    def observed_nowhere(self) -> bool:
        return not self.read_by and not self.written_by

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "read_by": list(self.read_by),
            "written_by": list(self.written_by),
            "in_schema_snapshot": self.in_schema_snapshot,
            "unresolved_in": list(self.unresolved_in),
        }


@dataclass(frozen=True, slots=True)
class TableGaps:
    """What the reverse index could not see, stated once for the whole run.

    :attr:`TableRecord.unresolved_in` can only mark a table some file was *observed* to
    touch. A table whose only mention in the whole repository is a statement nobody could
    read is not in the index at all, so no per-table mark can be attached to it -- the
    row is simply absent, and an absent row is indistinguishable from a table that does
    not exist. Found 2026-09-11: a full-text search table read by one ``WHERE x MATCH ?``
    sqlglot could not parse, and the index said nothing reads it.

    So the count lives here, beside the list it qualifies, and says that the list itself
    may be short.
    """

    #: Files holding at least one such statement. The places to go and look.
    files: tuple[str, ...] = ()
    #: How many unresolved entries across those files may hide a table reference.
    unresolved_count: int = 0

    @property
    def note(self) -> str:
        """The sentence a reader of the table list needs. Empty when there is none."""
        if not self.unresolved_count:
            return ""
        files = "file" if len(self.files) == 1 else "files"
        entries = "statement" if self.unresolved_count == 1 else "statements"
        return (
            f"{self.unresolved_count} {entries} in {len(self.files)} {files} could not be "
            "read, so the table list may be incomplete: a table mentioned only there is "
            "missing from it entirely, and a table that is listed may be touched in more "
            "places than it names."
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "files": list(self.files),
            "unresolved_count": self.unresolved_count,
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class AdapterInfo:
    """What the report records about an adapter that took part in the run."""

    name: str
    extensions: tuple[str, ...]
    capabilities: tuple[Capability, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "extensions": list(self.extensions),
            "capabilities": [str(cap) for cap in self.capabilities],
        }


@dataclass(frozen=True, slots=True)
class GeneratedMeta:
    """Provenance of the run itself.

    Mostly deliberately excluded from ``--check`` (see
    :func:`omitnix.render.payload_for_check`) -- ``commit``, ``dirty``, ``tool``,
    ``partial`` and ``adapters`` vary between two runs of the *same* command for reasons
    that have nothing to do with the inventory being stale. ``tracked_only`` is the one
    exception: it is not run-to-run noise, it is which question discovery answered, and
    two runs that answered different questions must not compare equal.
    """

    commit: str | None
    dirty: bool
    tool: str
    partial: bool
    adapters: tuple[AdapterInfo, ...] = ()
    #: Whether discovery was asked for what git tracks (the default) or for everything
    #: ``--all-files`` walks instead. Carried here, next to ``commit``, because it is a
    #: fact about how the run was asked to look, not about what it found -- and because it
    #: is the one field of this dataclass that ``--check`` must still compare: a run that
    #: discovered the tracked set and a run that discovered the whole working tree can
    #: legitimately disagree about which files exist, and treating that as "the document
    #: is stale" would be right, not a false alarm the way ``commit`` changing is.
    tracked_only: bool = True
    #: Set when git could not answer and discovery fell back to walking the tree instead.
    #: Kept out of ``--check`` (unlike ``tracked_only``) because it is provenance of the
    #: same kind as ``commit``: whether git could be asked at all on this machine, this
    #: run, not a fact about the files that were found.
    discovery_note: str = ""

    def commit_label(self) -> str:
        if self.commit is None:
            return "unknown (not a git working tree)"
        return f"{self.commit}{' (working tree dirty)' if self.dirty else ''}"

    def to_json(self) -> dict[str, Any]:
        return {
            "commit": self.commit,
            "dirty": self.dirty,
            "tool": self.tool,
            "partial": self.partial,
            "adapters": [adapter.to_json() for adapter in self.adapters],
            "tracked_only": self.tracked_only,
            "discovery_note": self.discovery_note,
        }


@dataclass(frozen=True, slots=True)
class Report:
    generated: GeneratedMeta
    coverage: Coverage
    files: tuple[FileRecord, ...]
    tables: tuple[TableRecord, ...]
    table_gaps: TableGaps = field(default_factory=TableGaps)

    def file(self, path: str) -> FileRecord | None:
        for record in self.files:
            if record.path == path:
                return record
        return None

    @property
    def unclaimed_extensions(self) -> dict[str, int]:
        """How many files no adapter claims, by extension, commonest first.

        The only form in which unclaimed files are ever *displayed*. Naming 95 ``.md``
        files one by one buries the single ``.php`` the parser choked on, and the list is
        not information anyway: the extension is the whole fact, repeated 95 times.
        """
        counts: dict[str, int] = {}
        for record in self.files:
            if record.status is Status.UNCLAIMED:
                extension = extension_of(record.path)
                counts[extension] = counts.get(extension, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    @property
    def unknown_files(self) -> tuple[FileRecord, ...]:
        """The files an adapter claimed and could not read. Named one by one, always."""
        return tuple(record for record in self.files if record.status is Status.UNKNOWN)
