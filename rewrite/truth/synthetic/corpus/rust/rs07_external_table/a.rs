pub fn browse(conn: &Connection) {
    let name = std::env::args().nth(1).unwrap();
    conn.prepare(&format!("SELECT * FROM {}", name));
}
