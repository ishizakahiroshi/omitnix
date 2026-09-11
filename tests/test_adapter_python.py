"""The Python adapter.

Every fixture under ``tests/fixtures/python`` is invented. The vocabulary (orders,
customers, search_index, audit_log, require_session, apply_visibility_filter) is the
fictional schema the rest of this repository already uses.
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
from omitnix.adapters.python import ADAPTER
from omitnix.analyze import build_report
from omitnix.config import load_config
from omitnix.model import Capability, FieldState, Status

from .conftest import FIXTURES

PYTHON_FIXTURES = FIXTURES / "python"

AUTHN = ("require_session",)
AUTHZ = ("apply_visibility_filter",)

pytest.importorskip("tree_sitter", reason="the Python adapter needs the tree-sitter binding")
pytest.importorskip("tree_sitter_python", reason="the Python adapter needs the Python grammar")
pytest.importorskip("sqlglot", reason="the Python adapter reads SQL with sqlglot")


def analyze(
    rel: str,
    *,
    authn: tuple[str, ...] = AUTHN,
    authz: tuple[str, ...] = AUTHZ,
    schema: frozenset[str] = frozenset(),
) -> AnalysisResult:
    absolute = PYTHON_FIXTURES / rel
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
    """No screen-to-api claim, so the core renders that column out of scope, not empty."""
    assert Capability.SCREEN_TO_API not in ADAPTER.capabilities
    assert Capability.READS in ADAPTER.capabilities
    assert ADAPTER.extensions == (".py", ".pyi")


# --- summary ----------------------------------------------------------------------


def test_the_summary_is_the_first_line_of_the_module_docstring() -> None:
    result = analyze("orders_list.py")
    assert result.values[Capability.SUMMARY] == "List orders for the signed-in customer."


def test_annotation_lines_are_not_mistaken_for_the_summary() -> None:
    result = analyze("orders_list.py")
    assert ":param" not in result.values[Capability.SUMMARY]


def test_a_module_without_a_docstring_falls_back_to_its_header_comment() -> None:
    result = analyze("reindex.py")
    assert result.values[Capability.SUMMARY] == "Nightly reindex of the order search table."


def test_a_file_with_neither_reports_no_summary_rather_than_inventing_one() -> None:
    """Left empty so the core can say 'none observed'. A placeholder string here would
    claim a summary was extracted."""
    result = analyze("notes.py")
    assert result.values[Capability.SUMMARY] == ""


def test_a_sentence_that_begins_with_a_directive_word_is_still_a_summary() -> None:
    """'Type stubs for ...' opens with a word that also appears in @type directives.
    Discarding it left every stub file in the index with no summary at all."""
    result = analyze("client.pyi")
    assert result.values[Capability.SUMMARY].startswith("Type stubs")


# --- authentication and authorization ---------------------------------------------


def test_configured_authentication_and_authorization_calls_are_reported() -> None:
    result = analyze("orders_list.py")
    assert values(result, Capability.AUTHENTICATION) == ["require_session"]
    assert values(result, Capability.AUTHORIZATION) == ["apply_visibility_filter"]


def test_nothing_is_reported_as_authorization_when_the_repository_named_nothing() -> None:
    result = analyze("orders_list.py", authn=(), authz=())
    assert values(result, Capability.AUTHENTICATION) == []
    assert values(result, Capability.AUTHORIZATION) == []


def test_a_file_with_no_check_reports_none_rather_than_failing() -> None:
    result = analyze("reindex.py")
    assert values(result, Capability.AUTHENTICATION) == []
    assert result.unknown_reason is None


# --- reading SQL ------------------------------------------------------------------


def test_adjacent_string_literals_are_read_as_one_statement() -> None:
    """Python joins strings written next to each other, which is how a multi-line query
    is usually spelled. Read separately, the JOIN clause becomes a fragment with no verb
    and the second table is lost."""
    result = analyze("orders_list.py")
    assert values(result, Capability.READS) == ["customers", "orders"]


def test_insert_target_is_a_write_and_its_select_is_a_read() -> None:
    result = analyze("reindex.py")
    assert values(result, Capability.WRITES) == ["search_index"]
    assert values(result, Capability.READS) == ["orders"]


def test_prose_that_opens_like_sql_is_not_reported_as_a_table_or_a_finding() -> None:
    result = analyze("notes.py")
    assert values(result, Capability.READS) == []
    assert values(result, Capability.WRITES) == []
    assert result.unresolved == []


# --- a bound parameter is not an assembled statement ------------------------------


def test_a_parameterised_query_is_not_reported_as_assembled_at_run_time() -> None:
    """``%s`` is the DB-API parameter marker. Treating it as a template made the safest
    form of query in the language produce a finding, which would mark nearly every Python
    file unresolved and bury the statements that really are built by string arithmetic."""
    result = analyze("orders_list.py")
    assert DYNAMIC_SQL not in codes(result)
    assert result.unresolved == []


def test_the_percent_operator_is_reported_as_assembled_at_run_time() -> None:
    """The same characters, used the other way: here the value goes into the SQL text."""
    result = analyze("legacy_report.py")
    assert DYNAMIC_SQL in codes(result)
    assert "orders" in values(result, Capability.READS)


def test_str_format_is_reported_as_assembled_at_run_time() -> None:
    result = analyze("legacy_report.py")
    details = " ".join(item.detail for item in result.unresolved)
    assert "audit_log" in details
    assert "audit_log" in values(result, Capability.READS)


# --- what could not be read -------------------------------------------------------


def test_a_concatenated_statement_is_never_silently_empty() -> None:
    result = analyze("export.py")
    assert DYNAMIC_SQL in codes(result)
    assert DYNAMIC_TABLE_NAME in codes(result)
    assert values(result, Capability.WRITES) == []
    # The empty list above is only honest because the reasons above are attached to it.
    assert result.unresolved


def test_an_f_string_is_flagged_but_still_yields_its_tables() -> None:
    result = analyze("audit.py")
    assert DYNAMIC_SQL in codes(result)
    assert "audit_log" in values(result, Capability.WRITES)


def test_select_star_keeps_the_table_and_flags_only_the_columns() -> None:
    result = analyze("audit.py")
    assert "audit_log" in values(result, Capability.READS)
    assert SELECT_STAR in codes(result)


def test_no_reason_code_is_ever_recorded_without_a_detail() -> None:
    for rel in ("export.py", "audit.py", "legacy_report.py"):
        for item in analyze(rel).unresolved:
            assert item.detail.strip(), f"{rel}: {item.code} carries no detail"


# --- the schema snapshot ----------------------------------------------------------


def test_a_table_missing_from_the_snapshot_is_reported() -> None:
    schema = frozenset({"orders", "customers", "search_index"})
    result = analyze("audit.py", schema=schema)
    assert TABLE_NOT_IN_SCHEMA in codes(result)
    assert "audit_log" in " ".join(item.detail for item in result.unresolved)


def test_nothing_is_reported_against_a_schema_that_was_not_configured() -> None:
    assert TABLE_NOT_IN_SCHEMA not in codes(analyze("audit.py"))


# --- files the adapter cannot read ------------------------------------------------


def test_a_file_that_does_not_parse_is_unknown_rather_than_partially_reported() -> None:
    result = analyze("broken.py")
    assert result.unknown_reason is not None
    assert "syntax error" in result.unknown_reason


def test_a_missing_grammar_becomes_an_unknown_record_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: str, **_kwargs: str) -> None:
        raise GrammarUnavailable("the python grammar is not installed")

    monkeypatch.setattr("omitnix.adapters.python.load_grammar", unavailable)
    result = analyze("orders_list.py")
    assert result.unknown_reason is not None
    assert "not installed" in result.unknown_reason


# --- end to end through the core --------------------------------------------------

REPO_CONFIG = """
include:
  - '**/*.py'
  - '**/*.pyi'
