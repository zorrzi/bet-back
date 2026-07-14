from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.competition import League, Team
from src.models.match import Match, MatchStatus
from src.models.odds import Bookmaker, Market, OddsSnapshot
from src.models.signals import ModelPrediction
from src.services.modeling.dixon_coles import MODEL_VERSION, NotEnoughDataError
from src.services.prediction_service import PredictionService, UnknownTeamsError

NOW = datetime(2026, 7, 14, tzinfo=UTC)


def _seed_league_with_history(
    session: Session, n_teams: int = 6, rounds: int = 4
) -> list[Team]:
    """A small league with enough finished matches to fit the model."""
    rng = np.random.default_rng(7)
    league = League(provider_id="fdcuk:BRA", season="2025", name="Serie A", country="Brazil")
    session.add(league)
    session.flush()
    teams = [
        Team(provider_id=f"t{i}", name=f"Team {i}", league_id=league.id) for i in range(n_teams)
    ]
    session.add_all(teams)
    session.flush()
    day = 0
    for _ in range(rounds):
        for i, home in enumerate(teams):
            for j, away in enumerate(teams):
                if i == j:
                    continue
                day += 1
                session.add(
                    Match(
                        provider_id=f"hist-{day}",
                        league_id=league.id,
                        home_team_id=home.id,
                        away_team_id=away.id,
                        kickoff_utc=NOW - timedelta(days=400 - day),
                        status=MatchStatus.FINISHED,
                        home_goals=int(rng.poisson(1.5)),
                        away_goals=int(rng.poisson(1.1)),
                    )
                )
    session.commit()
    return teams


def _upcoming_match(session: Session, teams: list[Team]) -> Match:
    match = Match(
        provider_id="toa:up1",
        league_id=teams[0].league_id,
        home_team_id=teams[0].id,
        away_team_id=teams[1].id,
        kickoff_utc=NOW + timedelta(days=3),
        status=MatchStatus.SCHEDULED,
    )
    session.add(match)
    session.commit()
    return match


def test_predict_upcoming_writes_versioned_predictions(session: Session) -> None:
    teams = _seed_league_with_history(session)
    _upcoming_match(session, teams)

    service = PredictionService(session, xi=0.001)
    result = service.predict_upcoming(now=NOW)

    assert result.model_version == MODEL_VERSION
    assert result.matches_predicted == 1
    assert result.matches_skipped == 0
    rows = list(session.scalars(select(ModelPrediction)))
    assert result.predictions_written == len(rows)
    assert all(r.model_version == MODEL_VERSION for r in rows)

    # 1X2 probabilities are a distribution
    market_1x2 = session.scalar(select(Market).where(Market.code == "1X2"))
    assert market_1x2 is not None
    probs_1x2 = [float(r.model_prob) for r in rows if r.market_id == market_1x2.id]
    assert len(probs_1x2) == 3
    assert sum(probs_1x2) == pytest.approx(1.0, abs=1e-4)

    # BTTS present with YES/NO summing to 1
    market_btts = session.scalar(select(Market).where(Market.code == "BTTS"))
    assert market_btts is not None
    probs_btts = [float(r.model_prob) for r in rows if r.market_id == market_btts.id]
    assert sum(probs_btts) == pytest.approx(1.0, abs=1e-4)

    # default OU 2.5 line was predicted (no odds lines exist for the match)
    market_ou = session.scalar(select(Market).where(Market.code == "OU_2_5"))
    assert market_ou is not None


def test_repredicting_replaces_not_duplicates(session: Session) -> None:
    teams = _seed_league_with_history(session)
    _upcoming_match(session, teams)
    service = PredictionService(session, xi=0.001)
    first = service.predict_upcoming(now=NOW)
    second = service.predict_upcoming(now=NOW)

    rows = list(session.scalars(select(ModelPrediction)))
    assert len(rows) == first.predictions_written == second.predictions_written


def test_ou_lines_follow_the_match_odds(session: Session) -> None:
    teams = _seed_league_with_history(session)
    match = _upcoming_match(session, teams)
    bookmaker = Bookmaker(provider_id="pinnacle", name="Pinnacle", is_sharp=True)
    market = Market(code="OU_3", name="Over/Under 3.0", category="totals", n_selections=2)
    session.add_all([bookmaker, market])
    session.flush()
    session.add(
        OddsSnapshot(
            match_id=match.id,
            bookmaker_id=bookmaker.id,
            market_id=market.id,
            selection="OVER",
            line=Decimal("3.0"),
            price_decimal=Decimal("2.30"),
            captured_at=NOW,
        )
    )
    session.commit()

    PredictionService(session, xi=0.001).predict_upcoming(now=NOW)

    ou_rows = [r for r in session.scalars(select(ModelPrediction)) if r.line is not None]
    assert {str(r.line.normalize()) for r in ou_rows} == {"3"}
    # integer line: OVER + UNDER < 1 because the push (exactly 3 goals) is real
    total = sum(float(r.model_prob) for r in ou_rows)
    assert total < 0.999


def test_quarter_lines_are_excluded_from_predictions(session: Session) -> None:
    """2.25/2.75 are split bets; a single P(win) misprices them (Phase 3
    handles them by decomposition). Only half/integer lines are predicted."""
    teams = _seed_league_with_history(session)
    match = _upcoming_match(session, teams)
    bookmaker = Bookmaker(provider_id="pinnacle", name="Pinnacle", is_sharp=True)
    m225 = Market(code="OU_2_25", name="O/U 2.25", category="totals", n_selections=2)
    m30 = Market(code="OU_3", name="O/U 3.0", category="totals", n_selections=2)
    session.add_all([bookmaker, m225, m30])
    session.flush()
    for market, line in ((m225, Decimal("2.25")), (m30, Decimal("3.0"))):
        session.add(
            OddsSnapshot(
                match_id=match.id,
                bookmaker_id=bookmaker.id,
                market_id=market.id,
                selection="OVER",
                line=line,
                price_decimal=Decimal("1.90"),
                captured_at=NOW,
            )
        )
    session.commit()

    PredictionService(session, xi=0.001).predict_upcoming(now=NOW)

    predicted_lines = {
        str(r.line.normalize())
        for r in session.scalars(select(ModelPrediction))
        if r.line is not None
    }
    assert predicted_lines == {"3"}  # 2.25 excluded


def test_unknown_team_is_skipped_in_batch_and_raises_single(session: Session) -> None:
    teams = _seed_league_with_history(session)
    stranger = Team(provider_id="toa:new", name="Newcomer FC", league_id=teams[0].league_id)
    session.add(stranger)
    session.flush()
    match = Match(
        provider_id="toa:up2",
        league_id=teams[0].league_id,
        home_team_id=stranger.id,
        away_team_id=teams[1].id,
        kickoff_utc=NOW + timedelta(days=2),
        status=MatchStatus.SCHEDULED,
    )
    session.add(match)
    session.commit()

    service = PredictionService(session, xi=0.001)
    result = service.predict_upcoming(now=NOW)
    assert result.matches_skipped == 1

    model = service.fit(NOW)
    with pytest.raises(UnknownTeamsError):
        service.predict_match(match, model)


def test_fit_without_history_raises(session: Session) -> None:
    with pytest.raises(NotEnoughDataError):
        PredictionService(session, xi=0.001).fit(NOW)
