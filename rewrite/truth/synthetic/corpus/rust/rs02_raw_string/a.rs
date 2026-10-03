pub async fn totals(pool: &PgPool) {
    sqlx::query(r#"
        SELECT c.id, SUM(o.total)
        FROM customers c
        JOIN orders o ON o.customer_id = c.id
        GROUP BY c.id"#)
        .fetch_all(pool)
        .await;
}
