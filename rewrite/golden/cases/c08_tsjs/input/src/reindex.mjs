// Nightly reindex of the order search table.

import { db } from "./db.mjs";

export async function run() {
  await db.execute(
    "INSERT INTO search_index (order_id, term) SELECT id, name FROM orders"
  );
}
