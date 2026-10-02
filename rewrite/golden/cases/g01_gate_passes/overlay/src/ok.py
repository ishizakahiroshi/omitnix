"""Show one order to its owner."""

def show(order_id):
    require_session()
    apply_visibility_filter(order_id)
    return order_id
