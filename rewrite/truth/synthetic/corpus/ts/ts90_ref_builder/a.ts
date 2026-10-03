export function listOrders(knex: Knex) {
  return knex("orders").select("id").where({ status: "open" });
}
