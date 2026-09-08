"""What the generated documents say, and what they must never say.

A generated document is read later, out of context, by someone who will treat a blank
cell as a fact. So these tests are about wording as much as structure: a field outside an
adapter's capabilities reads differently from one it looked for and did not find, a file
nothing could analyze is not dressed up as either, and no table is ever called unused.
"""

from __future__ import annotations

from pathlib import Path

from omitnix.analyze import build_report
from omitnix.config import load_config
from omitnix.model import GeneratedMeta
from omitnix.render import (
    NONE_OBSERVED_CELL,
    NOT_ANALYZED_CELL,
    OUT_OF_SCOPE_CELL,
    PROVENANCE_PREFIXES,
    payload_for_check,
    provenance_line,
    render_json,
    render_markdown,
    to_payload,
)

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


def test_markdown_states_its_provenance_first(tmp_path: Path, with_test_adapters: None) -> None:
    markdown = render_markdown(build(tmp_path))
    lines = markdown.splitlines()
    assert lines[0] == "# omitnix index"
    assert lines[2].startswith(PROVENANCE_PREFIXES)
    assert lines[3].startswith("Coverage: ")
    assert "analyzed," in lines[3] and "unresolved," in lines[3] and "unknown" in lines[3]


def test_a_dirty_tree_is_not_described_as_the_commit_it_sits_on() -> None:
    """The usual case: the document is generated just before the commit that carries it.

    Saying "generated from commit X" then points the reader at a commit whose content is
    not what was analyzed -- and this document is committed, so that reader is everyone.
    """
    clean = GeneratedMeta(commit="0123456", dirty=False, tool="omitnix", partial=False)
    dirty = GeneratedMeta(commit="0123456", dirty=True, tool="omitnix", partial=False)
    absent = GeneratedMeta(commit=None, dirty=False, tool="omitnix", partial=False)

    assert provenance_line(clean) == "Generated from commit: 0123456"
    assert provenance_line(dirty).startswith("Generated from a working tree based on commit")
    assert "uncommitted changes present" in provenance_line(dirty)
    assert "unknown (not a git working tree)" in provenance_line(absent)
    # Whatever the wording, --check has to be able to drop the line.
    for meta in (clean, dirty, absent):
        assert provenance_line(meta).startswith(PROVENANCE_PREFIXES)


def test_markdown_separates_out_of_scope_from_none_observed(
    tmp_path: Path, with_test_adapters: None
) -> None:
    markdown = render_markdown(build(tmp_path))
    assert OUT_OF_SCOPE_CELL in markdown
    assert NONE_OBSERVED_CELL in markdown
    assert OUT_OF_SCOPE_CELL != NONE_OBSERVED_CELL
    assert "It is not a missing value." in markdown


def test_markdown_never_calls_anything_unused(tmp_path: Path, with_test_adapters: None) -> None:
    markdown = render_markdown(build(tmp_path))
    assert "audit_log" in markdown
    assert "no static reference observed" in markdown
    assert "unused" not in markdown.replace("does not mean the thing is unused", "")


def test_unknown_rows_are_not_dressed_up_as_out_of_scope(
    tmp_path: Path, with_test_adapters: None
) -> None:
    write_repo(tmp_path, {"api/helper.unheardof": "x"})
    report = build_report(load_config(tmp_path))
    markdown = render_markdown(report)
    row = next(line for line in markdown.splitlines() if "helper.unheardof" in line and "|" in line)
    assert NOT_ANALYZED_CELL in row
    assert OUT_OF_SCOPE_CELL not in row


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
    payload = to_payload(build(tmp_path))
    by_path = {entry["path"]: entry for entry in payload["files"]}
    note = by_path["docs/RELEASE.note"]["fields"]
    assert note["authorization"] == {"state": "out_of_scope"}
    reindex = by_path["batch/reindex.flow"]["fields"]
    # An empty list is still "the analyzer looked and found none", never a blank cell.
    assert reindex["authorization"] == {"state": "none_observed", "value": []}
    assert reindex["writes"] == {"state": "value", "value": ["search_index"]}
