"""Tests for the new-file gate.

Every repository here is a real git repository created in a temporary directory, because
the gate's first question -- "is this file new?" -- is answered by git and cannot be
faked convincingly with a stub.
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from omitnix.cli import EXIT_ERROR, EXIT_GATE, EXIT_OK, main

from .conftest import FIXTURES, write_repo

REPO_ROOT = Path(__file__).resolve().parents[1]
SEMGREP_DIR = REPO_ROOT / ".semgrep"
NEW_FIXTURES = FIXTURES / "new"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

CONFIG_YAML = """
include:
  - '**/*.flow'
  - '**/*.note'
  - '**/*.unmapped'
authentication_functions:
  - require_session
authorization_functions:
  - apply_visibility_filter
"""


def fixture(name: str) -> str:
    return (NEW_FIXTURES / name).read_text(encoding="utf-8")


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def baseline(root: Path, files: dict[str, str] | None = None, config: str = CONFIG_YAML) -> Path:
    """A committed repository. Anything added after this call is what the gate sees."""
    write_repo(root, {".omitnix.yaml": config, **(files or {})})
    git(root, "init", "-q")
    git(root, "config", "user.email", "tests@example.invalid")
    git(root, "config", "user.name", "omitnix tests")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "baseline")
    return root


def run(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(args, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def gate(root: Path, *extra: str) -> tuple[int, str, str]:
    return run(["--root", str(root), "--gate", *extra])


# --------------------------------------------------------------------------------------
# What the gate refuses
# --------------------------------------------------------------------------------------


def test_a_new_file_without_an_authorization_call_is_refused(
    tmp_path: Path, with_test_adapters: None
) -> None:
    root = baseline(tmp_path)
    (root / "orders_purge.flow").write_text(fixture("orders_purge.flow"), encoding="utf-8")

    code, _, err = gate(root)
    assert code == EXIT_GATE
    assert "orders_purge.flow: no authorization call" in err


def test_a_new_file_without_a_summary_is_refused(
    tmp_path: Path, with_test_adapters: None
) -> None:
    root = baseline(tmp_path)
    (root / "undocumented.flow").write_text(fixture("undocumented.flow"), encoding="utf-8")

    code, _, err = gate(root)
    assert code == EXIT_GATE
    assert "undocumented.flow: no summary" in err


def test_a_new_file_no_adapter_understands_is_refused_not_skipped(
    tmp_path: Path, with_test_adapters: None
) -> None:
    root = baseline(tmp_path)
    (root / "theme.unmapped").write_text(fixture("theme.unmapped"), encoding="utf-8")

    code, _, err = gate(root)
    assert code == EXIT_GATE
    assert "theme.unmapped: unknown" in err
    assert ".unmapped" in err  # the reason names the extension nothing claimed


def test_a_new_file_the_analyzer_could_not_follow_is_reported_not_refused(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """`unresolved` is this tool's limit, not a defect the file's author can fix.

    Refusing on it would block work nobody can unblock by editing the file, and a gate
    that cannot be satisfied is a gate that gets switched off. It has to stay visible,
    so it is printed on a passing run too.
    """
    root = baseline(tmp_path)
    (root / "reindex.flow").write_text(fixture("reindex.flow"), encoding="utf-8")

    code, out, err = gate(root)
    assert code == EXIT_OK
    assert "gate passed" in out
    assert "not followed: reindex.flow: unresolved (dynamic_sql)" in err


def test_a_repository_that_never_said_what_authorization_is_cannot_fail_on_it(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """"Not configured" and "not called" are different answers.

    A repository with no session layer configures no function names. Refusing its files
    for lacking a call the tool has no definition of would make the gate unusable there,
    and the parent plan settles it the other way: report "not configured", never
    "no authorization".
    """
    root = baseline(tmp_path, config="include:\n  - '**/*.flow'\n")
    (root / "plain.flow").write_text("summary: A file with no session layer\n", encoding="utf-8")

    code, out, err = gate(root)
    assert code == EXIT_OK
    assert "gate passed" in out
    assert "no authorization call" not in err
    assert "authorization not checked" in err
    assert "authentication not checked" in err


def test_unresolved_does_not_rescue_a_file_that_is_missing_a_check(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """Downgrading unresolved must not downgrade anything else on the same file."""
    root = baseline(tmp_path)
    (root / "leaky.flow").write_text(
        "summary: Rebuild the nightly report\n"
        "reads: orders\n"
        "unresolved: dynamic_sql / the table name is built at run time\n",
        encoding="utf-8",
    )

    code, _, err = gate(root)
    assert code == EXIT_GATE
    assert "leaky.flow: no authorization call" in err
    assert "not followed: leaky.flow: unresolved (dynamic_sql)" in err


def test_every_missing_item_gets_its_own_line(
    tmp_path: Path, with_test_adapters: None
) -> None:
    root = baseline(tmp_path)
    # Only a summary: the authentication and authorization checks are both absent.
    (root / "health_check.flow").write_text(fixture("health_check.flow"), encoding="utf-8")

    code, _, err = gate(root)
    assert code == EXIT_GATE
    lines = [line.strip() for line in err.splitlines() if "health_check.flow" in line]
    assert lines == [
        line
        for line in lines
        if line.startswith("health_check.flow: no ")
    ]
    assert any("no authentication call" in line for line in lines)
    assert any("no authorization call" in line for line in lines)
    assert len(lines) == 2


def test_the_gate_exit_code_is_distinct_from_the_unknown_exit_code(
    tmp_path: Path, with_test_adapters: None
) -> None:
    root = baseline(tmp_path)
    (root / "orders_purge.flow").write_text(fixture("orders_purge.flow"), encoding="utf-8")
    assert gate(root)[0] == EXIT_GATE == 4


# --------------------------------------------------------------------------------------
# What the gate must not refuse
# --------------------------------------------------------------------------------------


def test_a_complete_new_file_passes(tmp_path: Path, with_test_adapters: None) -> None:
    root = baseline(tmp_path)
    (root / "orders_list.flow").write_text(fixture("orders_list.flow"), encoding="utf-8")

    code, out, _ = gate(root)
    assert code == EXIT_OK
    assert "gate passed. checked 1 file newly added in the working tree" in out


def test_a_capability_the_adapter_never_declared_is_not_required(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The rule that keeps a stylesheet adapter from failing every new stylesheet.

    The ``note`` adapter declares only SUMMARY. Its files must not be refused for
    lacking an authorization call it could never have reported.
    """
    root = baseline(tmp_path)
    (root / "release.note").write_text(fixture("release.note"), encoding="utf-8")

    code, out, err = gate(root)
    assert code == EXIT_OK, err
    assert "gate passed" in out
    assert "authorization" not in err


