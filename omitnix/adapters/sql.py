"""The SQL adapter.

The cheapest full-tier adapter in the tool, because the file *is* the statement: there is
no host language to walk and no string to decide about. sqlglot reads the file and the
tables fall out. No tree-sitter grammar is involved.

It declares tables and nothing else. A schema file has no summary worth extracting, no
authentication call and no authorization call, so those columns render as out of scope --
never as a migration that was checked for an authorization call and found to have none.

Two decisions shape the rest.

*DDL is a write.* A migration that creates, alters, drops or truncates a table is the
strongest statement there is that a file touches it. Filing ``CREATE TABLE`` under "reads"
would be wrong, and filing ``DROP TABLE`` under nothing at all would hide the one change
anybody searching the reverse index for that table needs to see.

*A statement nobody could read is counted.* sqlglot accepts syntax it does not model as an
opaque command, which holds no tables. Left alone, a file of vendor-specific DDL would
appear in the index as a file that touches nothing -- the exact failure this tool exists
to prevent -- so those are reported as ``sql_unsupported`` and the file becomes
``unresolved``.
"""

from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import Iterator

from ..model import Capability
from ._extract import (
    SELECT_STAR,
    SQL_UNREADABLE,
    SQL_UNSUPPORTED,
    Findings,
    apply,
    check_against_schema,
    preview,
)
from ._sql import read_sql
from .base import Adapter, AnalysisRequest, AnalysisResult

# See omitnix/adapters/go.py for why the extra and the adapter name are one string.
EXTRA = "sql"

#: Comments, so that a chunk containing only a comment is not reported as a statement
#: sqlglot refused. Applied to a *copy* used for the emptiness test only -- the text
#: handed to sqlglot is always the original.
_COMMENTS = re.compile(r"(?s:/\*.*?\*/)|^[ \t]*(?:--|#)[^\n]*", re.MULTILINE)


@contextlib.contextmanager
def _quiet_sqlglot() -> Iterator[None]:
    """Silence sqlglot's per-statement fallback warnings for the duration of one file.

    sqlglot logs a warning every time it falls back to an opaque command. A repository of
    vendor SQL would print thousands of them and bury this tool's own output. Nothing is
    lost by silencing them: the same fallbacks are counted and reported as
    ``sql_unsupported``, which is a finding in the document rather than a line in a log.
    """
    logger = logging.getLogger("sqlglot")
    previous = logger.level
    logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(previous)


def _has_statement(chunk: str) -> bool:
    return bool(_COMMENTS.sub("", chunk).strip())


def _split(text: str) -> list[str]:
    """Break a file at semicolons.

    A fallback used only after sqlglot has refused the file as a whole, so that one
    unreadable statement does not cost the tables of every other statement in the file. It
    is not a parser and does not pretend to be one: a semicolon inside a string literal
    splits here too, and the halves are then reported as unreadable, which is the safe
    direction to be wrong in.
    """
    return [chunk for chunk in text.split(";") if _has_statement(chunk)]


def _absorb(reading, source: str, findings: Findings) -> None:
    findings.reads.update(reading.reads)
    findings.writes.update(reading.writes)
    if reading.select_star:
        findings.note(
            SELECT_STAR,
            f"a statement here selects every column: {preview(source)}",
        )
    if reading.unsupported:
        findings.note(
            SQL_UNSUPPORTED,
            f"{reading.unsupported} statement(s) were read only as an opaque command, "
            "so their tables are not in this index",
        )


class SqlAdapter(Adapter):
    """SQL files, read with sqlglot. No tree-sitter grammar is used."""

    name = EXTRA
    extensions = (".sql",)
    capabilities = frozenset({Capability.READS, Capability.WRITES})

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        findings = Findings()

        try:
            with _quiet_sqlglot():
                self._read(request.text, findings)
        except ImportError as exc:
            # Same contract as a missing grammar: counted, and the run still fails.
            return AnalysisResult.unknown(
                f'sqlglot is not installed ({exc}). '
                f'Install it with: pip install "omitnix[{EXTRA}]"'
            )

        check_against_schema(request, findings)
        return apply(AnalysisResult(), findings, request, self.capabilities)

    @staticmethod
    def _read(text: str, findings: Findings) -> None:
        if not _has_statement(text):
            return

        whole = read_sql(text)
        if whole.parsed:
            _absorb(whole, text, findings)
            return

        for chunk in _split(text):
            reading = read_sql(chunk)
            if reading.parsed:
                _absorb(reading, chunk, findings)
            else:
                findings.note(
                    SQL_UNREADABLE, f"sqlglot could not read this statement: {preview(chunk)}"
                )


ADAPTER = SqlAdapter()
