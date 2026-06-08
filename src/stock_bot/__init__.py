"""stock_bot package

Provides top-level package metadata and convenience helpers.
"""
from __future__ import annotations

__all__ = [
    "__version__",
    "configure_logging",
    "Settings",
]

__version__ = "0.1.0"

from .logging_config import configure_logging  # re-export
from .config.settings import Settings  # re-export

__all__.extend(["configure_logging", "Settings"])

def main() -> None:
    """Minimal entrypoint used by Docker and scripts.

    This prints a short health message and returns.
    """
    configure_logging()
    print("stock_bot package initialized (phase 1).")


if __name__ == "__main__":
    main()
