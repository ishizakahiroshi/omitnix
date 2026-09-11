"""The minimal tier: css, rust, shell, powershell and vue.

These adapters exist so that an extension a repository contains is *decided* rather than
left to fail the run, and so that deciding it does not require an exclusion written into
thirty configuration files. What they must never do is imply they looked at more than the
first comment of a file.

Every fixture under ``tests/fixtures/minimal`` is invented.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omitnix.adapters.base import AnalysisRequest, AnalysisResult
from omitnix.adapters.css import ADAPTER as CSS
from omitnix.adapters.powershell import ADAPTER as POWERSHELL
from omitnix.adapters.rust import ADAPTER as RUST
from omitnix.adapters.shell import ADAPTER as SHELL
from omitnix.adapters.vue import ADAPTER as VUE
from omitnix.analyze import build_report
from omitnix.config import load_config
from omitnix.gate import run_gate
from omitnix.model import (
    CAPABILITY_ORDER,
    GATE_REQUIRED_CAPABILITIES,
    Capability,
    FieldState,
    Status,
)
from omitnix.registry import build_adapter_set

from .conftest import FIXTURES

MINIMAL_FIXTURES = FIXTURES / "minimal"

ADAPTERS = {
    "styles.css": CSS,
    "counter.rs": RUST,
    "deploy.sh": SHELL,
    "banner.sh": SHELL,
    "deploy.ps1": POWERSHELL,
    "panel.vue": VUE,
}


def analyze(rel: str) -> AnalysisResult:
    absolute = MINIMAL_FIXTURES / rel
    return ADAPTERS[rel].analyze(
        AnalysisRequest(
            path=rel,
            absolute_path=absolute,
            text=absolute.read_text(encoding="utf-8"),
            authentication_functions=("require_session",),
            authorization_functions=("apply_visibility_filter",),
        )
    )


# --- what these adapters declare ---------------------------------------------------


@pytest.mark.parametrize("adapter", [RUST, SHELL, POWERSHELL, VUE])
def test_the_minimal_tier_claims_a_summary_and_nothing_else(adapter: object) -> None:
    assert adapter.capabilities == frozenset({Capability.SUMMARY})


def test_the_stylesheet_adapter_claims_nothing_at_all() -> None:
    """Every column renders as out of scope. A stylesheet must not appear in a document
    as a file that was checked for an authorization call and found to have none."""
    assert CSS.capabilities == frozenset()


@pytest.mark.parametrize("adapter", [CSS, RUST, SHELL, POWERSHELL, VUE])
def test_no_minimal_adapter_extracts_a_table(adapter: object) -> None:
    """Not until there is something to extract. Rust was measured across 6 repositories
    and not one of them declared a database crate."""
    assert Capability.READS not in adapter.capabilities
    assert Capability.WRITES not in adapter.capabilities


def test_no_grammar_package_is_needed_by_the_minimal_tier() -> None:
    """A grammar here would be a dependency standing between a file and being counted,
    bought for one column that a text scan already fills. Two of these languages have no
    grammar on PyPI to load in any case."""
    for rel in ADAPTERS:
        assert analyze(rel).unknown_reason is None


# --- the summaries they do extract -------------------------------------------------


def test_a_rust_inner_doc_comment_does_not_leave_its_marker_behind() -> None:
    """'//!' opens a comment. Stripping only the slashes left summaries beginning with a
    stray exclamation mark."""
    assert analyze("counter.rs").values[Capability.SUMMARY] == (
        "Counts orders in a batch. Touches no database."
    )


def test_a_shebang_is_not_mistaken_for_the_summary() -> None:
    """It names an interpreter. Promoting it would fill an index with the same words."""
    assert analyze("deploy.sh").values[Capability.SUMMARY] == (
        "Copy the built assets to the fictional staging host."
    )


def test_a_rule_of_punctuation_is_not_mistaken_for_the_summary() -> None:
    """A banner comment opens with a row of equals signs. Taking it put that row in the
    index in place of the sentence underneath, in twenty of the thirty-one shell scripts
    of the first real repository this was pointed at."""
    assert analyze("banner.sh").values[Capability.SUMMARY] == (
        "Rotate the fictional staging logs once a day."
    )


def test_a_powershell_help_marker_is_not_mistaken_for_the_summary() -> None:
    assert analyze("deploy.ps1").values[Capability.SUMMARY] == (
        "Copy the built assets to the fictional staging host."
    )


def test_a_single_file_component_is_summarised_from_its_leading_comment() -> None:
    assert analyze("panel.vue").values[Capability.SUMMARY].startswith("The order panel")


def test_a_file_with_no_header_comment_reports_no_summary_rather_than_inventing_one(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bare.sh"
    path.write_text("echo hello\n", encoding="utf-8")
    result = SHELL.analyze(
        AnalysisRequest(path="bare.sh", absolute_path=path, text=path.read_text("utf-8"))
    )
    assert result.values[Capability.SUMMARY] == ""


# --- through the core: counted, and not failing the gate ---------------------------

REPO_CONFIG = """
include:
  - '**/*.css'
  - '**/*.rs'
  - '**/*.sh'
  - '**/*.ps1'
  - '**/*.vue'
