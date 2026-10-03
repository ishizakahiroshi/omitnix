def open_orders(conn):
    return conn.execute('SELECT id FROM orders WHERE status = \'open\'').fetchall()
