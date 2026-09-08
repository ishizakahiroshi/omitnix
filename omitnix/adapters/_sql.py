"""Reading table names out of a SQL string.

There is no SQL parser here and there must never be one: sqlglot does the parsing, and
this module only decides which of the tables it found are read and which are written.

The distinction this module exists to protect is between *a table we saw* and *a table we
could not see*. A statement assembled at run time still usually shows some of its tables,
so the caller gets both the names and a flag saying the statement was incomplete. Dropping
either half would turn a partial reading into a confident blank.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Substituted for every run-time hole (an interpolated variable, a concatenated
#: expression, a printf conversion) so that the surrounding SQL still parses. A table
#: that resolves to this name is a table whose name is chosen at run time.
PLACEHOLDER = "omitnix_placeholder"

#: A candidate has to open with a DML keyword *and* reach that keyword's own clause.
#:
#: Testing for a keyword and a clause independently is not enough, because English hits
#: both: "Update your profile from the settings page" and "Delete an order from the list"
#: are a user-facing label and a heading, and sqlglot will happily read a table name out
#: of the second one. Pairing each keyword with the clause that must follow it rejects
#: both while still accepting lower-case SQL.
#:
#: The deliberate cost: MySQL's multi-table ``DELETE t1 FROM t1 JOIN t2`` does not match,
#: so it is not recognised as SQL at all. Widening the DELETE branch to allow a table
#: list before FROM is exactly what lets the prose back in.
_SQL_SHAPE = re.compile(
    r"""^[\s(;]*(
          SELECT\b[\s\S]{0,600}?\bFROM\b
        | (?:INSERT|REPLACE)\s+(?:\w+\s+){0,3}?INTO\b
        | UPDATE\b[\s\S]{0,300}?\bSET\b
        | DELETE\s+(?:LOW_PRIORITY\s+|QUICK\s+|IGNORE\s+)*FROM\b
        | WITH\b[\s\S]{0,300}?\bAS\s*\(
    )""",
    re.IGNORECASE | re.VERBOSE,
)

#: The opening keyword written the way SQL is conventionally written in source.
_UPPERCASE_OPENER = re.compile(r"^[\s(;]*(SELECT|INSERT|UPDATE|DELETE|REPLACE|WITH)\b")

#: Something only a query tends to carry. Required of a candidate whose keyword is not
#: upper-case, because "select the item from the shelf" matches the SELECT ... FROM shape
#: and sqlglot will read "shelf" out of it as a table. A phantom row in the reverse index
#: is worse than the cost of this test, which is that fully lower-case SQL with no clause
#: at all ("select id from orders") is not recognised.
_CLAUSE_EVIDENCE = re.compile(
    r"\b(WHERE|JOIN|VALUES|LIMIT|OFFSET|HAVING|UNION|DISTINCT|GROUP\s+BY|ORDER\s+BY)\b",
    re.IGNORECASE,
)

#: printf conversions, which make a string a template rather than a statement.
FORMAT_SPEC = re.compile(r"%(?:\d+\$)?[-+ 0#']*[\d.]*[bcdeEfFgGosuxX%]")

__all__ = [
    "PLACEHOLDER",
    "FORMAT_SPEC",
    "SqlReading",
    "looks_like_sql",
    "reads_as_written_sql",
    "read_sql",
]


@dataclass(frozen=True, slots=True)
class SqlReading:
    """What one SQL string turned out to say."""

    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    #: sqlglot understood the statement. False means the tables below are all we have.
    parsed: bool = False
    #: A ``SELECT *``: the tables are known, the columns are not.
    select_star: bool = False
    #: At least one table name was a run-time hole rather than an identifier.
    dynamic_table: bool = False
    #: Statements sqlglot accepted only as an opaque command, so their tables are lost.
    #: ``parsed`` is still True for these -- the file was read -- which is exactly why the
    #: count has to be reported: otherwise a statement nobody could read looks like a
    #: statement that touches no table.
    unsupported: int = 0


def reads_as_written_sql(text: str) -> bool:
    """Whether the opening keyword is upper-case, the way source code writes SQL.

    Used to decide whether a string the parser refused is worth reporting: prose that
    sqlglot cannot read is not a finding, it is prose.
    """
    return bool(_UPPERCASE_OPENER.match(text))


def looks_like_sql(text: str) -> bool:
    """Whether a string literal is worth handing to the SQL parser at all."""
    if not _SQL_SHAPE.match(text):
        return False
    return reads_as_written_sql(text) or bool(_CLAUSE_EVIDENCE.search(text))


def _parse(sql: str):
    """Parse with sqlglot, falling back to the MySQL dialect.

    The default dialect rejects MySQL's backtick quoting, which is exactly the quoting
    style a PHP codebase is most likely to use. Trying it second costs nothing when the
    first attempt already succeeded.
    """
    import sqlglot

    for dialect in (None, "mysql"):
        try:
            statements = sqlglot.parse(sql, read=dialect)
        except Exception:  # noqa: BLE001 - sqlglot raises several unrelated types
            continue
        if any(statement is not None for statement in statements):
            return statements
    return None


#: Where each kind of DDL statement keeps the object it acts on. Measured against
#: sqlglot 30.18.0 rather than assumed: ``DROP`` puts its target under ``tables``,
#: ``TRUNCATE`` under ``expressions``, and ``CREATE``/``ALTER`` under ``this``.
_DDL_TARGET_ARGS = ("this", "tables", "expressions")


def _tables_under(value, exp) -> list:
    if isinstance(value, exp.Expression):
        return list(value.find_all(exp.Table))
    if isinstance(value, list):
        return [table for item in value for table in _tables_under(item, exp)]
    return []


def _write_targets(statement, exp) -> set[int]:
    """The tables a statement writes to, identified by node identity.

    Identity rather than name: ``INSERT INTO orders SELECT ... FROM orders`` reads and
    writes the same name, and collapsing the two would lose one of them.

    DDL counts as a write. A migration that creates, alters, drops or truncates a table is
    the strongest possible statement that a file touches it, and leaving it out would file
    the migration under "reads" -- or, for ``DROP``, under nothing at all. The read side of
    a DDL statement survives: ``CREATE VIEW recent AS SELECT ... FROM orders`` keeps its
    target under ``this`` and its query under ``expression``, so ``orders`` stays a read.
    """
    if isinstance(statement, exp.Insert | exp.Update | exp.Delete):
        target = statement.this
        if target is None:
            return set()
        table = target if isinstance(target, exp.Table) else target.find(exp.Table)
        return {id(table)} if table is not None else set()

    if isinstance(statement, exp.Create | exp.Alter | exp.Drop | exp.TruncateTable):
        return {
            id(table)
            for key in _DDL_TARGET_ARGS
            for table in _tables_under(statement.args.get(key), exp)
        }

    return set()


def _selects_star(statement, exp) -> bool:
    for select in statement.find_all(exp.Select):
        for projection in select.expressions:
            if isinstance(projection, exp.Star):
                return True
            if isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star):
                return True
    return False


def read_sql(sql: str) -> SqlReading:
    """Read one SQL statement (or several, separated by ``;``)."""
    from sqlglot import expressions as exp

    statements = _parse(sql)
    if statements is None:
        return SqlReading(parsed=False)

    reads: set[str] = set()
    writes: set[str] = set()
    select_star = False
    dynamic_table = False
    unsupported = 0

    for statement in statements:
        if statement is None:
            continue
        if isinstance(statement, exp.Command):
            # sqlglot understood the statement's opening keyword and nothing else. It
            # holds no tables, so it must be counted rather than passed over: a file whose
            # every statement lands here would otherwise read as a file with no tables.
            unsupported += 1
            continue
        # A CTE name looks exactly like a table reference and is not one.
        cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
        targets = _write_targets(statement, exp)

        for table in statement.find_all(exp.Table):
            name = table.name
            if not name or name in cte_names:
                continue
            if name == PLACEHOLDER:
                dynamic_table = True
                continue
            (writes if id(table) in targets else reads).add(name)

        select_star = select_star or _selects_star(statement, exp)

    return SqlReading(
        reads=tuple(sorted(reads)),
        writes=tuple(sorted(writes)),
        parsed=True,
        select_star=select_star,
        dynamic_table=dynamic_table,
        unsupported=unsupported,
    )
