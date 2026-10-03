class Invoices:
    TABLE = "invoices"

    def open(self, conn):
        return conn.execute(f"SELECT * FROM {self.TABLE} WHERE paid = 0").fetchall()

def table_name():
    return "shipments"

def shipped(conn):
    return conn.execute(f"SELECT * FROM {table_name()}").fetchall()
