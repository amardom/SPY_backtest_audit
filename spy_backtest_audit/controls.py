"""Price-independent retrospective random-entry calendars."""
from decimal import Decimal, localcontext
import random
import statistics

from .data import DailyBar
from .signals import ScheduledTrade
def sample_calendar(bars: tuple[DailyBar, ...], first_entry: int, trades: int,
                    holding: int, rng: random.Random) -> tuple[ScheduledTrade, ...]:
    """Uniformly sample feasible fixed-count calendars via compressed entry slots."""
    if type(first_entry) is not int or not 1 <= first_entry < len(bars):
        raise ValueError("Require a preceding decision session and eligible entry sessions")
    if type(trades) is not int or trades < 1 or type(holding) is not int or holding < 1:
        raise ValueError("Trade count and holding must be positive integers")
    sessions = len(bars) - first_entry
    compressed = sessions - trades * holding
    if compressed < trades:
        raise ValueError("Insufficient sessions for the requested nonoverlapping calendar")
    slots = sorted(rng.sample(range(compressed), trades))
    entries = [first_entry + slot + j * holding for j, slot in enumerate(slots)]
    return tuple(ScheduledTrade(bars[e-1].date, bars[e].date, bars[e+holding].date, "scheduled")
                 for e in entries)
def mean_entry_volatility(bars, schedule, lookback):
    """Use only information available at the preceding close; no annualization."""
    positions = {bar.date: i for i, bar in enumerate(bars)}
    with localcontext() as context:
        context.prec = 28
        returns = [Decimal(0)]
        returns.extend((bars[i].close + bars[i].dividend) / bars[i-1].close - 1
                       for i in range(1, len(bars)))
        values = []
        for trade in schedule:
            e = positions[trade.entry_date]
            if e - lookback < 1:
                raise ValueError("Insufficient observable returns before entry")
            values.append(statistics.stdev(returns[e-lookback:e]))
        if not values:
            raise ValueError("At least one entry is required")
        return sum(values) / len(values)
