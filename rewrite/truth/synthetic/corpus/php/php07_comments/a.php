<?php
// $pdo->query("SELECT * FROM coupons");
# $pdo->query("DELETE FROM sessions");
/* $pdo->exec("UPDATE ledger_entries SET posted = 1"); */
function live(PDO $pdo) {
    $pdo->query("SELECT id FROM customers"); // was: SELECT id FROM payments
    return $pdo->query("SELECT id FROM orders")->fetchAll();
}
