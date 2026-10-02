<?php
/**
 * Show the audit log for one order.
 */

require_session();
apply_visibility_filter($viewer);

$rows = $db->query("SELECT * FROM audit_log WHERE order_id = $order_id");
$db->query('INSERT INTO audit_log (action) VALUES (1)');
