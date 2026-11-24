"""MySQL/TiDB connection configuration shared by dashboard and AI queries."""

from __future__ import annotations

import mysql.connector

from config import as_bool, get_setting


def open_mysql_connection(*, user: str, password: str):
    host = str(get_setting("MYSQL_HOST", "localhost")).strip()
    port = int(get_setting("MYSQL_PORT", "3306"))
    database = str(get_setting("MYSQL_DATABASE", "ecommerce_analytics")).strip()

    if not host:
        raise RuntimeError("MYSQL_HOST is not configured.")
    if not user:
        raise RuntimeError("A database user is not configured.")
    if password is None or password == "":
        raise RuntimeError("A database password is not configured.")

    config = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
        "connection_timeout": 15,
        "use_pure": True,
    }

    # TiDB Cloud Starter requires TLS on its public endpoint. Local MySQL
    # remains non-TLS by default, preserving the existing local workflow.
    default_ssl = host.lower().endswith("tidbcloud.com")
    ssl_enabled = as_bool(get_setting("MYSQL_SSL"), default=default_ssl)
    if ssl_enabled:
        import certifi

        config["ssl_verify_cert"] = True
        config["ssl_verify_identity"] = True
        config["ssl_ca"] = str(
            get_setting("MYSQL_SSL_CA", certifi.where())
        )

    return mysql.connector.connect(**config)
