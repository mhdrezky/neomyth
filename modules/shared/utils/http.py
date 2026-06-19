"""Shared HTTP client helpers."""

import httpx

from modules.shared.constants import (
    HTTP_CONNECT_TIMEOUT_SECONDS,
    HTTP_TIMEOUT_SECONDS,
)


def create_async_client() -> httpx.AsyncClient:
    """Create a configured async HTTP client for worker calls."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(
            HTTP_TIMEOUT_SECONDS,
            connect=HTTP_CONNECT_TIMEOUT_SECONDS,
        ),
        follow_redirects=True,
    )
