pub fn peek(conn: &Connection, table: &str) {
    conn.prepare(&format!("SELECT * FROM {} LIMIT 1", table));
}
