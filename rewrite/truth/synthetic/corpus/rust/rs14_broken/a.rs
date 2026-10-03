pub fn oops(conn: &Connection) {
    conn.prepare("INSERT INTO (id, total VALUES (1");
}
