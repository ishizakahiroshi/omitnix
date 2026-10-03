pub async fn one(pool: &PgPool, id: i64) {
    sqlx::query!("SELECT total FROM orders WHERE id = $1", id)
        .fetch_one(pool)
        .await;
}
