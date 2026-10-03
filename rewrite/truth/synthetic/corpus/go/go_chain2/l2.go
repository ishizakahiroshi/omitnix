package repo

func F2(db *sql.DB) {
    db.Query("SELECT id FROM orders")
}
