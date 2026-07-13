"""Shared rate limiter. Module-level so routers can mark routes exempt
(e.g. /health, polled by Railway) with @limiter.exempt."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
