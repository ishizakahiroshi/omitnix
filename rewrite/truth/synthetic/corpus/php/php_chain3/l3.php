<?php
function f3(PDO $pdo) {
    return $pdo->query("SELECT id FROM orders")->fetchAll();
}
