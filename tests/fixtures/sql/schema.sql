-- The fictional schema these fixtures share.

CREATE TABLE orders (
  id INT PRIMARY KEY,
  customer_id INT NOT NULL,
  name VARCHAR(120) NOT NULL
);

CREATE TABLE customers (
  id INT PRIMARY KEY,
  name VARCHAR(120) NOT NULL
);

CREATE INDEX orders_by_customer ON orders (customer_id);

CREATE OR REPLACE VIEW search_index AS
  SELECT o.id AS order_id, o.name AS term FROM orders AS o;
