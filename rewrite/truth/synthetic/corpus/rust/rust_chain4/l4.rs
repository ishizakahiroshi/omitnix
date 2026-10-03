pub fn f4(conn: &Connection) {
    conn.prepare("SELECT id FROM orders");
}
