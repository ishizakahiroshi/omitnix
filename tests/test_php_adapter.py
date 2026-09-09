"""The PHP adapter.

Every fixture under ``tests/fixtures/php`` is invented. The vocabulary (orders,
customers, search_index, audit_log, require_session, apply_visibility_filter) is the
fictional schema the rest of this repository already uses.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omitnix.adapters._sql import PLACEHOLDER, looks_like_sql, read_sql
from omitnix.adapters._treesitter import GrammarUnavailable
from omitnix.adapters.base import AnalysisRequest, AnalysisResult
from omitnix.adapters.php import (
    ADAPTER,
    DYNAMIC_SQL,
    DYNAMIC_TABLE_NAME,
    INDIRECT_CALL_DEPTH,
    SELECT_STAR,
    SQL_UNREADABLE,
    TABLE_NOT_IN_SCHEMA,
)
from omitnix.analyze import build_report
from omitnix.config import load_config
from omitnix.model import Capability, FieldState, Status

from .conftest import FIXTURES

PHP_FIXTURES = FIXTURES / "php"

AUTHN = ("require_session",)
AUTHZ = ("apply_visibility_filter",)

pytest.importorskip("tree_sitter", reason="the PHP adapter needs the tree-sitter binding")
pytest.importorskip("tree_sitter_php", reason="the PHP adapter needs the PHP grammar")
pytest.importorskip("sqlglot", reason="the PHP adapter reads SQL with sqlglot")


def analyze(
    rel: str,
    *,
    authn: tuple[str, ...] = AUTHN,
    authz: tuple[str, ...] = AUTHZ,
    schema: frozenset[str] = frozenset(),
    in_scope: frozenset[str] | None = None,
    root: Path = PHP_FIXTURES,
) -> AnalysisResult:
    absolute = root / rel
    return ADAPTER.analyze(
        AnalysisRequest(
            path=rel,
            absolute_path=absolute,
            text=absolute.read_text(encoding="utf-8"),
            authentication_functions=authn,
            authorization_functions=authz,
            schema_tables=schema,
            in_scope=in_scope,
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
    assert ADAPTER.extensions == (".php", ".phtml")


# --- summary ----------------------------------------------------------------------


def test_the_summary_is_the_first_description_line_of_the_docblock() -> None:
    result = analyze("orders_list.php")
    assert result.values[Capability.SUMMARY] == "List orders for the signed-in customer."


def test_annotation_lines_are_not_mistaken_for_the_summary() -> None:
    result = analyze("orders_list.php")
    assert "@param" not in result.values[Capability.SUMMARY]


def test_a_file_without_a_docblock_reports_no_summary_rather_than_inventing_one() -> None:
    """Left empty so the core can say 'none observed'. A placeholder string here would
    claim a summary was extracted."""
    result = analyze("notes.php")
    assert result.values[Capability.SUMMARY] == ""


# --- authentication and authorization ---------------------------------------------


def test_configured_authentication_and_authorization_calls_are_reported() -> None:
    result = analyze("orders_list.php")
    assert values(result, Capability.AUTHENTICATION) == ["require_session"]
    assert values(result, Capability.AUTHORIZATION) == ["apply_visibility_filter"]


def test_nothing_is_reported_as_authorization_when_the_repository_named_nothing() -> None:
    """Without configuration the adapter has no way to know which call is a check, and
    guessing would put a name in the authz column that nobody vouched for."""
    result = analyze("orders_list.php", authn=(), authz=())
    assert values(result, Capability.AUTHENTICATION) == []
    assert values(result, Capability.AUTHORIZATION) == []


def test_a_file_with_no_check_reports_none_rather_than_failing() -> None:
    result = analyze("reindex.php")
    assert values(result, Capability.AUTHENTICATION) == []
    assert values(result, Capability.AUTHORIZATION) == []
    assert result.unknown_reason is None


# --- reading SQL ------------------------------------------------------------------


def test_from_and_join_are_reads() -> None:
    result = analyze("common/queries.php")
    assert values(result, Capability.READS) == ["customers", "orders"]


def test_insert_target_is_a_write_and_its_select_is_a_read() -> None:
    result = analyze("reindex.php")
    assert values(result, Capability.WRITES) == ["search_index"]
    assert values(result, Capability.READS) == ["orders"]


def test_delete_is_a_write() -> None:
    result = analyze("common/queries.php")
    assert "audit_log" in values(result, Capability.WRITES)


def test_prose_that_opens_like_sql_is_not_reported_as_a_table_or_a_finding() -> None:
    """'Update your profile from the settings page' opens with a DML keyword and carries
    a clause keyword. Reporting it would bury the real findings under noise."""
    result = analyze("notes.php")
    assert values(result, Capability.READS) == []
    assert values(result, Capability.WRITES) == []
    assert result.unresolved == []


# --- following exactly one hop ----------------------------------------------------


def test_sql_in_a_required_file_is_found_through_the_call() -> None:
    """The endpoint holds no SQL of its own. Without the hop its table columns are empty,
    and an empty column is read as 'this file touches no table'."""
    result = analyze("orders_list.php")
    assert values(result, Capability.READS) == ["customers", "orders"]


def test_a_function_the_file_never_calls_is_not_attributed_to_it() -> None:
    """purge_audit_log() sits in the same required file and is never called here."""
    result = analyze("orders_list.php")
    assert "audit_log" not in values(result, Capability.WRITES)
    assert "audit_log" not in values(result, Capability.READS)


def test_a_second_hop_is_counted_rather_than_followed() -> None:
    """order_totals() is one hop and is followed. build_totals_sql(), which it calls, is
    two hops: its table must not appear, and the skipped hop must be counted."""
    result = analyze("summary.php")
    assert values(result, Capability.READS) == []
    assert INDIRECT_CALL_DEPTH in codes(result)
    detail = " ".join(item.detail for item in result.unresolved)
    assert "build_totals_sql" in detail


def test_a_skipped_hop_names_the_file_it_was_found_in() -> None:
    """The reader's next question is "where", and this tool builds no call graph.

    Measured against a real repository on 2026-09-08: an endpoint holds no SQL, requires
    a shared query file, and calls a function there that only forwards to another one.
    Four of that file's seven findings point at the query file by name, which turns
    "somewhere two hops away" into one jump. Following the hop instead would mean
    chasing a chain three deep and losing the boundary this tool exists to keep visible.
    """
    result = analyze("summary.php")
    detail = " ".join(item.detail for item in result.unresolved)
    assert "common/reports.php" in detail


def test_an_include_path_built_at_run_time_is_counted() -> None:
    result = analyze("router.php")
    assert INDIRECT_CALL_DEPTH in codes(result)
    assert "run time" in " ".join(item.detail for item in result.unresolved)


# --- the hop stops at the edge of the scan ----------------------------------------


def test_a_required_file_outside_the_scan_is_refused_rather_than_read() -> None:
    """The tables behind the hop are real, and the file holding them is not this run's
    to read. Reporting them anyway would make the index depend on what sits on the disk
    rather than on what the repository contains."""
    result = analyze("orders_list.php", in_scope=frozenset({"orders_list.php"}))
    assert values(result, Capability.READS) == []
    assert INDIRECT_CALL_DEPTH in codes(result)
    detail = " ".join(item.detail for item in result.unresolved)
    assert "common/queries.php" in detail
    assert "outside this scan" in detail


def test_a_required_file_inside_the_scan_is_still_followed() -> None:
    """The refusal is about the boundary, not about hops. Inside it, nothing changes."""
    result = analyze(
        "orders_list.php",
        in_scope=frozenset({"orders_list.php", "common/queries.php"}),
    )
    assert values(result, Capability.READS) == ["customers", "orders"]


def test_the_refusal_reads_the_same_whether_or_not_the_file_is_on_the_disk(
    tmp_path: Path,
) -> None:
    """The defect this rule exists for, stated as an assertion.

    Measured on 2026-09-09 against a real repository: a deploy script generates a version
    file that the repository deliberately does not track. Every developer's checkout has
    it; no CI checkout does. The adapter read it off the disk, so the index generated by
    hand and the index regenerated in CI disagreed on fifteen files and two coverage
    counts, and no amount of regenerating could make them agree.

    Deciding out of scope before touching the disk is what fixes it -- but only if the
    reason is identical in both worlds. A reason that says "not found" here and "outside
    this scan" there would put the machine back into the generated document.
    """
    scope = frozenset({"orders_list.php"})
    present = analyze("orders_list.php", in_scope=scope)

    absent_root = tmp_path / "checkout"
    absent_root.mkdir()
    shutil.copy(PHP_FIXTURES / "orders_list.php", absent_root / "orders_list.php")
    assert not (absent_root / "common" / "queries.php").exists()
    absent = analyze("orders_list.php", in_scope=scope, root=absent_root)

    assert [(item.code, item.detail) for item in present.unresolved] == [
        (item.code, item.detail) for item in absent.unresolved
    ]


def test_a_reason_never_carries_the_absolute_path_of_the_checkout() -> None:
    """``__DIR__`` expands to wherever the checkout happens to live. A detail built from
    it records the machine, and the shortening applied to long details then eats the file
    name -- the one part the reader needs."""
    result = analyze("orders_list.php", in_scope=frozenset({"orders_list.php"}))
    detail = " ".join(item.detail for item in result.unresolved)
    assert PHP_FIXTURES.as_posix() not in detail
    assert "..." not in detail


# --- what could not be read -------------------------------------------------------


def test_a_concatenated_statement_is_never_silently_empty() -> None:
    result = analyze("export.php")
    assert DYNAMIC_SQL in codes(result)
    assert DYNAMIC_TABLE_NAME in codes(result)
    assert values(result, Capability.READS) == []
    # The empty list above is only honest because the reasons above are attached to it.
    assert result.unresolved


def test_select_star_keeps_the_table_and_flags_only_the_columns() -> None:
    result = analyze("audit.php")
    assert "audit_log" in values(result, Capability.READS)
    assert SELECT_STAR in codes(result)


def test_an_interpolated_statement_is_flagged_but_still_yields_its_tables() -> None:
    result = analyze("audit.php")
    assert DYNAMIC_SQL in codes(result)
    assert "audit_log" in values(result, Capability.WRITES)


def test_a_statement_the_parser_cannot_read_is_reported_not_skipped() -> None:
    """A file whose only query is unreadable must not look like a file that queries
    nothing."""
    result = analyze("legacy_report.php")
    assert SQL_UNREADABLE in codes(result)
    assert values(result, Capability.READS) == []


def test_no_reason_code_is_ever_recorded_without_a_detail() -> None:
    for rel in ("export.php", "audit.php", "summary.php", "router.php", "legacy_report.php"):
        for item in analyze(rel).unresolved:
            assert item.detail.strip(), f"{rel}: {item.code} carries no detail"


# --- the schema snapshot ----------------------------------------------------------


def test_a_table_missing_from_the_snapshot_is_reported() -> None:
    """audit_log is absent from the snapshot, so the reference is either a typo or code
    left behind after the table was dropped."""
    schema = frozenset({"orders", "customers", "search_index"})
    result = analyze("audit.php", schema=schema)
    assert TABLE_NOT_IN_SCHEMA in codes(result)
    assert "audit_log" in " ".join(item.detail for item in result.unresolved)


def test_nothing_is_reported_against_a_schema_that_was_not_configured() -> None:
    result = analyze("audit.php")
    assert TABLE_NOT_IN_SCHEMA not in codes(result)


def test_a_table_present_in_the_snapshot_is_not_reported() -> None:
    schema = frozenset({"orders", "customers", "search_index"})
    result = analyze("reindex.php", schema=schema)
    assert TABLE_NOT_IN_SCHEMA not in codes(result)


# --- files the adapter cannot read ------------------------------------------------


def test_a_file_that_does_not_parse_is_unknown_rather_than_partially_reported() -> None:
    result = analyze("broken.php")
    assert result.unknown_reason is not None
    assert "syntax error" in result.unknown_reason


def test_a_missing_grammar_becomes_an_unknown_record_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing parser must still leave the file counted and the run failing. Skipping
    it quietly is the one outcome this tool exists to prevent."""

    def unavailable(*_args: str) -> None:
        raise GrammarUnavailable("the php grammar is not installed")

    monkeypatch.setattr("omitnix.adapters.php.load_grammar", unavailable)
    result = analyze("orders_list.php")
    assert result.unknown_reason is not None
    assert "not installed" in result.unknown_reason


