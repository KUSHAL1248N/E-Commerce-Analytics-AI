"""Shared configuration for local development and Streamlit Community Cloud.

Local values are loaded from .env. On Streamlit Community Cloud, values are
read from st.secrets. Environment variables take precedence in both cases.
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def get_setting(name: str, default: Any = None) -> Any:
    """Read a setting from environment variables, then Streamlit secrets."""
    value = os.getenv(name)
    if value not in (None, ""):
        return value

    try:
        import streamlit as st

        value = st.secrets.get(name)
        if value not in (None, ""):
            return value
    except Exception:
        # Streamlit secrets are unavailable during plain CLI/local execution.
        pass

    return default


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
