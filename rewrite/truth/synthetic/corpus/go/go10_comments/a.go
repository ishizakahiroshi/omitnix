package repo

// db.Exec("DELETE FROM sessions")
func Live(db *sql.DB) {
    db.Query("SELECT id FROM customers") // was: SELECT id FROM payments
    db.Query("SELECT id FROM orders WHERE url = 'http://shop.test/c' AND note = 'a -- b'")
    /* db.Exec("UPDATE ledger_entries SET posted = 1") */
}
