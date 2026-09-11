"""What the generated document says, and what it must never say.

A generated document is read later, out of context, by someone -- or something, an AI
assistant reading it as evidence -- who will treat a missing key or an empty value as a
fact. So these tests are about the JSON as much as its structure: a field outside an
adapter's capabilities carries a different ``state`` from one it looked for and did not
find, a file nothing could analyze is not dressed up as either, and no table is ever
called unused.

A Markdown rendering of the same facts used to live in this module and was tested here
too. It was removed (2026-09): a second tool started reading ``index.json`` and writing
the readable document itself, so the states below are asserted directly against the JSON
now instead of through a rendered table row.
"""

from __future__ import annotations

from pathlib import Path

from omitnix.analyze import build_report
from omitnix.config import load_config
from omitnix.model import Capability, FieldState, Status
from omitnix.render import payload_for_check, render_json, to_payload

from .conftest import EXPORT_FLOW, ORDERS_FLOW, PLAIN_NOTE, REINDEX_FLOW, write_repo

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


def test_json_round_trips_and_check_ignores_commit_and_dirty_but_not_discovery_mode(
    tmp_path: Path, with_test_adapters: None
) -> None:
    report = build(tmp_path)
    payload = to_payload(report)
    assert payload["schema_version"] == 1
    assert payload["coverage"]["discovered"] == len(payload["files"])
    assert "generated" in payload

    checked = payload_for_check(payload)
    # commit/dirty/tool/partial/adapters vary between two runs of the very same command
    # and must not turn --check red on their own -- but tracked_only records *which
    # question* discovery answered, and two runs that answered different questions must
    # not compare equal, so it is the one field of `generated` that survives here.
    assert checked["generated"] == {"tracked_only": payload["generated"]["tracked_only"]}
    assert render_json(report).endswith("\n")


def test_field_states_survive_serialisation(tmp_path: Path, with_test_adapters: None) -> None:
    """Three of the four per-field states are distinguishable after a JSON round trip.

    ``out_of_scope`` (the field is outside what this adapter declares -- never a missing
    value), ``none_observed`` (the adapter looked and found nothing -- never "unused"),
    and ``value`` (an ordinary result, even an empty list) must all read differently, or
    "did not look" and "looked and found nothing" collapse into the same JSON shape. The
    fourth, ``not_configured``, needs a repository that configured nothing and has its
    own test below.
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
    """The last state -- "not analyzed" -- is not a ``FieldState`` at all.

    It is the file record's own ``status``. A file nothing read has no adapter output to
    report a state *for*, so ``fields`` is empty and the reason lives in ``reason`` --
    never rendered as if it were an observed, empty value.
    """
    write_repo(tmp_path, {"api/helper.unheardof": "x"})
    report = build_report(load_config(tmp_path))
    record = report.file("api/helper.unheardof")

    assert record.status is Status.UNCLAIMED
    assert record.fields == {}
    assert record.reason is not None
    assert to_payload(report)["files"][0]["fields"] == {}


def test_the_reason_a_file_was_not_analyzed_reaches_the_document(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The reason is only worth recording if it survives into what is read.

    Written because the record object was asserted and the document was not: dropping
    ``reason`` from the JSON -- or attaching it, null, to every analyzed file instead --
    left the whole suite green. Either would hand a reader a file that was not analyzed
    and no reason, which is the failure this tool exists to prevent.

    Both statuses that carry a reason are checked here. They are printed differently (one
    named, one counted by extension), and the document is where that difference must not
    become a missing explanation for either.
    """
    write_repo(
        tmp_path,
        {
            "api/helper.unheardof": "x",
            "api/weird.flow": "unparsable: yes\n",
            "docs/RELEASE.note": PLAIN_NOTE,
        },
    )
    report = build_report(load_config(tmp_path))
    files = {record["path"]: record for record in to_payload(report)["files"]}

    unclaimed = files["api/helper.unheardof"]
    assert unclaimed["status"] == "unclaimed"
    assert ".unheardof" in unclaimed["reason"]

    unknown = files["api/weird.flow"]
    assert unknown["status"] == "unknown"
    assert "unparsable" in unknown["reason"]

    # Absent, not present and null: a reader must not have to tell an empty reason from
    # a file that had nothing to explain.
    analyzed = files["docs/RELEASE.note"]
    assert analyzed["status"] == "analyzed"
    assert "reason" not in analyzed


