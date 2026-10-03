def f3(conn):
    return conn.execute("SELECT id FROM orders").fetchall()
