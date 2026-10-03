def list_orders(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, total FROM orders WHERE total > 10")
    return cur.fetchall()
