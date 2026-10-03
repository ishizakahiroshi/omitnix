<?php
function settle(PDO $pdo, int $id) {
    $pdo->prepare("UPDATE invoices SET paid = 1 WHERE id = ?")->execute([$id]);
    $pdo->prepare("DELETE FROM sessions WHERE order_id = ?")->execute([$id]);
    $pdo->prepare("SELECT total FROM invoices WHERE id = ?")->execute([$id]);
}
