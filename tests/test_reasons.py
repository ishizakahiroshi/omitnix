"""The reason vocabulary: one definition, and every code in it classified.

Two failures this guards against, both of which the suite used to miss.

*Two copies.* ``adapters/_extract.py`` and ``adapters/php.py`` each defined the strings,
and each held a code the other did not. Nothing compared them, so the adapters could have
drifted into spelling the same fact two ways and the reverse index would have grouped
them as two facts.

*A code nobody classified.* The reverse index asks each code whether it could be hiding a
table. A code added without an answer to that question would silently get one, and
"assume it is fine" is the answer that makes a gap invisible.
"""

from __future__ import annotations

import ast
from pathlib import Path

from omitnix import reasons
from omitnix.adapters import _extract, php

#: Every code this project defines, and whether it means a table reference may be
#: missing. Written out rather than derived: the point is that adding a code forces
#: somebody to answer the question here, in one place, on purpose.
CLASSIFICATION: dict[str, bool] = {
    "dynamic_sql": True,
    "dynamic_table_name": True,
    "indirect_call_depth": True,
    "sql_unreadable": True,
    "sql_unsupported": True,
    "select_star": False,
    "table_not_in_schema": False,
    "dynamic_endpoint": False,
}


def _defined_codes() -> set[str]:
    return {
        value
        for name, value in vars(reasons).items()
        if name.isupper() and isinstance(value, str)
    }


def test_every_defined_reason_code_is_classified() -> None:
    assert _defined_codes() == set(CLASSIFICATION)
    for code, hides in CLASSIFICATION.items():
        assert reasons.hides_a_table_reference(code) is hides


def test_an_unclassified_code_counts_as_a_gap_rather_than_as_nothing() -> None:
    """The direction of the default, asserted on purpose.

    An adapter may define a code of its own -- ``omitnix/adapters/html.py`` does -- and
    the reverse index has to decide about it without having been told. Marking a table
    that turns out to be fine costs a look; not marking one costs the reading that
    nothing touches it.
    """
    assert reasons.hides_a_table_reference("a_reason_from_a_future_adapter") is True


def test_no_adapter_defines_a_reason_code_of_its_own_again() -> None:
    """Asserted against the source, because the values cannot tell you.

    ``php.DYNAMIC_SQL is reasons.DYNAMIC_SQL`` was the obvious test and is worthless:
    CPython interns every string that looks like an identifier, so the two copies this is
    about were already identical objects. Re-adding an assignment to either file has to be
    caught by reading the file.
    """
    names = {name for name, value in vars(reasons).items() if name.isupper()}
    for module in (_extract, php):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        assigned = {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        assert not assigned & names, f"{module.__name__} defines its own copy of a reason code"


def test_each_adapter_can_reach_every_code_not_only_the_ones_it_used_to_have() -> None:
    """Each of these lived in one of the two copies and not the other."""
    assert php.INDIRECT_CALL_DEPTH == reasons.INDIRECT_CALL_DEPTH
    assert _extract.SQL_UNSUPPORTED == reasons.SQL_UNSUPPORTED
    assert _extract.DYNAMIC_ENDPOINT == reasons.DYNAMIC_ENDPOINT
    assert reasons.INDIRECT_CALL_DEPTH in CLASSIFICATION
