use diesel::prelude::*;

diesel::table! {
    orders (id) {
        id -> Integer,
        customer_id -> Integer,
    }
}

pub fn save(conn: &mut PgConnection, customer_id: i64) {
    diesel::insert_into(orders::table).values(customer_id).execute(conn);
}
