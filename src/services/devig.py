"""De-vig: recover the market's fair probabilities from quoted odds (§5.1).

Quoted decimal odds embed the bookmaker's margin (vig/overround): the raw
implied probabilities 1/d sum to more than 1. These functions remove it.
Applied to the sharp book's line (Pinnacle), the result is the best
available estimate of the market's true probability — the baseline every
model probability is compared against, and the basis of de-vigged CLV.

All functions are pure and operate on plain floats.
"""

import math
from collections.abc import Sequence

MULTIPLICATIVE = "multiplicative"
SHIN = "shin"
POWER = "power"


def implied_probs(odds: Sequence[float]) -> list[float]:
    """Raw implied probabilities 1/d (they sum to the booksum, > 1)."""
    if any(d <= 1.0 for d in odds):
        raise ValueError(f"decimal odds must be > 1, got {list(odds)}")
    return [1.0 / d for d in odds]


def overround(odds: Sequence[float]) -> float:
    """Booksum minus 1: the margin embedded in the odds (e.g. 0.05 = 5%)."""
    return sum(implied_probs(odds)) - 1.0


def _complete_market_probs(odds: Sequence[float]) -> list[float]:
    """Implied probs plus the completeness guard: a booksum below 1 means
    selections are missing (suspended outcome, grouping bug). De-vigging a
    partial market silently fabricates probabilities — refuse instead."""
    raw = implied_probs(odds)
    if sum(raw) < 1.0 - 1e-9:
        raise ValueError(f"incomplete market: booksum {sum(raw):.4f} < 1 — missing selections?")
    return raw


def devig_multiplicative(odds: Sequence[float]) -> list[float]:
    """Proportional normalization: fair_i = (1/d_i) / booksum.

    The simplest method and the project default. Known bias: it slightly
    overstates favorites (the favourite-longshot bias lives in the margin
    distribution, which this method ignores).
    """
    raw = _complete_market_probs(odds)
    booksum = sum(raw)
    return [p / booksum for p in raw]


def devig_power(odds: Sequence[float], tolerance: float = 1e-12) -> list[float]:
    """Power method: find k so that sum((1/d_i)^k) = 1.

    Pushes more of the margin onto longshots than the multiplicative
    method, partially correcting the favourite-longshot bias.
    """
    raw = _complete_market_probs(odds)
    lo, hi = 1.0, 10.0  # booksum > 1 implies k > 1
    while sum(p**hi for p in raw) > 1.0:
        hi *= 2
        if hi > 1e6:
            raise ValueError("power de-vig failed to bracket the exponent")
    for _ in range(200):
        mid = (lo + hi) / 2
        total = sum(p**mid for p in raw)
        if abs(total - 1.0) < tolerance:
            break
        if total > 1.0:
            lo = mid
        else:
            hi = mid
    k = (lo + hi) / 2
    return [p**k for p in raw]


def devig_shin(odds: Sequence[float], tolerance: float = 1e-12) -> list[float]:
    """Shin's method: models the margin as protection against insider
    bettors (proportion z of informed money) and solves for z.

    fair_i = (sqrt(z^2 + 4(1-z) * raw_i^2 / booksum) - z) / (2(1-z))

    Reference: Shin (1992/1993); standard closed form with z found by
    bisection so the fair probabilities sum to 1.
    """
    raw = _complete_market_probs(odds)
    booksum = sum(raw)

    def fair_for(z: float) -> list[float]:
        return [
            (math.sqrt(z * z + 4.0 * (1.0 - z) * (p * p) / booksum) - z) / (2.0 * (1.0 - z))
            for p in raw
        ]

    lo, hi = 0.0, 0.5  # insider proportion is small; 50% is a safe ceiling
    for _ in range(200):
        mid = (lo + hi) / 2
        total = sum(fair_for(mid))
        if abs(total - 1.0) < tolerance:
            break
        if total > 1.0:
            lo = mid
        else:
            hi = mid
    return fair_for((lo + hi) / 2)


_METHODS = {
    MULTIPLICATIVE: devig_multiplicative,
    SHIN: devig_shin,
    POWER: devig_power,
}


def devig(odds: Sequence[float], method: str = MULTIPLICATIVE) -> list[float]:
    """De-vig `odds` with the configured method (settings.devig_method)."""
    try:
        return _METHODS[method](odds)
    except KeyError:
        raise ValueError(
            f"unknown de-vig method {method!r}; expected one of {sorted(_METHODS)}"
        ) from None
