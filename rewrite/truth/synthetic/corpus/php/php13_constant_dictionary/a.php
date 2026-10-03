<?php
const REPORT_TABLES = ['sales' => 'orders', 'billing' => 'invoices'];

function report(PDO $pdo, string $kind) {
    $t = REPORT_TABLES[$kind];
    return $pdo->query("SELECT COUNT(*) FROM $t")->fetchAll();
}
