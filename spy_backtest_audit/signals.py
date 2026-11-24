"""Generate dip signals and their entry and exit dates."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
import statistics

from .data import DailyBar
@dataclass(frozen=True)
class Strategy:
    lookback_sessions: int = 20
    threshold_sigma: Decimal = Decimal("2")
    holding_open_intervals: int = 5
    def __post_init__(self):
        if type(self.lookback_sessions) is not int or self.lookback_sessions < 2:
            raise ValueError("lookback_sessions must be an integer >= 2")
        if type(self.holding_open_intervals) is not int or self.holding_open_intervals < 1:
            raise ValueError("holding_open_intervals must be a positive integer")
        if not isinstance(self.threshold_sigma, Decimal) or not self.threshold_sigma.is_finite() or self.threshold_sigma <= 0:
            raise ValueError("threshold_sigma must be a finite positive Decimal")
@dataclass(frozen=True)
class SignalEvent:
    signal_date: date
    daily_return: Decimal
    prior_volatility: Decimal
    decision: str
@dataclass(frozen=True)
class ScheduledTrade:
    signal_date: date
    entry_date: date | None
    exit_date: date | None
    status: str
@dataclass(frozen=True)
class SignalResult:
    events: tuple[SignalEvent, ...]
    trades: tuple[ScheduledTrade, ...]
def generate_signals(bars: tuple[DailyBar, ...], strategy: Strategy, *, last_entry_index: int | None = None) -> SignalResult:
    """Use supplied session order; missing exchange sessions must be checked separately.

    Signals at the exit session's close can schedule a new entry the next session.
    A signal near the sample end is retained with unknown dates, never silently
    discarded because future prices are unavailable. No future return affects a decision.
    """
    if last_entry_index is not None and (type(last_entry_index) is not int or not 1 <= last_entry_index < len(bars)):
        raise ValueError("Invalid administrative entry cutoff")
    if any(bars[i].date <= bars[i-1].date for i in range(1, len(bars))):
        raise ValueError("Bars must be strictly ordered and unique")
    if any(bar.split_factor != 1 for bar in bars):
        raise ValueError("Split-event handling is not implemented for signals; refusing ambiguous price/share units")
    with localcontext() as context:
        context.prec = 28
        returns = [Decimal(0)]  # First bar has no observable preceding close.
        returns.extend((bars[i].close + bars[i].dividend) / bars[i-1].close - 1
                       for i in range(1, len(bars)))
        events, trades = [], []
        exit_index = -1
        for i in range(strategy.lookback_sessions + 1, len(bars)):
            # Forming the prior returns requires one more close than the lookback length.
            history = returns[i-strategy.lookback_sessions:i]
            volatility = statistics.stdev(history)
            if volatility == 0 or returns[i] > -strategy.threshold_sigma * volatility:
                continue
            if i < exit_index:
                events.append(SignalEvent(bars[i].date, returns[i], volatility, "ignored_holding"))
                continue
            if last_entry_index is not None and i + 1 > last_entry_index:
                events.append(SignalEvent(bars[i].date, returns[i], volatility, "excluded_tail"))
                continue
            events.append(SignalEvent(bars[i].date, returns[i], volatility, "enter_next_open"))
            entry_index = i + 1
            exit_index = entry_index + strategy.holding_open_intervals
            entry = bars[entry_index].date if entry_index < len(bars) else None
            exit_date = bars[exit_index].date if exit_index < len(bars) else None
            status = "scheduled" if exit_date is not None else "awaiting_exit" if entry is not None else "awaiting_entry"
            trades.append(ScheduledTrade(bars[i].date, entry, exit_date, status))
    return SignalResult(tuple(events), tuple(trades))
