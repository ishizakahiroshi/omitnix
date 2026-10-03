package repo

func Totals(db *sql.DB) {
    db.QueryRow(`
        SELECT c.id, SUM(o.total)
        FROM customers c
        JOIN orders o ON o.customer_id = c.id
        GROUP BY c.id`)
}
