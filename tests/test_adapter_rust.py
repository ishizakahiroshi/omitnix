"""The Rust adapter.

Every fixture under ``tests/fixtures/rust`` is invented, using the fictional schema the
rest of this repository already uses.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omitnix.adapters._extract import (
    DYNAMIC_SQL,
    DYNAMIC_TABLE_NAME,
    SELECT_STAR,
    TABLE_NOT_IN_SCHEMA,
)
from omitnix.adapters._treesitter import GrammarUnavailable
from omitnix.adapters.base import AnalysisRequest, AnalysisResult
from omitnix.adapters.rust import ADAPTER, QUERY_BUILDER
from omitnix.analyze import build_report
from omitnix.config import load_config
from omitnix.gate import run_gate
from omitnix.model import Capability, FieldState, Status
from omitnix.reasons import NOT_A_TABLE_GAP, hides_a_table_reference

from .conftest import FIXTURES

RUST_FIXTURES = FIXTURES / "rust"

AUTHN = ("require_session",)
AUTHZ = ("apply_visibility_filter",)

pytest.importorskip("tree_sitter", reason="the Rust adapter needs the tree-sitter binding")
pytest.importorskip("tree_sitter_rust", reason="the Rust adapter needs the Rust grammar")
pytest.importorskip("sqlglot", reason="the Rust adapter reads SQL with sqlglot")


def analyze(
    rel: str,
    *,
    authn: tuple[str, ...] = AUTHN,
    authz: tuple[str, ...] = AUTHZ,
    schema: frozenset[str] = frozenset(),
) -> AnalysisResult:
    absolute = RUST_FIXTURES / rel
    return ADAPTER.analyze(
        AnalysisRequest(
            path=rel,
            absolute_path=absolute,
            text=absolute.read_text(encoding="utf-8"),
            authentication_functions=authn,
            authorization_functions=authz,
            schema_tables=schema,
        )
    )


def codes(result: AnalysisResult) -> set[str]:
    return {item.code for item in result.unresolved}


def values(result: AnalysisResult, capability: Capability) -> list[str]:
    return list(result.values.get(capability) or [])


# --- what the adapter declares ----------------------------------------------------


def test_the_adapter_declares_only_what_it_can_produce() -> None:
    assert Capability.SCREEN_TO_API not in ADAPTER.capabilities
    assert Capability.WRITES in ADAPTER.capabilities
    assert ADAPTER.extensions == (".rs",)


def test_a_query_builder_finding_hides_a_table_reference() -> None:
    """An unclassified code is a gap. Classifying this one as harmless would put a
    builder's file back in the index as a file that touches no table."""
    assert QUERY_BUILDER not in NOT_A_TABLE_GAP
    assert hides_a_table_reference(QUERY_BUILDER)


# --- summary ----------------------------------------------------------------------


def test_the_summary_is_the_inner_doc_comment() -> None:
    result = analyze("orders_list.rs")
    assert result.values[Capability.SUMMARY] == "Lists orders for the signed-in customer."


def test_an_inner_doc_comment_does_not_leave_its_marker_behind() -> None:
    """``//!`` opens a comment. Stripping only the slashes left summaries beginning with
    a stray exclamation mark."""
    result = analyze("counter.rs")
    assert result.values[Capability.SUMMARY] == "Counts orders in a batch. Touches no database."


# --- authentication and authorization ---------------------------------------------


def test_a_method_call_and_a_scoped_call_are_matched_on_the_bare_name() -> None:
    result = analyze("orders_list.rs")
    assert values(result, Capability.AUTHENTICATION) == ["require_session"]
    assert values(result, Capability.AUTHORIZATION) == ["apply_visibility_filter"]


def test_a_bare_call_is_matched_on_the_name() -> None:
    result = analyze("audit.rs")
    assert values(result, Capability.AUTHENTICATION) == ["require_session"]


def test_nothing_is_reported_as_authorization_when_the_repository_named_nothing() -> None:
    result = analyze("orders_list.rs", authn=(), authz=())
    assert values(result, Capability.AUTHORIZATION) == []


# --- reading SQL ------------------------------------------------------------------


def test_a_raw_string_and_a_macro_argument_are_read_as_sql() -> None:
    """Raw strings and ``query!`` are how SQL is written in Rust. ``$1`` is a bound
    parameter, and a JSON object in the text is not a format hole."""
    result = analyze("orders_list.rs")
    assert values(result, Capability.READS) == ["customers", "orders"]
    assert result.unresolved == []


def test_concat_joins_the_pieces_before_they_are_read() -> None:
    result = analyze("export.rs")
    assert values(result, Capability.WRITES) == ["search_index"]
    assert "orders" in values(result, Capability.READS)


def test_a_format_hole_keeps_the_table_and_reports_the_hole() -> None:
    result = analyze("export.rs")
    assert "audit_log" in values(result, Capability.READS)
    assert SELECT_STAR in codes(result)
    assert DYNAMIC_SQL in codes(result)


