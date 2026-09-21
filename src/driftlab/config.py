"""Configuration models and input validation."""

from dataclasses import dataclass
from datetime import date


class ConfigurationError(ValueError):
    """A concise user-facing configuration error."""


@dataclass(frozen=True)
class RunConfig:
    tickers: tuple[str, ...]
    start: date
    end: date
    lookback: int = 126
    holdings: int = 3
    rebalance: str = "monthly"
    cost_bps: float = 10.0

    @classmethod
    def create(cls, tickers: list[str], start: date, end: date, lookback: int = 126,
               holdings: int = 3, rebalance: str = "monthly", cost_bps: float = 10.0) -> "RunConfig":
        normalized = tuple(dict.fromkeys(item.strip().upper() for item in tickers if item.strip()))
        if len(normalized) < 2:
            raise ConfigurationError("Provide at least two distinct ticker symbols.")
        if start >= end:
            raise ConfigurationError("--start must be earlier than --end.")
        if lookback < 1:
            raise ConfigurationError("--lookback must be a positive integer.")
        if not 1 <= holdings <= len(normalized):
            raise ConfigurationError("--holdings must be between 1 and the number of requested tickers.")
        if rebalance != "monthly":
            raise ConfigurationError("Only --rebalance monthly is supported.")
        if cost_bps < 0:
            raise ConfigurationError("--cost-bps must be nonnegative.")
        return cls(normalized, start, end, lookback, holdings, rebalance, float(cost_bps))
