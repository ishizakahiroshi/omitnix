<?php
/**
 * Deliberately unparsable: the run must fail rather than report a partial reading.
 */

function fetch_orders($db
{
    return $db->query('SELECT id FROM orders'
}
