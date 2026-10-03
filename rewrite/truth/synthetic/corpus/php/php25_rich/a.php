<?php
function checkout(PDO $pdo, int $id) {
    $pdo->beginTransaction();
    $row = $pdo->query("SELECT total FROM orders WHERE id = $id")->fetch();
    $pdo->exec("INSERT INTO payments (order_id, amount) VALUES ($id, {$row['total']})");
    $pdo->exec("UPDATE orders SET status = 'paid' WHERE id = $id");
    $pdo->exec("INSERT INTO audit_log (message) SELECT CONCAT('paid ', id) FROM orders WHERE id = $id");
    $pdo->commit();
}
