"""The Go adapter.

What it answers for one Go file: what the file is for, which of the repository's
authentication and authorization functions it calls, and which tables it reads and writes.

Like the Python adapter and unlike the PHP one, it follows nothing. An imported Go package
is other files with their own rows in the index; attributing their tables here would count
them once per importer.

The Go syntax lives in ``omitnix/queries/go.scm``, not here.
"""

from __future__ import annotations

import re

from ..model import Capability
from ._extract import (
    SYNTAX_ERROR_REASON,
    Findings,
    StringShape,
    apply,
    check_against_schema,
    harvest_sql,
    summary_from_leading_comments,
)
from ._treesitter import GrammarUnavailable, load_grammar, text_of
from .base import Adapter, AnalysisRequest, AnalysisResult

GRAMMAR_NAME = "go"
GRAMMAR_MODULE = "tree_sitter_go"
GRAMMAR_SYMBOL = "language"

#: Go's formatting verbs, which are not the same set as printf's. ``%v`` and ``%q`` in
#: particular have no printf equivalent and are the two most common ways a Go program
#: puts a value into a query, so the shared printf pattern would leave them in place and
#: hand sqlglot a statement containing a stray percent sign.
_GO_VERB = re.compile(r"%[-+ #0']*[\d.*]*[vTtbcdoqxXUeEfFgGsp%]")

SHAPE = StringShape(
    content=frozenset(
        {
            "interpreted_string_literal_content",
            "raw_string_literal_content",
            "escape_sequence",
        }
    ),
    transparent=frozenset(
        {"interpreted_string_literal", "raw_string_literal", "parenthesized_expression"}
    ),
    concatenation="binary_expression",
    concat_operator="+",
    format_spec=_GO_VERB,
)

#: Top-level nodes that do not end the file's leading comment block. A Go file's doc
#: comment sits above ``package``, so the package clause is where the block ends.
_HEADER_TYPES = frozenset({"comment"})


class GoAdapter(Adapter):
    """Go, parsed with tree-sitter; SQL read with sqlglot."""

    name = "go"
    extensions = (".go",)
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
            # An unknown record, not a silent skip: the file is still counted and the run
            # still exits non-zero.
            return AnalysisResult.unknown(str(exc))

        parsed = grammar.parse(request.text.encode("utf-8"))
        if parsed.has_error:
            return AnalysisResult.unknown(SYNTAX_ERROR_REASON)

        findings = Findings()
        harvest_sql(parsed, SHAPE, findings)
        findings.calls.update(text_of(node) for node in parsed.get("call.name"))
        check_against_schema(request, findings)

        result = AnalysisResult()
        result.values[Capability.SUMMARY] = summary_from_leading_comments(parsed, _HEADER_TYPES)
        return apply(result, findings, request, self.capabilities)


ADAPTER = GoAdapter()
