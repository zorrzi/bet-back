"""Shared HTTP plumbing for providers: timeouts and retry with backoff
(spec §11.1). Retries only on transient failures (connect errors, 5xx, 429);
4xx client errors surface immediately."""

import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Raised when a provider call fails permanently."""


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


@retry(
    reraise=True,
    retry=retry_if_exception(_is_transient),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=30),
)
def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> Any:
    response = httpx.get(url, headers=headers, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()
