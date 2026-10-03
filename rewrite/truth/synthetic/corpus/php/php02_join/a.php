<?php
function ordersWithCustomers(PDO $pdo) {
    $sql = "SELECT o.id, c.name
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            LEFT JOIN coupons cp ON cp.id = o.coupon_id";
    return $pdo->query($sql)->fetchAll();
}
