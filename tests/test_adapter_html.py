"""The HTML adapter -- the reverse-lookup tier.

Every fixture under ``tests/fixtures/html`` is invented.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from omitnix.adapters._extract import DYNAMIC_ENDPOINT
from omitnix.adapters._treesitter import GrammarUnavailable
from omitnix.adapters.base import AnalysisRequest, AnalysisResult
from omitnix.adapters.html import ADAPTER
from omitnix.analyze import build_report
from omitnix.config import load_config
from omitnix.model import Capability, FieldState, Status

from .conftest import FIXTURES

HTML_FIXTURES = FIXTURES / "html"

pytest.importorskip("tree_sitter", reason="the HTML adapter needs the tree-sitter binding")
pytest.importorskip("tree_sitter_html", reason="the HTML adapter needs the HTML grammar")
pytest.importorskip("tree_sitter_javascript", reason="inline scripts need the JS grammar")


def analyze(rel: str) -> AnalysisResult:
    absolute = HTML_FIXTURES / rel
    return ADAPTER.analyze(
        AnalysisRequest(
            path=rel,
            absolute_path=absolute,
            text=absolute.read_text(encoding="utf-8"),
        )
    )


def codes(result: AnalysisResult) -> set[str]:
    return {item.code for item in result.unresolved}


def values(result: AnalysisResult, capability: Capability) -> list[str]:
    return list(result.values.get(capability) or [])


# --- what the adapter declares ----------------------------------------------------


def test_the_adapter_claims_neither_authorization_nor_tables() -> None:
    """A page must never appear in a document as a file that was checked for an
    authorization call and found to have none."""
    assert Capability.AUTHORIZATION not in ADAPTER.capabilities
    assert Capability.READS not in ADAPTER.capabilities
    assert ADAPTER.capabilities == frozenset({Capability.SUMMARY, Capability.SCREEN_TO_API})
    assert ADAPTER.extensions == (".html", ".htm")


# --- the screen-to-API direction ---------------------------------------------------


def test_a_form_action_is_a_request_the_screen_makes() -> None:
    assert "/api/orders" in values(analyze("orders.html"), Capability.SCREEN_TO_API)


def test_a_script_src_is_recorded() -> None:
    assert "/static/orders.js" in values(analyze("orders.html"), Capability.SCREEN_TO_API)


def test_a_fetch_inside_an_inline_script_is_recorded() -> None:
    """The addresses a page requests are written in its script far more often than in a
    form action. Reading the script with the JavaScript grammar is what makes the
    screen-to-API index worth having."""
    assert "/api/customers" in values(analyze("orders.html"), Capability.SCREEN_TO_API)


def test_an_axios_call_inside_an_inline_script_is_recorded() -> None:
    assert "/api/audit" in values(analyze("orders.html"), Capability.SCREEN_TO_API)


def test_a_link_is_not_recorded_as_a_request() -> None:
    """A link is somewhere a person may go, not a call the page makes. Admitting links
    would bury the handful of real endpoints under every navigation item on the site."""
    assert "/help" not in values(analyze("orders.html"), Capability.SCREEN_TO_API)


def test_a_page_that_requests_nothing_reports_none_observed_rather_than_failing() -> None:
    result = analyze("about.htm")
    assert values(result, Capability.SCREEN_TO_API) == []
    assert result.unresolved == []


def test_a_templated_action_is_counted_rather_than_dropped() -> None:
    result = analyze("templated.html")
    assert values(result, Capability.SCREEN_TO_API) == []
    assert DYNAMIC_ENDPOINT in codes(result)
    assert all(item.detail.strip() for item in result.unresolved)


# --- summary ----------------------------------------------------------------------


def test_the_title_wins_over_a_leading_comment() -> None:
    """orders.html has both. The title is what names the page in a sentence."""
    assert analyze("orders.html").values[Capability.SUMMARY] == "Orders"


def test_the_title_is_the_summary_when_there_is_no_comment() -> None:
    assert analyze("about.htm").values[Capability.SUMMARY] == "About this fictional shop"


def test_the_leading_comment_is_the_summary_when_there_is_no_title() -> None:
    result = analyze("notes.html")
    assert result.values[Capability.SUMMARY].startswith("A fragment with no head")


# --- text the grammar refuses and the specification allows -------------------------


def test_a_bare_angle_bracket_in_text_does_not_discard_the_page() -> None:
    """``{{ a.length > 3 }}`` is text. The page is read, and the reading says so."""
    result = analyze("interpolated.html")
    assert result.unknown_reason is None
    assert values(result, Capability.SCREEN_TO_API) == ["/api/orders"]
    assert "unescaped_text" in codes(result)


def test_the_note_names_the_lines_the_grammar_could_not_read() -> None:
    detail = next(
        item.detail for item in analyze("interpolated.html").unresolved
        if item.code == "unescaped_text"
    )
    assert "7" in detail and "8" in detail and "9" in detail


def test_the_recovered_page_reads_the_same_as_its_escaped_twin() -> None:
    """The measurement the exception rests on, kept as a test.

    ``interpolated_escaped.html`` is the same document with those characters written as
    entities, so the grammar accepts it whole. If the two ever disagree, reading the
    recovered tree has started inventing something and the exception has to go.
    """
    recovered = analyze("interpolated.html")
    escaped = analyze("interpolated_escaped.html")

    assert recovered.values[Capability.SUMMARY] == escaped.values[Capability.SUMMARY]
    assert values(recovered, Capability.SCREEN_TO_API) == values(
        escaped, Capability.SCREEN_TO_API
    )
    assert codes(escaped) == set()


def test_a_bare_less_than_in_text_is_still_refused() -> None:
    """``<`` opens a tag. Unlike ``>`` and ``&`` it is genuinely ambiguous, so the
    recovery is a guess about structure and the page is not read."""
    result = analyze("stray_open_bracket.html")
    assert result.unknown_reason is not None
    assert "syntax error" in result.unknown_reason


# --- files the adapter cannot read ------------------------------------------------


def test_a_missing_grammar_becomes_an_unknown_record_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: str, **_kwargs: str) -> None:
        raise GrammarUnavailable("the html grammar is not installed")

    monkeypatch.setattr("omitnix.adapters.html.load_grammar", unavailable)
    result = analyze("orders.html")
    assert result.unknown_reason is not None
    assert "not installed" in result.unknown_reason


def test_an_unreadable_inline_script_is_reported_rather_than_passed_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A script that was not read is not a script that requests nothing."""
    monkeypatch.setattr(
        "omitnix.adapters.html.scan_javascript",
        lambda _source, _findings, **_kwargs: "the javascript grammar is not installed",
    )
    result = analyze("orders.html")
    assert "script_unreadable" in codes(result)
    assert "/api/customers" not in values(result, Capability.SCREEN_TO_API)


