from ai_db_connection import create_ai_connection

connection = None

try:
    connection = create_ai_connection()

    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM orders")
    result = cursor.fetchone()

    print("AI database connection successful!")
    print("Total orders:", result[0])

    cursor.close()

except Exception as error:
    print("Database connection failed:", error)

finally:
    if connection is not None and connection.is_connected():
        connection.close()