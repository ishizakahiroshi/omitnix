"""The PHP adapter.

What it answers for one PHP file: what the file is for, which of the repository's
authentication and authorization functions it calls, and which tables it reads and
writes. It follows ``require``/``include`` and a call into an included file **exactly one
hop**, and it counts everything it could not follow instead of leaving a blank.

Two rules shape every decision below.

*Never blank.* A table list that is empty because nothing was found and a table list that
is empty because the SQL was assembled at run time look identical in a document and mean
opposite things. So anything the adapter looked at and could not read becomes an
``Unresolved`` with a reason code, and the record's status stops being ``analyzed``.

*One hop, deliberately.* Chasing calls further would raise the hit rate and destroy the
property this tool exists for: that the gaps are counted. A second hop is recorded as
``indirect_call_depth``, not followed.

The PHP syntax lives in ``omitnix/queries/php.scm``, not here.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
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
from ._treesitter import GrammarUnavailable, Parsed, load_grammar, text_of
from .base import Adapter, AnalysisRequest, AnalysisResult

GRAMMAR_NAME = "php"
GRAMMAR_MODULE = "tree_sitter_php"
GRAMMAR_SYMBOL = "language_php"

# --- reason codes -----------------------------------------------------------------
#: SQL assembled at run time: what is written here is a fragment, not the statement.
DYNAMIC_SQL = "dynamic_sql"
#: The statement parsed, but the table name itself was a run-time value.
DYNAMIC_TABLE_NAME = "dynamic_table_name"
#: A hop the adapter refuses to take, or an include it could not resolve.
INDIRECT_CALL_DEPTH = "indirect_call_depth"
#: The tables are known; the columns are not.
SELECT_STAR = "select_star"
#: It opened like SQL and sqlglot could not read it.
SQL_UNREADABLE = "sql_unreadable"
#: A table this file touches is absent from the configured schema snapshot.
TABLE_NOT_IN_SCHEMA = "table_not_in_schema"

# --- node vocabulary --------------------------------------------------------------
#: Nodes whose text is literal source characters.
_CONTENT_TYPES = frozenset({"string_content", "nowdoc_string", "escape_sequence"})
#: Nodes that only wrap other nodes; their children carry the value.
_TRANSPARENT_TYPES = frozenset(
    {
        "string",
        "encapsed_string",
        "heredoc",
        "nowdoc",
        "heredoc_body",
        "nowdoc_body",
        "parenthesized_expression",
    }
)
#: Heredoc delimiters. Not content, and not a run-time hole either.
_DELIMITER_TYPES = frozenset({"heredoc_start", "heredoc_end"})
#: Top-level nodes that do not end the file's leading comment block.
#:
#: ``declare_statement`` is here because of a measurement, not a guess. Applied to a real
#: repository on 2026-09-08, this adapter produced a summary for none of its 364 files:
#: every one opens with ``declare(strict_types=1);`` before its docblock, and a node that
#: is not on this list ends the header, so the docblock was never reached. A modern file
#: is the common case, and a column that is empty everywhere teaches people to ignore it.
#:
#: ``namespace_definition`` and ``use_declaration`` are deliberately absent: a docblock
#: after those usually documents the class below it, and taking it would put a class's
#: description in a column that says "what this file is for".
_HEADER_TYPES = frozenset(
    {"php_tag", "comment", "text", "declaration_list", "declare_statement"}
)

_COMMENT_OPENERS = re.compile(r"^\s*(/\*+|\*+|//+|#+)")
_COMMENT_CLOSER = re.compile(r"\*+/\s*$")

_MAX_DETAIL = 70


def _operator(node: Any) -> str:
    child = node.child_by_field_name("operator")
    return text_of(child) if child is not None else ""


def _value_of(node: Any, constants: dict[str, str] | None = None) -> tuple[str, bool]:
    """The text of a string-like expression, and whether it has run-time holes.

    Every part the adapter cannot see -- an interpolated variable, a concatenated
    expression, a function call -- becomes :data:`~omitnix.adapters._sql.PLACEHOLDER`, so
    that the surrounding SQL still parses and the parts that *are* visible are not lost
    along with the parts that are not.
    """
    kind = node.type
    if kind in _CONTENT_TYPES:
        return text_of(node), False
    if kind in _DELIMITER_TYPES:
        return "", False
    if constants and kind == "name":
        literal = constants.get(text_of(node))
        if literal is not None:
            return literal, False
    if kind == "binary_expression":
        if _operator(node) != ".":
            return f" {PLACEHOLDER} ", True
        children = [node.child_by_field_name("left"), node.child_by_field_name("right")]
        return _join((child for child in children if child is not None), constants)
    if kind in _TRANSPARENT_TYPES:
        return _join((child for child in node.children if child.is_named), constants)
    return f" {PLACEHOLDER} ", True


def _join(nodes: Iterable[Any], constants: dict[str, str] | None = None) -> tuple[str, bool]:
    text = ""
    hole = False
    for node in nodes:
        part, part_hole = _value_of(node, constants)
        text += part
        hole = hole or part_hole
    return text, hole


def _sql_text(node: Any) -> tuple[str, bool]:
    """The SQL a node contributes, with printf conversions treated as holes.

    ``sprintf('UPDATE audit_log SET seen = %d', $id)`` is a static string as far as the
    parser is concerned and a template as far as the program is concerned. Substituting
    the conversion keeps the statement parsable and records that a value was filled in
    elsewhere.
    """
    text, hole = _value_of(node)
    substituted, count = FORMAT_SPEC.subn(f" {PLACEHOLDER} ", text)
    return substituted, hole or bool(count)


def _preview(text: str) -> str:
    flat = " ".join(text.split())
    return flat[:_MAX_DETAIL] + "..." if len(flat) > _MAX_DETAIL else flat


def _contains(outer: Any, inner: Any) -> bool:
    return outer.start_byte <= inner.start_byte and inner.end_byte <= outer.end_byte


def _sql_candidates(parsed: Parsed) -> list[Any]:
    """Every expression that might be a SQL statement, outermost first.

    A concatenation and each of its string operands are all captured by the query. Only
    the outermost survives here: reading ``'DELETE FROM ' . $table`` as its two halves
    would report a statement that reads no table and never mention that a table name was
    chosen at run time.
    """
    candidates = [
        node
        for node in parsed.get("sql.concatenated")
        if _operator(node) == "."
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


# --- one parsed file --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Unit:
    """One parsed PHP file and the parts of it other files can reach."""

    path: Path
    parsed: Parsed
    #: Function/method name -> its body node.
    definitions: dict[str, Any]
    #: Every name this file calls, in source order.
    calls: tuple[Any, ...]

    @classmethod
    def of(cls, path: Path, parsed: Parsed) -> _Unit:
        definitions: dict[str, Any] = {}
        for row in parsed.paired("definition.name", "definition.body"):
            definitions.setdefault(text_of(row["definition.name"]), row["definition.body"])
        return cls(
            path=path,
            parsed=parsed,
            definitions=definitions,
            calls=parsed.get("call.name"),
        )

    @property
    def body_ranges(self) -> tuple[tuple[int, int], ...]:
        return tuple((body.start_byte, body.end_byte) for body in self.definitions.values())

    def called_names(self, accept: Callable[[Any], bool]) -> set[str]:
        return {text_of(node) for node in self.calls if accept(node)}


def _everything(_node: Any) -> bool:
    return True


def _reachable_through_include(
    unit: _Unit, followed: tuple[tuple[int, int], ...]
) -> Callable[[Any], bool]:
    """Accept a node that an ``include`` of this file actually reaches.

    Two kinds of code qualify: statements outside every function body, because including
    a file executes them, and the bodies of the functions the including file calls by
    name. A body nobody called is code this file happens to contain, not code the
    including file runs.
    """
    bodies = unit.body_ranges

    def accept(node: Any) -> bool:
        in_a_body = any(start <= node.start_byte and node.end_byte <= end for start, end in bodies)
        if not in_a_body:
            return True
        return any(start <= node.start_byte and node.end_byte <= end for start, end in followed)

    return accept


# --- accumulating the answer ------------------------------------------------------


@dataclass(slots=True)
class _Findings:
    reads: set[str] = field(default_factory=set)
    writes: set[str] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)
    #: (code, detail) pairs, kept in insertion order and deduplicated.
    unresolved: dict[tuple[str, str], None] = field(default_factory=dict)

    def note(self, code: str, detail: str = "") -> None:
        self.unresolved[(code, detail)] = None


def _absorb(reading: SqlReading, sql: str, dynamic: bool, findings: _Findings) -> None:
    if not reading.parsed:
        # Only a statement written the way source writes SQL is worth reporting. A
        # lower-case candidate that sqlglot refused is far more likely to be prose, and
        # prose in the Unresolved table buries the findings that matter.
        if reads_as_written_sql(sql):
            findings.note(SQL_UNREADABLE, f"sqlglot could not read: {_preview(sql)}")
        return

    findings.reads.update(reading.reads)
    findings.writes.update(reading.writes)

    if dynamic:
        findings.note(DYNAMIC_SQL, f"assembled at run time: {_preview(sql)}")
    if reading.dynamic_table:
        findings.note(DYNAMIC_TABLE_NAME, f"the table name is a run-time value: {_preview(sql)}")
    if reading.select_star:
        findings.note(
            SELECT_STAR,
            f"the tables are known, the columns are not: {_preview(sql)}",
        )


def _harvest_sql(unit: _Unit, accept: Callable[[Any], bool], findings: _Findings) -> None:
    for node in _sql_candidates(unit.parsed):
        if not accept(node):
            continue
        sql, dynamic = _sql_text(node)
        if not looks_like_sql(sql):
            continue
        _absorb(read_sql(sql), sql, dynamic, findings)


# --- includes ---------------------------------------------------------------------


def _repository_root(request: AnalysisRequest) -> Path:
    root = request.absolute_path.parent
    for _ in range(request.path.count("/")):
        root = root.parent
    return root


def _include_target(node: Any, unit: _Unit, root: Path) -> tuple[Path | None, str]:
    """Resolve a ``require``/``include`` argument. Returns (path, why not)."""
    directory = unit.path.parent
    constants = {
        "__DIR__": directory.as_posix(),
        "__FILE__": unit.path.as_posix(),
    }
    raw, hole = _value_of(node, constants)
    literal = raw.strip()
    if hole or not literal:
        return None, f"the required path is built at run time: {_preview(text_of(node))}"

    candidate = Path(literal)
    if not candidate.is_absolute():
        candidate = directory / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None, f"the required path could not be resolved: {_preview(literal)}"

    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None, f"the required file is outside the repository: {_preview(literal)}"
    if not resolved.is_file():
        return None, f"the required file was not found: {_preview(literal)}"
    return resolved, ""


def _parse_file(path: Path, grammar: Any) -> Parsed | None:
    try:
        source = path.read_bytes()
    except OSError:
        return None
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    parsed = grammar.parse(text.encode("utf-8"))
    return None if parsed.has_error else parsed


# --- the adapter ------------------------------------------------------------------


class PhpAdapter(Adapter):
    """PHP, parsed with tree-sitter; SQL read with sqlglot."""

    name = "php"
    #: ``.inc`` is deliberately not claimed: it belongs to no language in particular, and
    #: a repository that uses it for PHP says so under ``adapters:`` in .omitnix.yaml.
    extensions = (".php", ".phtml")
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
            grammar = load_grammar(GRAMMAR_NAME, GRAMMAR_MODULE, GRAMMAR_SYMBOL)
        except GrammarUnavailable as exc:
            # An unknown record, not a silent skip: the file is still counted and the
            # run still exits non-zero.
            return AnalysisResult.unknown(str(exc))

        parsed = grammar.parse(request.text.encode("utf-8"))
        if parsed.has_error:
            return AnalysisResult.unknown(
                "tree-sitter reported a syntax error, so the file was not analyzed. "
                "Anything read from a partial parse would be a guess."
            )

        unit = _Unit.of(request.absolute_path, parsed)
        findings = _Findings()

        _harvest_sql(unit, _everything, findings)
        findings.calls.update(unit.called_names(_everything))

        self._follow_one_hop(unit, request, grammar, findings)
        self._check_against_schema(request, findings)

        result = AnalysisResult()
        result.values[Capability.SUMMARY] = _summary(parsed)
        result.values[Capability.READS] = sorted(findings.reads)
        result.values[Capability.WRITES] = sorted(findings.writes)
        result.values[Capability.AUTHENTICATION] = sorted(
            findings.calls & set(request.authentication_functions)
        )
        result.values[Capability.AUTHORIZATION] = sorted(
            findings.calls & set(request.authorization_functions)
        )
        for code, detail in findings.unresolved:
            result.add_unresolved(code, detail)
        return result

    def _follow_one_hop(
        self,
        unit: _Unit,
        request: AnalysisRequest,
        grammar: Any,
        findings: _Findings,
    ) -> None:
        """Follow every resolvable ``require``/``include`` exactly one level.

        The case this exists for: a screen's endpoint holds no SQL of its own because the
        statements live in a shared query file it requires. Without this hop that file's
        table columns are empty, and an empty column is read as "touches no table".
        """
        root = _repository_root(request)
        called_by_this_file = unit.called_names(_everything)
        included: list[_Unit] = []

        for node in unit.parsed.get("include.path"):
            target, why_not = _include_target(node, unit, root)
            if target is None:
                findings.note(INDIRECT_CALL_DEPTH, why_not)
                continue
            if target == unit.path.resolve():
                continue

            parsed = _parse_file(target, grammar)
            if parsed is None:
                findings.note(
                    INDIRECT_CALL_DEPTH,
                    f"the required file could not be parsed as PHP: {_relative(target, root)}",
                )
                continue

            included_unit = _Unit.of(target, parsed)
            followed = tuple(
                (body.start_byte, body.end_byte)
                for name, body in included_unit.definitions.items()
                if name in called_by_this_file
            )
            accept = _reachable_through_include(included_unit, followed)
            _harvest_sql(included_unit, accept, findings)
            findings.calls.update(included_unit.called_names(accept))
            included.append(included_unit)

        self._note_second_hops(unit, included, called_by_this_file, findings, root)

    @staticmethod
    def _note_second_hops(
        unit: _Unit,
        included: list[_Unit],
        called_by_this_file: set[str],
        findings: _Findings,
        root: Path,
    ) -> None:
        """Count the calls that a second hop would have followed.

        Only calls to names this run actually saw defined are counted. A call to a
        built-in, or to something defined in a file nobody included, is not evidence of a
        hop that was skipped -- it is evidence of nothing, and reporting it would bury
        the real findings.

        The file the call was found in is named, because that is what the reader needs
        next. Measured against a real repository on 2026-09-08: an endpoint holds no SQL
        of its own, requires a shared query file, and calls a function there that only
        forwards to another one. Saying "two hops away" leaves the reader to search for
        it; saying which file it was in makes it one jump. This tool does not build a
        call graph, and a pointer costs nothing next to one.
        """
        known: set[str] = set(unit.definitions)
        for included_unit in included:
            known |= set(included_unit.definitions)

        for included_unit in included:
            for name, body in included_unit.definitions.items():
                if name not in called_by_this_file:
                    continue
                for call in included_unit.calls:
                    if not (body.start_byte <= call.start_byte and call.end_byte <= body.end_byte):
                        continue
                    callee = text_of(call)
                    if callee in known and callee not in called_by_this_file:
                        where = _relative(included_unit.path, root)
                        findings.note(
                            INDIRECT_CALL_DEPTH,
                            f"'{name}()' in {where} calls '{callee}()', which is two "
                            "hops away and was not followed",
                        )

    @staticmethod
    def _check_against_schema(request: AnalysisRequest, findings: _Findings) -> None:
        """Flag a table this file touches that the schema snapshot does not have.

        Only when a snapshot is configured. It catches a typo and a statement left behind
        after its table was dropped -- both of which otherwise read as ordinary rows in
        the reverse index.
        """
        if not request.schema_tables:
            return
        for table in sorted(findings.reads | findings.writes):
            if table not in request.schema_tables:
                findings.note(
                    TABLE_NOT_IN_SCHEMA,
                    f"'{table}' is not in the configured schema snapshot",
                )


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:  # pragma: no cover - guarded by _include_target
        return path.name


def _summary(parsed: Parsed) -> str:
    """The first description line of the comment block at the head of the file.

    Empty when there is none. It is left empty on purpose rather than filled with a
    phrase like "no summary": the core already distinguishes "observed nothing" from
    "outside this adapter's capabilities", and a placeholder written into the value would
    claim a summary was extracted.
    """
    boundary = parsed.root.end_byte
    for child in parsed.root.children:
        if child.is_named and child.type not in _HEADER_TYPES:
            boundary = child.start_byte
            break

    for comment in parsed.get("comment"):
        if comment.end_byte > boundary:
            continue
        line = _first_description_line(text_of(comment))
        if line:
            return line
    return ""


def _first_description_line(block: str) -> str:
    for raw in block.splitlines():
        line = _COMMENT_OPENERS.sub("", raw).strip()
        line = _COMMENT_CLOSER.sub("", line).strip()
        if not line or line.startswith("@"):
            continue
        return line
    return ""


ADAPTER = PhpAdapter()
