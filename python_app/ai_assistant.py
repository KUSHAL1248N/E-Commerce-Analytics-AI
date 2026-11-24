
import re

import requests

from config import get_setting
from sql_validator import validate_sql
from ai_db_connection import create_ai_connection


DATABASE_SCHEMA = """
Database: ecommerce_analytics

Tables and columns:
- customers(customer_id, first_name, last_name, email, phone, city, registration_date)
- categories(category_id, category_name)
- sellers(seller_id, seller_name, email, city, rating)
- products(product_id, product_name, category_id, seller_id, price, cost_price)
- inventory(inventory_id, product_id, stock_quantity, reorder_level)
- orders(order_id, customer_id, order_date, status, total_amount)
- order_items(order_item_id, order_id, product_id, quantity, unit_price)
- payments(payment_id, order_id, payment_date, payment_method, payment_status, amount)
- reviews(review_id, customer_id, product_id, rating, review_text, review_date)

Relationships:
- orders.customer_id -> customers.customer_id
- order_items.order_id -> orders.order_id
- order_items.product_id -> products.product_id
- products.category_id -> categories.category_id
- products.seller_id -> sellers.seller_id
- inventory.product_id -> products.product_id
- payments.order_id -> orders.order_id
- reviews.customer_id -> customers.customer_id
- reviews.product_id -> products.product_id

Important rules:
1. Generate exactly one MySQL SELECT query for supported questions.
2. Use only listed tables, columns, and relationships.
3. Never join sellers directly to orders. Join sellers -> products -> order_items -> orders.
4. For product-level revenue, use SUM(oi.quantity * oi.unit_price).
5. For delivered-order revenue, filter with o.status = 'Delivered'.
6. For total delivered-order revenue, return one aggregate unless a breakdown is requested.
7. Do not add payment filters unless explicitly requested.
8. Do not invent columns, tables, prediction scores, or model outputs.
9. Questions requiring unsupported predictions, such as customer churn or future sales forecasts, must return exactly:
UNSUPPORTED: This question requires a prediction method or model that is not available.
10. For ambiguous questions, use a reasonable interpretation only when supported by the schema.
11. Return SQL only for supported questions, without Markdown fences or explanations.

CUSTOMER SPENDING RULES:
- When asked about customers' actual spending or successful purchases,
  exclude cancelled orders unless the user explicitly requests all orders.
- Use o.status = 'Delivered' when the question specifically asks about
  delivered orders or completed sales.
- When calculating total spending from orders, use SUM(o.total_amount).
- When counting orders, use COUNT(DISTINCT o.order_id) if joins could
  duplicate order rows.
- Do not claim that a customer has the highest lifetime value unless
  the query calculates and ranks customer spending appropriately.
- When calculating customer spending and joining orders to order_items,
  calculate spending using SUM(oi.quantity * oi.unit_price), not
  SUM(o.total_amount), to avoid counting an order multiple times.
"""


def _ask_local_ollama(question):
    """Use the original local Ollama + Qwen 2.5 3B setup."""
    import ollama

    host = str(get_setting("OLLAMA_HOST", "http://localhost:11434"))
    model = str(get_setting("OLLAMA_MODEL", "qwen2.5:3b"))
    client = ollama.Client(host=host)
    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": DATABASE_SCHEMA},
            {"role": "user", "content": question},
        ],
        options={"temperature": 0.1, "num_predict": 512},
    )
    return response["message"]["content"].strip()


