"""The counting invariant and the four field states, checked on a synthetic repository.

Covers what the core promises regardless of language: every discovered file lands in
exactly one of analyzed / unresolved / unknown / unclaimed, an adapter that cannot handle
a file produces a counted record rather than a silence, a capability an adapter never
declared is never reported as a missing value, and a check the repository never configured
is never reported as a check that was made.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omitnix.analyze import assemble_report, build_report
from omitnix.config import Config, load_config, unconfigured_capabilities
from omitnix.errors import AdapterContractError, CompletenessError, ConfigError
from omitnix.model import (
    CONFIGURED_BY,
    Capability,
    FieldState,
    FileRecord,
    Status,
    TableGaps,
)
from omitnix.registry import build_adapter_set

from .conftest import (
    BAD_ADAPTER_FIXTURES,
    EXPORT_FLOW,
    ORDERS_FLOW,
    PLAIN_NOTE,
    REINDEX_FLOW,
    adapter_path,
    write_repo,
)

CONFIG_YAML = """
authentication_functions:
  - require_session
authorization_functions:
  - apply_visibility_filter
"""


def sample_repo(tmp_path: Path, extra: dict[str, str] | None = None) -> Config:
    files = {
        ".omitnix.yaml": CONFIG_YAML,
        "api/orders_list.flow": ORDERS_FLOW,
        "api/orders_export.flow": EXPORT_FLOW,
        "batch/reindex.flow": REINDEX_FLOW,
        "docs/RELEASE.note": PLAIN_NOTE,
        "vendor/library/ignored.flow": ORDERS_FLOW,
    }
    files.update(extra or {})
    write_repo(tmp_path, files)
    return load_config(tmp_path)


def test_counting_invariant_holds(tmp_path: Path, with_test_adapters: None) -> None:
    config = sample_repo(tmp_path)
    report = build_report(config)
    coverage = report.coverage
    assert coverage.holds
    assert coverage.discovered == (
        coverage.analyzed + coverage.unresolved + coverage.unknown + coverage.unclaimed
    )


def test_a_status_the_count_does_not_recognize_ends_the_run(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The positive control for the invariant: it has to be able to fail.

    A record is fabricated with a status that is none of the four, which is what a fifth
    status added without a slot in ``Coverage`` would look like. The run must die rather
    than report a total that quietly leaves that file out -- a smaller, tidier number
    describing fewer files than the repository holds is the failure this tool is for.
    """
    config = sample_repo(tmp_path)
    adapter_set = build_adapter_set(config.adapters)
    records = [
        FileRecord(path="api/orders_list.flow", adapter="flow", status=Status.ANALYZED),
        FileRecord(path="api/invented.flow", adapter="flow", status="invented"),  # type: ignore[arg-type]
    ]

    with pytest.raises(CompletenessError, match="counting invariant broke"):
        assemble_report(config, records, adapter_set)


def test_default_exclusions_keep_vendor_out(tmp_path: Path, with_test_adapters: None) -> None:
    config = sample_repo(tmp_path)
    report = build_report(config)
    paths = [record.path for record in report.files]
    assert "api/orders_list.flow" in paths
    assert not any(path.startswith("vendor/") for path in paths)


