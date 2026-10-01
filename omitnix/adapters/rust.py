"""The Rust adapter.

What it answers for one Rust file: what the file is for, which of the repository's
authentication and authorization functions it calls, and which tables it reads and writes.

SQL is read where a file writes it as text: a string, a raw string, the string argument
of a macro such as ``query!``, the pieces of ``concat!`` joined back together, and a
chain built with ``+``. A ``format!`` hole is a value filled in at run time. The
statement is still read, and the hole is reported, so a table name that was not in the
source does not become a confident blank.

A query built by method calls has no SQL text to read. Diesel, SeaORM and SeaQuery are
named here, and a call of theirs is recorded as unresolved: the file is not shown as one
that touches no table, and a table name is not invented from the method. Schema macros
such as ``table!`` define a mapping; they are not queries and are not recorded.

Nothing is followed into another file. ``include_str!`` and ``query_file!`` leave the
statement in the file they name, which has its own row when that file is in the scan.

The Rust syntax lives in ``omitnix/queries/rust.scm``, not here.
"""

from __future__ import annotations

import re
from typing import Any

from ..model import Capability
from ._extract import (
    SYNTAX_ERROR_REASON,
    Findings,
    StringShape,
    absorb,
    apply,
    check_against_schema,
    looks_like_sql,
    operator_of,
    sql_candidates,
    sql_text,
    summary_from_leading_comments,
    value_of,
)
from ._sql import read_sql
from ._treesitter import GrammarUnavailable, Parsed, load_grammar, text_of
from .base import Adapter, AnalysisRequest, AnalysisResult

# The packaging extra that installs this adapter's dependencies, and the name the
# adapter registers under. One string, so a reason cannot name an extra that is not
# the adapter's own.
EXTRA = "rust"
GRAMMAR_NAME = "rust"
GRAMMAR_MODULE = "tree_sitter_rust"
GRAMMAR_SYMBOL = "language"

#: A reason code of this adapter's own.
#:
#: The shared codes describe SQL that was seen and could not be finished. A query
#: builder is the opposite shape: the call is visible and the SQL is not. Left
#: unclassified on purpose. :func:`omitnix.reasons.hides_a_table_reference` treats an
#: unclassified code as a table the lists may be missing, which is what this is.
QUERY_BUILDER = "query_builder"

#: Crates whose call style builds a query out of methods and schema modules.
_BUILDER_CRATES = frozenset({"diesel", "diesel_async", "sea_orm", "sea_query"})

#: Macros that declare a schema. They mention a table and do not query it.
_SCHEMA_ITEMS = frozenset(
    {"table", "joinable", "allow_tables_to_appear_in_same_query"}
)

#: Call names that build a query once the file has imported one of the crates above.
#:
#: ``update`` and ``delete`` are ordinary words. They count only in a file that imported
#: a query-builder crate, because that is the file in which they are the crate's API
#: rather than a method of the program's own. A file that does both pays for a finding
#: it has to look at; a file that queries through them and was reported empty would be
#: wrong.
_UNQUALIFIED_CALLS = frozenset(
    {
        "insert_into",
        "replace_into",
        "update",
        "delete",
        "sql_query",
        "load",
        "get_result",
        "get_results",
        "get_only_result",
        "first",
        "find",
        "find_by_id",
        "find_by_statement",
        "insert",
        "insert_many",
        "update_many",
        "delete_many",
    }
)

#: ``{}``, ``{name}``, ``{0}`` and ``{name:?}``. Not a JSON object: ``{"a": 1}`` has a
#: quote where a format field has an identifier, and marking it would call every query
#: that stores JSON dynamic.
_RUST_FORMAT = re.compile(
    r"\{(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+)?(?::[^{}]*)?\}"
)

#: ``diesel`` has to be tried after ``diesel_async``, or the longer name never matches.
_CRATE_NAME = re.compile(r"\b(diesel_async|diesel|sea_orm|sea_query)\b")

_STRING_NODES = frozenset({"string_literal", "raw_string_literal"})