# --- the SQL reader on its own ----------------------------------------------------


def test_a_common_table_expression_is_not_a_table() -> None:
    reading = read_sql("WITH recent AS (SELECT id FROM orders) SELECT id FROM recent")
    assert reading.reads == ("orders",)


def test_a_run_time_table_name_is_reported_rather_than_recorded_as_a_table() -> None:
    reading = read_sql(f"DELETE FROM {PLACEHOLDER} WHERE id = 1")
    assert reading.dynamic_table is True
    assert reading.writes == ()


def test_backtick_quoting_is_read() -> None:
    assert read_sql("SELECT id FROM `orders`").reads == ("orders",)


def test_a_candidate_needs_a_keyword_and_that_keyword_s_own_clause() -> None:
    assert looks_like_sql("SELECT id FROM orders")
    assert not looks_like_sql("Update your profile from the settings page")
    assert not looks_like_sql("Delete an order from the list")
    assert not looks_like_sql("Deleted")


def test_lower_case_prose_that_fits_the_shape_still_needs_evidence_of_a_query() -> None:
    """sqlglot reads 'shelf' as a table out of the first string. A phantom row in the
    reverse index would be a fact the tool invented."""
    assert not looks_like_sql("select the item from the shelf")
    assert looks_like_sql("select id from orders where id = ?")


