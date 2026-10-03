<?php
function byName(PDO $pdo, string $name) {
    return $pdo->query("SELECT id FROM orders WHERE name = '$name' AND total > " . $_GET['min'])->fetchAll();
}
function pick(PDO $pdo, array $ids) {
    return $pdo->query("UPDATE customers SET flag = 1 WHERE id IN (" . implode(',', $ids) . ")");
}
