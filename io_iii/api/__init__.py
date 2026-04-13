"""
io_iii.api — Phase 9 HTTP transport adapter (ADR-025).

Exports the FastAPI application instance for use by the serve command
and by test clients.

Usage:
    from io_iii.api import app          # FastAPI app
    from io_iii.api.app import app      # equivalent
"""
from io_iii.api.app import app

__all__ = ["app"]
