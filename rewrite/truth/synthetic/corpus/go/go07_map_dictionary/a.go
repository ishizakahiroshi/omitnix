package repo

var reportTables = map[string]string{"sales": "orders", "billing": "invoices"}

func Report(db *sql.DB, kind string) {
    t := reportTables[kind]
    db.QueryRow("SELECT COUNT(*) FROM " + t)
}
