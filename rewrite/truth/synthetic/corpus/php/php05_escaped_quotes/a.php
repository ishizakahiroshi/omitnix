<?php
function openOrders(PDO $pdo) {
    return $pdo->query('SELECT id FROM orders WHERE status = \'open\'')->fetchAll();
}
function namedCustomers(PDO $pdo) {
    return $pdo->query("SELECT id FROM customers WHERE name = \"Ann\"")->fetchAll();
}
