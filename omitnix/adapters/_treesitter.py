"""Shared tree-sitter plumbing for language adapters.

Adapter discovery skips modules whose name begins with an underscore, which is what lets
this module sit beside the adapters without being mistaken for one.

Nothing here knows about a particular language. An adapter names a grammar package and a
query file; it gets back a parse of the source and the captures its own query asked for.
One parsing library for every language is a deliberate choice: the alternative is a
different parser, a different node vocabulary, and a different set of surprises per
language, which is how "add a language" stops being cheap.

A grammar that is not installed raises :class:`GrammarUnavailable`. That is *not* an
:class:`~omitnix.errors.OmitnixError`: a missing parser is not a defect in omitnix, and
it must not abort the run. The adapter turns it into an ``unknown`` record, so the file
is still counted and the run still exits non-zero. It is never silently skipped.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from ..errors import AdapterContractError

__all__ = [
    "GrammarUnavailable",
    "Grammar",
    "Parsed",
    "load_grammar",
    "text_of",
]

#: Query files live beside the package, not beside the adapters, because a query is data
#: the adapter reads rather than code it imports.
QUERY_DIR = Path(__file__).resolve().parent.parent / "queries"


class GrammarUnavailable(RuntimeError):
    """The tree-sitter binding or a grammar package is not installed."""


@dataclass(frozen=True, slots=True)
class Parsed:
    """One parsed file, together with the captures the language's query produced.

    ``captures`` flattens every match, which is what most lookups want ("every call
    name"). ``matches`` keeps each pattern's captures grouped, which is what a pattern
    with two captures needs ("this function name goes with *that* body").
    """

    root: Any
    source: bytes
    captures: dict[str, tuple[Any, ...]]
    matches: tuple[dict[str, tuple[Any, ...]], ...]

    @property
    def has_error(self) -> bool:
        return bool(self.root.has_error)

    def get(self, capture: str) -> tuple[Any, ...]:
        return self.captures.get(capture, ())

    def paired(self, *captures: str) -> tuple[dict[str, Any], ...]:
        """Matches that produced exactly one node for each of ``captures``.

        Used for patterns such as "a definition's name and its body", where taking the
        flattened capture lists would pair the first name with every body.
        """
        rows: list[dict[str, Any]] = []
        for match in self.matches:
            if not all(len(match.get(name, ())) == 1 for name in captures):
                continue
            rows.append({name: match[name][0] for name in captures})
        return tuple(rows)


def _document_order(nodes: Any) -> tuple[Any, ...]:
    """Captured nodes, earliest first.

    The query cursor does not promise to return a capture's nodes in the order they
    appear in the file, and measurement on 2026-09-08 showed the order changing between
    processes for the same input. Anything phrased as "the first comment" or "the first
    statement" then means something different from one run to the next, and a generated
    document that changes without its source changing is the one thing this tool cannot
    ship: `--check` would flap, and the committed inventory would churn.
    """
    return tuple(sorted(nodes, key=lambda node: (node.start_byte, node.end_byte)))


def _earliest_byte(group: dict[str, tuple[Any, ...]]) -> tuple[int, int]:
    positions = [(node.start_byte, node.end_byte) for nodes in group.values() for node in nodes]
    return min(positions) if positions else (0, 0)


@dataclass(frozen=True, slots=True)
class Grammar:
    """A parser and the compiled query for one language."""

    name: str
    language: Any
    query: Any

    def parse(self, source: bytes) -> Parsed:
        from tree_sitter import Parser, QueryCursor

        tree = Parser(self.language).parse(source)
        cursor = QueryCursor(self.query)
        raw_captures = cursor.captures(tree.root_node)
        captures = {name: _document_order(nodes) for name, nodes in raw_captures.items()}

        matches: list[dict[str, tuple[Any, ...]]] = []
        for _pattern_index, group in QueryCursor(self.query).matches(tree.root_node):
            matches.append({name: _document_order(nodes) for name, nodes in group.items()})
        matches.sort(key=_earliest_byte)

        return Parsed(
            root=tree.root_node,
            source=source,
            captures=captures,
            matches=tuple(matches),
        )


def _query_source(name: str) -> str:
    path = QUERY_DIR / f"{name}.scm"
    if not path.is_file():
        # The query ships with the adapter, so a missing one is a defect in omitnix
        # itself rather than something about the repository being scanned.
        raise AdapterContractError(f"query file missing from the omitnix package: {path}")
    return path.read_text(encoding="utf-8")


@cache
def load_grammar(
    name: str,
    module_name: str,
    symbol: str,
    query_name: str | None = None,
    *,
    extra: str,
) -> Grammar:
    """Load the grammar for ``name`` and compile ``omitnix/queries/<name>.scm``.

    ``module_name``/``symbol`` name the grammar package and its entry point, e.g.
    ``("tree_sitter_php", "language_php")``. Cached: compiling a query for every file in
    a repository would dominate the run.

    ``query_name`` points the query somewhere other than ``<name>.scm``. One adapter can
    cover several grammars that share a node vocabulary -- TypeScript, TSX and JavaScript
    are one language family split into three grammar entry points -- and a query has to be
    compiled separately against each :class:`Language` even when the source text is
    identical. Without this the choice is three copies of one query file that must be
    edited in lockstep, which is how a pattern gets fixed in two of them.

    ``extra`` names the packaging extra that installs everything this call needs, and is
    keyword-only and required so that no call site can leave it out. It is what the
    reasons below tell the reader to install. Naming the missing distribution instead --
    ``tree-sitter``, then ``tree-sitter-python`` -- is accurate twice and useless once:
    the reader installs the first, runs again, and is told about the second. The extra
    installs the binding, the grammar and sqlglot together, so following the reason once
    is enough.
    """
    try:
        from tree_sitter import Language, Query
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise GrammarUnavailable(
            "the tree-sitter Python binding is not installed "
            f'({exc}). Install it with: pip install "omitnix[{extra}]"'
        ) from exc

    try:
        grammar_module = importlib.import_module(module_name)
    except ImportError as exc:
        raise GrammarUnavailable(
            f"the {name} grammar is not installed ({exc}). "
            f'Install it with: pip install "omitnix[{extra}]"'
        ) from exc

    entry = getattr(grammar_module, symbol, None)
    if entry is None:
        raise GrammarUnavailable(
            f"{module_name} has no {symbol}(); the installed version is not the grammar "
            "package omitnix expects"
        )

    try:
        language = Language(entry())
    except Exception as exc:  # noqa: BLE001 - any binding/ABI mismatch lands here
        raise GrammarUnavailable(
            f"the {name} grammar could not be loaded by this tree-sitter binding "
            f"({type(exc).__name__}: {exc}). The grammar and the binding are usually "
            "version-mismatched; reinstall both."
        ) from exc

    source = _query_source(query_name or name)
    return Grammar(name=name, language=language, query=Query(language, source))


def text_of(node: Any) -> str:
    """The source text of a node, decoded permissively.

    Permissive because the core already guaranteed the file decodes as UTF-8; a
    replacement character here would mean a node boundary landed mid-character, which is
    not a reason to lose the whole file.
    """
    return node.text.decode("utf-8", "replace")
