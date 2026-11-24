"""Long-only portfolio accounting with dividends and proportional trading costs."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from .data import DailyBar
from .signals import ScheduledTrade
@dataclass(frozen=True)
class EquityPoint:
    date: date
    cash: Decimal
    shares: Decimal
    equity: Decimal
    drawdown: Decimal
@dataclass(frozen=True)
class ExecutedTrade:
    signal_date: date
    entry_date: date
    exit_date: date
    entry_price: Decimal
    exit_price: Decimal
    shares: Decimal
    entry_cost: Decimal
    exit_cost: Decimal
    dividends: Decimal
    net_return: Decimal
    exit_reason: str
@dataclass(frozen=True)
class BacktestResult:
    equity: tuple[EquityPoint, ...]
    trades: tuple[ExecutedTrade, ...]
    total_return: Decimal
    max_drawdown: Decimal
    total_cost: Decimal
    terminal_liquidations: int
def simulate(bars: tuple[DailyBar, ...], schedule: tuple[ScheduledTrade, ...],
             cost_bps: Decimal, initial_capital: Decimal = Decimal("100000")) -> BacktestResult:
    """Execute a precomputed causal calendar, crediting dividends before open orders."""
    if not bars or any(bars[i].date <= bars[i-1].date for i in range(1, len(bars))):
        raise ValueError("Require nonempty, strictly increasing bars")
    if any(bar.split_factor != 1 for bar in bars):
        raise ValueError("Split-event accounting is not implemented")
    if not cost_bps.is_finite() or not Decimal(0) <= cost_bps < Decimal(10000):
        raise ValueError("Cost must be finite and between 0 and 10000 bps")
    if not initial_capital.is_finite() or initial_capital <= 0:
        raise ValueError("Initial capital must be finite and positive")
    dates = {bar.date for bar in bars}
    entries = {}
    for trade in schedule:
        if trade.entry_date is None:
            if trade.exit_date is not None:
                raise ValueError("Exit requires an entry")
            continue
        if trade.entry_date not in dates or trade.signal_date >= trade.entry_date:
            raise ValueError("Entry must follow its signal and lie in the evaluation window")
        if trade.exit_date is not None and (trade.exit_date not in dates or trade.exit_date <= trade.entry_date):
            raise ValueError("Exit must follow entry and lie in the evaluation window")
        if trade.entry_date in entries:
            raise ValueError("Duplicate entry date")
        entries[trade.entry_date] = trade
    with localcontext() as context:
        context.prec = 28
        fee = cost_bps / 10000
        cash, shares = initial_capital, Decimal(0)
        total_cost = Decimal(0)
        peak = initial_capital
        active = None
        entry_cash = entry_cost = dividends = Decimal(0)
        entry_price = Decimal(0)
        points, trades = [], []
        def sell(day, price, reason):
            nonlocal cash, shares, total_cost, active
            exit_cost = shares * price * fee
            cash += shares * price - exit_cost
            total_cost += exit_cost
            trades.append(ExecutedTrade(active.signal_date, active.entry_date, day,
                                        entry_price, price, shares, entry_cost, exit_cost,
                                        dividends, cash / entry_cash - 1, reason))
            shares = Decimal(0)
            active = None

        for index, bar in enumerate(bars):
            if active is not None:
                distribution = shares * bar.dividend
                cash += distribution
                dividends += distribution
                if active.exit_date == bar.date:
                    sell(bar.date, bar.open, "scheduled_open")
            if bar.date in entries:
                if active is not None:
                    raise ValueError("Overlapping scheduled positions")
                active = entries[bar.date]
                entry_cash = cash
                entry_price = bar.open
                shares = cash / (bar.open * (1 + fee))
                entry_cost = shares * bar.open * fee
                total_cost += entry_cost
                cash = dividends = Decimal(0)
            if index == len(bars) - 1 and active is not None:
                sell(bar.date, bar.close, "terminal_close")
            equity = cash + shares * bar.close
            peak = max(peak, equity)
            points.append(EquityPoint(bar.date, cash, shares, equity, equity / peak - 1))
        return BacktestResult(tuple(points), tuple(trades), points[-1].equity / initial_capital - 1,
                              min(p.drawdown for p in points), total_cost,
                              sum(t.exit_reason == "terminal_close" for t in trades))
