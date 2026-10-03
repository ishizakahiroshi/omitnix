package repo

func Browse(db *sql.DB, r *http.Request) {
    db.Query("SELECT * FROM " + r.URL.Query().Get("table"))
}
