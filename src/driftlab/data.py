"""Historical adjusted-close data access."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
import pandas as pd


class DataError(ValueError):
    """Raised when market data cannot support the requested study."""


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
        elif "Close" in raw.columns.get_level_values(0):
            result = raw["Close"].copy()
        else:
            raise DataError("Downloaded data did not contain adjusted-close prices.")
    else:
        field = "Adj Close" if "Adj Close" in raw.columns else "Close"
        if field not in raw.columns:
            raise DataError("Downloaded data did not contain adjusted-close prices.")
        result = raw[[field]].copy()
        result.columns = [requested[0]]
    return result.reindex(columns=requested)


def clean_prices(prices: pd.DataFrame, requested: tuple[str, ...]) -> PriceData:
    frame = prices.copy()
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index().reindex(columns=requested)
    frame = frame.apply(pd.to_numeric, errors="coerce").where(lambda item: item > 0)
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
    notes = ["Prices are positive adjusted closes with no missing observations in the common usable range."]
    if excluded:
        notes.append("Excluded unavailable tickers: " + ", ".join(excluded) + ".")
    return PriceData(usable, valid, excluded, tuple(notes))


def fetch_prices(tickers: tuple[str, ...], start: date, end: date) -> PriceData:
    import yfinance as yf
    raw = yf.download(list(tickers), start=start.isoformat(), end=end.isoformat(), interval="1d",
                      auto_adjust=False, actions=False, progress=False, group_by="column", threads=True)
    return clean_prices(_extract_adjusted_close(raw, tickers), tickers)
