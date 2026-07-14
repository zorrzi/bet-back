"""Value-bet signal generation (spec §5.3, Fase 3).

For every upcoming match with model predictions:

1. group the latest pre-now snapshots per (bookmaker, selection) for each
   market the model priced;
2. de-vig the SHARP book's complete market to get the fair probabilities
   (no sharp line -> no baseline -> no signal, by design);
3. compare the MODEL probability against the BEST offered odds across
   books: edge = p*d - 1 (push-aware on integer total lines);
4. emit a `value_bets` candidate only when edge > min_edge AND the Kelly
   fraction is positive — no value, no bet (spec §12).

Re-running expires the match's previous candidates first, so the feed
always reflects the latest capture.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.match import Match, MatchStatus
from src.models.odds import Bookmaker, Market, OddsSnapshot
from src.models.signals import ModelPrediction, ValueBet, ValueBetStatus
from src.repositories.betting_repository import BankrollRepository, ValueBetRepository
from src.services.devig import devig
from src.services.staking import edge as edge_of
from src.services.staking import kelly_fraction, suggested_stake

logger = logging.getLogger(__name__)

_SELECTION_ORDER = {
    "1X2": ("HOME", "DRAW", "AWAY"),
    "OU": ("OVER", "UNDER"),
    "BTTS": ("YES", "NO"),
}


@dataclass(frozen=True)
class SignalGenerationResult:
    matches_scanned: int
    signals_created: int
    candidates_expired: int


class ValueBetService:
    def __init__(
        self,
        session: Session,
        *,
        min_edge: float,
        kelly_multiplier: float,
        max_stake_pct: float,
        devig_method: str,
        initial_bankroll: Decimal,
    ) -> None:
        self._session = session
        self._min_edge = min_edge
        self._kelly_multiplier = kelly_multiplier
        self._max_stake_pct = max_stake_pct
        self._devig_method = devig_method
        self._value_bets = ValueBetRepository(session)
        self._bankroll = BankrollRepository(session, initial_bankroll)

    def generate_signals(self, now: datetime | None = None) -> SignalGenerationResult:
        now = now or datetime.now(UTC)
        matches = list(
            self._session.scalars(
                select(Match).where(
                    Match.status == MatchStatus.SCHEDULED, Match.kickoff_utc > now
                )
            )
        )
        bankroll = float(self._bankroll.current_balance(is_paper=True))
        created = 0
        expired = 0
        for match in matches:
            expired += self._value_bets.expire_candidates_for_match(match.id)
            created += self._generate_for_match(match, bankroll)
        self._session.commit()
        result = SignalGenerationResult(
            matches_scanned=len(matches),
            signals_created=created,
            candidates_expired=expired,
        )
        logger.info(
            "value_bets.generation_completed",
            extra={
                "matches_scanned": result.matches_scanned,
                "signals_created": result.signals_created,
                "candidates_expired": result.candidates_expired,
            },
        )
        return result

    def _generate_for_match(self, match: Match, bankroll: float) -> int:
        predictions = list(
            self._session.scalars(
                select(ModelPrediction).where(ModelPrediction.match_id == match.id)
            )
        )
        if not predictions:
            return 0
        by_market: dict[int, dict[str, ModelPrediction]] = {}
        for row in predictions:
            by_market.setdefault(row.market_id, {})[row.selection] = row

        created = 0
        for market_id, model_probs in by_market.items():
            market = self._session.get(Market, market_id)
            if market is None:
                continue
            created += self._generate_for_market(match, market, model_probs, bankroll)
        return created

    def _generate_for_market(
        self,
        match: Match,
        market: Market,
        model_probs: dict[str, ModelPrediction],
        bankroll: float,
    ) -> int:
        latest = self._latest_quotes(match.id, market.id)
        if not latest:
            return 0

        fair = self._fair_probs(market, latest)
        if fair is None:
            return 0  # no complete sharp line -> no honest baseline

        # push mass on integer total lines: 1 - P(over wins) - P(under wins)
        p_push = 0.0
        if len(model_probs) == 2 and market.code.startswith("OU_"):
            p_push = max(0.0, 1.0 - sum(float(p.model_prob) for p in model_probs.values()))

        created = 0
        for selection, prediction in model_probs.items():
            offers = [
                (bookmaker_id, snap)
                for (bookmaker_id, sel), snap in latest.items()
                if sel == selection
            ]
            if not offers or selection not in fair:
                continue
            best_bookmaker_id, best = max(offers, key=lambda o: o[1].price_decimal)
            p_model = float(prediction.model_prob)
            odds = float(best.price_decimal)
            edge_value = edge_of(p_model, odds, p_push)
            fraction = kelly_fraction(p_model, odds, p_push)
            if edge_value <= self._min_edge or fraction <= 0.0:
                continue
            stake = suggested_stake(
                bankroll,
                p_model,
                odds,
                kelly_multiplier=self._kelly_multiplier,
                max_stake_pct=self._max_stake_pct,
                p_push=p_push,
            )
            self._value_bets.add(
                ValueBet(
                    match_id=match.id,
                    market_id=market.id,
                    bookmaker_id=best_bookmaker_id,
                    selection=selection,
                    line=prediction.line,
                    model_prob=prediction.model_prob,
                    fair_prob=Decimal(f"{fair[selection]:.6f}"),
                    offered_odds=best.price_decimal,
                    edge=Decimal(f"{edge_value:.6f}"),
                    kelly_fraction=Decimal(f"{fraction:.6f}"),
                    suggested_stake=Decimal(f"{stake:.2f}"),
                    model_version=prediction.model_version,
                    status=ValueBetStatus.CANDIDATE,
                )
            )
            created += 1
        return created

    def _latest_quotes(
        self, match_id: int, market_id: int
    ) -> dict[tuple[int, str], OddsSnapshot]:
        """Latest snapshot per (bookmaker, selection) for one market."""
        latest: dict[tuple[int, str], OddsSnapshot] = {}
        for snap in self._session.scalars(
            select(OddsSnapshot)
            .where(OddsSnapshot.match_id == match_id, OddsSnapshot.market_id == market_id)
            .order_by(OddsSnapshot.captured_at)
        ):
            latest[(snap.bookmaker_id, snap.selection)] = snap
        return latest

    def _fair_probs(
        self, market: Market, latest: dict[tuple[int, str], OddsSnapshot]
    ) -> dict[str, float] | None:
        """De-vig the sharp book's market. None when no sharp book quotes
        ALL selections (partial markets are refused by devig, honestly)."""
        sharp_ids = set(
            self._session.scalars(select(Bookmaker.id).where(Bookmaker.is_sharp.is_(True)))
        )
        family = market.code.split("_")[0] if market.code != "1X2" else "1X2"
        order = _SELECTION_ORDER.get(family)
        if order is None:
            return None
        for sharp_id in sharp_ids:
            quotes = [latest.get((sharp_id, selection)) for selection in order]
            if any(q is None for q in quotes):
                continue
            odds = [float(q.price_decimal) for q in quotes if q is not None]
            try:
                fair = devig(odds, self._devig_method)
            except ValueError:
                continue
            return dict(zip(order, fair, strict=True))
        return None
