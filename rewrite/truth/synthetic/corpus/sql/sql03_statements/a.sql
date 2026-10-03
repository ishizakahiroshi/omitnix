INSERT INTO search_index (order_id, total)
SELECT id, total FROM orders;
UPDATE invoices SET paid = 1 WHERE id IN (SELECT invoice_id FROM payments);
DELETE FROM sessions WHERE expires < NOW();
WITH recent AS (SELECT id FROM orders WHERE id > 5) SELECT * FROM recent;
SELECT table_name FROM information_schema.tables;
