<?php
function live(PDO $pdo) {
    $pdo->query("SELECT id FROM orders WHERE note = 'a -- b' AND url = 'http://shop.test/c'");
    $pdo->query("SELECT id FROM invoices WHERE memo = '/* x */' AND tag = '#vip'");
    $pdo->query("SELECT id FROM customers"); // trailing comment
}
