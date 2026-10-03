pub fn counts(conn: &Connection) {
    for t in ["orders", "customers"] {
        conn.query_row(&format!("SELECT COUNT(*) FROM {}", t), [], |r| r.get(0));
    }
}
