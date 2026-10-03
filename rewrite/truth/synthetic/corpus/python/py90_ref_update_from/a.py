def refresh(conn):
    conn.execute("UPDATE orders SET total = s.total FROM staging_orders s WHERE s.id = orders.id")
