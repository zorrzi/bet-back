"""Staking math validated against hand-calculated cases (spec §11.3)."""

import pytest

from src.services.staking import edge, kelly_fraction, suggested_stake

# Hand case: p = 0.55, d = 2.00
#   edge  = 0.55*2.0 - 1 = 0.10
#   kelly = (0.55*2.0 - 1)/(2.0 - 1) = 0.10


def test_edge_hand_case() -> None:
    assert edge(0.55, 2.0) == pytest.approx(0.10)


def test_edge_negative_when_no_value() -> None:
    assert edge(0.45, 2.0) == pytest.approx(-0.10)


def test_edge_with_push_hand_case() -> None:
    # OU integer line: p_win=0.40, p_push=0.20, d=2.10
    # edge = 0.40*2.10 + 0.20 - 1 = 0.04
    assert edge(0.40, 2.10, p_push=0.20) == pytest.approx(0.04)


def test_kelly_hand_case() -> None:
    assert kelly_fraction(0.55, 2.0) == pytest.approx(0.10)


def test_kelly_never_negative() -> None:
    # no value -> no bet (spec §12)
    assert kelly_fraction(0.40, 2.0) == 0.0


def test_kelly_with_push_uses_conditional_probability() -> None:
    # p_win=0.40, p_push=0.20 -> conditional p' = 0.40/0.80 = 0.50
    # f* = (0.50*2.10 - 1)/(2.10 - 1) = 0.05/1.10 = 0.0454545...
    assert kelly_fraction(0.40, 2.10, p_push=0.20) == pytest.approx(0.0454545, abs=1e-6)


def test_suggested_stake_fractional_kelly() -> None:
    # bankroll 1000, f*=0.10, multiplier 0.25 -> 25.0 (below the 2% cap? cap
    # = 20.0, so the cap binds)
    stake = suggested_stake(1000.0, 0.55, 2.0, kelly_multiplier=0.25, max_stake_pct=0.02)
    assert stake == pytest.approx(20.0)  # capped at 2% of bankroll


def test_suggested_stake_below_cap() -> None:
    # f* = (0.52*2 - 1)/1 = 0.04 -> 1000*0.25*0.04 = 10.0 < cap 20.0
    stake = suggested_stake(1000.0, 0.52, 2.0, kelly_multiplier=0.25, max_stake_pct=0.02)
    assert stake == pytest.approx(10.0)


def test_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError):
        edge(1.2, 2.0)
    with pytest.raises(ValueError):
        edge(0.5, 1.0)
    with pytest.raises(ValueError):
        kelly_fraction(0.7, 2.0, p_push=0.5)  # p_win + p_push > 1
