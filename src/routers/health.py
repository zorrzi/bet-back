"""Health check for Railway (spec §11.5)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config.rate_limit import limiter
from src.database.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
@limiter.exempt  # type: ignore[untyped-decorator]  # Railway polls this; never 429 it
def health(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
