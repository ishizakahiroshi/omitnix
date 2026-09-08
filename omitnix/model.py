"""The data model.

Two ideas carry the whole design.

1. Every discovered file lands in exactly one of three statuses, and the three counts
   must add up to the number discovered.
2. Every field of every record carries a *state*, so that "this adapter cannot produce
   this field" is never rendered the same way as "this adapter produced nothing".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


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


class FieldState(StrEnum):
    """Why a field looks the way it does."""

    VALUE = "value"
    #: The adapter declares this capability but observed nothing. Not "unused".
    NONE_OBSERVED = "none_observed"
    #: The adapter does not declare this capability. Not a missing value.
    OUT_OF_SCOPE = "out_of_scope"


class Status(StrEnum):
    ANALYZED = "analyzed"
    UNRESOLVED = "unresolved"
    UNKNOWN = "unknown"


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
        if self.state is FieldState.OUT_OF_SCOPE:
            return {"state": str(self.state)}
        return {"state": str(self.state), "value": self.value}


@dataclass(frozen=True, slots=True)
class FileRecord:
    path: str
    adapter: str | None
    status: Status
    fields: dict[Capability, Field] = field(default_factory=dict)
    unresolved: tuple[Unresolved, ...] = ()
    unknown_reason: str | None = None

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
        if self.unknown_reason is not None:
            payload["unknown_reason"] = self.unknown_reason
        return payload


@dataclass(frozen=True, slots=True)
class Coverage:
    discovered: int
    analyzed: int
    unresolved: int
    unknown: int
    skipped_by_config: int = 0

    @property
    def holds(self) -> bool:
        return self.discovered == self.analyzed + self.unresolved + self.unknown

    def to_json(self) -> dict[str, int]:
        return {
            "discovered": self.discovered,
            "analyzed": self.analyzed,
            "unresolved": self.unresolved,
            "unknown": self.unknown,
            "skipped_by_config": self.skipped_by_config,
        }

    def headline(self) -> str:
        """The line printed at the top of every generated document."""
        return (
            f"Coverage: {self.analyzed}/{self.discovered} analyzed, "
            f"{self.unresolved} unresolved, {self.unknown} unknown"
        )


@dataclass(frozen=True, slots=True)
class TableRecord:
    name: str
    read_by: tuple[str, ...] = ()
    written_by: tuple[str, ...] = ()
    #: True when the name came from a schema snapshot rather than only from source.
    in_schema_snapshot: bool = False

    @property
    def observed_nowhere(self) -> bool:
        return not self.read_by and not self.written_by

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "read_by": list(self.read_by),
            "written_by": list(self.written_by),
            "in_schema_snapshot": self.in_schema_snapshot,
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
    """Provenance of the run itself. Deliberately excluded from ``--check``."""

    commit: str | None
    dirty: bool
    tool: str
    partial: bool
    adapters: tuple[AdapterInfo, ...] = ()

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
        }


@dataclass(frozen=True, slots=True)
class Report:
    generated: GeneratedMeta
    coverage: Coverage
    files: tuple[FileRecord, ...]
    tables: tuple[TableRecord, ...]

    def file(self, path: str) -> FileRecord | None:
        for record in self.files:
            if record.path == path:
                return record
        return None
