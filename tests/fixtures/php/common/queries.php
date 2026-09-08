<?php
/**
 * Shared queries for the orders screens.
 */

function fetch_orders($db, $viewer)
{
    return $db->query(
        'SELECT orders.id, customers.name
           FROM orders
           JOIN customers ON customers.id = orders.customer_id'
    );
}

function purge_audit_log($db)
{
    return $db->query('DELETE FROM audit_log WHERE created_at < NOW()');
}
