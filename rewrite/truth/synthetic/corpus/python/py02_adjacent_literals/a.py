def joined(conn):
    return conn.execute(
        "SELECT o.id FROM orders o "
        "JOIN customers c ON c.id = o.customer_id "
        "WHERE c.active = 1"
    ).fetchall()
