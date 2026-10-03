def f4(conn):
    return conn.execute("SELECT id FROM orders").fetchall()
