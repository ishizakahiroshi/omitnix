"""The vocabulary of reasons the analyzer could not follow something.

One definition, in the core rather than in an adapter, for two reasons.

*The strings are a shared key.* Every ``Unresolved`` a reader groups, counts or filters
by code is only coherent because two adapters that mean the same thing spell it the same
way. They were defined twice -- once in ``adapters/_extract.py`` and once in
``adapters/php.py`` -- with each copy holding a code the other lacked, which is a
divergence nothing would have reported.

*The core reads them now.* The reverse index has to decide, per file, whether an
unresolved statement could be hiding a table reference (see
:func:`hides_a_table_reference`), and a judgement written against one of two copies would
have silently ignored everything the other one emitted.

An adapter may still define a code of its own -- ``omitnix/adapters/html.py`` does, for
things only an HTML document can fail at -- and the classification below is written so
that an unclassified code is handled conservatively rather than assumed harmless.
"""

from __future__ import annotations

__all__ = [
    "DYNAMIC_ENDPOINT",
    "DYNAMIC_SQL",
    "DYNAMIC_TABLE_NAME",
    "INDIRECT_CALL_DEPTH",
    "SELECT_STAR",
    "SQL_UNREADABLE",
    "SQL_UNSUPPORTED",
    "TABLE_NOT_IN_SCHEMA",
    "NOT_A_TABLE_GAP",
    "hides_a_table_reference",
]

#: SQL assembled at run time: what is written here is a fragment, not the statement.
DYNAMIC_SQL = "dynamic_sql"
#: The statement parsed, but the table name itself was a run-time value.
DYNAMIC_TABLE_NAME = "dynamic_table_name"
#: A request was made to an address assembled at run time.
DYNAMIC_ENDPOINT = "dynamic_endpoint"
#: A hop the adapter refuses to take, or an include it could not resolve.
INDIRECT_CALL_DEPTH = "indirect_call_depth"
#: The tables are known; the columns are not.
SELECT_STAR = "select_star"
#: It opened like SQL and sqlglot could not read it.
SQL_UNREADABLE = "sql_unreadable"
#: sqlglot accepted the statement only as an opaque command, so its tables are lost.
SQL_UNSUPPORTED = "sql_unsupported"
#: A table this file touches is absent from the configured schema snapshot.
TABLE_NOT_IN_SCHEMA = "table_not_in_schema"


#: Reasons that are known *not* to be about which tables a file touches.
#:
#: Each of the three named a table successfully; what it could not read is something
#: else. ``select_star`` has the tables and not the columns, ``table_not_in_schema`` has
#: the table and a disagreement with the snapshot about it, and ``dynamic_endpoint`` is
#: about a request address and never about SQL at all.
NOT_A_TABLE_GAP: frozenset[str] = frozenset(
    {SELECT_STAR, TABLE_NOT_IN_SCHEMA, DYNAMIC_ENDPOINT}
)


def hides_a_table_reference(code: str) -> bool:
    """Whether this reason means a table the file touches may be missing from its lists.

    Written as "anything but these three" rather than as a list of the codes that do
    qualify, and the direction is the point. The set of reasons is open -- an adapter may
    define its own, and adding one is meant to be cheap -- so a list of qualifying codes
    would quietly stop covering a new reason the day it was introduced, and the table
    index would go back to looking complete. A code nobody has classified is a reason
    nobody understood, and "it is fine" is the one reading this tool must not default to.

    The cost is the other direction: a reason about something unrelated marks tables it
    has nothing to do with. That mark says "go and look", which wastes a minute. The
    omission it replaces says "nothing reads this table", which is wrong.
    """
    return code not in NOT_A_TABLE_GAP
