def f2(conn):
    return conn.execute("SELECT id FROM orders").fetchall()
