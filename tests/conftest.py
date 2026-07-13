"""Shared fixtures. Tests run on an isolated in-memory SQLite database.

Note on timezones: SQLite stores tz-aware datetimes correctly for comparison
but returns them naive (UTC). Production Postgres (timestamptz) returns them
aware. Tests therefore never assert on tzinfo of round-tripped values.
"""

import os

# Must be set before any src import (settings are cached at first use).
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SCHEDULER_ENABLED"] = "false"

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.database import Base


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    yield db
    db.close()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    from src.app import create_app
    from src.database.database import get_db

    app = create_app()

    def _override_get_db() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
