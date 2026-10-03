<?php
function recent(PDO $pdo) {
    $sql = <<<SQL
SELECT id
FROM orders
-- JOIN coupons ON coupons.id = orders.coupon_id
WHERE id > 5
SQL;
    return $pdo->query($sql)->fetchAll();
}
