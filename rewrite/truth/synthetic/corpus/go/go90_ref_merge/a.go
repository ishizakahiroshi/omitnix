package repo

func Upsert(db *sql.DB) {
    db.Exec("MERGE INTO customers AS t USING staging_customers AS s ON t.id = s.id WHEN MATCHED THEN UPDATE SET t.name = s.name")
}
