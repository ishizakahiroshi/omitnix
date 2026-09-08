"""The HTML adapter -- the reverse-lookup tier.

Every fixture under ``tests/fixtures/html`` is invented.
"""

from __future__ import annotations

import shutil
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


def test_the_leading_comment_is_the_summary_when_there_is_one() -> None:
    result = analyze("orders.html")
    assert result.values[Capability.SUMMARY].startswith("The order list screen.")


def test_the_title_is_the_summary_when_there_is_no_comment() -> None:
    assert analyze("about.htm").values[Capability.SUMMARY] == "About this fictional shop"


# --- files the adapter cannot read ------------------------------------------------


def test_a_missing_grammar_becomes_an_unknown_record_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: str) -> None:
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
        lambda _source, _findings: "the javascript grammar is not installed",
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
    assert report.coverage.unknown == 0


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
