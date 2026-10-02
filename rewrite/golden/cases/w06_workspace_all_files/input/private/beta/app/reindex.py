# Nightly reindex of the order search table.
# Run from the scheduler; it takes no arguments.

from example import db


def run():
    db.execute("INSERT INTO search_index (order_id, term) SELECT id, name FROM orders")
