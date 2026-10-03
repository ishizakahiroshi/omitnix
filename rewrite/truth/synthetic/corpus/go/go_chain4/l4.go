package repo

func F4(db *sql.DB) {
    db.Query("SELECT id FROM orders")
}
