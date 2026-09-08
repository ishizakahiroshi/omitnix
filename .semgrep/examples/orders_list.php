<?php
// Fictional example: a listing endpoint that satisfies every rule in this directory.
// Nothing here is copied from a real codebase.

function list_customer_orders(array $input): array
{
    require_session();

    $query = apply_visibility_filter('SELECT id, placed_at FROM orders');
    return list_rows(run_query($query, $input));
}
