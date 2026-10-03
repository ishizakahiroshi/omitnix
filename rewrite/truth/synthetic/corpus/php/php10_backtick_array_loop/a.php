<?php
function counts(PDO $pdo) {
    foreach (['orders', 'customers', 'invoices'] as $t) {
        $pdo->query("SELECT COUNT(*) FROM `$t`");
    }
}
