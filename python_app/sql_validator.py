
import re
import sqlglot
from sqlglot import exp


def validate_sql(query):
    query = query.strip()

    if not query:
        return False, "Query is empty."

    # Remove one optional trailing semicolon.
    if query.endswith(";"):
        query = query[:-1].strip()

    # Reject multiple SQL statements.
    if ";" in query:
        return False, "Multiple SQL statements are not allowed."

    try:
        statements = sqlglot.parse(query, read="mysql")
    except sqlglot.errors.ParseError:
        return False, "Invalid SQL syntax."

    if len(statements) != 1 or statements[0] is None:
        return False, "Exactly one SQL statement is required."

    statement = statements[0]

    # Unwrap a SELECT query enclosed in parentheses.
    while isinstance(statement, exp.Subquery):
        statement = statement.this

    # Allow only read-only SELECT query structures.
    allowed_types = (
        exp.Select,
        exp.Union,
        exp.Intersect,
        exp.Except,
    )

    if not isinstance(statement, allowed_types):
        return False, "Only read-only SELECT queries are allowed."

    # Reject SELECT INTO.
    if any(isinstance(node, exp.Into) for node in statement.walk()):
        return False, "SELECT INTO is not allowed."

    normalized_query = " ".join(query.lower().split())

    # Reject the known incorrect product-revenue calculation,
    # but do not reject customer-spending queries.
    is_product_revenue_query = (
        "order_items" in normalized_query
        and "products" in normalized_query
        and bool(
            re.search(
                r"\bsum\s*\(\s*o\.total_amount\s*\)",
                normalized_query,
            )
        )
        and not bool(
            re.search(
                r"\bc\.customer_id\b",
                normalized_query,
            )
        )
    )

    if is_product_revenue_query:
        return (
            False,
            "Invalid product-revenue calculation. "
            "Use SUM(oi.quantity * oi.unit_price).",
        )

    # Detect when order_items is aliased as oi.
    order_items_aliased_as_oi = any(
        isinstance(table, exp.Table)
        and table.name.lower() == "order_items"
        and table.alias
        and table.alias.lower() == "oi"
        for table in statement.find_all(exp.Table)
    )

    # Reject references to the original table name after aliasing.
    if order_items_aliased_as_oi:
        for column in statement.find_all(exp.Column):
            if (
                column.table.lower() == "order_items"
                and column.name.lower() in ("quantity", "unit_price")
            ):
                return (
                    False,
                    "Invalid table alias. Use oi.quantity and oi.unit_price "
                    "when order_items is aliased as oi.",
                )

    return True, "Query passed SQL parsing and basic read-only checks."


if __name__ == "__main__":
    tests = [
        # Basic SELECT.
        "SELECT COUNT(*) FROM orders",

        # Modification query: must be rejected.
        "DELETE FROM orders",

        # Multiple statements: must be rejected.
        "SELECT * FROM orders; DROP TABLE orders;",

        # Ordinary SELECT.
        "SELECT * FROM orders",

        # Incorrect product-revenue calculation: must be rejected.
        (
            "SELECT p.product_name, SUM(o.total_amount) "
            "FROM products p "
            "JOIN order_items oi ON p.product_id = oi.product_id "
            "JOIN orders o ON o.order_id = oi.order_id "
            "GROUP BY p.product_name"
        ),

        # Correct product-revenue calculation: must be accepted.
        (
            "SELECT p.product_name, "
            "SUM(oi.quantity * oi.unit_price) AS total_revenue "
            "FROM products p "
            "JOIN order_items oi ON p.product_id = oi.product_id "
            "JOIN orders o ON o.order_id = oi.order_id "
            "WHERE o.status = 'Delivered' "
            "GROUP BY p.product_id, p.product_name"
        ),

        # Incorrect alias usage: must be rejected.
        (
            "SELECT p.product_name, "
            "SUM(order_items.quantity * order_items.unit_price) "
            "FROM products p "
            "JOIN order_items oi ON p.product_id = oi.product_id "
            "JOIN orders o ON o.order_id = oi.order_id "
            "GROUP BY p.product_name"
        ),

        # Parenthesized SELECT query.
        "(SELECT COUNT(*) FROM orders)",

        # Customer spending: must not trigger the product-revenue check.
        (
            "SELECT c.customer_id, "
            "SUM(o.total_amount) AS total_spent "
            "FROM customers c "
            "JOIN orders o ON c.customer_id = o.customer_id "
            "JOIN order_items oi ON o.order_id = oi.order_id "
            "JOIN products p ON oi.product_id = p.product_id "
            "WHERE o.status = 'Delivered' "
            "GROUP BY c.customer_id"
        ),
    ]

    for query in tests:
        valid, message = validate_sql(query)
        print(f"\nQuery: {query}")
        print(f"Valid: {valid} | {message}")
