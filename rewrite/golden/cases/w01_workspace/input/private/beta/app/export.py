"""Export rows from a table chosen by the caller."""

from example import db


def purge(table, cutoff):
    db.execute("DELETE FROM " + table + " WHERE created_at < %s", (cutoff,))