# --- end to end through the core --------------------------------------------------

REPO_CONFIG = """
include:
  - '**/*.php'
authentication_functions:
  - require_session
authorization_functions:
  - apply_visibility_filter
"""


@pytest.fixture
def php_repo(tmp_path: Path) -> Path:
    shutil.copytree(PHP_FIXTURES, tmp_path / "src")
    (tmp_path / ".omitnix.yaml").write_text(REPO_CONFIG, encoding="utf-8")
    return tmp_path


def test_the_counting_invariant_holds_over_a_php_repository(php_repo: Path) -> None:
    report = build_report(load_config(php_repo))
    assert report.coverage.holds
    assert report.coverage.discovered == len(report.files)
    assert report.coverage.unknown == 1  # broken.php, and it must fail the run


def test_the_table_reverse_index_names_the_php_files(php_repo: Path) -> None:
    report = build_report(load_config(php_repo))
    orders = next(table for table in report.tables if table.name == "orders")
    assert "src/orders_list.php" in orders.read_by
    search_index = next(table for table in report.tables if table.name == "search_index")
    assert search_index.written_by == ("src/reindex.php",)
    assert search_index.read_by == ()


def test_the_core_holds_an_adapter_to_the_files_the_run_selected(php_repo: Path) -> None:
    """The adapter's own tests can pass with the wire missing: the core has to hand the
    selection down. Here the required file is excluded from the run but still sits on the
    disk, which is exactly the shape of an untracked or generated file."""
    (php_repo / ".omitnix.yaml").write_text(
        REPO_CONFIG + "exclude:\n  - 'src/common/**'\n", encoding="utf-8"
    )
    assert (php_repo / "src" / "common" / "queries.php").is_file()

    report = build_report(load_config(php_repo))
    record = report.file("src/orders_list.php")
    assert record.fields[Capability.READS].value == []
    detail = " ".join(item.detail for item in record.unresolved)
    assert "src/common/queries.php" in detail
    assert "outside this scan" in detail


def test_a_file_with_a_finding_is_unresolved_and_one_without_is_analyzed(
    php_repo: Path,
) -> None:
    report = build_report(load_config(php_repo))
    assert report.file("src/reindex.php").status is Status.ANALYZED
    assert report.file("src/export.php").status is Status.UNRESOLVED


def test_the_screen_to_api_column_is_out_of_scope_not_empty(php_repo: Path) -> None:
    report = build_report(load_config(php_repo))
    record = report.file("src/reindex.php")
    assert record.fields[Capability.SCREEN_TO_API].state is FieldState.OUT_OF_SCOPE
    assert record.fields[Capability.AUTHORIZATION].state is FieldState.NONE_OBSERVED


def test_a_declare_statement_does_not_hide_the_docblock_after_it() -> None:
    """Found by applying the tool to a real repository, not by reading the code.

    `declare(strict_types=1);` sits between the opening tag and the docblock in modern
    PHP. Until 2026-09-08 that ended the leading comment block, so the summary was never
    reached: across 364 files of one real repository the summary column was empty in
    every single one. A column that is empty everywhere is a column people learn to skip.
    """
    result = analyze("declared.php")
    assert result.values[Capability.SUMMARY] == "List orders for the signed-in customer."