# --- end to end through the core --------------------------------------------------

REPO_CONFIG = """
include:
  - '**/*.html'
  - '**/*.htm'
"""


@pytest.fixture
def html_repo(tmp_path: Path) -> Path:
    shutil.copytree(HTML_FIXTURES, tmp_path / "src")
    (tmp_path / ".omitnix.yaml").write_text(REPO_CONFIG, encoding="utf-8")
    return tmp_path


def test_the_counting_invariant_holds_over_an_html_repository(html_repo: Path) -> None:
    report = build_report(load_config(html_repo))
    assert report.coverage.holds
    refused = [record.path for record in report.files if record.status is Status.UNKNOWN]
    # One fixture is written to be refused, and naming it here is the point: if any other
    # page joins it the assertion fails, and if it stops being refused it fails too.
    assert refused == ["src/stray_open_bracket.html"]


def test_the_columns_outside_this_tier_are_out_of_scope_not_empty(html_repo: Path) -> None:
    record = build_report(load_config(html_repo)).file("src/orders.html")
    assert record.status is Status.ANALYZED
    for capability in (
        Capability.AUTHENTICATION,
        Capability.AUTHORIZATION,
        Capability.READS,
        Capability.WRITES,
    ):
        assert record.fields[capability].state is FieldState.OUT_OF_SCOPE
    assert record.fields[Capability.SCREEN_TO_API].state is FieldState.VALUE


# --------------------------------------------------------------------------------------
# Cost
# --------------------------------------------------------------------------------------


def _generated_page(rows: int) -> str:
    """A page with nothing interesting in it, only a great many ordinary tags."""
    body = "\n".join(
        f'<div class="row r{i}" data-id="{i}"><span title="t{i}">text {i}</span></div>'
        for i in range(rows)
    )
    return f"<!doctype html>\n<html><body>\n{body}\n</body></html>\n"


def _seconds_to_analyze(text: str, *, attempts: int = 5) -> float:
    """The fastest of several runs, which is the honest estimate of what the work costs.

    Interference on a shared runner only ever adds time, so a single reading is an
    upper bound of unknown looseness rather than a measurement. Taking the smallest
    reading removes the noise without weakening the guard: a query that costs the
    square of the page is slower in every attempt, not in an unlucky one.
    """
    request = AnalysisRequest(path="generated.html", absolute_path=None, text=text)
    best = float("inf")
    for _ in range(attempts):
        start = time.perf_counter()
        ADAPTER.analyze(request)
        best = min(best, time.perf_counter() - start)
    return best


def test_cost_grows_with_the_page_rather_than_with_its_square() -> None:
    """A guard on the query's shape, phrased as a ratio so it does not depend on the machine.

    Until 2026-09-08 the query asked for several nodes at different depths in one
    pattern, and doubling a page quadrupled the time: one real 2.6 MB page took 27.3
    seconds and was 44% of a whole 52-repository run. The query now captures whole nodes
    and the adapter walks their children, which is linear. A wall-clock budget would say
    more about the runner than about the code, so this compares one size against another.

    Measured 2026-09-11 over 12 attempts on one machine: a single reading of each size
    put the ratio anywhere between 1.6 and 2.8, and the same test on a macOS runner read
    3.1 and failed while the adapter was untouched. The comparison is sound; one reading
    of each side was not enough to make it.
    """
    small = _seconds_to_analyze(_generated_page(3000))
    large = _seconds_to_analyze(_generated_page(6000))

    assert large < small * 3, (
        f"doubling the page took {large / small:.1f} times as long "
        "(linear is about 2, quadratic about 4)"
    )
