package repo

func Orders(db *sql.DB) {
    CountRows(db, "orders")
}
