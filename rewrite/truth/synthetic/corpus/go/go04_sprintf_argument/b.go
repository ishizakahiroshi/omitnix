package repo

func Customers(db *sql.DB) {
    CountRows(db, "customers")
}
