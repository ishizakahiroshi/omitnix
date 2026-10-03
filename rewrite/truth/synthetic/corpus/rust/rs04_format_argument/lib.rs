pub fn count_rows(conn: &Connection, table: &str) {
    conn.query_row(&format!("SELECT COUNT(*) FROM {}", table), [], |r| r.get(0));
}
