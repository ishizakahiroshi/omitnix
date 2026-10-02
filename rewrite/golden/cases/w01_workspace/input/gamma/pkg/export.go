// Package export removes rows from a table chosen by the caller.
package export

import (
	"database/sql"
	"fmt"
)

func Purge(db *sql.DB, table string, cutoff string) error {
	_, err := db.Exec("DELETE FROM " + table + " WHERE created_at < ?")
	if err != nil {
		return err
	}
	_, err = db.Exec(fmt.Sprintf("SELECT * FROM audit_log WHERE actor = %q LIMIT 1", cutoff))
	return err
}
