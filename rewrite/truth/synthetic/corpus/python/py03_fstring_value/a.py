def one(conn, oid):
    return conn.execute(f"SELECT total FROM orders WHERE id = {oid}").fetchone()

def named(conn, name):
    return conn.execute("SELECT id FROM customers WHERE name = '%s'" % name).fetchall()

def fmt(conn, oid):
    return conn.execute("SELECT id FROM invoices WHERE id = {}".format(oid)).fetchall()
