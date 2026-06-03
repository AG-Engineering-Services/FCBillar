"""FastAPI HTTP layer for fcb-opens.

Importing this subpackage pulls in fastapi + pydantic, so keep it out
of hot paths if you only need the core scraper/generator logic.
"""

from .app import app, create_app

__all__ = ["app", "create_app"]
