"""Build statements the unsafe way, so that the safe way can be told apart from it."""

from example import db


def by_status(status):
    # The value is put into the SQL text itself. This one is assembled at run time.
    return db.execute("SELECT id FROM orders WHERE status = '%s'" % status)


def by_actor(actor):
    return db.execute("SELECT id FROM audit_log WHERE actor = '{}'".format(actor))
