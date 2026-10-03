package repo

func Counts(db *sql.DB) {
    for _, t := range []string{"orders", "customers"} {
        db.QueryRow(fmt.Sprintf("SELECT COUNT(*) FROM %s", t))
    }
}
