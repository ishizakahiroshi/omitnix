pub fn f1(conn: &Connection) {
    conn.prepare("SELECT id FROM orders");
}
