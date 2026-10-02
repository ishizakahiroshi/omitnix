//! Reads the audit log from a string the query builder is given.

use diesel::prelude::*;

pub fn recent(conn: &mut PgConnection) {
    require_session();
    let _ = diesel::sql_query("SELECT id FROM audit_log WHERE actor = $1");
}
