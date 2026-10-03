export async function one(db: Db, id: number) {
  return db.query(`SELECT total FROM orders WHERE id = ${id}`);
}

export async function many(db: Db, ids: number[]) {
  return db.query(`
    SELECT c.id
    FROM customers c
    JOIN orders o ON o.customer_id = c.id
    WHERE o.id IN (${ids.join(",")})`);
}
