<?php
// Fictional example: every rule in this directory should fire somewhere in this file.
// It is the "before" half of the pair, kept so the rules can be run against something.

function export_orders(array $input, $conn): array
{
    // No require_session() in this function body -> omitnix-query-without-session
    $rows = run_query('SELECT id, total FROM orders', $input);

    // Raw SQL against customers -> omitnix-direct-customer-table-access
    $names = $conn->rawQuery('SELECT name FROM customers');

    // No apply_visibility_filter() in this function body -> omitnix-unfiltered-listing
    return list_rows($rows, $names);
}

function rebuild_report(): array
{
    require_session();

    // Documented bypass, called from a request path -> omitnix-authorization-bypass-call
    return fetch_orders_unfiltered();
}
