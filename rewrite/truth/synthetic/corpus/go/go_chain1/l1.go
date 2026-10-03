package repo

func F1(db *sql.DB) {
    db.Query("SELECT id FROM orders")
}
