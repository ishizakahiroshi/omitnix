"""Check the synthetic corpus against the pinned repository SQL reader."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from rewrite.sqlbehavior import make_cases as corpus

HERE = Path(__file__).resolve().parent
REGENERATE = "python rewrite/sqlbehavior/make_cases.py"
EXPECTED_CATEGORIES = frozenset(
    """
    alter_add_column
    alter_change
    alter_constraint
    alter_drop_column
    alter_engine
    alter_modify
    alter_owner
    alter_rename
    alter_rls
    alter_trigger
    analyze
    column_fragment
    comment_on
    create_extension
    create_index
    create_policy
    create_role
    create_schema
    create_sequence
    create_table
    create_trigger
    create_type
    create_view
    deallocate
    delete
    drop
    dynamic_table
    execute
    explain
    fullwidth
    grant_all_tables
    grant_function
    grant_named_function
    grant_schema
    grant_table
    insert
    joins
    leading_comments
    lock
    multistatement
    mysql_backticks
    mysql_limit
    mysql_multi_update
    mysql_on_duplicate
    near_blank
    placeholders
    plpgsql_assignment
    postgres_cast
    postgres_for_update
    postgres_interval
    postgres_on_conflict
    postgres_returning
    prepare
    procedural_block
    prose
    return_new
    revoke_all_tables
    revoke_function
    revoke_named_function
    revoke_schema
    revoke_table
    select
    sqlite_ignore
    subquery
    truncate
    truncated_insert
    unclosed_parenthesis
    union
    update
    vacuum
    with
    """.split()
)
CASE_FIELDS = (
    "id", "category", "sql", "reads", "writes",
    "parsed", "select_star", "dynamic_table", "unsupported",
)


@pytest.fixture(scope="module")
def recorded() -> dict:
    path = HERE / "cases.json"
    assert path.is_file(), (
        "The corpus has not been recorded by read_sql. "
        f"Install requirements.txt, then run: {REGENERATE}"
    )
    return json.loads(path.read_bytes())


def test_input_count_ids_and_category_coverage() -> None:
    cases = corpus.inputs()
    # This is a definition count, never a prediction of parser successes.
    assert len(cases) == 534
    assert {case["category"] for case in cases} == EXPECTED_CATEGORIES
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)
    assert len({(case["category"], case["sql"]) for case in cases}) == len(cases)
    assert cases == corpus.inputs()


def test_header_and_exact_input_order(recorded: dict) -> None:
    assert list(recorded) == (
        ["format_version", "sqlglot_version", "reference", "case_count", "cases"]
    )
    assert recorded["format_version"] == 1
    assert recorded["sqlglot_version"] == "30.18.0"
    assert recorded["reference"] == {
        "commit": "9311c9c8334ed74808e374aecf0cb2fb13534307",
        "source": "omitnix/adapters/_sql.py",
        "git_blob": "8b43f832505826518bc68782ee6065db20212e32",
        "entry_point": "read_sql",
    }
    cases = recorded["cases"]
    assert recorded["case_count"] == len(cases) == 534
    assert [
        {key: case[key] for key in ("id", "category", "sql")} for case in cases
    ] == corpus.inputs()
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["category"] for case in cases} == EXPECTED_CATEGORIES


def test_result_types_sorted_arrays_and_no_omitted_fields(recorded: dict) -> None:
    for case in recorded["cases"]:
        assert tuple(case) == CASE_FIELDS, case["id"]
        for key in ("reads", "writes"):
            assert isinstance(case[key], list), case["id"]
            assert all(isinstance(name, str) for name in case[key]), case["id"]
            assert case[key] == sorted(set(case[key])), case["id"]
        for key in ("parsed", "select_star", "dynamic_table"):
            assert type(case[key]) is bool, case["id"]
        assert type(case["unsupported"]) is int, case["id"]
        assert case["unsupported"] >= 0, case["id"]


def test_recorded_json_has_canonical_bytes(recorded: dict) -> None:
    assert (HERE / "cases.json").read_bytes() == corpus.json_bytes(recorded)


def test_regeneration_is_byte_identical(recorded: dict, tmp_path: Path) -> None:
    # Execute the real CLI in a separate process; never rewrite the committed fixture.
    subprocess.run(
        [
            sys.executable, str(HERE / "make_cases.py"),
            "--output-dir", str(tmp_path),
        ],
        cwd=corpus.ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    for name in ("cases.json", "README.md"):
        assert (tmp_path / name).read_bytes() == (HERE / name).read_bytes(), name
    assert json.loads((tmp_path / "cases.json").read_bytes()) == recorded


def test_each_row_comes_from_exactly_one_reader_call(
    recorded: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = corpus.reference.read_sql
    calls = []

    def observed(sql: str):
        calls.append(sql)
        return original(sql)

    monkeypatch.setattr(corpus.reference, "read_sql", observed)
    assert corpus.build_document() == recorded
    assert calls == [case["sql"] for case in corpus.inputs()]


def test_readme_summary_is_derived_from_results(recorded: dict) -> None:
    cases = recorded["cases"]
    summary = corpus.category_stats(cases)
    assert [row["category"] for row in summary] == sorted(EXPECTED_CATEGORIES)
    assert sum(row["n"] for row in summary) == len(cases)
    for row in summary:
        group = [case for case in cases if case["category"] == row["category"]]
        assert row["parsed_true"] == sum(case["parsed"] for case in group)
        assert row["parsed_false"] == sum(not case["parsed"] for case in group)
        assert row["parsed_true"] + row["parsed_false"] == row["n"]
        assert row["unsupported_ge_1"] == sum(case["unsupported"] >= 1 for case in group)
        assert row["nonempty_reads"] == sum(bool(case["reads"]) for case in group)
        assert row["nonempty_writes"] == sum(bool(case["writes"]) for case in group)
    assert len(corpus.empirical_notes(cases)) == 16
    assert (HERE / "README.md").read_bytes() == corpus.render_readme(recorded)


def test_different_sqlglot_version_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(corpus, "version", lambda _: "0.0.0")
    with pytest.raises(RuntimeError, match="Expected sqlglot 30.18.0"):
        corpus.build_document()


def test_different_reference_source_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(corpus, "REFERENCE_BLOB", "0" * 40)
    with pytest.raises(RuntimeError, match="differs from the recorded reference"):
        corpus.build_document()


def test_check_missing_artifacts_fails_without_writing(tmp_path: Path) -> None:
    assert corpus.main(["--output-dir", str(tmp_path), "--check"]) == 1
    assert not list(tmp_path.iterdir())


def test_reader_exception_is_not_converted_to_an_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(sql: str):
        raise ValueError("synthetic reader failure")

    monkeypatch.setattr(corpus.reference, "read_sql", refused)
    with pytest.raises(ValueError, match="synthetic reader failure"):
        corpus.main(["--output-dir", str(tmp_path)])
    assert not list(tmp_path.iterdir())
