"""Leagues, teams and players (spec §4.1).

`provider_id` columns carry the external provider's identifier and are the
idempotency key for ingestion upserts (spec §11.5).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database.database import Base


class League(Base):
    __tablename__ = "leagues"
    __table_args__ = (UniqueConstraint("provider_id", "season"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    sport: Mapped[str] = mapped_column(Text, default="football", server_default="football")
    season: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("provider_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("provider_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    # nullable: players transfer between teams
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    position: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
