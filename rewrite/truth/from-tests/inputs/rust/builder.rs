//! Writes an order through a query builder.

use diesel::prelude::*;
use sea_orm::EntityTrait;

diesel::table! {
    orders (id) {
        id -> Integer,
        customer_id -> Integer,
    }
}

pub fn save(conn: &mut PgConnection, customer_id: i64) {
    diesel::insert_into(orders::table)
        .values(customer_id)
        .execute(conn);
    let _rows = orders::table
        .filter(orders::customer_id.eq(customer_id))
        .load::<i64>(conn);
    let _found = orders::Entity::find().one(conn);
}
