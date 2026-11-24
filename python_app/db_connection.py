from config import get_setting
from mysql_utils import open_mysql_connection


def create_connection():
    """Connect to the analytics database using the dashboard read-only user."""
    return open_mysql_connection(
        user=str(get_setting("MYSQL_USER", "")),
        password=get_setting("MYSQL_PASSWORD", ""),
    )
