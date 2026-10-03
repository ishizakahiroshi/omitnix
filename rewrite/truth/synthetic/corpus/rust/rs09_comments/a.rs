// conn.execute("DELETE FROM sessions", []);
/// conn.execute("SELECT * FROM coupons", []);
pub fn live(conn: &Connection) {
    conn.prepare("SELECT id FROM customers"); // was: SELECT id FROM payments
    conn.prepare("SELECT id FROM orders WHERE url = 'http://shop.test/c' AND note = 'a -- b'");
    /* conn.execute("UPDATE ledger_entries SET posted = 1", []); */
}
