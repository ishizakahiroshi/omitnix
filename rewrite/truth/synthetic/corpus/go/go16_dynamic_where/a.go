package repo

func ByName(db *sql.DB, name string) {
    db.Query("SELECT id FROM orders WHERE name = '" + name + "'")
    db.Exec(fmt.Sprintf("UPDATE customers SET flag = 1 WHERE id = %d", 3))
}
