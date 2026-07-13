from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.odds import Bookmaker, Market, OddsSnapshot
from tests.helpers import KICKOFF, seed_match


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_matches_empty(client: TestClient) -> None:
    response = client.get("/matches")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []


def test_match_detail_and_404(client: TestClient, session: Session) -> None:
    match = seed_match(session)

    ok = client.get(f"/matches/{match.id}")
    assert ok.status_code == 200
    body = ok.json()
    assert body["home_team"]["name"] == "Flamengo"
    assert body["away_team"]["name"] == "Palmeiras"
    assert body["status"] == "scheduled"

    missing = client.get("/matches/99999")
    assert missing.status_code == 404


def test_list_matches_filters_by_status(client: TestClient, session: Session) -> None:
    seed_match(session)
    assert len(client.get("/matches?status=scheduled").json()["items"]) == 1
    assert len(client.get("/matches?status=finished").json()["items"]) == 0


def test_match_odds_returns_snapshot_series(client: TestClient, session: Session) -> None:
    match = seed_match(session)
    bookmaker = Bookmaker(provider_id="pinnacle", name="Pinnacle", is_sharp=True)
    market = Market(code="1X2", name="Match Result", category="match_result", n_selections=3)
    session.add_all([bookmaker, market])
    session.flush()
    for hours, price in ((6, "2.30"), (1, "2.10")):
        session.add(
            OddsSnapshot(
                match_id=match.id,
                bookmaker_id=bookmaker.id,
                market_id=market.id,
                selection="HOME",
                price_decimal=Decimal(price),
                captured_at=KICKOFF - timedelta(hours=hours),
            )
        )
    session.commit()

    response = client.get(f"/matches/{match.id}/odds")
    assert response.status_code == 200
    body = response.json()
    assert len(body["snapshots"]) == 2
    assert body["bookmakers"][0]["is_sharp"] is True
    assert body["markets"][0]["code"] == "1X2"
    # ordered by captured_at: oldest first
    prices = [s["price_decimal"] for s in body["snapshots"]]
    assert float(prices[0]) == 2.30
    assert float(prices[1]) == 2.10


def test_job_routes_require_api_key_when_configured(
    client: TestClient, session: Session
) -> None:
    from src.config.settings import Settings, get_settings

    app = client.app
    app.dependency_overrides[get_settings] = lambda: Settings(  # type: ignore[attr-defined]
        api_key="s3cret", database_url="sqlite://"
    )
    try:
        denied = client.post("/jobs/mark-closing")
        assert denied.status_code == 401

        wrong = client.post("/jobs/mark-closing", headers={"X-API-Key": "nope"})
        assert wrong.status_code == 401

        allowed = client.post("/jobs/mark-closing", headers={"X-API-Key": "s3cret"})
        assert allowed.status_code == 200
        assert allowed.json() == {"matches_processed": 0, "snapshots_marked": 0}
    finally:
        app.dependency_overrides.pop(get_settings)  # type: ignore[attr-defined]
