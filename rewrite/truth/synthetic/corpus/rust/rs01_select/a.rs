pub fn list_orders(conn: &Connection) {
    conn.prepare("SELECT id, total FROM orders WHERE total > 10");
}
