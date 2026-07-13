"""Matches (fixtures), post-match stats and lineups (spec §4.1)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.database import Base
from src.models.competition import Team


class MatchStatus:
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        Index("ix_matches_kickoff_utc", "kickoff_utc"),
        Index("ix_matches_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[str] = mapped_column(Text, unique=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id"))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default=MatchStatus.SCHEDULED)
    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # joined-eager by default: match listings always need both team names
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id], lazy="joined")
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id], lazy="joined")


class MatchStats(Base):
    __tablename__ = "match_stats"
    __table_args__ = (UniqueConstraint("match_id", "team_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    shots: Mapped[int | None] = mapped_column(Integer)
    shots_on_target: Mapped[int | None] = mapped_column(Integer)
    corners: Mapped[int | None] = mapped_column(Integer)
    fouls: Mapped[int | None] = mapped_column(Integer)
    yellow_cards: Mapped[int | None] = mapped_column(Integer)
    red_cards: Mapped[int | None] = mapped_column(Integer)
    possession: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    xg: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))


class PlayerMatchStats(Base):
    __tablename__ = "player_match_stats"
    __table_args__ = (UniqueConstraint("match_id", "player_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    minutes: Mapped[int | None] = mapped_column(Integer)
    goals: Mapped[int | None] = mapped_column(Integer)
    assists: Mapped[int | None] = mapped_column(Integer)
    shots: Mapped[int | None] = mapped_column(Integer)
    shots_on_target: Mapped[int | None] = mapped_column(Integer)
    fouls_committed: Mapped[int | None] = mapped_column(Integer)
    fouls_drawn: Mapped[int | None] = mapped_column(Integer)
    yellow_cards: Mapped[int | None] = mapped_column(Integer)
    red_cards: Mapped[int | None] = mapped_column(Integer)


class Lineup(Base):
    __tablename__ = "lineups"
    __table_args__ = (UniqueConstraint("match_id", "player_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    is_starter: Mapped[bool] = mapped_column(Boolean, default=False)
