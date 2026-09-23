"""Deterministic momentum signal calculations."""

import pandas as pd


def trailing_momentum(prices: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Return trailing simple returns using only the current and lookback-day prices."""
    return prices / prices.shift(lookback) - 1.0


def completed_month_end_dates(index: pd.DatetimeIndex, end_exclusive: pd.Timestamp) -> pd.DatetimeIndex:
    """Last actual sessions only for calendar months complete before the configured end."""
    periods = index.to_period("M")
    dates = index.to_series().groupby(periods).max()
    complete = [when for period, when in dates.items() if pd.Timestamp(period.end_time.date()) < end_exclusive]
    return pd.DatetimeIndex(complete)
