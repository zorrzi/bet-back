"""Central application configuration.

Every tunable lives here and is read from the environment (or `.env` in dev).
Domain parameters (min_edge, kelly_multiplier, max_stake_pct) are config by
design — see spec §11.2: no magic constants spread through the code.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor .env to the repo root so uvicorn/alembic/pytest find it regardless
# of the process working directory (a CWD-relative path fails silently).
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- runtime ---
    environment: str = "dev"  # dev | test | prod
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/betting"
    cors_origins: str = "http://localhost:5173"  # comma-separated exact origins
    api_key: str = ""  # required in prod; protects write/job routes (X-API-Key)

    # --- external providers ---
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
    the_odds_api_key: str = ""
    the_odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    provider_timeout_seconds: float = 15.0

    # --- ingestion (Phase 1: one league) ---
    ingest_league_provider_id: str = "71"  # API-Football: Brasileirão Série A
    ingest_season: str = "2026"
    odds_sport_key: str = "soccer_brazil_campeonato"  # The Odds API sport key
    odds_regions: str = "eu"  # region(s) queried on The Odds API
    odds_markets: str = "h2h,totals"  # market keys queried on The Odds API
    # API-Football's free plan cannot see current seasons (2022-2024 only),
    # so upcoming matches are bootstrapped from The Odds API events and
    # results come from its /scores endpoint. Disable if a fixtures provider
    # with current-season access becomes the primary source (see ADR-0004).
    odds_autocreate_matches: bool = True
    scores_days_from: int = 3  # lookback window for the scores endpoint

    # --- domain reference data ---
    # comma-separated provider ids treated as sharp books (de-vig/CLV reference)
    sharp_bookmakers: str = "pinnacle"
    # how far back the mark-closing job looks for unmarked matches
    closing_lookback_days: int = 7

    # --- scheduler ---
    scheduler_enabled: bool = False
    fixtures_poll_minutes: int = 360
    # The Odds API free tier = 500 credits/month. Budget:
    #   odds: 2 credits/poll (2 markets x 1 region), 360 min => 4/day => ~240/mo
    #   scores: 2 credits/poll (daysFrom set), 720 min => 2/day => ~120/mo
    # total ~360/mo, leaving headroom for manual triggers.
    odds_poll_minutes: int = 360
    scores_poll_minutes: int = 720
    closing_poll_minutes: int = 5
    settle_poll_minutes: int = 30  # bets settlement (Phase 3+)

    # --- domain parameters (used from Phase 2/3 on; config from day one) ---
    min_edge: float = 0.03
    kelly_multiplier: float = 0.25
    max_stake_pct: float = 0.02
    devig_method: str = "multiplicative"  # multiplicative | shin | power
    initial_bankroll: float = 1000.0  # paper bankroll seeded on first use

    # --- modeling (Phase 2) ---
    # temporal decay per day for the Dixon-Coles likelihood
    # (0.0019/day ~= one-year half-life)
    dc_xi: float = 0.0019
    dc_max_goals: int = 10
    # only train on matches this recent: beyond ~4 years the decay weight is
    # ~0.06 anyway, and dropping defunct teams shrinks the parameter space
    dc_training_window_days: int = 1460
    # historical results + Pinnacle closing 1X2 (ADR-0005)
    fdcuk_csv_url: str = "https://www.football-data.co.uk/new/BRA.csv"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """Railway/Heroku expose postgres:// URLs; SQLAlchemy needs the driver."""
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sharp_bookmaker_set(self) -> set[str]:
        return {b.strip() for b in self.sharp_bookmakers.split(",") if b.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
