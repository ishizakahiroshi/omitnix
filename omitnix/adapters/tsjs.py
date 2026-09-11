"""The TypeScript / JavaScript adapter.

One adapter for five extensions and three grammars. ``.ts``, ``.tsx``, ``.js``, ``.mjs``
and ``.cjs`` are one language family whose files sit in the same directories and call each
other; splitting them across adapters would mean the same query maintained in several
places, and a repository's ``.js`` and ``.ts`` files answering the same question
differently for no reason a reader could see.

Three grammars are still needed because TSX and TypeScript disagree about what ``<T>``
means and neither of them is JavaScript. They share a node vocabulary, so
``omitnix/queries/tsjs.scm`` is compiled once against each.

Besides the four things every full adapter reports, this one reports the addresses a file
requests -- the screen-to-API direction the index exists to make navigable. The set of
calls recognised as requests is deliberately tiny (``fetch`` and ``axios``); a wrong entry
in that column is a reference the tool invented, which is worse than one it admits it did
not find.

The syntax lives in ``omitnix/queries/tsjs.scm``, not here.
"""

from __future__ import annotations

import re
from typing import Any

from ..model import Capability
from ._extract import (
    DYNAMIC_ENDPOINT,
    SYNTAX_ERROR_REASON,
    Findings,
    StringShape,
    apply,
    check_against_schema,
    harvest_sql,
    looks_like_endpoint,
    preview,
    summary_from_leading_comments,
    value_of,
)
from ._treesitter import GrammarUnavailable, Parsed, load_grammar, text_of
from .base import Adapter, AnalysisRequest, AnalysisResult

#: One query source, compiled against each grammar below.
QUERY_NAME = "tsjs"

#: extension -> (grammar name, package, entry point). The grammar name is what the cache
#: and the error messages use; the query comes from ``QUERY_NAME`` for all of them.
GRAMMARS: dict[str, tuple[str, str, str]] = {
    ".ts": ("typescript", "tree_sitter_typescript", "language_typescript"),
    ".tsx": ("tsx", "tree_sitter_typescript", "language_tsx"),
    ".js": ("javascript", "tree_sitter_javascript", "language"),
    ".mjs": ("javascript", "tree_sitter_javascript", "language"),
    ".cjs": ("javascript", "tree_sitter_javascript", "language"),
}

# See omitnix/adapters/go.py for why the extra and the adapter name are one string.
EXTRA = "tsjs"
JAVASCRIPT = GRAMMARS[".js"]

#: Never matches. Unlike PHP, Go and Python, this language family does not build SQL with
#: printf conversions -- it uses template literals, which the tree already shows as holes.
#: Substituting percent conversions here would corrupt ``LIKE '%draft%'`` into a statement
#: the adapter then reports as assembled at run time, which is a finding about nothing.
_NO_FORMAT = re.compile(r"(?!)")

SHAPE = StringShape(
    content=frozenset({"string_fragment", "escape_sequence"}),
    transparent=frozenset({"string", "template_string", "parenthesized_expression"}),
    concatenation="binary_expression",
    concat_operator="+",
    format_spec=_NO_FORMAT,
)

#: The same shape for values a person reads rather than values sqlglot parses.
_ENDPOINT_SHAPE = SHAPE.with_hole("*")

#: Calls whose first argument is a request address. Kept small on purpose: widening it to
#: every ``.get()`` would put map lookups and query-string helpers in the index as API
#: calls. A repository that uses its own client wrapper is better served by saying so in
#: configuration than by this file guessing at names.
_REQUEST_FUNCTIONS = frozenset({"fetch", "axios"})
_REQUEST_OBJECTS = frozenset({"axios"})

#: Top-level nodes that do not end the file's leading comment block.
_HEADER_TYPES = frozenset({"comment", "hash_bang_line"})


def _first_argument(arguments: Any) -> Any | None:
    for child in arguments.children:
        if child.is_named and child.type != "comment":
            return child
    return None


