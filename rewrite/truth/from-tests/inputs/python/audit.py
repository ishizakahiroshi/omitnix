"""Read and stamp the audit trail."""

from example import db


def recent(limit):
    return db.execute(f"SELECT * FROM audit_log ORDER BY id DESC LIMIT {limit}")


def mark_seen(row_id):
    db.execute(f"UPDATE audit_log SET seen = 1 WHERE id = {row_id}")
