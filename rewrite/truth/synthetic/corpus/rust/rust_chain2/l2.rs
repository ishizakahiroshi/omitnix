pub fn f2(conn: &Connection) {
    conn.prepare("SELECT id FROM orders");
}
