package repo

func Peek(db *sql.DB, table string) {
    db.Query("SELECT * FROM " + table + " LIMIT 1")
}
