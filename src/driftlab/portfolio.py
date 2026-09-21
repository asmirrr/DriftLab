"""Portfolio selection, timing, turnover, and true buy-and-hold benchmark."""

from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class PortfolioResult:
    target_weights: pd.DataFrame
    held_weights: pd.DataFrame
    turnover: pd.Series
    gross_returns: pd.Series
    net_returns: pd.Series
    rebalances: pd.DataFrame


def select_weights(signal: pd.Series, holdings: int) -> pd.Series:
    """Choose top signals; ticker-name order breaks ties deterministically."""
    eligible = signal.dropna().sort_index().sort_values(ascending=False, kind="stable")
    selected = eligible.iloc[:holdings]
    result = pd.Series(0.0, index=signal.index)
    if not selected.empty:
        result.loc[selected.index] = 1.0 / len(selected)
    return result


def build_portfolio(prices: pd.DataFrame, signals: pd.DataFrame, rebalance_dates: pd.DatetimeIndex,
                    holdings: int, cost_bps: float) -> PortfolioResult:
    index, columns = prices.index, prices.columns
    targets = pd.DataFrame(float("nan"), index=index, columns=columns)
    ledger_rows: list[dict[str, object]] = []
    event_dates: list[pd.Timestamp] = []
    for when in rebalance_dates:
        if when not in index or when == index[-1] or signals.loc[when].dropna().empty:
            continue
        weights = select_weights(signals.loc[when], holdings)
        targets.loc[when] = weights
        event_dates.append(when)
        for ticker in columns:
            ledger_rows.append({"rebalance_date": when, "ticker": ticker,
                                "momentum_signal": signals.loc[when, ticker],
                                "target_weight": weights[ticker], "selected": bool(weights[ticker])})
    # Target is selected at close and becomes held only on the next trading date.
    target_filled = targets.ffill().fillna(0.0)
    held = target_filled.shift(1).fillna(0.0)
    # Trades are determined and charged at each rebalance close. The new target
    # is only exposed to market returns from the following trading day.
    prior_held_at_close = held
    turnover = pd.Series(0.0, index=index)
    for when in event_dates:
        turnover.loc[when] = (target_filled.loc[when] - prior_held_at_close.loc[when]).abs().sum()
    returns = prices.pct_change().fillna(0.0)
    gross = (held * returns).sum(axis=1)
    net = gross - turnover * (cost_bps / 10_000.0)
    ledger = pd.DataFrame(ledger_rows, columns=["rebalance_date", "ticker", "momentum_signal", "target_weight", "selected"])
    return PortfolioResult(target_filled, held, turnover, gross, net, ledger)


def true_buy_and_hold_returns(prices: pd.DataFrame, initial_investable_date: pd.Timestamp) -> pd.Series:
    """Equal cash allocation once; holdings drift thereafter and are never rebalanced."""
    window = prices.loc[initial_investable_date:]
    growth = window.div(window.iloc[0])
    equity = growth.mean(axis=1)
    return equity.pct_change().fillna(0.0)
