"""What a run tells the reader to install when a dependency is missing.

A reason that cannot be acted on in one step is only half a reason. Until 2026-09-11
these hints named the distribution that failed to import, which was accurate and led
nowhere useful: a bare ``pip install omitnix`` reports ``tree-sitter`` is missing, and
after installing it the next run reports ``tree-sitter-python`` is missing. Three runs
to analyze one file, with each message correct.

The packaging extra installs the binding, the grammar and sqlglot at once, so it is what
the reader is told to install. These tests hold that in place, and hold the extra to
being a real one -- a hint naming ``omitnix[typescript]`` would be worse than the old
message, because the command it gives fails.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

from omitnix.adapters import _treesitter, go, html, php, python, sql, tsjs
from omitnix.adapters._treesitter import GrammarUnavailable
from omitnix.adapters.base import AnalysisRequest

#: The adapters that can fail for want of something the user has to install. The minimal
#: tier (css, rust, shell, powershell, vue) is absent on purpose: those need nothing, so
#: they have no extra, and giving them one would put a dependency between a file and
#: being counted.
MODULES_WITH_AN_EXTRA = (go, html, php, python, sql, tsjs)


def declared_extras() -> set[str]:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    return set(project["optional-dependencies"])


@pytest.mark.parametrize("module", MODULES_WITH_AN_EXTRA, ids=lambda m: m.__name__)
def test_the_extra_an_adapter_names_is_one_a_user_can_actually_install(module) -> None:
    """The hint is a command. A command that names a nonexistent extra fails."""
    assert module.EXTRA in declared_extras()


@pytest.mark.parametrize("module", MODULES_WITH_AN_EXTRA, ids=lambda m: m.__name__)
def test_the_extra_and_the_adapter_name_are_the_same_string(module) -> None:
    """Written once per module, so the two cannot drift.

    They are the same fact: ``omitnix[go]`` is what installs the adapter registered as
    ``go``. Two literals would let somebody rename one and leave a hint pointing at an
    extra that no longer matches the adapter doing the complaining.
    """
    adapter = next(
        value
        for value in vars(module).values()
        if isinstance(value, type) and getattr(value, "name", None) == module.EXTRA
    )
    assert adapter.name == module.EXTRA


def test_a_missing_grammar_tells_the_reader_the_one_command_that_fixes_it() -> None:
    with pytest.raises(GrammarUnavailable) as raised:
        _treesitter.load_grammar(
            "python", "tree_sitter_python_that_is_not_installed", "language", extra="python"
        )

    reason = str(raised.value)
    assert 'pip install "omitnix[python]"' in reason
    # The distribution name alone sends the reader round again for the next one.
    assert "pip install tree-sitter" not in reason


def test_a_missing_tree_sitter_binding_names_the_extra_as_well(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first of the two steps the reader used to be walked through.

    This branch is the one a bare ``pip install omitnix`` actually hits, and it is the
    harder of the two to reach from a test, because the environment running the suite
    has the binding. Left untested it stayed on the old wording while its neighbour was
    fixed -- which is the shape of the original defect, not a variation on it.
    """
    monkeypatch.setitem(sys.modules, "tree_sitter", None)

    with pytest.raises(GrammarUnavailable) as raised:
        # A symbol no other call uses, so the cache cannot answer this one.
        _treesitter.load_grammar(
            "python", "tree_sitter_python", "language_for_this_test", extra="python"
        )

    reason = str(raised.value)
    assert "binding is not installed" in reason
    assert 'pip install "omitnix[python]"' in reason
    assert "pip install tree-sitter" not in reason


def test_a_missing_sqlglot_names_the_extra_rather_than_the_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SQL adapter has no grammar, and the same obligation.

    ``pip install sqlglot`` does make the adapter work, so this hint was never a walk of
    two steps. It is here because a reader who has followed ``omitnix[python]`` once has
    learned a shape, and one message in a different shape reads as a different kind of
    problem.
    """

    def not_installed(*_args: object, **_kwargs: object) -> None:
        raise ImportError("No module named 'sqlglot'")

    monkeypatch.setattr("omitnix.adapters.sql.read_sql", not_installed)

    result = sql.ADAPTER.analyze(
        AnalysisRequest(
            path="orders_report.sql",
            absolute_path=Path("orders_report.sql"),
            text="SELECT id FROM orders;\n",
        )
    )

    assert result.unknown_reason is not None
    assert 'pip install "omitnix[sql]"' in result.unknown_reason


def test_an_unreadable_inline_script_points_at_the_extra_for_the_file_that_was_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The caller's extra, not the module's.

    ``scan_javascript`` lives in the TypeScript/JavaScript adapter but is called by the
    HTML adapter on a ``<script>`` block. The reader ran omitnix on an HTML file, and
    ``omitnix[tsjs]`` would not have made that file readable -- the JavaScript grammar
    reaches them through ``omitnix[html]``. So the hint has to follow the file, not the
    module the code happens to live in.
    """
    asked: list[str] = []

    def record(*_args: str, extra: str, **_kwargs: object) -> None:
        asked.append(extra)
        raise GrammarUnavailable(f'grammar missing. pip install "omitnix[{extra}]"')

    monkeypatch.setattr("omitnix.adapters.tsjs.load_grammar", record)

    fixture = Path(__file__).resolve().parent / "fixtures" / "html" / "orders.html"
    result = html.ADAPTER.analyze(
        AnalysisRequest(
            path="orders.html",
            absolute_path=fixture,
            text=fixture.read_text(encoding="utf-8"),
        )
    )

    assert asked == ["html"], "the HTML file's own extra, not tsjs"
    assert any('omitnix[html]' in str(item) for item in result.unresolved)
