from sqlalchemy import text

def totals(session):
    return session.execute(text('''
        SELECT c.id, SUM(o.total)
        FROM customers c
        JOIN orders o ON o.customer_id = c.id
        GROUP BY c.id
    ''')).all()
