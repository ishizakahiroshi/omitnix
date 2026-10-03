<?php
function upsert(PDO $pdo) {
    $pdo->exec("MERGE INTO customers AS t USING staging_customers AS s ON t.id = s.id
                WHEN MATCHED THEN UPDATE SET t.name = s.name");
}
