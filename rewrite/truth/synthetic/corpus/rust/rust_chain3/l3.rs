pub fn f3(conn: &Connection) {
    conn.prepare("SELECT id FROM orders");
}
