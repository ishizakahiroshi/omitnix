package repo

func Recent(db *sql.DB) {
    db.Query("WITH recent AS (SELECT id FROM orders) SELECT * FROM recent")
    db.Query("SELECT table_name FROM information_schema.tables")
}
