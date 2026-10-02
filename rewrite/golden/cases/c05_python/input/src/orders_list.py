"""List orders for the signed-in customer.

Every name in this file is invented. It exists to be analyzed, not to run.

:param customer_id: which customer's orders to list
"""

from example import apply_visibility_filter, db, require_session


def load(customer_id):
    require_session()
    apply_visibility_filter(customer_id)
    return db.execute(
        "SELECT o.id, c.name FROM orders AS o "
        "JOIN customers AS c ON c.id = o.customer_id "
        "WHERE o.customer_id = %s",
        (customer_id,),
    )
