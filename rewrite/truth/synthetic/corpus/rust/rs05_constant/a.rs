const LEDGER: &str = "ledger_entries";

pub fn postings(conn: &Connection) {
    conn.prepare(&format!("SELECT * FROM {} WHERE posted = 1", LEDGER));
}
