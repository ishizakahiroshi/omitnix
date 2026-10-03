package repo

func ListOrders(db *sql.DB) {
    db.Query("SELECT id, total FROM orders WHERE total > 10")
}