def test_the_configuration_file_itself_is_unclaimed(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """No adapter claims .yaml, so it is counted, not skipped. That is the point.

    Counted as ``unclaimed`` rather than ``unknown``: nothing tried to read it, so nothing
    failed. What must not happen is that it disappears from the totals.
    """
    config = sample_repo(tmp_path)
    report = build_report(config)
    record = report.file(".omitnix.yaml")
    assert record is not None
    assert record.status is Status.UNCLAIMED
    assert "'.yaml'" in (record.reason or "")
    assert report.coverage.unclaimed >= 1
    assert report.coverage.unknown == 0
    assert report.unclaimed_extensions[".yaml"] == 1


def test_a_file_an_adapter_claimed_and_could_not_read_is_unknown_not_unclaimed(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The other half of the pair, and the whole reason the two are separate.

    ``.flow`` has an adapter. This file is one it cannot read, which is somebody's defect
    -- and it has to stay findable rather than sit in a list of ninety-five ``.md`` files.
    """
    config = sample_repo(tmp_path, {"api/weird.flow": "unparsable: yes\n"})
    report = build_report(config)

    assert report.coverage.unknown == 1
    assert [record.path for record in report.unknown_files] == ["api/weird.flow"]
    # The .yaml and .note files discovered alongside it are in the other bucket entirely.
    assert ".flow" not in report.unclaimed_extensions


def test_unresolved_carries_a_reason(tmp_path: Path, with_test_adapters: None) -> None:
    config = sample_repo(tmp_path)
    report = build_report(config)
    record = report.file("api/orders_export.flow")
    assert record is not None
    assert record.status is Status.UNRESOLVED
    assert record.unresolved[0].code == "dynamic_sql"
    assert record.unresolved[0].detail


def test_adapter_declaring_itself_unable_becomes_unknown(
    tmp_path: Path, with_test_adapters: None
) -> None:
    config = sample_repo(tmp_path, {"api/weird.flow": "unparsable: yes\n"})
    report = build_report(config)
    record = report.file("api/weird.flow")
    assert record is not None
    assert record.status is Status.UNKNOWN
    assert record.adapter == "flow"


def test_adapter_crash_becomes_unknown_not_a_lost_file(
    tmp_path: Path, with_test_adapters: None
) -> None:
    config = sample_repo(tmp_path, {"api/boom.flow": "raise: yes\n"})
    report = build_report(config)
    record = report.file("api/boom.flow")
    assert record is not None
    assert record.status is Status.UNKNOWN
    assert "ValueError" in (record.reason or "")
    assert report.coverage.holds


def test_binary_file_is_unknown_rather_than_skipped(
    tmp_path: Path, with_test_adapters: None
) -> None:
    config = sample_repo(tmp_path)
    (tmp_path / "api" / "blob.flow").write_bytes(b"\xff\xfe\x00binary")
    report = build_report(config)
    record = report.file("api/blob.flow")
    assert record is not None
    assert record.status is Status.UNKNOWN
    assert "UTF-8" in (record.reason or "")


def test_out_of_scope_and_none_observed_are_different_states(
    tmp_path: Path, with_test_adapters: None
) -> None:
    config = sample_repo(tmp_path)
    report = build_report(config)

    note = report.file("docs/RELEASE.note")
    assert note is not None
    # The note adapter declares summary only.
    assert note.fields[Capability.SUMMARY].state is FieldState.VALUE
    assert note.fields[Capability.AUTHORIZATION].state is FieldState.OUT_OF_SCOPE
    assert note.fields[Capability.READS].state is FieldState.OUT_OF_SCOPE

    reindex = report.file("batch/reindex.flow")
    assert reindex is not None
    # The flow adapter declares authorization and found none. Different thing entirely.
    assert reindex.fields[Capability.AUTHORIZATION].state is FieldState.NONE_OBSERVED
    assert reindex.fields[Capability.WRITES].state is FieldState.VALUE


def test_a_check_nobody_configured_is_not_reported_as_a_check_that_found_nothing(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The state says nothing was looked for, because nothing was.

    A repository with no ``.omitnix.yaml`` hands the adapter an empty list of
    authorization functions. Reporting the empty result as ``none_observed`` says the
    file was checked and holds no authorization call -- for every file at once, which
    reads as a finding about the repository. Measured 2026-09-11: all 618 files of one.
    """
    write_repo(tmp_path, {"batch/reindex.flow": REINDEX_FLOW})
    report = build_report(load_config(tmp_path))
    record = report.file("batch/reindex.flow")
    assert record is not None

    assert record.fields[Capability.AUTHORIZATION].state is FieldState.NOT_CONFIGURED
    assert record.fields[Capability.AUTHENTICATION].state is FieldState.NOT_CONFIGURED
    # Nothing configures which tables count, so an empty list there is still an
    # observation and keeps the state it always had.
    assert record.fields[Capability.READS].state is FieldState.VALUE


def test_a_configured_check_that_finds_nothing_is_still_none_observed(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The other half of the pair: naming the function is what makes the empty an answer."""
    config = sample_repo(tmp_path)
    report = build_report(config)
    record = report.file("batch/reindex.flow")
    assert record is not None
    assert record.fields[Capability.AUTHORIZATION].state is FieldState.NONE_OBSERVED
    assert record.fields[Capability.AUTHORIZATION].value == []


def test_which_checks_can_be_unconfigured_comes_from_one_table(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """Driven from ``CONFIGURED_BY`` rather than from a pair written out here.

    A test that named authentication and authorization itself would keep passing if the
    analyzer grew its own second copy of the table, which is the defect this is for: the
    gate decides from it whether a check can be made at all, and a disagreement between
    the two means the document says a check happened where the gate says it did not.
    """
    for capability, attribute in CONFIGURED_BY.items():
        root = tmp_path / str(capability)
        write_repo(
            root,
            {
                ".omitnix.yaml": f"{attribute}:\n  - some_function\n",
                "batch/reindex.flow": REINDEX_FLOW,
            },
        )
        config = load_config(root)
        assert unconfigured_capabilities(config) == set(CONFIGURED_BY) - {capability}

        record = build_report(config).file("batch/reindex.flow")
        assert record is not None
        assert record.fields[capability].state is FieldState.NONE_OBSERVED
        for other in set(CONFIGURED_BY) - {capability}:
            assert record.fields[other].state is FieldState.NOT_CONFIGURED


def test_configured_function_names_reach_the_adapter(
    tmp_path: Path, with_test_adapters: None
) -> None:
    config = sample_repo(tmp_path)
    report = build_report(config)
    record = report.file("api/orders_list.flow")
    assert record is not None
    assert record.fields[Capability.AUTHENTICATION].value == ["require_session"]
    assert record.fields[Capability.AUTHORIZATION].value == ["apply_visibility_filter"]


def test_reverse_index(tmp_path: Path, with_test_adapters: None) -> None:
    config = sample_repo(tmp_path)
    report = build_report(config)
    by_name = {table.name: table for table in report.tables}
    assert by_name["orders"].read_by == (
        "api/orders_export.flow",
        "api/orders_list.flow",
        "batch/reindex.flow",
    )
    assert by_name["search_index"].written_by == ("batch/reindex.flow",)
    assert by_name["customers"].written_by == ()


def test_a_table_is_marked_where_the_file_touching_it_could_not_be_read_in_full(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """``read_by`` is what was legible, and the mark is what says so.

    ``api/orders_export.flow`` reads ``orders`` and also holds a statement the analyzer
    could not follow, so its entry for ``orders`` is a floor, not a total.
    """
    config = sample_repo(tmp_path)
    by_name = {table.name: table for table in build_report(config).tables}

    assert by_name["orders"].unresolved_in == ("api/orders_export.flow",)
    # Read and written only by files that were read in full: nothing to go and check.
    assert by_name["customers"].unresolved_in == ()
    assert by_name["search_index"].unresolved_in == ()


def test_a_run_with_an_unreadable_statement_says_the_table_list_may_be_short(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The per-table mark cannot reach a table that is missing from the index entirely."""
    report = build_report(sample_repo(tmp_path))

    assert report.table_gaps.files == ("api/orders_export.flow",)
    assert report.table_gaps.unresolved_count == 1
    assert "may be incomplete" in report.table_gaps.note


def test_nothing_is_marked_when_every_statement_was_read(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The control. A mark on every table would be a mark nobody acts on."""
    write_repo(
        tmp_path,
        {"api/orders_list.flow": ORDERS_FLOW, "batch/reindex.flow": REINDEX_FLOW},
    )
    report = build_report(load_config(tmp_path))

    assert report.tables
    assert all(table.unresolved_in == () for table in report.tables)
    assert report.table_gaps == TableGaps()
    assert report.table_gaps.note == ""


def test_a_reason_that_is_not_about_which_tables_were_touched_marks_nothing(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """``select_star`` read the table and not the columns. The table list is complete."""
    write_repo(
        tmp_path,
        {
            "api/wide.flow": (
                "summary: Read everything\n"
                "reads: orders\n"
                "unresolved: select_star / the tables are known, the columns are not\n"
            )
        },
    )
    report = build_report(load_config(tmp_path))

    assert report.file("api/wide.flow").status is Status.UNRESOLVED
    assert report.tables[0].unresolved_in == ()
    assert report.table_gaps == TableGaps()


def test_a_reason_nobody_classified_marks_the_tables_it_might_be_hiding(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """An adapter may invent a code, and an unclassified one is not evidence of safety."""
    write_repo(
        tmp_path,
        {
            "api/odd.flow": (
                "summary: Something new\n"
                "reads: orders\n"
                "unresolved: a_reason_from_a_future_adapter / nobody has classified this\n"
            )
        },
    )
    report = build_report(load_config(tmp_path))

    assert report.tables[0].unresolved_in == ("api/odd.flow",)
    assert report.table_gaps.unresolved_count == 1


def test_an_adapter_that_reports_no_tables_marks_no_table(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """Nothing the note adapter fails to follow can be hiding a table it never reports."""
    write_repo(
        tmp_path,
        {
            "api/orders_list.flow": ORDERS_FLOW,
            "docs/RELEASE.note": PLAIN_NOTE + "unresolved: sql_unreadable / not this one\n",
        },
    )
    report = build_report(load_config(tmp_path))

    assert report.file("docs/RELEASE.note").status is Status.UNRESOLVED
    assert all(table.unresolved_in == () for table in report.tables)
    assert report.table_gaps == TableGaps()


def test_schema_snapshot_tables_appear_even_with_no_reference(
    tmp_path: Path, with_test_adapters: None
) -> None:
    write_repo(
        tmp_path,
        {
            ".omitnix.yaml": CONFIG_YAML + "schema_snapshot: schema.json\n",
            "api/orders_list.flow": ORDERS_FLOW,
            "schema.json": '{"tables": [{"name": "orders"}, {"name": "audit_log"}]}',
        },
    )
    report = build_report(load_config(tmp_path))
    by_name = {table.name: table for table in report.tables}
    assert by_name["audit_log"].observed_nowhere
    assert by_name["audit_log"].in_schema_snapshot
    assert not by_name["orders"].observed_nowhere


def test_missing_schema_snapshot_is_an_error(tmp_path: Path, with_test_adapters: None) -> None:
    write_repo(
        tmp_path,
        {
            ".omitnix.yaml": "schema_snapshot: nowhere.json\n",
            "api/orders_list.flow": ORDERS_FLOW,
        },
    )
    with pytest.raises(ConfigError, match="schema_snapshot not found"):
        build_report(load_config(tmp_path))


def test_partial_run_covers_only_the_given_files(tmp_path: Path, with_test_adapters: None) -> None:
    config = sample_repo(tmp_path)
    report = build_report(config, files=["api/orders_list.flow", "vendor/library/ignored.flow"])
    assert [record.path for record in report.files] == ["api/orders_list.flow"]
    assert report.coverage.discovered == 1
    assert report.coverage.skipped_by_config == 1
    assert report.generated.partial is True


def test_capability_outside_the_declaration_is_an_adapter_defect(tmp_path: Path) -> None:
    write_repo(tmp_path, {"thing.over": "anything"})
    with adapter_path(BAD_ADAPTER_FIXTURES):
        with pytest.raises(AdapterContractError, match="without declaring the capability"):
            build_report(load_config(tmp_path))
