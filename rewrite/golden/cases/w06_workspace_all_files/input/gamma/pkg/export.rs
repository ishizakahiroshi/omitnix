//! Removes rows from a table chosen by the caller.

pub fn purge(table: &str, cutoff: &str) {
    let _ = "DELETE FROM ".to_owned() + table + " WHERE created_at < $1";
    let _ = format!("SELECT * FROM audit_log WHERE actor = {}", cutoff);
    let _ = concat!(
        "INSERT INTO ",
        "search_index",
        " (order_id) SELECT id FROM orders"
    );
}
