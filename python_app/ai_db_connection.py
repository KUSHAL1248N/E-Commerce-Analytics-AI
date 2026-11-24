from config import get_setting
from mysql_utils import open_mysql_connection


def create_ai_connection():
    """Connect using the separate least-privilege AI reader account."""
    return open_mysql_connection(
        user=str(get_setting("AI_MYSQL_USER", "ai_reader")),
        password=get_setting("AI_MYSQL_PASSWORD", ""),
    )
