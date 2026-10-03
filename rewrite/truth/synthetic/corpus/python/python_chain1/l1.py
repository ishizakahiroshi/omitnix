def f1(conn):
    return conn.execute("SELECT id FROM orders").fetchall()
