"""The counting invariant and the three field states, checked on a synthetic repository.

Covers what the core promises regardless of language: every discovered file lands in
exactly one of analyzed / unresolved / unknown, an adapter that cannot handle a file
produces a counted record rather than a silence, and a capability an adapter never
declared is never reported as a missing value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omitnix.analyze import build_report
from omitnix.config import Config, load_config
from omitnix.errors import AdapterContractError, ConfigError
from omitnix.model import Capability, FieldState, Status

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
    assert coverage.discovered == coverage.analyzed + coverage.unresolved + coverage.unknown


def test_default_exclusions_keep_vendor_out(tmp_path: Path, with_test_adapters: None) -> None:
    config = sample_repo(tmp_path)
    report = build_report(config)
    paths = [record.path for record in report.files]
    assert "api/orders_list.flow" in paths
    assert not any(path.startswith("vendor/") for path in paths)


def test_the_configuration_file_itself_is_unknown(tmp_path: Path, with_test_adapters: None) -> None:
    """No adapter claims .yaml, so it is counted, not skipped. That is the point."""
    config = sample_repo(tmp_path)
    report = build_report(config)
    record = report.file(".omitnix.yaml")
    assert record is not None
    assert record.status is Status.UNKNOWN
    assert "'.yaml'" in (record.unknown_reason or "")
    assert report.coverage.unknown >= 1


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
    assert "ValueError" in (record.unknown_reason or "")
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
    assert "UTF-8" in (record.unknown_reason or "")


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
