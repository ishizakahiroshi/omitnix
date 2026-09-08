<?php

declare(strict_types=1);

/**
 * List orders for the signed-in customer.
 *
 * Written the way a modern PHP file is: strict types first, then the docblock.
 */

require_once __DIR__ . '/common/queries.php';

function list_declared_orders(): array
{
    require_session();
    return fetch_customer_orders();
}
