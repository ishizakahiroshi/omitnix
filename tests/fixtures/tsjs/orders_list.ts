// List orders for the signed-in customer.
//
// Every name in this file is invented. It exists to be analyzed, not to run.

import { applyVisibilityFilter, requireSession } from "./session";

export async function load(customerId: number): Promise<Response> {
  requireSession();
  applyVisibilityFilter(customerId);
  return fetch("/api/orders");
}

export async function loadOne(orderId: number): Promise<Response> {
  return fetch(`/api/orders/${orderId}`);
}
