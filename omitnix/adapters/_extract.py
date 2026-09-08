"""Extraction that belongs to no single language.

Three adapters (Python, Go, TypeScript/JavaScript) answer the same question in the same
shape: walk a parse tree, decide which string literals are SQL, hand those to sqlglot, and
count everything that could not be read. Only the node names differ. Keeping that shared
logic here is what makes a fourth full adapter a query file plus a node vocabulary rather
than another copy of the same eighty lines -- and, more importantly, it means a correction
to *how* a partially-known statement is reported lands in every language at once instead
of in whichever one the fix was written for.

Adapter discovery skips modules whose name begins with an underscore, so this sits beside
the adapters without being mistaken for one.

The reason codes below repeat the strings in ``omitnix/adapters/php.py`` rather than
importing them. Both files are the definition of the same vocabulary, and the reverse
index is only coherent because the strings agree; unifying them means editing php.py,
which is deliberately left alone here. It is written down in the C6 plan as a follow-up.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from ..model import Capability
from ._sql import (
    FORMAT_SPEC,
    PLACEHOLDER,
    SqlReading,
    looks_like_sql,
    read_sql,
    reads_as_written_sql,
)
from ._treesitter import Parsed, text_of
from .base import AnalysisRequest, AnalysisResult

__all__ = [
    "DYNAMIC_ENDPOINT",
    "DYNAMIC_SQL",
    "DYNAMIC_TABLE_NAME",
    "SELECT_STAR",
    "SQL_UNREADABLE",
    "SQL_UNSUPPORTED",
    "TABLE_NOT_IN_SCHEMA",
    "SYNTAX_ERROR_REASON",
    "Findings",
    "StringShape",
    "apply",
    "check_against_schema",
    "first_description_line",
    "harvest_sql",
    "looks_like_endpoint",
    "operator_of",
    "preview",
    "sql_text",
    "summary_from_leading_comments",
    "value_of",
]

# --- reason codes -----------------------------------------------------------------
#: SQL assembled at run time: what is written here is a fragment, not the statement.
DYNAMIC_SQL = "dynamic_sql"
#: The statement parsed, but the table name itself was a run-time value.
DYNAMIC_TABLE_NAME = "dynamic_table_name"
#: A request was made to an address assembled at run time.
DYNAMIC_ENDPOINT = "dynamic_endpoint"
#: The tables are known; the columns are not.
SELECT_STAR = "select_star"
#: It opened like SQL and sqlglot could not read it.
SQL_UNREADABLE = "sql_unreadable"
#: sqlglot accepted the statement only as an opaque command, so its tables are lost.
SQL_UNSUPPORTED = "sql_unsupported"
#: A table this file touches is absent from the configured schema snapshot.
TABLE_NOT_IN_SCHEMA = "table_not_in_schema"

#: Why a file that does not parse becomes ``unknown`` rather than partially reported.
#: tree-sitter recovers from errors and will happily hand back a partial tree; a table
#: list read out of one looks exactly like a table list read out of a whole file.
SYNTAX_ERROR_REASON = (
    "tree-sitter reported a syntax error, so the file was not analyzed. "
    "Anything read from a partial parse would be a guess."
)

_MAX_DETAIL = 70

#: ``//[/!]*`` rather than ``//+``: Rust's ``//!`` is a comment opener, and stripping only
#: the two slashes leaves a summary that begins with a stray exclamation mark. Measured on
#: a fixture, not assumed.
_COMMENT_OPENERS = re.compile(r"^\s*(/\*+|\*+|//[/!]*|<#|#+|<!--|--+|;+)")
_COMMENT_CLOSER = re.compile(r"(\*+/|-->|#>)\s*$")

#: A description line has to survive this to count as a summary. Machine-readable
#: preambles -- annotations, build tags, linter directives, licence identifiers -- open
#: the comment block of an enormous number of files, and promoting one to the summary
#: column would fill the index with text that describes no file in particular.
_NOT_A_DESCRIPTION = re.compile(
    r"""^(
          @                        # @param, @returns, @ts-ignore
        | \#!                      # a shebang
        | \.[A-Z]{3,}\b            # .SYNOPSIS, .DESCRIPTION: PowerShell help markers
        | go:\w+                   # go:build, go:generate
        | \+build\b                # the older Go build constraint
        | nolint\b
        | \w+:\s*\S+$              # eslint-disable-next-line: ...
        # Whole words only, and only words that never open a sentence about a file.
        # 'type' and 'global' were here for /* global x */ and dropped again: they
        # discarded the summary of every file whose docstring opened with "Type stubs
        # for ..." or "Global configuration ...", which is a sentence, not a directive.
        | (?i:spdx-license-identifier|copyright|eslint|prettier|jshint)\b
        | -\*-                     # an editor mode line
    )""",
    re.VERBOSE,
)


def preview(text: str) -> str:
    """A one-line excerpt of source, short enough to sit in a table cell."""
    flat = " ".join(text.split())
    return flat[:_MAX_DETAIL] + "..." if len(flat) > _MAX_DETAIL else flat


# --- reading a string literal out of a parse tree ---------------------------------


@dataclass(frozen=True, slots=True)
class StringShape:
    """How one language spells a string, expressed as node types.

    The distinction that matters is between a node whose text is literal source characters
    and a node that stands for a value only known at run time. Everything the walker
    cannot see becomes :data:`~omitnix.adapters._sql.PLACEHOLDER`, so the surrounding SQL
    still parses and the visible half of a statement is not thrown away with the invisible
    half.
    """

    #: Nodes whose text is literal characters.
    content: frozenset[str]
    #: Nodes that only wrap others; the children carry the value.
    transparent: frozenset[str]
    #: Quotes, prefixes and terminators: they contribute nothing and are not holes.
    ignored: frozenset[str] = frozenset()
    #: The node type used for concatenation, and the operator that means "join".
    concatenation: str = ""
    concat_operator: str = "+"
    #: Conversions that make a string a template rather than a finished statement.
    format_spec: re.Pattern[str] = FORMAT_SPEC
    #: Whether matching :attr:`format_spec` means the statement was assembled at run time.
    #:
    #: False for exactly one reason, and it is a real one: in Python ``%s`` is the DB-API
    #: parameter marker, so ``execute("... WHERE id = %s", (id,))`` is the *safe*,
    #: parameterised form and is not assembled at all. Flagging it would make almost every
    #: Python file in a repository ``unresolved`` and bury the statements that really are
    #: built at run time. Those are still caught, by position rather than by text:
    #: see ``harvest_sql``'s ``templated`` argument.
    format_is_assembly: bool = True
    #: What a run-time hole is replaced with.
    hole: str = f" {PLACEHOLDER} "

    def with_hole(self, marker: str) -> StringShape:
        """The same shape with a different marker, for values that are not SQL.

        A URL is read by a person, so a hole in one should look like a gap in a path
        rather than like a table name.
        """
        return StringShape(
            content=self.content,
            transparent=self.transparent,
            ignored=self.ignored,
            concatenation=self.concatenation,
            concat_operator=self.concat_operator,
            format_spec=self.format_spec,
            format_is_assembly=self.format_is_assembly,
            hole=marker,
        )


def operator_of(node: Any) -> str:
    child = node.child_by_field_name("operator")
    return text_of(child) if child is not None else ""


def value_of(node: Any, shape: StringShape) -> tuple[str, bool]:
    """The text of a string-like expression, and whether it has run-time holes."""
    kind = node.type
    if kind in shape.content:
        return text_of(node), False
    if kind in shape.ignored:
        return "", False
    if shape.concatenation and kind == shape.concatenation:
        if operator_of(node) != shape.concat_operator:
            return shape.hole, True
        children = [node.child_by_field_name("left"), node.child_by_field_name("right")]
        return _join((child for child in children if child is not None), shape)
    if kind in shape.transparent:
        return _join((child for child in node.children if child.is_named), shape)
    return shape.hole, True


def _join(nodes: Iterable[Any], shape: StringShape) -> tuple[str, bool]:
    text = ""
    hole = False
    for node in nodes:
        part, part_hole = value_of(node, shape)
        text += part
        hole = hole or part_hole
    return text, hole


def sql_text(node: Any, shape: StringShape) -> tuple[str, bool]:
    """The SQL a node contributes, with printf conversions treated as holes.

    A formatted string is static to the parser and a template to the program. Substituting
    the conversion keeps the statement parsable; whether it also means the statement was
    *assembled* is a question about the language, which is why
    :attr:`StringShape.format_is_assembly` answers it rather than this function.
    """
    text, hole = value_of(node, shape)
    substituted, count = shape.format_spec.subn(shape.hole, text)
    return substituted, hole or bool(count and shape.format_is_assembly)


def _contains(outer: Any, inner: Any) -> bool:
    return outer.start_byte <= inner.start_byte and inner.end_byte <= outer.end_byte


def sql_candidates(parsed: Parsed, shape: StringShape) -> list[Any]:
    """Every expression that might be a SQL statement, outermost first.

    A concatenation and each of its operands are all captured. Only the outermost
    survives: reading ``"DELETE FROM " + table`` as its two halves would report a
    statement that touches no table and never mention that the table name was chosen at
    run time.
    """
    candidates = [
        node
        for node in parsed.get("sql.concatenated")
        if operator_of(node) == shape.concat_operator
    ]
    candidates.extend(parsed.get("sql.interpolated"))
    candidates.extend(parsed.get("sql.literal"))
    candidates.sort(key=lambda node: (node.start_byte, -node.end_byte))

    kept: list[Any] = []
    for node in candidates:
        if any(_contains(outer, node) for outer in kept):
            continue
        kept.append(node)
    return kept


# --- accumulating the answer ------------------------------------------------------


@dataclass(slots=True)
class Findings:
    """What one file turned out to say, before it is shaped into a result."""

    reads: set[str] = field(default_factory=set)
    writes: set[str] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)
    endpoints: set[str] = field(default_factory=set)
    #: (code, detail) pairs, kept in insertion order and deduplicated.
    unresolved: dict[tuple[str, str], None] = field(default_factory=dict)

    def note(self, code: str, detail: str = "") -> None:
        self.unresolved[(code, detail)] = None


def absorb(reading: SqlReading, sql: str, dynamic: bool, findings: Findings) -> None:
    """Fold one reading into the findings, reasons included.

    A partially readable statement contributes both its tables *and* the reason it was
    partial. Dropping either half turns a partial reading into a confident blank.
    """
    if not reading.parsed:
        # Only a statement written the way source writes SQL is worth reporting. A
        # lower-case candidate sqlglot refused is far more likely to be prose, and prose
        # in the Unresolved table buries the findings that matter.
        if reads_as_written_sql(sql):
            findings.note(SQL_UNREADABLE, f"sqlglot could not read: {preview(sql)}")
        return

    findings.reads.update(reading.reads)
    findings.writes.update(reading.writes)

    if dynamic:
        findings.note(DYNAMIC_SQL, f"assembled at run time: {preview(sql)}")
    if reading.dynamic_table:
        findings.note(DYNAMIC_TABLE_NAME, f"the table name is a run-time value: {preview(sql)}")
    if reading.select_star:
        findings.note(SELECT_STAR, f"the tables are known, the columns are not: {preview(sql)}")
    if reading.unsupported:
        findings.note(
            SQL_UNSUPPORTED,
            f"sqlglot read this only as an opaque command, so its tables are not "
            f"in this index: {preview(sql)}",
        )


def harvest_sql(
    parsed: Parsed,
    shape: StringShape,
    findings: Findings,
    templated: Callable[[Any], bool] | None = None,
) -> None:
    """Read every string in the file that is actually a SQL statement.

    ``templated`` decides from a string's *position* whether it is a template, for the
    languages where its text cannot say. It is what lets the Python adapter treat
    ``"... %s"`` as a bound parameter and ``"... %s" % value`` as a statement assembled at
    run time, which are the same characters and opposite facts.
    """
    for node in sql_candidates(parsed, shape):
        sql, dynamic = sql_text(node, shape)
        if not looks_like_sql(sql):
            continue
        if templated is not None and templated(node):
            dynamic = True
        absorb(read_sql(sql), sql, dynamic, findings)


def check_against_schema(request: AnalysisRequest, findings: Findings) -> None:
    """Flag a table this file touches that the schema snapshot does not have.

    Only when a snapshot is configured. It catches a typo and a statement left behind
    after its table was dropped -- both of which otherwise read as ordinary rows in the
    reverse index.
    """
    if not request.schema_tables:
        return
    for table in sorted(findings.reads | findings.writes):
        if table not in request.schema_tables:
            findings.note(
                TABLE_NOT_IN_SCHEMA, f"'{table}' is not in the configured schema snapshot"
            )


def apply(
    result: AnalysisResult,
    findings: Findings,
    request: AnalysisRequest,
    capabilities: frozenset[Capability],
) -> AnalysisResult:
    """Write the findings into a result, filling only declared capabilities.

    Nothing outside ``capabilities`` is written, because the core treats an undeclared
    value as an adapter contract error -- and because a value an adapter never promised is
    a value nobody vouched for.
    """
    if Capability.READS in capabilities:
        result.values[Capability.READS] = sorted(findings.reads)
    if Capability.WRITES in capabilities:
        result.values[Capability.WRITES] = sorted(findings.writes)
    if Capability.AUTHENTICATION in capabilities:
        result.values[Capability.AUTHENTICATION] = sorted(
            findings.calls & set(request.authentication_functions)
        )
    if Capability.AUTHORIZATION in capabilities:
        result.values[Capability.AUTHORIZATION] = sorted(
            findings.calls & set(request.authorization_functions)
        )
    if Capability.SCREEN_TO_API in capabilities:
        result.values[Capability.SCREEN_TO_API] = sorted(findings.endpoints)
    for code, detail in findings.unresolved:
        result.add_unresolved(code, detail)
    return result


# --- summaries --------------------------------------------------------------------


def first_description_line(block: str) -> str:
    """The first line of a comment block that describes the file rather than annotating it.

    Empty when there is none, and deliberately not replaced with a phrase like "no
    summary": the core already distinguishes "observed nothing" from "outside this
    adapter's capabilities", and a placeholder written in as a *value* would claim a
    summary was extracted.
    """
    for raw in block.splitlines():
        line = _COMMENT_OPENERS.sub("", raw).strip()
        line = _COMMENT_CLOSER.sub("", line).strip()
        if not line or _NOT_A_DESCRIPTION.match(line):
            continue
        if not any(character.isalnum() for character in line):
            # A rule drawn out of punctuation -- "# =========" above a banner header --
            # is the commonest first line of a shell or PowerShell script: twenty of the
            # thirty-one shell scripts in the first real repository this was pointed at
            # opened with one, and each put a row of equals signs in the index where the
            # sentence underneath belonged. A description says something; a line with no
            # letter and no digit in it cannot.
            continue
        return line
    return ""


def summary_from_leading_comments(parsed: Parsed, header_types: frozenset[str]) -> str:
    """The first description line of the comment block at the head of the file.

    ``header_types`` names the top-level nodes that do not end that block -- comments
    themselves, and whatever else a language allows to precede its first real statement.
    """
    boundary = parsed.root.end_byte
    for child in parsed.root.children:
        if child.is_named and child.type not in header_types:
            boundary = child.start_byte
            break

    for comment in parsed.get("comment"):
        if comment.end_byte > boundary:
            continue
        line = first_description_line(text_of(comment))
        if line:
            return line
    return ""


# --- endpoints --------------------------------------------------------------------

#: Whitespace anywhere disqualifies a candidate: a request address has none, and a
#: sentence that happens to contain a slash has plenty.
_ENDPOINT_PREFIXES = ("/", "./", "../", "http://", "https://")


def looks_like_endpoint(text: str) -> bool:
    """Whether a string is plausibly the address of a request.

    Conservative on purpose. A wrong entry in the screen-to-API column is a reference the
    tool invented, which is worse than a reference it admits it did not find -- and a
    missing one is still counted, because the call that produced it is recorded as
    unresolved when its address was assembled at run time.
    """
    candidate = text.strip()
    if not candidate or len(candidate) > 200 or any(ch.isspace() for ch in candidate):
        return False
    if candidate.startswith(_ENDPOINT_PREFIXES):
        return True
    return "/" in candidate and not candidate.startswith("*")
