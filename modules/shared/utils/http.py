"""Shared HTTP client helpers."""

import httpx

from modules.shared.constants import (
    HTTP_CONNECT_TIMEOUT_SECONDS,
    HTTP_TIMEOUT_SECONDS,
    WEBHOOK_TIMEOUT_SECONDS,
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


async def post_webhook(url: str, payload: dict) -> bool:
    """Best-effort JSON POST to a caller-supplied webhook. Never raises.

    Redirects are not followed (a webhook target should answer directly).
    Returns True when the target responded with a 2xx.
    """
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                WEBHOOK_TIMEOUT_SECONDS,
                connect=HTTP_CONNECT_TIMEOUT_SECONDS,
            ),
            follow_redirects=False,
        ) as client:
            resp = await client.post(url, json=payload)
            return resp.is_success
    except Exception:
        return False
