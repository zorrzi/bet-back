"""FastAPI application factory.

Wires CORS (explicit origins — never '*' in prod), rate limiting on public
routes, global error handling (no stack traces to clients), routers and the
optional in-process scheduler.
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.config.logging_config import setup_logging
from src.config.rate_limit import limiter
from src.config.settings import get_settings
from src.jobs.scheduler import build_scheduler
from src.routers import betting, health, jobs, matches

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.environment == "prod" and not settings.api_key:
        raise RuntimeError("API_KEY must be set in prod (write routes are protected).")
    if not settings.api_key:
        logger.warning(
            "security.write_routes_unprotected",
            extra={"environment": settings.environment},
        )
    scheduler = None
    if settings.scheduler_enabled:
        scheduler = build_scheduler(settings)
        scheduler.start()
        logger.info("scheduler.started")
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("scheduler.stopped")


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()

    app = FastAPI(
        title="Betting Value Analysis API",
        description=(
            "Disciplined betting analysis: EV signals vs de-vigged market "
            "probabilities, CLV as the primary metric. Analysis tool — no "
            "profit is promised."
        ),
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    # slowapi's handler signature is narrower than Starlette's protocol
    app.add_exception_handler(
        RateLimitExceeded,
        _rate_limit_exceeded_handler,  # type: ignore[arg-type]
    )

    # Error-catching middleware INSIDE CORS (registered before, so CORS wraps
    # it): Starlette's default Exception handler sits outside CORSMiddleware
    # and would return 500s without CORS headers, which browsers mask as
    # opaque network errors.
    @app.middleware("http")
    async def json_500_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            return await call_next(request)
        except Exception:
            logger.exception("unhandled_error", extra={"path": request.url.path})
            return JSONResponse(status_code=500, content={"detail": "Internal server error."})

    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    app.include_router(health.router)
    app.include_router(matches.router)
    app.include_router(betting.router)
    app.include_router(jobs.router)
    return app


app = create_app()
