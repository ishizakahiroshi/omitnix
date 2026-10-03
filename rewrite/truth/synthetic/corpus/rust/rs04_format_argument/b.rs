use crate::lib::count_rows;

pub fn customers(conn: &Connection) {
    count_rows(conn, "customers");
}
