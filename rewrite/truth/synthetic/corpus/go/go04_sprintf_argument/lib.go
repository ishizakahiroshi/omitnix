package repo

func CountRows(db *sql.DB, table string) {
    db.QueryRow(fmt.Sprintf("SELECT COUNT(*) FROM %s", table))
}
