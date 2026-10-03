pub fn recent(conn: &Connection) {
    conn.prepare("WITH recent AS (SELECT id FROM orders) SELECT * FROM recent");
    conn.prepare("SELECT table_name FROM information_schema.tables");
}
