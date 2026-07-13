from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from src.config.settings import Settings
from src.providers import the_odds_api
from src.providers.the_odds_api import TheOddsApiProvider, format_line


def _event_payload() -> list[dict[str, Any]]:
    return [
        {
            "id": "abc123",
            "sport_key": "soccer_brazil_campeonato",
            "commence_time": "2026-07-20T16:00:00Z",
            "home_team": "Flamengo",
            "away_team": "Palmeiras",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Flamengo", "price": 2.10},
                                {"name": "Palmeiras", "price": 3.60},
                                {"name": "Draw", "price": 3.40},
                            ],
                        },
                        {
                            "key": "totals",
                            "outcomes": [
                                {"name": "Over", "price": 1.95, "point": 2.5},
                                {"name": "Under", "price": 1.87, "point": 2.5},
                            ],
                        },
                        {
                            "key": "spreads",
                            "outcomes": [
                                {"name": "Flamengo", "price": 1.90, "point": -0.5},
                                {"name": "Palmeiras", "price": 1.92, "point": 0.5},
                            ],
                        },
                    ],
                }
            ],
        }
    ]


@pytest.fixture
def provider() -> TheOddsApiProvider:
    return TheOddsApiProvider(Settings(the_odds_api_key="test-key"))


def test_format_line() -> None:
    assert format_line(Decimal("2.5")) == "2_5"
    assert format_line(Decimal("-0.5")) == "-0_5"
    assert format_line(Decimal("1")) == "1"


def test_parses_event_and_normalizes_markets(
    provider: TheOddsApiProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(the_odds_api, "get_json", lambda *a, **k: _event_payload())
    events = provider.fetch_odds("soccer_brazil_campeonato", "eu", "h2h,totals,spreads")
    assert len(events) == 1
    event = events[0]
    assert event.kickoff_utc == datetime(2026, 7, 20, 16, 0, tzinfo=UTC)
    assert len(event.quotes) == 7

    h2h = [q for q in event.quotes if q.market_code == "1X2"]
    assert {q.selection for q in h2h} == {"HOME", "DRAW", "AWAY"}
    home = next(q for q in h2h if q.selection == "HOME")
    assert home.price_decimal == Decimal("2.1")
    assert home.n_selections == 3
    assert home.bookmaker_provider_id == "pinnacle"

    totals = [q for q in event.quotes if q.market_code == "OU_2_5"]
    assert {q.selection for q in totals} == {"OVER", "UNDER"}
    assert all(q.line == Decimal("2.5") for q in totals)

    # both spread outcomes share ONE market keyed by the home handicap,
    # and both store the SAME line so (market, line) is consistent
    spreads = [q for q in event.quotes if q.market_code.startswith("AH_")]
    assert {q.market_code for q in spreads} == {"AH_-0_5"}
    assert {q.line for q in spreads} == {Decimal("-0.5")}


def test_zero_spread_yields_single_market_code(
    provider: TheOddsApiProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """point 0 spreads: negating Decimal('0') gives Decimal('-0'); both sides
    must land in ONE market ('AH_0'), never 'AH_0' + 'AH_-0'."""
    payload = _event_payload()
    payload[0]["bookmakers"][0]["markets"] = [
        {
            "key": "spreads",
            "outcomes": [
                {"name": "Flamengo", "price": 1.90, "point": 0},
                {"name": "Palmeiras", "price": 1.92, "point": 0},
            ],
        }
    ]
    monkeypatch.setattr(the_odds_api, "get_json", lambda *a, **k: payload)
    events = provider.fetch_odds("soccer_brazil_campeonato", "eu", "spreads")
    assert {q.market_code for q in events[0].quotes} == {"AH_0"}
    assert {q.line for q in events[0].quotes} == {Decimal("0")}


def test_malformed_price_skips_event_not_run(
    provider: TheOddsApiProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _event_payload()
    payload[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = None
    monkeypatch.setattr(the_odds_api, "get_json", lambda *a, **k: payload)
    events = provider.fetch_odds("soccer_brazil_campeonato", "eu", "h2h")
    assert events == []  # bad event dropped; fetch itself survives


def test_parses_scores_payload(
    provider: TheOddsApiProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = [
        {
            "id": "abc123",
            "commence_time": "2026-07-20T16:00:00Z",
            "completed": True,
            "home_team": "Flamengo",
            "away_team": "Palmeiras",
            "scores": [
                {"name": "Flamengo", "score": "2"},
                {"name": "Palmeiras", "score": "1"},
            ],
        },
        {
            "id": "def456",
            "commence_time": "2026-07-21T16:00:00Z",
            "completed": False,
            "home_team": "Cruzeiro",
            "away_team": "Bahia",
            "scores": None,  # not started yet
        },
    ]
    monkeypatch.setattr(the_odds_api, "get_json", lambda *a, **k: payload)
    scores = provider.fetch_scores("soccer_brazil_campeonato", 3)

    assert len(scores) == 2
    done = scores[0]
    assert done.completed is True
    assert (done.home_score, done.away_score) == (2, 1)
    assert done.kickoff_utc == datetime(2026, 7, 20, 16, 0, tzinfo=UTC)
    pending = scores[1]
    assert pending.completed is False
    assert pending.home_score is None


def test_unknown_outcome_names_are_skipped(
    provider: TheOddsApiProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _event_payload()
    payload[0]["bookmakers"][0]["markets"][0]["outcomes"].append(
        {"name": "Unrelated Team", "price": 9.0}
    )
    monkeypatch.setattr(the_odds_api, "get_json", lambda *a, **k: payload)
    events = provider.fetch_odds("soccer_brazil_campeonato", "eu", "h2h")
    assert len(events[0].quotes) == 7  # the stray outcome was ignored
