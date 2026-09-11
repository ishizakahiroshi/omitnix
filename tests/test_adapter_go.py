"""The Go adapter.

Every fixture under ``tests/fixtures/go`` is invented, using the fictional schema the
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
from omitnix.adapters.go import ADAPTER
from omitnix.analyze import build_report
from omitnix.config import load_config
from omitnix.model import Capability, FieldState, Status

from .conftest import FIXTURES

GO_FIXTURES = FIXTURES / "go"

AUTHN = ("requireSession",)
AUTHZ = ("applyVisibilityFilter",)

pytest.importorskip("tree_sitter", reason="the Go adapter needs the tree-sitter binding")
pytest.importorskip("tree_sitter_go", reason="the Go adapter needs the Go grammar")
pytest.importorskip("sqlglot", reason="the Go adapter reads SQL with sqlglot")


def analyze(
    rel: str,
    *,
    authn: tuple[str, ...] = AUTHN,
    authz: tuple[str, ...] = AUTHZ,
    schema: frozenset[str] = frozenset(),
) -> AnalysisResult:
    absolute = GO_FIXTURES / rel
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
    assert ADAPTER.extensions == (".go",)


# --- summary ----------------------------------------------------------------------


def test_the_summary_is_the_package_comment() -> None:
    result = analyze("orders_list.go")
    assert result.values[Capability.SUMMARY] == (
        "Package orders lists orders for the signed-in customer."
    )


def test_a_build_constraint_is_not_mistaken_for_the_summary() -> None:
    """'//go:build ignore' is a directive to the compiler and describes no file."""
    result = analyze("reindex.go")
    assert result.values[Capability.SUMMARY] == "Package reindex rebuilds the order search table."


# --- authentication and authorization ---------------------------------------------


def test_configured_authentication_and_authorization_calls_are_reported() -> None:
    result = analyze("orders_list.go")
    assert values(result, Capability.AUTHENTICATION) == ["requireSession"]
    assert values(result, Capability.AUTHORIZATION) == ["applyVisibilityFilter"]


def test_nothing_is_reported_as_authorization_when_the_repository_named_nothing() -> None:
    result = analyze("orders_list.go", authn=(), authz=())
    assert values(result, Capability.AUTHORIZATION) == []


# --- reading SQL ------------------------------------------------------------------


def test_a_raw_string_literal_is_read_as_sql() -> None:
    """Backtick strings are how multi-line SQL is written in Go. Not reading them leaves
    every query in an idiomatic Go codebase invisible."""
    result = analyze("orders_list.go")
    assert values(result, Capability.READS) == ["customers", "orders"]


def test_insert_target_is_a_write_and_its_select_is_a_read() -> None:
    result = analyze("reindex.go")
    assert values(result, Capability.WRITES) == ["search_index"]
    assert values(result, Capability.READS) == ["orders"]


def test_prose_that_opens_like_sql_is_not_reported_as_a_table_or_a_finding() -> None:
    result = analyze("notes.go")
    assert values(result, Capability.READS) == []
    assert result.unresolved == []


# --- what could not be read -------------------------------------------------------


def test_a_concatenated_statement_is_never_silently_empty() -> None:
    result = analyze("export.go")
    assert DYNAMIC_SQL in codes(result)
    assert DYNAMIC_TABLE_NAME in codes(result)
    assert values(result, Capability.WRITES) == []
    assert result.unresolved


def test_a_go_formatting_verb_is_treated_as_a_value_filled_in_elsewhere() -> None:
    """%q has no printf equivalent, so the shared printf pattern left it in place and
    handed sqlglot a statement with a stray percent sign."""
    result = analyze("export.go")
    assert "audit_log" in values(result, Capability.READS)
    assert SELECT_STAR in codes(result)


def test_no_reason_code_is_ever_recorded_without_a_detail() -> None:
    for item in analyze("export.go").unresolved:
        assert item.detail.strip(), f"{item.code} carries no detail"


# --- the schema snapshot ----------------------------------------------------------


def test_a_table_missing_from_the_snapshot_is_reported() -> None:
    schema = frozenset({"orders", "customers", "search_index"})
    result = analyze("export.go", schema=schema)
    assert TABLE_NOT_IN_SCHEMA in codes(result)


# --- files the adapter cannot read ------------------------------------------------


def test_a_file_that_does_not_parse_is_unknown_rather_than_partially_reported() -> None:
    result = analyze("broken.go")
    assert result.unknown_reason is not None
    assert "syntax error" in result.unknown_reason


def test_a_missing_grammar_becomes_an_unknown_record_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: str, **_kwargs: str) -> None:
        raise GrammarUnavailable("the go grammar is not installed")

    monkeypatch.setattr("omitnix.adapters.go.load_grammar", unavailable)
    result = analyze("orders_list.go")
    assert result.unknown_reason is not None
    assert "not installed" in result.unknown_reason


# --- end to end through the core --------------------------------------------------

REPO_CONFIG = """
include:
  - '**/*.go'
authentication_functions:
  - requireSession
authorization_functions:
  - applyVisibilityFilter
"""


@pytest.fixture
def go_repo(tmp_path: Path) -> Path:
    shutil.copytree(GO_FIXTURES, tmp_path / "src")
    (tmp_path / ".omitnix.yaml").write_text(REPO_CONFIG, encoding="utf-8")
    return tmp_path


def test_the_counting_invariant_holds_over_a_go_repository(go_repo: Path) -> None:
    report = build_report(load_config(go_repo))
    assert report.coverage.holds
    assert report.coverage.unknown == 1  # broken.go, and it must fail the run


def test_the_table_reverse_index_names_the_go_files(go_repo: Path) -> None:
    report = build_report(load_config(go_repo))
    orders = next(table for table in report.tables if table.name == "orders")
    assert "src/orders_list.go" in orders.read_by


def test_the_screen_to_api_column_is_out_of_scope_not_empty(go_repo: Path) -> None:
    record = build_report(load_config(go_repo)).file("src/reindex.go")
    assert record.status is Status.ANALYZED
    assert record.fields[Capability.SCREEN_TO_API].state is FieldState.OUT_OF_SCOPE
