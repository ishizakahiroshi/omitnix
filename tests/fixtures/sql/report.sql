-- Orders with the customer who placed them.

SELECT o.id, c.name
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE o.customer_id = 1;
