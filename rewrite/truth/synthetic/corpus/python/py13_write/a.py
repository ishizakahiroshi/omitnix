def settle(conn, i):
    conn.execute("INSERT INTO payments (order_id) VALUES (?)", (i,))
    conn.execute("UPDATE invoices SET paid = 1 WHERE id = ?", (i,))
    conn.execute("DELETE FROM sessions WHERE order_id = ?", (i,))
    conn.execute("INSERT INTO search_index (order_id) SELECT id FROM orders")
