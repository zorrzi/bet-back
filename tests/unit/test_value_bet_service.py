from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.odds import Bookmaker, Market, OddsSnapshot
from src.models.signals import ModelPrediction, ValueBet, ValueBetStatus
from src.services.value_bet_service import ValueBetService
from tests.helpers import KICKOFF, seed_match

NOW = KICKOFF - timedelta(days=1)


def _service(session: Session, min_edge: float = 0.03) -> ValueBetService:
    return ValueBetService(
        session,
        min_edge=min_edge,
        kelly_multiplier=0.25,
        max_stake_pct=0.02,
        devig_method="multiplicative",
        initial_bankroll=Decimal("1000"),
    )


def _seed_market_with_odds(
    session: Session,
    match_id: int,
    *,
    sharp_prices: tuple[str, str, str] = ("2.00", "3.60", "4.00"),
    soft_home_price: str = "2.20",
) -> Market:
    """Pinnacle quotes the full 1X2; a soft book offers a better HOME price."""
    pinnacle = Bookmaker(provider_id="pinnacle", name="Pinnacle", is_sharp=True)
    soft = Bookmaker(provider_id="soft", name="SoftBook", is_sharp=False)
    market = Market(code="1X2", name="Match Result", category="match_result", n_selections=3)
    session.add_all([pinnacle, soft, market])
    session.flush()
    for selection, price in zip(("HOME", "DRAW", "AWAY"), sharp_prices, strict=True):
        session.add(
            OddsSnapshot(
                match_id=match_id,
                bookmaker_id=pinnacle.id,
                market_id=market.id,
                selection=selection,
                price_decimal=Decimal(price),
                captured_at=NOW - timedelta(hours=1),
            )
        )
    session.add(
        OddsSnapshot(
            match_id=match_id,
            bookmaker_id=soft.id,
            market_id=market.id,
            selection="HOME",
            price_decimal=Decimal(soft_home_price),
            captured_at=NOW - timedelta(minutes=30),
        )
    )
    session.commit()
    return market


def _seed_predictions(
    session: Session, match_id: int, market_id: int, probs: dict[str, str]
) -> None:
    for selection, prob in probs.items():
        session.add(
            ModelPrediction(
                match_id=match_id,
                market_id=market_id,
                selection=selection,
                line=None,
                model_prob=Decimal(prob),
                model_version="dixoncoles_v1",
            )
        )
    session.commit()


def test_signal_created_with_best_odds_and_fair_prob(session: Session) -> None:
    match = seed_match(session)
    market = _seed_market_with_odds(session, match.id)
    # model: 52% home. Best offer = soft book 2.20 -> edge = .52*2.2-1 = .144
    _seed_predictions(
        session, match.id, market.id, {"HOME": "0.52", "DRAW": "0.26", "AWAY": "0.22"}
    )

    result = _service(session).generate_signals(now=NOW)

    assert result.signals_created >= 1
    signal = session.scalar(select(ValueBet).where(ValueBet.selection == "HOME"))
    assert signal is not None
    assert signal.offered_odds == Decimal("2.20")  # best price, not Pinnacle's
    assert float(signal.edge) == round(0.52 * 2.20 - 1, 6)
    # fair prob from de-vigged Pinnacle: 1/2.0 / (1/2 + 1/3.6 + 1/4) = 0.4864
    assert float(signal.fair_prob) == round((0.5) / (0.5 + 1 / 3.6 + 0.25), 6)
    assert signal.status == ValueBetStatus.CANDIDATE
    # fractional Kelly stake, capped at 2% of the 1000 bankroll
    assert Decimal("0") < signal.suggested_stake <= Decimal("20.00")


def test_no_signal_below_min_edge(session: Session) -> None:
    match = seed_match(session)
    market = _seed_market_with_odds(session, match.id, soft_home_price="2.00")
    # 51% at 2.00 -> edge 0.02 < min_edge 0.03
    _seed_predictions(
        session, match.id, market.id, {"HOME": "0.51", "DRAW": "0.27", "AWAY": "0.22"}
    )

    result = _service(session).generate_signals(now=NOW)

    assert result.signals_created == 0


def test_no_sharp_line_no_signal(session: Session) -> None:
    """Without a complete sharp market there is no honest fair baseline."""
    match = seed_match(session)
    soft = Bookmaker(provider_id="soft", name="SoftBook", is_sharp=False)
    market = Market(code="1X2", name="Match Result", category="match_result", n_selections=3)
    session.add_all([soft, market])
    session.flush()
    session.add(
        OddsSnapshot(
            match_id=match.id,
            bookmaker_id=soft.id,
            market_id=market.id,
            selection="HOME",
            price_decimal=Decimal("3.00"),
            captured_at=NOW - timedelta(hours=1),
        )
    )
    _seed_predictions(
        session, match.id, market.id, {"HOME": "0.50", "DRAW": "0.28", "AWAY": "0.22"}
    )

    result = _service(session).generate_signals(now=NOW)

    assert result.signals_created == 0


def test_regeneration_expires_previous_candidates(session: Session) -> None:
    match = seed_match(session)
    market = _seed_market_with_odds(session, match.id)
    _seed_predictions(
        session, match.id, market.id, {"HOME": "0.52", "DRAW": "0.26", "AWAY": "0.22"}
    )
    service = _service(session)
    service.generate_signals(now=NOW)
    service.generate_signals(now=NOW)

    statuses = [vb.status for vb in session.scalars(select(ValueBet))]
    assert statuses.count(ValueBetStatus.CANDIDATE) == 1
    assert statuses.count(ValueBetStatus.EXPIRED) == 1
