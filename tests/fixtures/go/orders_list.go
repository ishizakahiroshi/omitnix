// Package orders lists orders for the signed-in customer.
//
// Every name in this file is invented. It exists to be analyzed, not to run.
package orders

import "database/sql"

// Load returns the caller's orders.
func Load(db *sql.DB, customerID int) (*sql.Rows, error) {
	requireSession()
	applyVisibilityFilter(customerID)

	const query = `
		SELECT o.id, c.name
		FROM orders AS o
		JOIN customers AS c ON c.id = o.customer_id
		WHERE o.customer_id = ?
	`
	return db.Query(query, customerID)
}
