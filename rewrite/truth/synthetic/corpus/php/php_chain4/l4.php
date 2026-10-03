<?php
function f4(PDO $pdo) {
    return $pdo->query("SELECT id FROM orders")->fetchAll();
}
