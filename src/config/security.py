"""Write-route protection (spec §11.1 — MVP single-user).

All mutating routes (POST /bets, /jobs/*, /backtests, /matches/{id}/predict)
require the X-API-Key header matching settings.api_key. In dev, an empty
api_key disables the check to keep local iteration frictionless; in prod an
empty key is a startup error (see app lifespan).
"""

import hmac

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from src.config.settings import Settings, get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    provided: str | None = Security(_api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    if settings.environment != "prod" and not settings.api_key:
        return
    # constant-time comparison: a plain != leaks matching-prefix length timing
    if not provided or not hmac.compare_digest(provided, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
