"""The Python adapter.

What it answers for one Python file: what the file is for, which of the repository's
authentication and authorization functions it calls, and which tables it reads and writes.

It does not follow imports. The PHP adapter follows ``require`` one hop because an
included file's statements *execute* in the including file, which makes them that file's
behaviour; an imported Python module is a different file with its own row in the index,
and attributing its tables to every module that imports it would double-count them. What
this costs -- a module whose SQL lives in a query helper shows no tables of its own -- is
visible in the index rather than hidden, because the helper's own row carries them.

The Python syntax lives in ``omitnix/queries/python.scm``, not here.
"""

from __future__ import annotations

import re
from typing import Any

from ..model import Capability
from ._extract import (
    SYNTAX_ERROR_REASON,
    Findings,
    StringShape,
    apply,
    check_against_schema,
    first_description_line,
    harvest_sql,
    operator_of,
    summary_from_leading_comments,
    value_of,
)
from ._sql import FORMAT_SPEC
from ._treesitter import GrammarUnavailable, Parsed, load_grammar, text_of
from .base import Adapter, AnalysisRequest, AnalysisResult

# See omitnix/adapters/go.py for why the extra and the adapter name are one string.
EXTRA = "python"
GRAMMAR_NAME = "python"
GRAMMAR_MODULE = "tree_sitter_python"
GRAMMAR_SYMBOL = "language"

#: Percent conversions *and* ``str.format`` fields. Both have to be substituted for the
#: surrounding statement to reach sqlglot at all -- ``WHERE id = {}`` is not SQL -- but
#: substituting them says nothing about whether the statement was assembled.
_PYTHON_TEMPLATE = re.compile(FORMAT_SPEC.pattern + r"|\{[A-Za-z0-9_.\[\]]{0,40}\}")

SHAPE = StringShape(
    content=frozenset({"string_content", "escape_sequence"}),
    #: The quote and the prefix letters are tokens of their own here, and they are not
    #: run-time holes: a bare "" would otherwise be reported as an assembled string.
    ignored=frozenset({"string_start", "string_end"}),
    transparent=frozenset({"string", "concatenated_string", "parenthesized_expression"}),
    concatenation="binary_operator",
    concat_operator="+",
    format_spec=_PYTHON_TEMPLATE,
    #: ``%s`` is the DB-API parameter marker. ``execute("... WHERE id = %s", (id,))`` is
    #: the parameterised form every Python codebase is supposed to use, and calling it
    #: "assembled at run time" would mark almost every file in a repository unresolved --
    #: burying the statements that really are built by string arithmetic. Those are found
    #: by ``_is_templated`` instead, which looks at what the string is *used by*.
    format_is_assembly=False,
)

#: Top-level nodes that do not end the file's leading comment block.
_HEADER_TYPES = frozenset({"comment"})


def _docstring(parsed: Parsed) -> Any | None:
    """The module docstring, or None.

    Position is what makes a string a docstring, which is why this is done on the tree
    rather than in the query: the first statement of the module, and nothing else.
    """
    for child in parsed.root.children:
        if not child.is_named or child.type == "comment":
            continue
        if child.type != "expression_statement":
            return None
        inner = [node for node in child.children if node.is_named]
        if len(inner) == 1 and inner[0].type == "string":
            return inner[0]
        return None
    return None


def _is_templated(node: Any) -> bool:
    """Whether this string is *used* as a template rather than passed as a statement.

    The two spellings that matter are ``"..." % values`` and ``"...".format(values)``.
    Both put the value into the SQL text itself, which is what the ``dynamic_sql`` finding
    is about; the identical characters passed as a second argument to ``execute()`` are
    bound by the driver and change no SQL at all.
    """
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "binary_operator" and operator_of(parent) == "%":
        left = parent.child_by_field_name("left")
        return left is not None and left.start_byte == node.start_byte
    if parent.type == "attribute":
        attribute = parent.child_by_field_name("attribute")
        return attribute is not None and text_of(attribute) == "format"
    return False


def _summary(parsed: Parsed) -> str:
    """The first description line of the docstring, or of the header comment block.

    Left empty when there is neither, on purpose: the core already distinguishes "observed
    nothing" from "outside this adapter's capabilities", and writing a phrase in as a
    value would claim a summary was extracted.
    """
    docstring = _docstring(parsed)
    if docstring is not None:
        text, _hole = value_of(docstring, SHAPE)
        line = first_description_line(text)
        if line:
            return line
    return summary_from_leading_comments(parsed, _HEADER_TYPES)


class PythonAdapter(Adapter):
    """Python, parsed with tree-sitter; SQL read with sqlglot."""

    name = EXTRA
    #: ``.pyi`` is Python syntax and parses with the same grammar. A stub has no SQL and
    #: no checks, and reporting that honestly -- observed none -- is better than leaving
    #: the extension unclaimed, which would fail every run that meets one.
    extensions = (".py", ".pyi")
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
        harvest_sql(parsed, SHAPE, findings, templated=_is_templated)
        findings.calls.update(text_of(node) for node in parsed.get("call.name"))
        check_against_schema(request, findings)

        result = AnalysisResult()
        result.values[Capability.SUMMARY] = _summary(parsed)
        return apply(result, findings, request, self.capabilities)


ADAPTER = PythonAdapter()
