use crate::lib::count_rows;

pub fn orders(conn: &Connection) {
    count_rows(conn, "orders");
}
