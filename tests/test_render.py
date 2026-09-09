"""What the generated document says, and what it must never say.

A generated document is read later, out of context, by someone -- or something, an AI
assistant reading it as evidence -- who will treat a missing key or an empty value as a
fact. So these tests are about the JSON as much as its structure: a field outside an
adapter's capabilities carries a different ``state`` from one it looked for and did not
find, a file nothing could analyze is not dressed up as either, and no table is ever
called unused.

A Markdown rendering of the same facts used to live in this module and was tested here
too. It was removed (2026-09): a second tool started reading ``index.json`` and writing
the readable document itself, so the four states below are asserted directly against the
JSON now instead of through a rendered table row.
"""

from __future__ import annotations

from pathlib import Path

from omitnix.analyze import build_report
from omitnix.config import load_config
from omitnix.model import Capability, FieldState, Status
from omitnix.render import payload_for_check, render_json, to_payload

from .conftest import ORDERS_FLOW, PLAIN_NOTE, REINDEX_FLOW, write_repo

CONFIG_YAML = """
authentication_functions:
  - require_session
authorization_functions:
  - apply_visibility_filter
schema_snapshot: schema.json
"""


def build(tmp_path: Path):
    write_repo(
        tmp_path,
        {
            ".omitnix.yaml": CONFIG_YAML,
            "api/orders_list.flow": ORDERS_FLOW,
            "batch/reindex.flow": REINDEX_FLOW,
            "docs/RELEASE.note": PLAIN_NOTE,
            "schema.json": '{"tables": [{"name": "orders"}, {"name": "audit_log"}]}',
        },
    )
    return build_report(load_config(tmp_path))


def test_json_round_trips_and_check_ignores_provenance(
    tmp_path: Path, with_test_adapters: None
) -> None:
    report = build(tmp_path)
    payload = to_payload(report)
    assert payload["schema_version"] == 1
    assert payload["coverage"]["discovered"] == len(payload["files"])
    assert "generated" in payload
    assert "generated" not in payload_for_check(payload)
    assert render_json(report).endswith("\n")


def test_field_states_survive_serialisation(tmp_path: Path, with_test_adapters: None) -> None:
    """The three per-field states are distinguishable after a JSON round trip.

    ``out_of_scope`` (the field is outside what this adapter declares -- never a missing
    value), ``none_observed`` (the adapter looked and found nothing -- never "unused"),
    and ``value`` (an ordinary result, even an empty list) must all read differently, or
    "did not look" and "looked and found nothing" collapse into the same JSON shape.
    """
    payload = to_payload(build(tmp_path))
    by_path = {entry["path"]: entry for entry in payload["files"]}

    note = by_path["docs/RELEASE.note"]["fields"]
    assert note["authorization"] == {"state": "out_of_scope"}
    # out_of_scope carries no "value" key at all -- there is nothing to be empty or absent.
    assert "value" not in note["authorization"]

    reindex = by_path["batch/reindex.flow"]["fields"]
    # An empty list is still "the analyzer looked and found none", never a blank cell.
    assert reindex["authorization"] == {"state": "none_observed", "value": []}
    assert reindex["writes"] == {"state": "value", "value": ["search_index"]}


def test_out_of_scope_and_none_observed_are_never_the_same_state(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The distinction the whole project exists for, asserted directly on ``FieldState``."""
    report = build(tmp_path)
    note = report.file("docs/RELEASE.note")
    reindex = report.file("batch/reindex.flow")

    assert note.fields[Capability.AUTHORIZATION].state is FieldState.OUT_OF_SCOPE
    assert reindex.fields[Capability.AUTHORIZATION].state is FieldState.NONE_OBSERVED
    assert FieldState.OUT_OF_SCOPE != FieldState.NONE_OBSERVED


def test_an_unanalyzable_file_carries_no_field_states_at_all(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The fourth state -- "not analyzed" -- is not a ``FieldState`` at all.

    It is the file record's own ``status``. A file nothing could read has no adapter
    output to report a state *for*, so ``fields`` is empty and the reason lives in
    ``unknown_reason`` -- never rendered as if it were an observed, empty value.
    """
    write_repo(tmp_path, {"api/helper.unheardof": "x"})
    report = build_report(load_config(tmp_path))
    record = report.file("api/helper.unheardof")

    assert record.status is Status.UNKNOWN
    assert record.fields == {}
    assert record.unknown_reason is not None
    assert to_payload(report)["files"][0]["fields"] == {}


def test_tables_with_no_reference_are_reported_never_as_unused(
    tmp_path: Path, with_test_adapters: None
) -> None:
    report = build(tmp_path)
    by_name = {table.name: table for table in report.tables}
    audit_log = by_name["audit_log"]
    assert audit_log.observed_nowhere
    assert audit_log.read_by == ()
    assert audit_log.written_by == ()
