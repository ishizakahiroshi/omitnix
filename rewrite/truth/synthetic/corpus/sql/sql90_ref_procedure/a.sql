DELIMITER //
CREATE PROCEDURE close_orders()
BEGIN
  UPDATE orders SET status = 'closed' WHERE status = 'paid';
END //
DELIMITER ;
