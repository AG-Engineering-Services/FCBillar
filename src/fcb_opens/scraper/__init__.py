"""Scrapers for FCB web pages."""

from . import classificacio, ranking
from .http import fetch

__all__ = ["ranking", "classificacio", "fetch"]
