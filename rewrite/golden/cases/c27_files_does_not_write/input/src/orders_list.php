<?php
/**
 * List orders for the signed-in customer.
 *
 * @param int $customer_id
 */

require_once __DIR__ . '/common/queries.php';

require_session();
apply_visibility_filter($viewer);

$rows = fetch_orders($db, $viewer);
