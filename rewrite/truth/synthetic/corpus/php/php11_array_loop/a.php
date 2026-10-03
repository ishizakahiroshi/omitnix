<?php
function counts(PDO $pdo) {
    foreach (['orders', 'customers'] as $t) {
        $pdo->query("SELECT COUNT(*) FROM $t");
    }
}