authentication_functions:
  - require_session
authorization_functions:
  - apply_visibility_filter
"""


@pytest.fixture
def python_repo(tmp_path: Path) -> Path:
    shutil.copytree(PYTHON_FIXTURES, tmp_path / "src")
    (tmp_path / ".omitnix.yaml").write_text(REPO_CONFIG, encoding="utf-8")
    return tmp_path


def test_the_counting_invariant_holds_over_a_python_repository(python_repo: Path) -> None:
    report = build_report(load_config(python_repo))
    assert report.coverage.holds
    assert report.coverage.discovered == len(report.files)
    assert report.coverage.unknown == 1  # broken.py, and it must fail the run


def test_the_table_reverse_index_names_the_python_files(python_repo: Path) -> None:
    report = build_report(load_config(python_repo))
    search_index = next(table for table in report.tables if table.name == "search_index")
    assert search_index.written_by == ("src/reindex.py",)
    assert search_index.read_by == ()


def test_the_screen_to_api_column_is_out_of_scope_not_empty(python_repo: Path) -> None:
    report = build_report(load_config(python_repo))
    record = report.file("src/reindex.py")
    assert record.status is Status.ANALYZED
    assert record.fields[Capability.SCREEN_TO_API].state is FieldState.OUT_OF_SCOPE
    assert record.fields[Capability.AUTHORIZATION].state is FieldState.NONE_OBSERVED