def test_the_document_is_written_the_same_way_every_time(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The bytes are the product, so the three arguments that shape them are pinned.

    A repository commits this document and compares it on every run. Changing the indent,
    escaping non-ASCII, or sorting the keys would rewrite every committed index in every
    repository at once, while the facts inside stayed identical -- and none of the three
    failed a test before this one existed.
    """
    write_repo(tmp_path, {"api/orders_list.flow": "summary: Résumé of nightly totals\n"})
    text = render_json(build_report(load_config(tmp_path)))

    assert text.endswith("\n")
    assert text.startswith('{\n  "schema_version": 1,')  # two spaces, not three
    assert "Résumé" in text and "\\u00e9" not in text  # written, not escaped to ASCII
    # Insertion order, not alphabetical: sorting would put "coverage" first.
    assert text.index('"schema_version"') < text.index('"coverage"')


def test_a_check_nobody_configured_carries_no_value_key_at_all(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """``not_configured`` is shaped like ``out_of_scope``, and for the same reason.

    Nothing was looked for, so there is no result to be empty. An ``"value": []`` beside
    it would be read as an observation -- which is the whole defect: a reader seeing
    ``{"state": "...", "value": []}`` on every file of a repository concludes the
    repository has no authorization calls, when in fact none were ever searched for.
    """
    write_repo(tmp_path, {"batch/reindex.flow": REINDEX_FLOW})
    payload = to_payload(build_report(load_config(tmp_path)))
    fields = payload["files"][0]["fields"]

    assert fields["authorization"] == {"state": "not_configured"}
    assert "value" not in fields["authorization"]
    # The distinction it exists for: an empty list here *is* an observation.
    assert fields["reads"] == {"state": "value", "value": ["orders"]}


def test_a_marked_table_and_an_unmarked_one_are_different_in_the_document(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The mark has to survive into the file, or only the in-memory record has it."""
    write_repo(
        tmp_path,
        {
            ".omitnix.yaml": CONFIG_YAML.replace("schema_snapshot: schema.json\n", ""),
            "api/orders_export.flow": EXPORT_FLOW,
            "batch/reindex.flow": REINDEX_FLOW,
        },
    )
    payload = to_payload(build_report(load_config(tmp_path)))
    tables = {entry["name"]: entry for entry in payload["tables"]}

    assert tables["orders"]["unresolved_in"] == ["api/orders_export.flow"]
    assert tables["search_index"]["unresolved_in"] == []
    assert tables["orders"] != tables["search_index"]


def test_the_document_says_the_table_list_itself_may_be_short(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """A table whose only mention could not be read has no row to be marked.

    So the count sits beside the list, where somebody reading ``tables`` as "the tables
    this repository has" will see it. ``--check`` compares it like the rest of the
    inventory, because a run where more statements stopped being readable is a document
    that changed.
    """
    write_repo(tmp_path, {"api/orders_export.flow": EXPORT_FLOW})
    payload = to_payload(build_report(load_config(tmp_path)))

    assert payload["table_gaps"]["files"] == ["api/orders_export.flow"]
    assert payload["table_gaps"]["unresolved_count"] == 1
    assert "may be incomplete" in payload["table_gaps"]["note"]
    assert "table_gaps" in payload_for_check(payload)


def test_a_run_with_nothing_unreadable_says_so_by_saying_nothing(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The keys stay, the note is empty. A reader must not have to tell absent from none."""
    payload = to_payload(build(tmp_path))
    assert payload["table_gaps"] == {"files": [], "unresolved_count": 0, "note": ""}


def test_tables_with_no_reference_are_reported_never_as_unused(
    tmp_path: Path, with_test_adapters: None
) -> None:
    report = build(tmp_path)
    by_name = {table.name: table for table in report.tables}
    audit_log = by_name["audit_log"]
    assert audit_log.observed_nowhere
    assert audit_log.read_by == ()
    assert audit_log.written_by == ()