def test_existing_files_are_not_gated(tmp_path: Path, with_test_adapters: None) -> None:
    """No false positive on a repository that was already there.

    Every fixture that would fail the gate is committed as part of the baseline, so a
    single passing run is the whole claim: the gate looks only at what is new.
    """
    root = baseline(
        tmp_path,
        {
            "orders_purge.flow": fixture("orders_purge.flow"),
            "undocumented.flow": fixture("undocumented.flow"),
            "health_check.flow": fixture("health_check.flow"),
            "reindex.flow": fixture("reindex.flow"),
            "theme.unmapped": fixture("theme.unmapped"),
            "release.note": fixture("release.note"),
        },
    )

    code, out, err = gate(root)
    assert code == EXIT_OK, err
    assert "checked 0 files newly added in the working tree" in out


def test_a_rewritten_tracked_file_is_not_new(
    tmp_path: Path, with_test_adapters: None
) -> None:
    root = baseline(tmp_path, {"orders_list.flow": fixture("orders_list.flow")})
    # Rewrite it into something that would fail the gate if it counted as new.
    (root / "orders_list.flow").write_text(fixture("orders_purge.flow"), encoding="utf-8")

    code, out, err = gate(root)
    assert code == EXIT_OK, err
    assert "checked 0 files newly added in the working tree" in out


# --------------------------------------------------------------------------------------
# How "new" is decided
# --------------------------------------------------------------------------------------


