<?php
function f2(PDO $pdo) {
    return $pdo->query("SELECT id FROM orders")->fetchAll();
}
