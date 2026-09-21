"""Deterministic momentum signal calculations."""

import pandas as pd


def trailing_momentum(prices: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Return trailing simple returns using only the current and lookback-day prices."""
    return prices / prices.shift(lookback) - 1.0


def month_end_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    periods = index.to_period("M")
    return pd.DatetimeIndex(index.to_series().groupby(periods).max().tolist())
