<?php
function tables(PDO $pdo) {
    $pdo->query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'shop'");
    return $pdo->query("SELECT id FROM orders")->fetchAll();
}
