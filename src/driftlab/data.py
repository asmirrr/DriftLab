"""Historical adjusted-close data access."""

from dataclasses import dataclass
from datetime import date
import numpy as np
import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay,
                                    USMartinLutherKingJr, USMemorialDay,
                                    USPresidentsDay, USThanksgivingDay,
                                    nearest_workday)
from pandas.tseries.offsets import CustomBusinessDay


class DataError(ValueError):
    """Raised when market data cannot support the requested study."""


class _NYSEHolidayCalendar(AbstractHolidayCalendar):
    """Regular NYSE closures needed to distinguish normal holidays from gaps."""

    rules = [
        # New Year's Day, Juneteenth, Independence Day, and Christmas.
        # The calendar intentionally does not infer exceptional ad-hoc closures.
        Holiday("NewYearsDay", month=1, day=1, observance=nearest_workday),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, observance=nearest_workday, start_date="2022-01-01"),
        Holiday("IndependenceDay", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]


_NYSE_BUSINESS_DAY = CustomBusinessDay(calendar=_NYSEHolidayCalendar())


def expected_sessions(start: pd.Timestamp, end_exclusive: pd.Timestamp) -> pd.DatetimeIndex:
    """Regular NYSE weekday sessions in [start, end), excluding known holidays."""
    if start >= end_exclusive:
        return pd.DatetimeIndex([])
    return pd.date_range(start.normalize(), (end_exclusive - pd.Timedelta(days=1)).normalize(), freq=_NYSE_BUSINESS_DAY)


@dataclass(frozen=True)
class PriceData:
    prices: pd.DataFrame
    valid_tickers: tuple[str, ...]
    excluded_tickers: tuple[str, ...]
    notes: tuple[str, ...]


def _extract_adjusted_close(raw: pd.DataFrame, requested: tuple[str, ...]) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=requested)
    if isinstance(raw.columns, pd.MultiIndex):
        if "Adj Close" in raw.columns.get_level_values(0):
            result = raw["Adj Close"].copy()
        else:
            raise DataError("Downloaded data did not contain an Adj Close series; raw Close is not accepted.")
    else:
        if "Adj Close" not in raw.columns:
            raise DataError("Downloaded data did not contain an Adj Close series; raw Close is not accepted.")
        result = raw[["Adj Close"]].copy()
        result.columns = [requested[0]]
    return result.reindex(columns=requested)


def clean_prices(prices: pd.DataFrame, requested: tuple[str, ...], start: date | None = None,
                 end: date | None = None) -> PriceData:
    frame = prices.copy()
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index().reindex(columns=requested)
    if start is not None:
        frame = frame.loc[frame.index >= pd.Timestamp(start)]
    if end is not None:
        frame = frame.loc[frame.index < pd.Timestamp(end)]
    frame = frame.apply(pd.to_numeric, errors="coerce").where(lambda item: np.isfinite(item) & (item > 0))
    valid = tuple(column for column in requested if frame[column].notna().any())
    excluded = tuple(column for column in requested if column not in valid)
    if len(valid) < 2:
        raise DataError("Fewer than two tickers have usable positive price observations.")
    frame = frame.loc[:, valid]
    # A common, contiguous observation window is necessary: no invented prices or multi-day daily returns.
    complete = frame.notna().all(axis=1)
    if not complete.any():
        raise DataError("No common date has observations for every valid ticker.")
    first, last = complete[complete].index[[0, -1]]
    usable = frame.loc[first:last]
    if usable.isna().any().any():
        raise DataError("Missing observations within the common usable date range; no data were filled.")
    # Validate the data's grid. We only begin at the first common observation,
    # allowing legitimate later listings, but reject unknown sessions thereafter.
    expected_end = pd.Timestamp(end) if end is not None else last + _NYSE_BUSINESS_DAY
    expected = expected_sessions(first, expected_end)
    missing_sessions = expected.difference(usable.index)
    if len(missing_sessions):
        dates = ", ".join(day.date().isoformat() for day in missing_sessions[:3])
        suffix = "..." if len(missing_sessions) > 3 else ""
        raise DataError(f"Missing expected NYSE trading session(s): {dates}{suffix}. No prices were filled.")
    notes = ["Prices are finite positive adjusted closes with no missing regular NYSE sessions in the common usable range."]
    if excluded:
        notes.append("Excluded unavailable tickers: " + ", ".join(excluded) + ".")
    return PriceData(usable, valid, excluded, tuple(notes))


def fetch_prices(tickers: tuple[str, ...], start: date, end: date) -> PriceData:
    import yfinance as yf
    raw = yf.download(list(tickers), start=start.isoformat(), end=end.isoformat(), interval="1d",
                      auto_adjust=False, actions=False, progress=False, group_by="column", threads=True)
    return clean_prices(_extract_adjusted_close(raw, tickers), tickers, start, end)
