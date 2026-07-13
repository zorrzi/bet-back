from datetime import UTC, datetime
from typing import Any

import pytest

from src.config.settings import Settings
from src.models.match import MatchStatus
from src.providers import api_football
from src.providers.api_football import ApiFootballProvider
from src.providers.http import ProviderError


def _payload(status_short: str, goals: dict[str, Any]) -> dict[str, Any]:
    return {
        "errors": [],
        "response": [
            {
                "fixture": {
                    "id": 1234,
                    "date": "2026-07-20T13:00:00-03:00",
                    "status": {"short": status_short},
                },
                "league": {
                    "id": 71,
                    "name": "Serie A",
                    "country": "Brazil",
                    "season": 2026,
                },
                "teams": {
                    "home": {"id": 127, "name": "Flamengo"},
                    "away": {"id": 121, "name": "Palmeiras"},
                },
                "goals": goals,
            }
        ],
    }


@pytest.fixture
def provider() -> ApiFootballProvider:
    return ApiFootballProvider(Settings(api_football_key="test-key"))


def test_parses_fixture_and_converts_kickoff_to_utc(
    provider: ApiFootballProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        api_football, "get_json", lambda *a, **k: _payload("NS", {"home": None, "away": None})
    )
    fixtures = provider.fetch_fixtures("71", "2026")
    assert len(fixtures) == 1
    fixture = fixtures[0]
    assert fixture.provider_id == "1234"
    assert fixture.kickoff_utc == datetime(2026, 7, 20, 16, 0, tzinfo=UTC)
    assert fixture.status == MatchStatus.SCHEDULED
    assert fixture.home_team_name == "Flamengo"
    assert fixture.home_goals is None


def test_finished_fixture_carries_result(
    provider: ApiFootballProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        api_football, "get_json", lambda *a, **k: _payload("FT", {"home": 2, "away": 1})
    )
    fixture = provider.fetch_fixtures("71", "2026")[0]
    assert fixture.status == MatchStatus.FINISHED
    assert (fixture.home_goals, fixture.away_goals) == (2, 1)


def test_provider_errors_raise(
    provider: ApiFootballProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        api_football,
        "get_json",
        lambda *a, **k: {"errors": {"token": "Invalid API key"}, "response": []},
    )
    with pytest.raises(ProviderError):
        provider.fetch_fixtures("71", "2026")


def test_malformed_fixture_is_skipped_not_fatal(
    provider: ApiFootballProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _payload("NS", {"home": None, "away": None})
    payload["response"].append({"fixture": {"id": 9}})  # missing everything else
    monkeypatch.setattr(api_football, "get_json", lambda *a, **k: payload)
    assert len(provider.fetch_fixtures("71", "2026")) == 1
