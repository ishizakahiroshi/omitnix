-- A file whose second statement the parser accepts only as an opaque command. Its
-- tables are not in the index, and the file has to say so rather than look like a file
-- that touches only what the first statement touches.

SELECT id FROM customers WHERE id = 1;

OPTIMIZE TABLE orders;
