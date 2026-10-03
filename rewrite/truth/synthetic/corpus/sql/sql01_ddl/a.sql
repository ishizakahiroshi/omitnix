CREATE TABLE orders (id INT PRIMARY KEY, customer_id INT);
ALTER TABLE orders ADD COLUMN note VARCHAR(40);
RENAME TABLE legacy_orders TO archive_orders;
CREATE TABLE order_copy LIKE orders;
DROP TABLE IF EXISTS tmp_orders;
CREATE INDEX idx_customer ON payments (customer_id);
