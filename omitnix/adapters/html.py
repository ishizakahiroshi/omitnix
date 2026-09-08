"""The HTML adapter -- the reverse-lookup tier.

A page is where a person starts. "Which screen calls this endpoint?" is the question an
inventory gets asked most often and the one a file-by-file index answers worst, so this
adapter reports what a document requests: the ``action`` of its forms, the ``src`` of the
scripts it pulls in, and the addresses its inline scripts fetch.

It reports **nothing else**, and that is the point of the tier. HTML has no authorization
call and no tables, so those columns render as out of scope rather than as observed and
empty -- a page must never appear in a document as a file that was checked for an
authorization call and found to have none.

Inline scripts are parsed with the JavaScript grammar through the TypeScript/JavaScript
adapter rather than with a pattern of this file's own. It is the same language in both
places, and two readings of it would disagree eventually.

The syntax lives in ``omitnix/queries/html.scm``, not here.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ..model import Capability
from ._extract import (
    DYNAMIC_ENDPOINT,
    SYNTAX_ERROR_REASON,
    Findings,
    apply,
    first_description_line,
    looks_like_endpoint,
    summary_from_leading_comments,
)
from ._treesitter import GrammarUnavailable, Parsed, load_grammar, text_of
from .base import Adapter, AnalysisRequest, AnalysisResult
from .tsjs import scan_javascript

GRAMMAR_NAME = "html"
GRAMMAR_MODULE = "tree_sitter_html"
GRAMMAR_SYMBOL = "language"

#: (tag, attribute) pairs that name an address the page requests.
#:
#: ``a href`` is deliberately absent. A link is a place a person may go next, not a call
#: the page makes, and admitting links would bury the handful of real endpoints under
#: every navigation item in the site.
_REQUEST_ATTRIBUTES: frozenset[tuple[str, str]] = frozenset(
    {("form", "action"), ("script", "src")}
)

#: Top-level nodes that do not end the document's leading comment block.
_HEADER_TYPES = frozenset({"comment", "doctype"})

#: A reason code of this adapter's own: the page has a script it could not read, so its
#: request list is incomplete and says so.
SCRIPT_UNREADABLE = "script_unreadable"


#: Tags whose attributes are worth reading at all. Checked before walking a tag's
#: attributes, so an ordinary page of divs costs one comparison per tag.
_REQUEST_TAGS: frozenset[str] = frozenset(tag for tag, _ in _REQUEST_ATTRIBUTES)


def _tag_name(start_tag: Any) -> str:
    for child in start_tag.named_children:
        if child.type == "tag_name":
            return text_of(child).lower()
    return ""


def _attributes(start_tag: Any) -> Iterator[tuple[str, str]]:
    """Each ``(name, value)`` on a start tag, quoted or bare.

    The query used to express this shape itself. It cost quadratic time on large pages;
    the measurement is in ``omitnix/queries/html.scm``. Walking the children here is more
    code for the same answers, and it is linear.
    """
    for child in start_tag.named_children:
        if child.type != "attribute":
            continue
        name = ""
        value = ""
        for part in child.named_children:
            if part.type == "attribute_name":
                name = text_of(part)
            elif part.type == "attribute_value":
                value = text_of(part)
            elif part.type == "quoted_attribute_value":
                for inner in part.named_children:
                    if inner.type == "attribute_value":
                        value = text_of(inner)
        yield name.lower(), value


def _title(parsed: Parsed) -> str:
    for start_tag in parsed.get("start_tag"):
        if _tag_name(start_tag) != "title":
            continue
        element = start_tag.parent
        if element is None:
            continue
        for child in element.named_children:
            if child.type != "text":
                continue
            line = first_description_line(text_of(child))
            if line:
                return line
    return ""


def _summary(parsed: Parsed) -> str:
    """The document's leading comment, or failing that its title.

    The comment comes first because it was written for a reader of the source, which is
    who reads this index; a title is written for the person using the page and is often a
    site-wide template ("Example Shop"). Either is better than a blank, and a blank is
    what is left when there is neither -- never a placeholder phrase.
    """
    return summary_from_leading_comments(parsed, _HEADER_TYPES) or _title(parsed)


def _record_attribute_endpoints(parsed: Parsed, findings: Findings) -> None:
    for start_tag in parsed.get("start_tag"):
        tag = _tag_name(start_tag)
        if tag not in _REQUEST_TAGS:
            continue
        for name, raw in _attributes(start_tag):
            pair = (tag, name)
            if pair not in _REQUEST_ATTRIBUTES:
                continue
            value = raw.strip()
            if looks_like_endpoint(value):
                findings.endpoints.add(value)
            elif value:
                # A templated action such as "{{ url_for(...) }}" is a request whose
                # address this tool cannot resolve. Counted, not dropped.
                findings.note(
                    DYNAMIC_ENDPOINT,
                    f"the {tag} {name} is not a literal address: {value[:70]}",
                )


def _record_script_endpoints(parsed: Parsed, findings: Findings) -> None:
    for node in parsed.get("script.body"):
        source = text_of(node)
        if not source.strip():
            continue
        why_not = scan_javascript(source, findings)
        if why_not:
            findings.note(SCRIPT_UNREADABLE, why_not)


class HtmlAdapter(Adapter):
    """HTML, parsed with tree-sitter. Inline scripts go through the JavaScript grammar."""

    name = "html"
    extensions = (".html", ".htm")
    capabilities = frozenset({Capability.SUMMARY, Capability.SCREEN_TO_API})

    def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        try:
            grammar = load_grammar(GRAMMAR_NAME, GRAMMAR_MODULE, GRAMMAR_SYMBOL)
        except GrammarUnavailable as exc:
            return AnalysisResult.unknown(str(exc))

        parsed: Parsed | Any = grammar.parse(request.text.encode("utf-8"))
        if parsed.has_error:
            return AnalysisResult.unknown(SYNTAX_ERROR_REASON)

        findings = Findings()
        _record_attribute_endpoints(parsed, findings)
        _record_script_endpoints(parsed, findings)

        result = AnalysisResult()
        result.values[Capability.SUMMARY] = _summary(parsed)
        return apply(result, findings, request, self.capabilities)


ADAPTER = HtmlAdapter()
