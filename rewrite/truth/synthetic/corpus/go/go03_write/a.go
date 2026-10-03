package repo

func Settle(db *sql.DB, id int) {
    db.Exec("INSERT INTO payments (order_id) VALUES (?)", id)
    db.Exec("UPDATE invoices SET paid = 1 WHERE id = ?", id)
    db.Exec("DELETE FROM sessions WHERE order_id = ?", id)
    db.Exec("INSERT INTO search_index (order_id) SELECT id FROM orders")
}
