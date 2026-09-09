"""The adapter contract.

An adapter answers one question about one file, and declares up front which parts of
that question it is able to answer. The core asks for nothing outside the declaration
and renders everything outside it as out of scope -- never as a missing value.

Minimal adapter::

    from omitnix.adapters.base import Adapter, AnalysisRequest, AnalysisResult
    from omitnix.model import Capability


    class IniAdapter(Adapter):
        name = "ini"
        extensions = (".ini",)
        capabilities = frozenset({Capability.SUMMARY})

        def analyze(self, request: AnalysisRequest) -> AnalysisResult:
            first = request.text.splitlines()[0] if request.text else ""
            return AnalysisResult(values={Capability.SUMMARY: first.strip("; ")})


    ADAPTER = IniAdapter()

Returning an empty value is not the same as declining: an adapter that declares
``READS`` and returns no table names states that it looked and observed none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from ..model import Capability, Unresolved

__all__ = ["Adapter", "AnalysisRequest", "AnalysisResult"]


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    """Everything an adapter is given about one file."""

    #: Repository-relative POSIX path. Use this in any output, never the absolute path.
    path: str
    absolute_path: Path
    #: Decoded file contents. The core never hands an adapter a file it could not decode.
    text: str
    #: Function names the repository considers authentication, from its configuration.
    authentication_functions: tuple[str, ...] = ()
    #: Function names the repository considers authorization, from its configuration.
    authorization_functions: tuple[str, ...] = ()
    #: Table names from the schema snapshot, when one is configured. Empty otherwise.
    schema_tables: frozenset[str] = frozenset()
    #: Repository-relative POSIX paths of every file this run discovered.
    #:
    #: An adapter that follows a reference to another file -- a PHP ``require``, an
    #: import -- must not read one that is absent from this set, however plainly it sits
    #: on the disk. The index has to be a function of the repository, not of the machine
    #: that generated it. Measured on 2026-09-09: a deploy script writes a version file
    #: that the repository deliberately does not track, every developer has it, no CI
    #: checkout does, and following it moved fifteen files and two coverage counts. The
    #: index could never agree with itself.
    #:
    #: An out-of-scope target is not a missing one. Report it as unresolved with the
    #: reason, and say the same thing whether or not the file happens to exist locally --
    #: a message that varies with the disk reintroduces the defect it describes.
    #:
    #: ``None`` means the core stated no set. Every path in the core passes one.
    in_scope: frozenset[str] | None = None


@dataclass(slots=True)
class AnalysisResult:
    """What an adapter reports back.

    The status of the record is derived by the core from this result, not chosen by the
    adapter: a reason makes it ``unknown``, any unresolved finding makes it
    ``unresolved``, otherwise it is ``analyzed``.
    """

    values: dict[Capability, Any] = field(default_factory=dict)
    unresolved: list[Unresolved] = field(default_factory=list)
    #: Set when the adapter recognised the file but could not analyze it at all.
    unknown_reason: str | None = None

    @classmethod
    def unknown(cls, reason: str) -> AnalysisResult:
        return cls(unknown_reason=reason)

    def add_unresolved(self, code: str, detail: str = "") -> None:
        self.unresolved.append(Unresolved(code=code, detail=detail))


class Adapter:
    """Base class for every adapter. Subclass it and expose an instance at module level."""

    #: Short identifier, also used in configuration to resolve an ambiguous extension.
    name: ClassVar[str] = ""
    #: Lower-case extensions including the dot, e.g. ``(".php", ".inc")``.
    extensions: ClassVar[tuple[str, ...]] = ()
    #: The subset of capabilities this adapter can produce.
    capabilities: ClassVar[frozenset[Capability]] = frozenset()

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:  # pragma: no cover
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Adapter {self.name} {' '.join(self.extensions)}>"
