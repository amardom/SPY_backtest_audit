"""Calculate yearly and multi-year portfolio statistics."""
from datetime import date
from decimal import Decimal, localcontext
import math
import statistics
def period_metrics(result, initial_capital, blocks):
    if not result.equity:
        raise ValueError("Require an equity path")
    points = result.equity
    first, last = points[0].date, points[-1].date
    windows = [("all", "all", first, date(last.year + 1, 1, 1))]
    windows += [("year", str(year), date(year, 1, 1), date(year+1, 1, 1))
                for year in range(first.year, last.year+1)]
    windows += [("block", block["label"], date.fromisoformat(block["start"]),
                 date.fromisoformat(block["end_exclusive"])) for block in blocks]
    with localcontext() as context:
        context.prec = 28
        previous = initial_capital
        observations = []
        for point in points:
            observations.append((point, previous, point.equity / previous - 1))
            previous = point.equity
        rows = []
        for kind, label, start, end in windows:
            group = [(p, before, r) for p, before, r in observations if start <= p.date < end]
            if not group:
                continue
            starting = group[0][1]
            ending = group[-1][0].equity
            peak, minimum = starting, Decimal(0)
            for point, _, _ in group:
                peak = max(peak, point.equity)
                minimum = min(minimum, point.equity / peak - 1)
            daily_returns = [r for _, _, r in group]
            rows.append(dict(period_kind=kind, period=label, first_date=str(group[0][0].date),
                             last_date=str(group[-1][0].date), observations=len(group),
                             starting_equity=str(starting), ending_equity=str(ending),
                             pnl_usd=str(ending-starting), total_return=str(ending/starting-1),
                             local_max_close_drawdown=str(minimum),
                             daily_portfolio_volatility=str(statistics.stdev(daily_returns)) if len(group)>1 else None,
                             close_exposure_fraction=str(Decimal(sum(p.shares > 0 for p, _, _ in group))/len(group)),
                             entries=sum(start <= t.entry_date < end for t in result.trades)))
    return rows
def quantiles(values):
    values = sorted(Decimal(str(v)) for v in values)
    if not values:
        raise ValueError("Require a nonempty control distribution")
    return {label: str(values[math.ceil(p*len(values))-1])
            for label, p in (("p05", .05), ("p50", .5), ("p95", .95))}
