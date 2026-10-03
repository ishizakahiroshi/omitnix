package repo

const ledgerTable = "ledger_entries"

func Postings(db *sql.DB) {
    db.Query("SELECT * FROM " + ledgerTable + " WHERE posted = 1")
}