#: What ``"SELECT ".to_owned() + rest`` uses to get a string ``+`` can append to.
_UNWRAP_METHODS = frozenset({"to_owned", "to_string"})

SHAPE = StringShape(
    content=frozenset({"string_content", "escape_sequence"}),
    transparent=frozenset({"string_literal", "raw_string_literal"}),
    concatenation="binary_expression",
    concat_operator="+",
    format_spec=_RUST_FORMAT,
)

#: Top-level nodes that do not end the file's leading comment block. A module doc
#: comment is a line comment in this grammar, and an inner attribute may sit beside it.
_HEADER_TYPES = frozenset(
    {"line_comment", "block_comment", "attribute_item", "inner_attribute_item"}
)


def _inside(node: Any, outers: tuple[Any, ...]) -> bool:
    return any(
        outer.start_byte <= node.start_byte and node.end_byte <= outer.end_byte
        for outer in outers
    )


def _outermost(nodes: list[Any]) -> list[Any]:
    ordered = sorted(nodes, key=lambda node: (node.start_byte, -node.end_byte))
    kept: list[Any] = []
    for node in ordered:
        if _inside(node, tuple(kept)):
            continue
        kept.append(node)
    return kept


def _unwrap_owned(node: Any) -> Any | None:
    """The receiver of ``to_owned`` or ``to_string``, which exists to allow ``+``."""
    if node.type != "call_expression":
        return None
    function = node.child_by_field_name("function")
    if function is None or function.type != "field_expression":
        return None
    field = function.child_by_field_name("field")
    if field is None or text_of(field) not in _UNWRAP_METHODS:
        return None
    return function.child_by_field_name("value")


def _added_text(node: Any) -> tuple[str, bool]:
    """The text of a ``+`` chain, with each run-time piece replaced by a hole."""
    if node.type in _STRING_NODES:
        return value_of(node, SHAPE)
    if node.type == "binary_expression" and operator_of(node) == "+":
        parts: list[str] = []
        dynamic = False
        for name in ("left", "right"):
            child = node.child_by_field_name(name)
            if child is None:
                parts.append(SHAPE.hole)
                dynamic = True
                continue
            text, hole = _added_text(child)
            parts.append(text)
            dynamic = dynamic or hole
        return "".join(parts), dynamic
    inner = _unwrap_owned(node)
    if inner is not None:
        return _added_text(inner)
    return SHAPE.hole, True


def _concat_text(macro: Any) -> tuple[str, bool]:
    """The text of a ``concat!`` invocation.

    The macro's name is a child of the invocation and is not part of the string. Only
    the token tree is. A piece that is not itself a string is a hole: ``concat!`` can
    only join literals, so anything else was not readable as one.
    """
    tree = next((child for child in macro.children if child.type == "token_tree"), None)
    if tree is None:
        return "", True
    parts: list[str] = []
    dynamic = False
    for child in tree.children:
        if not child.is_named:
            continue
        if child.type in _STRING_NODES:
            text, hole = value_of(child, SHAPE)
            parts.append(text)
            dynamic = dynamic or hole
        else:
            parts.append(SHAPE.hole)
            dynamic = True
    return "".join(parts), dynamic


def _absorb_text(text: str, dynamic: bool, findings: Findings) -> None:
    substituted, count = SHAPE.format_spec.subn(SHAPE.hole, text)
    if count and SHAPE.format_is_assembly:
        dynamic = True
    if not looks_like_sql(substituted):
        return
    absorb(read_sql(substituted), substituted, dynamic, findings)


def _harvest(parsed: Parsed, findings: Findings) -> None:
    concats = [
        row["sql.concat"]
        for row in parsed.paired("sql.concat", "sql.concat.name")
        if text_of(row["sql.concat.name"]) == "concat"
    ]
    adds = _outermost(
        [node for node in parsed.get("sql.add") if operator_of(node) == "+"]
    )
    adds = [node for node in adds if not _inside(node, tuple(concats))]
    covered = tuple(concats) + tuple(adds)

    for node in sql_candidates(parsed, SHAPE):
        if _inside(node, covered):
            continue
        sql, dynamic = sql_text(node, SHAPE)
        if not looks_like_sql(sql):
            continue
        absorb(read_sql(sql), sql, dynamic, findings)

    for node in concats:
        text, dynamic = _concat_text(node)
        _absorb_text(text, dynamic, findings)
    for node in adds:
        text, dynamic = _added_text(node)
        _absorb_text(text, dynamic, findings)


