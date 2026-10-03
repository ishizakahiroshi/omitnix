package repo

func F3(db *sql.DB) {
    db.Query("SELECT id FROM orders")
}
