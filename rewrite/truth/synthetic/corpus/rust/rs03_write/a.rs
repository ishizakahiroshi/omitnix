pub fn settle(conn: &Connection, id: i64) {
    conn.execute("INSERT INTO payments (order_id) VALUES (?1)", [id]);
    conn.execute("UPDATE invoices SET paid = 1 WHERE id = ?1", [id]);
    conn.execute("DELETE FROM sessions WHERE order_id = ?1", [id]);
    conn.execute("INSERT INTO search_index (order_id) SELECT id FROM orders", []);
}
