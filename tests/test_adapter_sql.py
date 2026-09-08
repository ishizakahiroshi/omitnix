"""The SQL adapter.

Every fixture under ``tests/fixtures/sql`` is invented, using the fictional schema the
rest of this repository already uses.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omitnix.adapters._extract import SQL_UNREADABLE, SQL_UNSUPPORTED, TABLE_NOT_IN_SCHEMA
from omitnix.adapters.base import AnalysisRequest, AnalysisResult
from omitnix.adapters.sql import ADAPTER
from omitnix.analyze import build_report
from omitnix.config import load_config
from omitnix.model import Capability, FieldState, Status

from .conftest import FIXTURES

SQL_FIXTURES = FIXTURES / "sql"

pytest.importorskip("sqlglot", reason="the SQL adapter reads SQL with sqlglot")


def analyze(rel: str, *, schema: frozenset[str] = frozenset()) -> AnalysisResult:
    absolute = SQL_FIXTURES / rel
    return ADAPTER.analyze(
        AnalysisRequest(
            path=rel,
            absolute_path=absolute,
            text=absolute.read_text(encoding="utf-8"),
            schema_tables=schema,
        )
    )


def codes(result: AnalysisResult) -> set[str]:
    return {item.code for item in result.unresolved}


def values(result: AnalysisResult, capability: Capability) -> list[str]:
    return list(result.values.get(capability) or [])


# --- what the adapter declares ----------------------------------------------------


def test_the_adapter_claims_tables_and_nothing_else() -> None:
    """A migration has no summary, no authentication and no authorization, and the index
    has to say that rather than show empty cells."""
    assert ADAPTER.capabilities == frozenset({Capability.READS, Capability.WRITES})
    assert ADAPTER.extensions == (".sql",)


def test_no_tree_sitter_grammar_is_needed() -> None:
    """The file is the statement. Requiring a grammar would make every .sql file in a
    repository unanalyzable on a machine that has sqlglot but no compiler toolchain."""
    result = analyze("report.sql")
    assert result.unknown_reason is None


# --- reading statements -----------------------------------------------------------


def test_from_and_join_are_reads() -> None:
    assert values(analyze("report.sql"), Capability.READS) == ["customers", "orders"]


def test_create_table_is_a_write() -> None:
    """Filing a migration under 'reads' would put the one file that defines a table in
    the wrong half of the reverse index."""
    result = analyze("schema.sql")
    assert "orders" in values(result, Capability.WRITES)
    assert "customers" in values(result, Capability.WRITES)


def test_a_view_writes_its_own_name_and_reads_what_it_selects_from() -> None:
    result = analyze("schema.sql")
    assert "search_index" in values(result, Capability.WRITES)
    assert "orders" in values(result, Capability.READS)


def test_alter_truncate_and_drop_are_writes() -> None:
    result = analyze("migrate_audit.sql")
    assert "audit_log" in values(result, Capability.WRITES)
    assert "search_index" in values(result, Capability.WRITES)


def test_the_select_inside_an_insert_is_still_a_read() -> None:
    assert "audit_log" in values(analyze("migrate_audit.sql"), Capability.READS)


def test_a_file_of_comments_touches_nothing_and_reports_no_finding() -> None:
    """It must not be reported as a statement nobody could read either."""
    result = analyze("notes.sql")
    assert values(result, Capability.READS) == []
    assert result.unresolved == []


# --- what could not be read -------------------------------------------------------


def test_one_unreadable_statement_does_not_cost_the_tables_of_the_others() -> None:
    result = analyze("salvage.sql")
    assert "orders" in values(result, Capability.READS)
    assert "audit_log" in values(result, Capability.WRITES)
    assert SQL_UNREADABLE in codes(result)


def test_a_statement_read_only_as_an_opaque_command_is_counted() -> None:
    """sqlglot accepts syntax it does not model as a command, which holds no tables. Left
    alone, a file of vendor SQL would appear in the index as a file touching nothing."""
    result = analyze("vendor.sql")
    assert SQL_UNSUPPORTED in codes(result)
    assert values(result, Capability.READS) == ["customers"]


def test_no_reason_code_is_ever_recorded_without_a_detail() -> None:
    for rel in ("salvage.sql", "vendor.sql"):
        for item in analyze(rel).unresolved:
            assert item.detail.strip(), f"{rel}: {item.code} carries no detail"


# --- the schema snapshot ----------------------------------------------------------


def test_a_table_missing_from_the_snapshot_is_reported() -> None:
    schema = frozenset({"orders", "customers", "search_index"})
    result = analyze("migrate_audit.sql", schema=schema)
    assert TABLE_NOT_IN_SCHEMA in codes(result)


# --- end to end through the core --------------------------------------------------

REPO_CONFIG = """
include:
  - '**/*.sql'
"""


@pytest.fixture
def sql_repo(tmp_path: Path) -> Path:
    shutil.copytree(SQL_FIXTURES, tmp_path / "src")
    (tmp_path / ".omitnix.yaml").write_text(REPO_CONFIG, encoding="utf-8")
    return tmp_path


def test_the_counting_invariant_holds_over_a_sql_repository(sql_repo: Path) -> None:
    report = build_report(load_config(sql_repo))
    assert report.coverage.holds
    assert report.coverage.unknown == 0


def test_the_reverse_index_names_the_migration_that_defines_a_table(sql_repo: Path) -> None:
    report = build_report(load_config(sql_repo))
    orders = next(table for table in report.tables if table.name == "orders")
    assert "src/schema.sql" in orders.written_by


def test_the_summary_column_is_out_of_scope_not_empty(sql_repo: Path) -> None:
    record = build_report(load_config(sql_repo)).file("src/report.sql")
    assert record.status is Status.ANALYZED
    assert record.fields[Capability.SUMMARY].state is FieldState.OUT_OF_SCOPE
    assert record.fields[Capability.AUTHORIZATION].state is FieldState.OUT_OF_SCOPE
