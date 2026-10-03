<?php
function f1(PDO $pdo) {
    return $pdo->query("SELECT id FROM orders")->fetchAll();
}
