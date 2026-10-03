<?php
/**
 * Summarise orders for the dashboard.
 */

require_once __DIR__ . '/common/reports.php';

$totals = order_totals($db);
