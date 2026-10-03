//! Lists orders for the signed-in customer.
//!
//! Every name in this file is invented. It exists to be analyzed, not to run.

/// Load returns the caller's orders.
pub fn load(customer_id: i64) -> usize {
    session.require_session();
    auth::apply_visibility_filter(customer_id);

    let _query = r#"
        SELECT o.id, c.name
        FROM orders AS o
        JOIN customers AS c ON c.id = o.customer_id
        WHERE o.customer_id = $1
    "#;
    let _ = sqlx::query!(
        "SELECT id FROM orders WHERE customer_id = $1",
        customer_id,
    );
    let _ = r#"SELECT id FROM orders WHERE payload = '{"status":"open"}'"#;
    0
}