def test_a_plus_chain_is_never_silently_empty() -> None:
    """``"DELETE FROM ".to_owned() + table`` is the chain Rust actually compiles. Reading
    the ``+`` and missing the string it appends to would drop the statement."""
    result = analyze("export.rs")
    assert DYNAMIC_TABLE_NAME in codes(result)
    assert "table" not in values(result, Capability.WRITES)


def test_prose_that_opens_like_sql_is_not_reported_as_a_table_or_a_finding() -> None:
    result = analyze("notes.rs")
    assert values(result, Capability.READS) == []
    assert result.unresolved == []


def test_no_reason_code_is_ever_recorded_without_a_detail() -> None:
    for item in analyze("export.rs").unresolved:
        assert item.detail.strip(), f"{item.code} carries no detail"


# --- query builders ---------------------------------------------------------------


def test_a_query_builder_call_is_unresolved_and_names_no_table() -> None:
    result = analyze("builder.rs")
    assert values(result, Capability.READS) == []
    assert values(result, Capability.WRITES) == []
    assert QUERY_BUILDER in codes(result)
    details = " ".join(item.detail for item in result.unresolved)
    assert "call 'insert_into'" in details
    assert "call 'load'" in details
    assert "call 'find'" in details
    assert "call 'table'" not in details


def test_a_string_passed_to_the_builder_is_read_and_the_call_is_not_a_second_gap() -> None:
    """``sql_query`` with a finished statement has nothing left hidden. Recording the
    call as well would say the tables might be missing after they had been listed."""
    result = analyze("audit.rs")
    assert values(result, Capability.READS) == ["audit_log"]
    assert QUERY_BUILDER not in codes(result)


def test_the_same_call_name_without_the_crate_is_not_a_query_builder() -> None:
    result = analyze("plain.rs")
    assert values(result, Capability.READS) == []
    assert result.unresolved == []


# --- the schema snapshot ----------------------------------------------------------


def test_a_table_missing_from_the_snapshot_is_reported() -> None:
    schema = frozenset({"orders", "customers", "search_index"})
    result = analyze("export.rs", schema=schema)
    assert TABLE_NOT_IN_SCHEMA in codes(result)


# --- files the adapter cannot read ------------------------------------------------


def test_a_file_that_does_not_parse_is_unknown_rather_than_partially_reported() -> None:
    result = analyze("broken.rs")
    assert result.unknown_reason is not None
    assert "syntax error" in result.unknown_reason


def test_a_missing_grammar_becomes_an_unknown_record_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: str, **_kwargs: str) -> None:
        raise GrammarUnavailable("the rust grammar is not installed")

    monkeypatch.setattr("omitnix.adapters.rust.load_grammar", unavailable)
    result = analyze("orders_list.rs")
    assert result.unknown_reason is not None
    assert "not installed" in result.unknown_reason


# --- end to end through the core --------------------------------------------------

REPO_CONFIG = """
include:
  - '**/*.rs'
authentication_functions:
  - require_session
authorization_functions:
  - apply_visibility_filter
"""


@pytest.fixture
def rust_repo(tmp_path: Path) -> Path:
    shutil.copytree(RUST_FIXTURES, tmp_path / "src")
    (tmp_path / ".omitnix.yaml").write_text(REPO_CONFIG, encoding="utf-8")
    return tmp_path


def test_the_counting_invariant_holds_over_a_rust_repository(rust_repo: Path) -> None:
    report = build_report(load_config(rust_repo))
    assert report.coverage.holds
    assert report.coverage.discovered == 8
    assert report.coverage.unknown == 1
    assert report.coverage.unresolved == 2
    assert report.coverage.analyzed == 5


def test_the_table_reverse_index_names_the_rust_files(rust_repo: Path) -> None:
    report = build_report(load_config(rust_repo))
    orders = next(table for table in report.tables if table.name == "orders")
    assert "src/orders_list.rs" in orders.read_by
    assert "src/export.rs" in orders.read_by


def test_the_screen_to_api_column_is_out_of_scope_not_empty(rust_repo: Path) -> None:
    record = build_report(load_config(rust_repo)).file("src/counter.rs")
    assert record.status is Status.ANALYZED
    assert record.fields[Capability.SCREEN_TO_API].state is FieldState.OUT_OF_SCOPE


def test_a_new_rust_file_with_no_auth_call_fails_the_gate(rust_repo: Path) -> None:
    config = load_config(rust_repo)
    report = build_report(config, files=["src/counter.rs"])
    gate = run_gate(report, config)
    assert not gate.passed
    assert any(finding.item == "no authentication call" for finding in gate.findings)


def test_a_rust_file_that_makes_the_calls_passes_the_gate(rust_repo: Path) -> None:
    config = load_config(rust_repo)
    report = build_report(config, files=["src/orders_list.rs"])
    gate = run_gate(report, config)
    assert gate.passed, [finding.line() for finding in gate.findings]
