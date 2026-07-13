"""The migration chain must build the full §4 schema from scratch and be
reversible. Runs against a throwaway SQLite file; CI runs it on every push."""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

EXPECTED_TABLES = {
    "leagues",
    "teams",
    "players",
    "matches",
    "match_stats",
    "player_match_stats",
    "lineups",
    "bookmakers",
    "markets",
    "odds_snapshots",
    "model_predictions",
    "value_bets",
    "bets",
    "bankroll_history",
    "backtest_runs",
}


@pytest.fixture
def alembic_config(tmp_path: Path) -> tuple[Config, str]:
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config, url


def test_upgrade_head_creates_full_schema(alembic_config: tuple[Config, str]) -> None:
    config, url = alembic_config
    command.upgrade(config, "head")

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert tables >= EXPECTED_TABLES


def test_downgrade_base_removes_everything(alembic_config: tuple[Config, str]) -> None:
    config, url = alembic_config
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert not (EXPECTED_TABLES & tables)