def _path_root(node: Any) -> str:
    current = node
    while current is not None and current.type == "scoped_identifier":
        path = current.child_by_field_name("path")
        if path is None:
            return ""
        if path.type != "scoped_identifier":
            return text_of(path)
        current = path
    return ""


def _enclosing_call(node: Any) -> Any | None:
    current = node.parent
    while current is not None:
        if current.type in {"call_expression", "macro_invocation"}:
            return current
        current = current.parent
    return None


def _contains_sql(node: Any) -> bool:
    """Whether this call already holds a string the SQL reader will accept."""
    pending = list(node.children)
    while pending:
        current = pending.pop()
        if current.type in _STRING_NODES:
            text, _hole = value_of(current, SHAPE)
            substituted, _count = SHAPE.format_spec.subn(SHAPE.hole, text)
            if looks_like_sql(substituted):
                return True
        pending.extend(current.children)
    return False


def _note_query_builders(parsed: Parsed, findings: Findings) -> None:
    imported: set[str] = set()
    for node in parsed.get("builder.use"):
        imported.update(_CRATE_NAME.findall(text_of(node)))
    imported &= _BUILDER_CRATES

    found: dict[str, int] = {}

    def remember(name: str, call: Any, root: str) -> None:
        if not name or _contains_sql(call):
            return
        if root in _BUILDER_CRATES:
            if name in _SCHEMA_ITEMS:
                return
        elif name not in _UNQUALIFIED_CALLS or not imported:
            return
        start = call.start_byte
        if name not in found or start < found[name]:
            found[name] = start

    for node in parsed.get("builder.scoped"):
        call = _enclosing_call(node)
        name_node = node.child_by_field_name("name")
        if call is None or name_node is None:
            continue
        remember(text_of(name_node), call, _path_root(node))

    for capture in ("builder.bare", "builder.method"):
        for node in parsed.get(capture):
            call = _enclosing_call(node)
            if call is None:
                continue
            remember(text_of(node), call, "")

    for name in sorted(found, key=lambda item: (found[item], item)):
        findings.note(
            QUERY_BUILDER,
            f"query builder call '{name}' does not spell its tables out as SQL",
        )


class RustAdapter(Adapter):
    """Rust, parsed with tree-sitter; SQL read with sqlglot."""

    name = EXTRA
    extensions = (".rs",)
    capabilities = frozenset(
        {
            Capability.SUMMARY,
            Capability.AUTHENTICATION,
            Capability.AUTHORIZATION,
            Capability.READS,
            Capability.WRITES,
        }
    )

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        try:
            grammar = load_grammar(
                GRAMMAR_NAME, GRAMMAR_MODULE, GRAMMAR_SYMBOL, extra=EXTRA
            )
        except GrammarUnavailable as exc:
            # An unknown record, not a silent skip: the file is still counted and the run
            # still exits non-zero.
            return AnalysisResult.unknown(str(exc))

        parsed = grammar.parse(request.text.encode("utf-8"))
        if parsed.has_error:
            return AnalysisResult.unknown(SYNTAX_ERROR_REASON)

        findings = Findings()
        _harvest(parsed, findings)
        findings.calls.update(text_of(node) for node in parsed.get("call.name"))
        _note_query_builders(parsed, findings)
        check_against_schema(request, findings)

        result = AnalysisResult()
        result.values[Capability.SUMMARY] = summary_from_leading_comments(
            parsed, _HEADER_TYPES
        )
        return apply(result, findings, request, self.capabilities)


ADAPTER = RustAdapter()
