from datetime import date
import math

import numpy as np
import pandas as pd
import pytest

from driftlab.config import ConfigurationError, RunConfig
from driftlab.data import DataError, _extract_adjusted_close, clean_prices, expected_sessions
from driftlab.metrics import maximum_drawdown
from driftlab.portfolio import build_portfolio, select_weights, true_buy_and_hold_returns


def test_adjusted_close_is_required_and_invalid_prices_are_rejected() -> None:
    with pytest.raises(DataError, match="Adj Close"):
        _extract_adjusted_close(pd.DataFrame({"Close": [10]}, index=pd.DatetimeIndex(["2024-01-02"])), ("AAA",))
    bad = pd.DataFrame({"AAA": [10, np.inf], "BBB": [10, 11]}, index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"]))
    with pytest.raises(DataError, match="finite and positive"):
        clean_prices(bad, ("AAA", "BBB"), date(2024, 1, 2), date(2024, 1, 4))
    with pytest.raises(ConfigurationError, match="finite nonnegative"):
        RunConfig.create(["AAA", "BBB"], date(2024, 1, 1), date(2024, 2, 1), 20, 1, cost_bps=math.inf)


def test_regular_holidays_are_not_missing_but_expected_sessions_are() -> None:
    sessions = expected_sessions(pd.Timestamp("2024-01-12"), pd.Timestamp("2024-01-18"))
    frame = pd.DataFrame({"AAA": 10.0, "BBB": 11.0}, index=sessions)
    clean_prices(frame, ("AAA", "BBB"), date(2024, 1, 12), date(2024, 1, 18))
    broken = frame.drop(pd.Timestamp("2024-01-16"))
    with pytest.raises(DataError, match="2024-01-16"):
        clean_prices(broken, ("AAA", "BBB"), date(2024, 1, 12), date(2024, 1, 18))


def test_tie_at_selection_cutoff_is_alphabetical() -> None:
    weights = select_weights(pd.Series({"ZZZ": .3, "BBB": .2, "AAA": .2}), 2)
    assert weights.to_dict() == {"ZZZ": .5, "BBB": 0.0, "AAA": .5}


def test_same_day_switch_has_no_same_day_exposure() -> None:
    index = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    prices = pd.DataFrame({"AAA": [100, 110, 110, 110], "BBB": [100, 100, 120, 144]}, index=index)
    signals = pd.DataFrame({"AAA": [1, 1, 0, 0], "BBB": [0, 0, 1, 1]}, index=index)
    result = build_portfolio(prices, signals, pd.DatetimeIndex([index[1], index[2]]), 1, 0)
    assert result.gross_returns.loc[index[1]] == 0
    assert result.gross_returns.loc[index[2]] == 0
    assert result.gross_returns.loc[index[3]] == pytest.approx(.2)
    assert result.turnover.loc[index[2]] == pytest.approx(2.0)


def test_buy_and_hold_second_return_uses_drifting_weights() -> None:
    index = pd.bdate_range("2024-01-02", periods=3)
    prices = pd.DataFrame({"AAA": [100, 200, 400], "BBB": [100, 100, 100]}, index=index)
    returns = true_buy_and_hold_returns(prices, index[0])
    assert returns.iloc[1] == pytest.approx(.5)
    assert returns.iloc[2] == pytest.approx(2 / 3)


@pytest.mark.parametrize(("equity", "expected"), [([.9], -.1), ([.99], -.01), ([.9, .8], -.2), ([.9, 1.0], -.1), ([1.1, 1.0, 1.2], -1 / 11)])
def test_drawdown_includes_initial_capital_and_handles_recovery(equity, expected) -> None:
    assert maximum_drawdown(pd.Series(equity)) == pytest.approx(expected)
