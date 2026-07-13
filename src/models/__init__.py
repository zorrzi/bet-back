"""All ORM models. Import everything here so Base.metadata is complete
for Alembic autogenerate and for create_all in tests."""

from src.models.betting import BacktestRun, BankrollHistory, Bet, BetResult
from src.models.competition import League, Player, Team
from src.models.match import Lineup, Match, MatchStats, MatchStatus, PlayerMatchStats
from src.models.odds import Bookmaker, Market, MarketCategory, OddsSnapshot
from src.models.signals import ModelPrediction, ValueBet, ValueBetStatus

__all__ = [
    "BacktestRun",
    "BankrollHistory",
    "Bet",
    "BetResult",
    "Bookmaker",
    "League",
    "Lineup",
    "Market",
    "MarketCategory",
    "Match",
    "MatchStats",
    "MatchStatus",
    "ModelPrediction",
    "OddsSnapshot",
    "Player",
    "PlayerMatchStats",
    "Team",
    "ValueBet",
    "ValueBetStatus",
]
