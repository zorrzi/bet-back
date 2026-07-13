"""Shared repository helpers."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.database import Base


def get_or_create[T: Base](
    session: Session,
    model: type[T],
    filters: dict[str, Any],
    defaults: dict[str, Any] | None = None,
) -> tuple[T, bool]:
    """Select by natural key; create+flush when missing. Returns
    (instance, created). Note: select-then-insert can race under concurrent
    writers (IntegrityError aborts one run) — acceptable for the MVP's
    single-process scheduler; the next idempotent run repairs it."""
    query = select(model).filter_by(**filters)
    instance = session.scalar(query)
    if instance is not None:
        return instance, False
    instance = model(**filters, **(defaults or {}))
    session.add(instance)
    session.flush()
    return instance, True
