"""The TypeScript / JavaScript adapter.

Every fixture under ``tests/fixtures/tsjs`` is invented, using the fictional schema the
rest of this repository already uses.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omitnix.adapters._extract import DYNAMIC_ENDPOINT, DYNAMIC_SQL, SELECT_STAR
from omitnix.adapters._treesitter import GrammarUnavailable
from omitnix.adapters.base import AnalysisRequest, AnalysisResult
from omitnix.adapters.tsjs import ADAPTER
from omitnix.analyze import build_report
from omitnix.config import load_config
from omitnix.model import Capability, FieldState, Status

from .conftest import FIXTURES

TSJS_FIXTURES = FIXTURES / "tsjs"

AUTHN = ("requireSession",)
AUTHZ = ("applyVisibilityFilter",)

pytest.importorskip("tree_sitter", reason="the tsjs adapter needs the tree-sitter binding")
pytest.importorskip("tree_sitter_typescript", reason="the tsjs adapter needs the TS grammar")
pytest.importorskip("tree_sitter_javascript", reason="the tsjs adapter needs the JS grammar")
pytest.importorskip("sqlglot", reason="the tsjs adapter reads SQL with sqlglot")


def analyze(
    rel: str,
    *,
    authn: tuple[str, ...] = AUTHN,
    authz: tuple[str, ...] = AUTHZ,
) -> AnalysisResult:
    absolute = TSJS_FIXTURES / rel
    return ADAPTER.analyze(
        AnalysisRequest(
            path=rel,
            absolute_path=absolute,
            text=absolute.read_text(encoding="utf-8"),
            authentication_functions=authn,
            authorization_functions=authz,
        )
    )


def codes(result: AnalysisResult) -> set[str]:
    return {item.code for item in result.unresolved}


def values(result: AnalysisResult, capability: Capability) -> list[str]:
    return list(result.values.get(capability) or [])


# --- what the adapter declares ----------------------------------------------------


def test_one_adapter_covers_the_five_extensions_of_the_family() -> None:
    assert ADAPTER.extensions == (".ts", ".tsx", ".js", ".mjs", ".cjs")


def test_the_adapter_declares_the_screen_to_api_direction() -> None:
    assert Capability.SCREEN_TO_API in ADAPTER.capabilities


# --- every extension actually parses, with the grammar that suits it ---------------


@pytest.mark.parametrize(
    ("rel", "summary"),
    [
        ("orders_list.ts", "List orders for the signed-in customer."),
        ("panel.tsx", "The customer panel screen."),
        ("audit.js", "Read and stamp the audit trail."),
        ("reindex.mjs", "Nightly reindex of the order search table."),
        ("client.cjs", "A request whose address is decided at run time."),
    ],
)
def test_each_extension_is_parsed_rather_than_reported_unknown(rel: str, summary: str) -> None:
    """A file the grammar cannot read is `unknown`, so a wrong grammar for an extension
    would show up here as a whole extension nobody can analyze."""
    result = analyze(rel)
    assert result.unknown_reason is None, result.unknown_reason
    assert result.values[Capability.SUMMARY] == summary


def test_jsx_is_parsed_by_the_tsx_grammar_rather_than_failing() -> None:
    result = analyze("panel.tsx")
    assert result.unknown_reason is None
    assert values(result, Capability.SCREEN_TO_API) == ["/api/customers/*"]


# --- authentication and authorization ---------------------------------------------


def test_configured_authentication_and_authorization_calls_are_reported() -> None:
    result = analyze("orders_list.ts")
    assert values(result, Capability.AUTHENTICATION) == ["requireSession"]
    assert values(result, Capability.AUTHORIZATION) == ["applyVisibilityFilter"]


# --- reading SQL ------------------------------------------------------------------


def test_insert_target_is_a_write_and_its_select_is_a_read() -> None:
    result = analyze("reindex.mjs")
    assert values(result, Capability.WRITES) == ["search_index"]
    assert values(result, Capability.READS) == ["orders"]


def test_a_template_literal_is_flagged_but_still_yields_its_tables() -> None:
    result = analyze("audit.js")
    assert DYNAMIC_SQL in codes(result)
    assert SELECT_STAR in codes(result)
    assert "audit_log" in values(result, Capability.READS)


def test_a_like_wildcard_is_not_mistaken_for_a_value_filled_in_elsewhere() -> None:
    """A percent sign in this family is a LIKE wildcard, never a printf conversion.
    Substituting it corrupted a static statement into one reported as assembled at run
    time -- a finding about nothing, on a file that has a real finding elsewhere."""
    result = analyze("audit.js")
    details = " ".join(item.detail for item in result.unresolved)
    assert "draft" not in details


# --- the screen-to-API direction ---------------------------------------------------


def test_a_literal_fetch_address_is_recorded() -> None:
    assert "/api/orders" in values(analyze("orders_list.ts"), Capability.SCREEN_TO_API)


def test_an_axios_call_is_recorded() -> None:
    assert "/api/audit" in values(analyze("audit.js"), Capability.SCREEN_TO_API)


def test_a_partly_known_address_keeps_the_part_that_is_known_and_is_flagged() -> None:
    result = analyze("orders_list.ts")
    assert "/api/orders/*" in values(result, Capability.SCREEN_TO_API)
    assert DYNAMIC_ENDPOINT in codes(result)


def test_an_address_that_is_a_variable_is_counted_rather_than_dropped() -> None:
    """The call was seen and its address was not readable. Recording nothing at all would
    make a file that calls an API look like a file that calls none."""
    result = analyze("client.cjs")
    assert values(result, Capability.SCREEN_TO_API) == []
    assert DYNAMIC_ENDPOINT in codes(result)


def test_an_ordinary_method_call_is_not_recorded_as_a_request() -> None:
    """Only fetch and axios are treated as requests. Widening it to every .get() would
    put map lookups in the index as API calls."""
    result = analyze("reindex.mjs")
    assert values(result, Capability.SCREEN_TO_API) == []
    assert DYNAMIC_ENDPOINT not in codes(result)


def test_no_reason_code_is_ever_recorded_without_a_detail() -> None:
    for rel in ("audit.js", "client.cjs", "orders_list.ts"):
        for item in analyze(rel).unresolved:
            assert item.detail.strip(), f"{rel}: {item.code} carries no detail"


# --- files the adapter cannot read ------------------------------------------------


def test_a_file_that_does_not_parse_is_unknown_rather_than_partially_reported() -> None:
    result = analyze("broken.js")
    assert result.unknown_reason is not None
    assert "syntax error" in result.unknown_reason


def test_a_missing_grammar_becomes_an_unknown_record_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: str) -> None:
        raise GrammarUnavailable("the javascript grammar is not installed")

    monkeypatch.setattr("omitnix.adapters.tsjs.load_grammar", unavailable)
    result = analyze("orders_list.ts")
    assert result.unknown_reason is not None
    assert "not installed" in result.unknown_reason


# --- end to end through the core --------------------------------------------------

REPO_CONFIG = """
include:
  - '**/*.ts'
  - '**/*.tsx'
  - '**/*.js'
  - '**/*.mjs'
  - '**/*.cjs'
authentication_functions:
  - requireSession
authorization_functions:
  - applyVisibilityFilter
"""


@pytest.fixture
def tsjs_repo(tmp_path: Path) -> Path:
    shutil.copytree(TSJS_FIXTURES, tmp_path / "src")
    (tmp_path / ".omitnix.yaml").write_text(REPO_CONFIG, encoding="utf-8")
    return tmp_path


def test_the_counting_invariant_holds_over_a_tsjs_repository(tsjs_repo: Path) -> None:
    report = build_report(load_config(tsjs_repo))
    assert report.coverage.holds
    assert report.coverage.unknown == 1  # broken.js, and it must fail the run


def test_every_extension_of_the_family_is_routed_to_this_adapter(tsjs_repo: Path) -> None:
    report = build_report(load_config(tsjs_repo))
    adapters = {record.adapter for record in report.files}
    assert adapters == {"tsjs"}


def test_a_file_that_touches_no_table_is_analyzed_not_unresolved(tsjs_repo: Path) -> None:
    record = build_report(load_config(tsjs_repo)).file("src/reindex.mjs")
    assert record.status is Status.ANALYZED
    assert record.fields[Capability.SCREEN_TO_API].state is FieldState.NONE_OBSERVED