authentication_functions:
  - require_session
authorization_functions:
  - apply_visibility_filter
"""


@pytest.fixture
def minimal_repo(tmp_path: Path) -> Path:
    shutil.copytree(MINIMAL_FIXTURES, tmp_path / "src")
    (tmp_path / ".omitnix.yaml").write_text(REPO_CONFIG, encoding="utf-8")
    return tmp_path


def test_every_file_of_the_minimal_tier_is_counted_as_analyzed(minimal_repo: Path) -> None:
    report = build_report(load_config(minimal_repo))
    assert report.coverage.holds
    assert report.coverage.unknown == 0
    assert report.coverage.unresolved == 0
    assert report.coverage.analyzed == len(ADAPTERS)


def test_a_new_stylesheet_does_not_fail_the_gate(minimal_repo: Path) -> None:
    """The day a stylesheet adapter is added must not be the day every new stylesheet
    fails a commit for missing an authorization check it could never have had."""
    config = load_config(minimal_repo)
    report = build_report(config, files=["src/styles.css"])
    gate = run_gate(report, config)
    assert gate.passed, [finding.line() for finding in gate.findings]


def test_the_gate_asks_a_minimal_adapter_only_for_what_it_declared(minimal_repo: Path) -> None:
    config = load_config(minimal_repo)
    report = build_report(config, files=["src/deploy.sh"])
    record = report.file("src/deploy.sh")
    assert record.fields[Capability.AUTHORIZATION].state is FieldState.OUT_OF_SCOPE
    gate = run_gate(report, config)
    assert gate.passed, [finding.line() for finding in gate.findings]


def test_a_stylesheet_row_reads_as_out_of_scope_rather_than_as_a_missing_check(
    minimal_repo: Path,
) -> None:
    report = build_report(load_config(minimal_repo))
    record = report.file("src/styles.css")
    assert record.status is Status.ANALYZED
    for capability in GATE_REQUIRED_CAPABILITIES:
        assert record.fields[capability].state is FieldState.OUT_OF_SCOPE

    # Every one of the six capability columns reads out_of_scope, and none reads
    # none_observed: a stylesheet must never look like a file that was checked for an
    # authorization call and found to have none.
    assert len(record.fields) == len(CAPABILITY_ORDER)
    states = {capability: record.fields[capability].state for capability in CAPABILITY_ORDER}
    assert set(states.values()) == {FieldState.OUT_OF_SCOPE}

    payload = record.to_json()["fields"]
    assert len(payload) == len(CAPABILITY_ORDER)
    assert all(field == {"state": "out_of_scope"} for field in payload.values())


# --- an extension nobody claims is still counted ------------------------------------


def test_an_extension_nobody_claims_is_counted_as_unclaimed(tmp_path: Path) -> None:
    """The minimal tier decides the extensions it names. The ones it does not name are
    somebody's files all the same, and they stay in the count."""
    (tmp_path / "notes.zzz").write_text("nothing in particular\n", encoding="utf-8")
    report = build_report(load_config(tmp_path), adapter_set=build_adapter_set())
    assert report.coverage.unclaimed == 1
    assert report.coverage.discovered == 1
    assert report.files[0].status is Status.UNCLAIMED
    assert report.unclaimed_extensions == {".zzz": 1}
