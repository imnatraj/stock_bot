"""Environment-driven settings for stock_bot.

This module purposefully avoids external dependencies for Phase 1 and
validates required environment variables on construction.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Final


# Attempt to load a local .env file if present. This requires python-dotenv
# which is declared in `requirements.txt`. Loading is non-destructive: existing
# environment variables are not overridden.
try:
    from dotenv import load_dotenv  # type: ignore

    # load .env from project root (or current cwd); do not override existing env vars
    load_dotenv(override=False)
except Exception:
    # If dotenv isn't installed or loading fails, continue — env vars may be
    # provided by the environment (e.g., Docker, CI). We do not fail here to
    # keep the import surface forgiving; validation happens in `from_env`.
    pass


@dataclass(frozen=True)
class Settings:
    """Application settings read from environment variables.

    Raises:
        ValueError: if a required environment variable is missing or invalid.
    """

    MYSQL_HOST: Final[str]
    MYSQL_PORT: Final[int]
    MYSQL_DATABASE: Final[str]
    MYSQL_USER: Final[str]
    MYSQL_PASSWORD: Final[str]
    TELEGRAM_BOT_TOKEN: Final[str]
    TELEGRAM_CHAT_ID: Final[str]
    GOOGLE_SHEET_ID: Final[str]
    GEMINI_API_KEY: Final[str]

    @classmethod
    def from_env(cls) -> "Settings":
        def get(name: str, required: bool = True) -> str:
            val = os.getenv(name)
            if required and (val is None or val.strip() == ""):
                raise ValueError(f"Missing required environment variable: {name}")
            return val or ""

        host = get("MYSQL_HOST")
        port_raw = get("MYSQL_PORT")
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ValueError("MYSQL_PORT must be an integer") from exc

        google_sheet_id = os.getenv("GOOGLE_SHEET_ID") or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        if not google_sheet_id or google_sheet_id.strip() == "":
            raise ValueError("Missing required environment variable: GOOGLE_SHEET_ID or GOOGLE_SHEETS_SPREADSHEET_ID")

        return cls(
            MYSQL_HOST=host,
            MYSQL_PORT=port,
            MYSQL_DATABASE=get("MYSQL_DATABASE"),
            MYSQL_USER=get("MYSQL_USER"),
            MYSQL_PASSWORD=get("MYSQL_PASSWORD"),
            TELEGRAM_BOT_TOKEN=get("TELEGRAM_BOT_TOKEN"),
            TELEGRAM_CHAT_ID=get("TELEGRAM_CHAT_ID"),
            GOOGLE_SHEET_ID=google_sheet_id.strip(),
            GEMINI_API_KEY=get("GEMINI_API_KEY"),
        )