def _record_endpoint(arguments: Any, findings: Findings) -> None:
    """Read the address out of a request call, or record that it could not be read."""
    argument = _first_argument(arguments)
    if argument is None:
        return

    text, hole = value_of(argument, _ENDPOINT_SHAPE)
    candidate = text.strip()
    if looks_like_endpoint(candidate):
        findings.endpoints.add(candidate)
        if hole:
            findings.note(
                DYNAMIC_ENDPOINT,
                f"part of this address is filled in at run time: {preview(candidate)}",
            )
        return

    # Not blank, and not invented either: the call was seen, and what it asks for was not
    # readable from the source.
    findings.note(
        DYNAMIC_ENDPOINT,
        f"the address of this request is a run-time value: {preview(text_of(argument))}",
    )


def _harvest_endpoints(parsed: Parsed, findings: Findings) -> None:
    for row in parsed.paired("endpoint.callee", "endpoint.arguments"):
        if text_of(row["endpoint.callee"]) in _REQUEST_FUNCTIONS:
            _record_endpoint(row["endpoint.arguments"], findings)

    for row in parsed.paired("endpoint.object", "endpoint.property", "endpoint.arguments"):
        if text_of(row["endpoint.object"]) in _REQUEST_OBJECTS:
            _record_endpoint(row["endpoint.arguments"], findings)


def scan_javascript(source: str, findings: Findings, *, extra: str = EXTRA) -> str:
    """Add the request addresses in a fragment of JavaScript to ``findings``.

    Exists for the HTML adapter, whose ``<script>`` blocks are JavaScript held inside
    another language. Returns an empty string on success, or the reason the fragment could
    not be read -- which the caller records rather than swallowing, because a script that
    was not read is not a script that requests nothing.

    ``extra`` is the caller's, not this module's: an HTML file whose script could not be
    read is fixed by installing ``omitnix[html]``, and telling its reader to install
    ``omitnix[tsjs]`` would send them to an extra that does not cover the file they ran on.
    """
    try:
        grammar = load_grammar(*JAVASCRIPT, QUERY_NAME, extra=extra)
    except GrammarUnavailable as exc:
        return str(exc)

    parsed = grammar.parse(source.encode("utf-8"))
    if parsed.has_error:
        return "the inline script did not parse as JavaScript"
    _harvest_endpoints(parsed, findings)
    return ""


class TsJsAdapter(Adapter):
    """TypeScript, TSX and JavaScript, parsed with tree-sitter; SQL read with sqlglot."""

    name = EXTRA
    extensions = (".ts", ".tsx", ".js", ".mjs", ".cjs")
    capabilities = frozenset(
        {
            Capability.SUMMARY,
            Capability.AUTHENTICATION,
            Capability.AUTHORIZATION,
            Capability.READS,
            Capability.WRITES,
            Capability.SCREEN_TO_API,
        }
    )

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        extension = request.path.rsplit(".", 1)[-1].lower()
        grammar_spec = GRAMMARS.get(f".{extension}", JAVASCRIPT)
        try:
            grammar = load_grammar(*grammar_spec, QUERY_NAME, extra=EXTRA)
        except GrammarUnavailable as exc:
            # An unknown record, not a silent skip: the file is still counted and the run
            # still exits non-zero.
            return AnalysisResult.unknown(str(exc))

        parsed = grammar.parse(request.text.encode("utf-8"))
        if parsed.has_error:
            return AnalysisResult.unknown(SYNTAX_ERROR_REASON)

        findings = Findings()
        harvest_sql(parsed, SHAPE, findings)
        _harvest_endpoints(parsed, findings)
        findings.calls.update(text_of(node) for node in parsed.get("call.name"))
        check_against_schema(request, findings)

        result = AnalysisResult()
        result.values[Capability.SUMMARY] = summary_from_leading_comments(parsed, _HEADER_TYPES)
        return apply(result, findings, request, self.capabilities)


ADAPTER = TsJsAdapter()