def _ask_cloudflare_workers_ai(question):
    """Use Cloudflare Workers AI for the hosted Streamlit deployment."""
    account_id = get_setting("CLOUDFLARE_ACCOUNT_ID")
    api_token = get_setting("CLOUDFLARE_API_TOKEN")
    model = str(
        get_setting(
            "CLOUDFLARE_MODEL",
            "@cf/qwen/qwen2.5-coder-32b-instruct",
        )
    )

    if not account_id or not api_token:
        raise RuntimeError(
            "Cloudflare AI is selected, but CLOUDFLARE_ACCOUNT_ID or "
            "CLOUDFLARE_API_TOKEN is missing from Streamlit Secrets."
        )

    try:
        max_tokens = int(get_setting("CLOUDFLARE_MAX_TOKENS", "512"))
    except (TypeError, ValueError):
        max_tokens = 512
    max_tokens = max(128, min(max_tokens, 1024))

    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{account_id}/ai/run/{model}"
    )
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [
            {"role": "system", "content": DATABASE_SCHEMA},
            {"role": "user", "content": question},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "top_p": 0.9,
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=(10, 90),
        )
    except requests.RequestException as error:
        raise RuntimeError(
            "Could not reach Cloudflare Workers AI. Check the app's "
            "internet connection and Cloudflare service status."
        ) from error

    try:
        response_data = response.json()
    except ValueError as error:
        raise RuntimeError(
            f"Cloudflare Workers AI returned a non-JSON response "
            f"(HTTP {response.status_code})."
        ) from error

    if not response.ok or response_data.get("success") is False:
        errors = response_data.get("errors") or []
        error_messages = [
            str(item.get("message", ""))
            for item in errors
            if isinstance(item, dict) and item.get("message")
        ]
        detail = "; ".join(error_messages) or "Request was rejected."
        raise RuntimeError(
            f"Cloudflare Workers AI request failed (HTTP "
            f"{response.status_code}): {detail}"
        )

    result = response_data.get("result") or {}
    generated_text = result.get("response")
    if not generated_text and isinstance(result.get("choices"), list):
        try:
            generated_text = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            generated_text = None

    if not isinstance(generated_text, str) or not generated_text.strip():
        raise RuntimeError(
            "Cloudflare Workers AI returned an empty response. "
            "Please try the question again."
        )

    return generated_text.strip()


def generate_sql(question):
    """Generate SQL with local Ollama or hosted Cloudflare Workers AI.

    Local development defaults to Ollama. The Streamlit deployment selects
    Cloudflare by setting AI_PROVIDER='cloudflare' in Streamlit Secrets.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Please enter a non-empty business question.")

    provider = str(get_setting("AI_PROVIDER", "ollama")).strip().lower()
    if provider == "ollama":
        return _ask_local_ollama(question)
    if provider == "cloudflare":
        return _ask_cloudflare_workers_ai(question)

    raise RuntimeError(
        "Unsupported AI_PROVIDER. Use 'ollama' locally or 'cloudflare' "
        "for the hosted deployment."
    )


def ask_ollama(question):
    """Backward-compatible alias used by older project scripts."""
    return generate_sql(question)


def get_ai_provider_label():
    provider = str(get_setting("AI_PROVIDER", "ollama")).strip().lower()
    if provider == "cloudflare":
        return "Cloudflare Workers AI · Qwen2.5-Coder 32B"
    return "Local Ollama · Qwen 2.5 3B"


def clean_sql(generated_sql):
    generated_sql = generated_sql.strip()

    # Remove optional Markdown fences.
    generated_sql = re.sub(
        r"^```(?:sql)?\s*",
        "",
        generated_sql,
        flags=re.IGNORECASE,
    )
    generated_sql = re.sub(r"\s*```$", "", generated_sql)

    return generated_sql.strip()


def execute_read_only_query(query):
    # Do not validate or execute unsupported responses as SQL.
    if query.strip().upper().startswith("UNSUPPORTED:"):
        return False, query.strip()

    connection = None
    cursor = None

    try:
        # Validate before connecting to the database.
        is_valid, message = validate_sql(query)

        if not is_valid:
            return False, message

        connection = create_ai_connection()
        cursor = connection.cursor()

        # Apply a MySQL execution time limit for this session.
        cursor.execute("SET SESSION MAX_EXECUTION_TIME = 5000")

        cursor.execute(query)

        if cursor.description is None:
            return False, "The query did not return a result set."

        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchmany(100)

        return True, {
            "columns": columns,
            "rows": rows,
            "truncated_possible": len(rows) == 100,
        }

    except Exception as error:
        return False, f"Query execution failed: {error}"

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    question = input("Ask your e-commerce analytics assistant: ")

    generated_response = clean_sql(generate_sql(question))

    if generated_response.upper().startswith("UNSUPPORTED:"):
        print("\nAI response:\n")
        print(generated_response)
        print("\nNo SQL query was executed.")

    else:
        print("\nGenerated SQL:\n")
        print(generated_response)

        success, result = execute_read_only_query(generated_response)

        if success:
            print("\nQuery results:")
            print("Columns:", result["columns"])

            for row in result["rows"]:
                print(row)

            if result["truncated_possible"]:
                print("Showing at most 100 rows.")

        else:
            print("\nQuery rejected or failed:")
            print(result)
