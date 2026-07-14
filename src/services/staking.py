"""Staking math (spec §5.3): EV/edge and the Kelly criterion.

Pure functions over floats. The stored probabilities are P(bet WINS); for
markets with a push outcome (integer total lines) the caller passes
`p_push` and the formulas account for the returned stake.

Payout model per 1 unit staked at decimal odds d:
    win -> d, push -> 1, loss -> 0.
"""


def edge(p_win: float, odds: float, p_push: float = 0.0) -> float:
    """EV per unit staked: p_win*d + p_push*1 - 1 (spec: edge = p*d - 1
    when there is no push)."""
    _validate(p_win, odds, p_push)
    return p_win * odds + p_push - 1.0


def kelly_fraction(p_win: float, odds: float, p_push: float = 0.0) -> float:
    """Full-Kelly fraction f* = (p*d - 1) / (d - 1).

    With a push outcome, Kelly is applied to the push-conditioned bet (the
    stake is simply returned on a push, so the bet effectively happens only
    when it does not push): p' = p_win / (1 - p_push).

    Never negative: no value -> no bet (spec §12).
    """
    _validate(p_win, odds, p_push)
    if p_push >= 1.0 - 1e-12:
        return 0.0
    p_conditional = p_win / (1.0 - p_push)
    fraction = (p_conditional * odds - 1.0) / (odds - 1.0)
    return max(fraction, 0.0)


def suggested_stake(
    bankroll: float,
    p_win: float,
    odds: float,
    *,
    kelly_multiplier: float,
    max_stake_pct: float,
    p_push: float = 0.0,
) -> float:
    """Fractional-Kelly stake, capped per bet (spec §5.3: full Kelly with an
    overestimated p busts the bankroll — the fraction is non-negotiable)."""
    fraction = kelly_fraction(p_win, odds, p_push)
    stake = bankroll * kelly_multiplier * fraction
    return min(stake, bankroll * max_stake_pct)


def _validate(p_win: float, odds: float, p_push: float) -> None:
    if not 0.0 <= p_win <= 1.0:
        raise ValueError(f"p_win must be in [0, 1], got {p_win}")
    if not 0.0 <= p_push <= 1.0 or p_win + p_push > 1.0 + 1e-12:
        raise ValueError(f"invalid push probability {p_push} (p_win={p_win})")
    if odds <= 1.0:
        raise ValueError(f"decimal odds must be > 1, got {odds}")