def test_a_staged_addition_is_gated(tmp_path: Path, with_test_adapters: None) -> None:
    """What a pre-commit hook actually sees: the file is added to the index, not yet committed."""
    root = baseline(tmp_path)
    (root / "orders_purge.flow").write_text(fixture("orders_purge.flow"), encoding="utf-8")
    git(root, "add", "orders_purge.flow")

    code, _, err = gate(root)
    assert code == EXIT_GATE
    assert "orders_purge.flow: no authorization call" in err


def test_files_narrows_the_gate_to_the_listed_paths(
    tmp_path: Path, with_test_adapters: None
) -> None:
    root = baseline(tmp_path)
    (root / "orders_list.flow").write_text(fixture("orders_list.flow"), encoding="utf-8")
    (root / "orders_purge.flow").write_text(fixture("orders_purge.flow"), encoding="utf-8")

    code, out, err = gate(root, "--files", "orders_list.flow")
    assert code == EXIT_OK, err
    assert "checked 1 file newly added in the working tree" in out


def test_files_still_gates_only_what_is_new(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """A hook passes every changed path. Only the added ones are this gate's business."""
    root = baseline(tmp_path, {"orders_list.flow": fixture("orders_list.flow")})
    (root / "orders_list.flow").write_text(fixture("orders_purge.flow"), encoding="utf-8")
    (root / "undocumented.flow").write_text(fixture("undocumented.flow"), encoding="utf-8")

    code, _, err = gate(root, "--files", "orders_list.flow", "undocumented.flow")
    assert code == EXIT_GATE
    assert "undocumented.flow: no summary" in err
    assert "orders_list.flow" not in err


def test_outside_a_git_working_tree_the_gate_refuses_to_report_a_pass(
    tmp_path: Path, with_test_adapters: None
) -> None:
    write_repo(tmp_path, {".omitnix.yaml": CONFIG_YAML})
    code, out, err = gate(tmp_path)
    assert code == EXIT_ERROR
    assert "git working tree" in err
    assert "passed" not in out


def test_gate_cannot_be_combined_with_writing_or_checking(tmp_path: Path) -> None:
    for flag in ("--write", "--check"):
        code, _, err = run(["--root", str(tmp_path), "--gate", flag])
        assert code == EXIT_ERROR
        assert "cannot be combined" in err


# --------------------------------------------------------------------------------------
# Asking about a range instead of the working tree
# --------------------------------------------------------------------------------------
#
# The working-tree question only has an answer while the file is still uncommitted, so a
# gate that can only ask it runs in a pre-commit hook, and a hook is enabled one machine
# at a time. A file committed by someone who never enabled it is tracked and clean by the
# time anyone else sees it, and is never gated again by anybody. `--since` is what a
# server asks instead.


def test_a_file_committed_without_the_hook_is_still_gated_afterwards(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """The whole point. The working tree has nothing to say about this file any more."""
    root = baseline(tmp_path)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()

    (root / "orders_purge.flow").write_text(fixture("orders_purge.flow"), encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "committed with no hook installed")

    # The working tree is clean, so the question a hook asks now finds nothing at all.
    code, out, err = gate(root)
    assert code == EXIT_OK, err
    assert "checked 0 files newly added in the working tree" in out

    # The same file, asked about as a range, is still refused.
    code, _, err = gate(root, "--since", base)
    assert code == EXIT_GATE
    assert "orders_purge.flow: no authorization call" in err


def test_the_range_gate_says_what_it_was_asked_about(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """"The gate passed" means nothing until you know which question it answered."""
    root = baseline(tmp_path)
    code, out, err = gate(root, "--since", "HEAD")
    assert code == EXIT_OK, err
    assert "checked 0 files added since HEAD" in out


def test_a_range_the_repository_cannot_resolve_refuses_rather_than_passes(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """A shallow clone is the real case: the base ref is simply not there.

    Reporting "nothing was added" would be a green run over an unexamined push, which is
    the failure this flag exists to end rather than one to reintroduce.
    """
    root = baseline(tmp_path)
    code, out, err = gate(root, "--since", "refs/heads/no-such-branch")
    assert code == EXIT_ERROR
    assert "could not answer" in err
    assert "passed" not in out


def test_a_rename_is_not_an_addition_in_a_range_either(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """Consistent with the working-tree question: the content existed before."""
    root = baseline(tmp_path, {"orders_purge.flow": fixture("orders_purge.flow")})
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    git(root, "mv", "orders_purge.flow", "purge_orders.flow")
    git(root, "commit", "-q", "-m", "rename")

    code, out, err = gate(root, "--since", base)
    assert code == EXIT_OK, err
    assert "checked 0 files added since" in out


def test_since_without_the_gate_is_refused_rather_than_ignored(tmp_path: Path) -> None:
    """A CI job with --gate left off would otherwise do a full run and go green."""
    code, _, err = run(["--root", str(tmp_path), "--since", "HEAD"])
    assert code == EXIT_ERROR
    assert "--since only applies with --gate" in err


# --------------------------------------------------------------------------------------
# Exemptions
# --------------------------------------------------------------------------------------

EXEMPTION_YAML = (
    CONFIG_YAML
    + """
gate_exemptions:
  - paths: ['health_check.flow']
    skip: [authentication, authorization]
    reason: Public liveness endpoint, deliberately reachable without a session.
"""
)


def test_a_reasoned_exemption_is_applied_and_stays_visible(
    tmp_path: Path, with_test_adapters: None
) -> None:
    root = baseline(tmp_path, config=EXEMPTION_YAML)
    (root / "health_check.flow").write_text(fixture("health_check.flow"), encoding="utf-8")

    code, out, err = gate(root)
    assert code == EXIT_OK, err
    assert "gate passed" in out
    # The reason is printed every time it is used: an invisible exemption is one nobody
    # ever re-examines.
    assert "exemption applied" in err
    assert "deliberately reachable without a session" in err


def test_an_exemption_without_a_reason_is_rejected(
    tmp_path: Path, with_test_adapters: None
) -> None:
    config = (
        CONFIG_YAML
        + "gate_exemptions:\n  - paths: ['health_check.flow']\n    skip: [authorization]\n"
    )
    root = baseline(tmp_path, config=config)
    (root / "health_check.flow").write_text(fixture("health_check.flow"), encoding="utf-8")

    code, _, err = gate(root)
    assert code == EXIT_ERROR
    assert "'reason' is required" in err


def test_an_exemption_cannot_switch_off_a_check_the_gate_never_makes(
    tmp_path: Path, with_test_adapters: None
) -> None:
    config = (
        CONFIG_YAML
        + "gate_exemptions:\n  - paths: ['*.flow']\n    skip: [reads]\n    reason: nope\n"
    )
    root = baseline(tmp_path, config=config)

    code, _, err = gate(root)
    assert code == EXIT_ERROR
    assert "cannot skip reads" in err


def test_an_exemption_cannot_admit_an_unanalyzable_file(
    tmp_path: Path, with_test_adapters: None
) -> None:
    """``unknown`` is the one refusal no configuration can turn off."""
    config = (
        CONFIG_YAML
        + "gate_exemptions:\n  - paths: ['**/*']\n    skip: [summary, authentication, "
        "authorization]\n    reason: Everything is exempt, which must still not help here.\n"
    )
    root = baseline(tmp_path, config=config)
    (root / "theme.unmapped").write_text(fixture("theme.unmapped"), encoding="utf-8")

    code, _, err = gate(root)
    assert code == EXIT_GATE
    assert "theme.unmapped: unknown" in err


# --------------------------------------------------------------------------------------
# The shipped semgrep rules
# --------------------------------------------------------------------------------------

#: Every domain name allowed to appear in the shipped rules. This repository is public,
#: and a rule file is one of the easiest places for a real internal name to escape into
#: it. Adding a name here has to be a deliberate act.
FICTIONAL_TABLES = {"orders", "customers", "search_index", "audit_log"}
FICTIONAL_FUNCTIONS = {
    "require_session",
    "apply_visibility_filter",
    "run_query",
    "list_rows",
    "fetch_orders_unfiltered",
    "rawQuery",
    "function",
}

TABLE_REFERENCE = re.compile(r"\b(?:FROM|INTO|JOIN|UPDATE)\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)
CALL = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
SQL_LITERAL = re.compile(r"'([^']*)'|\"([^\"]*)\"")


def rule_files() -> list[Path]:
    return sorted(SEMGREP_DIR.glob("*.yaml"))


def test_the_rules_are_shipped_and_parse() -> None:
    files = rule_files()
    assert files, "no semgrep rule file is shipped"
    for path in files:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(document, dict) and document.get("rules"), f"{path} declares no rules"
        for rule in document["rules"]:
            assert rule["id"].startswith("omitnix-"), rule["id"]
            for key in ("languages", "severity", "message"):
                assert rule.get(key), f"{rule['id']} has no {key}"
            assert any(
                key in rule for key in ("pattern", "patterns", "pattern-either")
            ), f"{rule['id']} matches nothing"


def test_the_rules_never_build_an_index() -> None:
    """The division of labour, asserted rather than merely documented."""
    text = " ".join(path.read_text(encoding="utf-8") for path in rule_files()).lower()
    assert "semgrep" in text and "index" in text  # the boundary is stated in the file
    for path in rule_files():
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for rule in document["rules"]:
            # A rule that reports on every file, rather than on a violation, would be an
            # index in disguise. Every shipped rule carries a severity that says so.
            assert rule["severity"] in {"ERROR", "WARNING"}, rule["id"]


#: Keys whose value is code to match. ``patterns`` and ``pattern-either`` are containers
#: and are simply recursed into, while ``metavariable-regex`` holds a regular expression
#: rather than code -- scanning that for identifiers reads ``\b(from|...`` as a call to
#: ``b``, which is how this check first went wrong.
LEAF_PATTERN_KEYS = {"pattern", "pattern-inside", "pattern-not", "pattern-not-inside"}


def _pattern_strings(node: object) -> list[str]:
    """Every piece of code-to-match in a rule document."""
    found: list[str] = []
    if isinstance(node, list):
        for item in node:
            found.extend(_pattern_strings(item))
    elif isinstance(node, dict):
        for key, value in node.items():
            if key in LEAF_PATTERN_KEYS:
                found.extend([value] if isinstance(value, str) else [])
            else:
                found.extend(_pattern_strings(value))
    return found


def test_the_rules_and_examples_name_nothing_real() -> None:
    checked_tables = 0
    checked_calls = 0

    for path in sorted(SEMGREP_DIR.rglob("*")):
        if not path.is_file() or path.suffix not in {".yaml", ".php"}:
            continue
        text = path.read_text(encoding="utf-8")
        for literal in SQL_LITERAL.findall(text):
            for table in TABLE_REFERENCE.findall("".join(literal)):
                assert table.lower() in FICTIONAL_TABLES, f"{path}: table '{table}'"
                checked_tables += 1
        if path.suffix == ".php":
            continue
        for pattern in _pattern_strings(yaml.safe_load(text)):
            # Metavariables are semgrep syntax, not names.
            for name in CALL.findall(re.sub(r"\$[A-Z_][A-Z0-9_]*", "", pattern)):
                assert name in FICTIONAL_FUNCTIONS, f"{path}: function '{name}'"
                checked_calls += 1

    # A test that silently examined nothing would pass just as loudly.
    assert checked_tables and checked_calls


@pytest.mark.skipif(shutil.which("semgrep") is None, reason="semgrep is not installed")
def test_the_rules_fire_on_the_violating_example_only() -> None:
    import json

    completed = subprocess.run(
        [
            "semgrep",
            "--config",
            str(SEMGREP_DIR),
            "--json",
            "--quiet",
            "--no-git-ignore",
            str(SEMGREP_DIR / "examples"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode in (0, 1), completed.stderr
    results = json.loads(completed.stdout)["results"]

    by_file: dict[str, set[str]] = {}
    for finding in results:
        name = Path(finding["path"]).name
        by_file.setdefault(name, set()).add(finding["check_id"].rsplit(".", 1)[-1])

    assert by_file.get("orders_list.php", set()) == set()
    fired = by_file.get("orders_export.php", set())
    declared = {
        rule["id"]
        for path in rule_files()
        for rule in yaml.safe_load(path.read_text(encoding="utf-8"))["rules"]
    }
    assert fired == declared, f"fired={sorted(fired)} declared={sorted(declared)}"
