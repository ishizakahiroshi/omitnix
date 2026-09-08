<?php
/**
 * Report helpers. The statement lives one call further in on purpose.
 */

function order_totals($db)
{
    return $db->query(build_totals_sql());
}

function build_totals_sql()
{
    return 'SELECT COUNT(*) FROM orders';
}
