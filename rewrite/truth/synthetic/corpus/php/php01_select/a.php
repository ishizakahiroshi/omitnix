<?php
function listOrders(PDO $pdo) {
    return $pdo->query("SELECT id, total FROM orders WHERE total > 10")->fetchAll();
}
