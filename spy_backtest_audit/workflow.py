"""Write development signals, portfolio results and random-entry controls."""
import csv
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import platform

from .data import Snapshot
from .signals import Strategy, generate_signals
def write_signal_artifacts(root: Path, snapshot: Snapshot):
    plan_bytes = (root / "research/data_plan.json").read_bytes()
    config_bytes = (root / "research/strategy.json").read_bytes()
    plan, config = json.loads(plan_bytes), json.loads(config_bytes)
    required = {
        "version": 1,
        "volatility": "sample_standard_deviation_excluding_signal_day",
        "signal_return": "close_to_close_including_ex_date_dividend",
        "entry": "next_available_session_open",
        "exit": "entry_open_plus_holding_open_intervals",
        "overlap": "ignore_signals_while_position_open",
        "scope": "development_only",
        "performance_evaluated": False,
    }
    if any(config.get(key) != value for key, value in required.items()):
        raise ValueError("Unsupported strategy semantics; update protocol and implementation together")
    strategy = Strategy(config["lookback_sessions"], Decimal(config["threshold_sigma"]), config["holding_open_intervals"])
    start, end = (date.fromisoformat(plan["development"][key]) for key in ("start", "end_exclusive"))
    if start >= end or end > date.fromisoformat(plan["validation"]["start"]):
        raise ValueError("Development window must exclude validation")
    bars = tuple(bar for bar in snapshot.bars if start <= bar.date < end)
    result = generate_signals(bars, strategy)
    output = root / "outputs/signals"
    output.mkdir(parents=True, exist_ok=True)
    for name, records, columns in (
        ("signal_events.csv", result.events, ("signal_date", "daily_return", "prior_volatility", "decision")),
        ("trade_schedule.csv", result.trades, ("signal_date", "entry_date", "exit_date", "status")),
    ):
        with (output / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(asdict(record) for record in records)
    code = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((root / "spy_backtest_audit").glob("*.py"))}
    metadata = dict(stage="signals_only", python=platform.python_version(), snapshot_sha256=snapshot.sha256,
                    strategy=config, strategy_sha256=hashlib.sha256(config_bytes).hexdigest(),
                    data_plan_sha256=hashlib.sha256(plan_bytes).hexdigest(), code_sha256=code,
                    development=plan["development"], bars_used=len(bars),
                    events=len(result.events), trades=len(result.trades),
                    pending_trades=sum(t.status != "scheduled" for t in result.trades),
                    performance_evaluated=False,
                    limitations=["No execution fills, portfolio sizing, P&L or costs calculated.",
                                 "Default entry point checks session membership against the pinned XNYS model calendar.",
                                 "Dividend events are assumed known on their ex-date; vendor historical revisions are not point-in-time data.",
                                 "Split events are explicitly unsupported and rejected."])
    (output / "run.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return result, output
def write_backtest_artifacts(root: Path, snapshot: Snapshot, signals):
    """Run fixed development scenarios and a descriptive buy-and-hold reference."""
    from .backtest import simulate
    from .signals import ScheduledTrade

    execution_bytes = (root / "research/execution.json").read_bytes()
    execution = json.loads(execution_bytes)
    required = dict(version=1, sizing="all_available_cash_fractional_shares", cash_return="zero",
                    dividends="ex_date_cash_no_intraposition_reinvestment",
                    terminal_policy="liquidate_at_last_development_close",
                    benchmark="buy_and_hold_same_evaluation_window", scope="development_only",
                    cost_interpretation="illustrative_all_in_proportional_cost_not_empirical_estimate")
    if any(execution.get(k) != v for k, v in required.items()):
        raise ValueError("Unsupported execution assumptions")
    plan = json.loads((root / "research/data_plan.json").read_text())
    config = json.loads((root / "research/strategy.json").read_text())
    start, end = (date.fromisoformat(plan["development"][k]) for k in ("start", "end_exclusive"))
    if end > date.fromisoformat(plan["validation"]["start"]):
        raise ValueError("Backtest must exclude validation")
    development = tuple(b for b in snapshot.bars if start <= b.date < end)
    first_entry = config["lookback_sessions"] + 2
    if len(development) <= first_entry:
        raise ValueError("Insufficient development data after warmup")
    evaluation = development[first_entry:]
    benchmark = (ScheduledTrade(development[first_entry-1].date, evaluation[0].date, None, "awaiting_exit"),)
    capital = Decimal(execution["initial_capital_usd"])
    fees = [Decimal(value) for value in execution["cost_scenarios_bps_per_side"]]
    primary = Decimal(execution["primary_cost_bps_per_side"])
    if primary not in fees or len(set(fees)) != len(fees):
        raise ValueError("Require distinct cost scenarios including the primary")
    output = root / "outputs/backtest"
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for fee in fees:
        for name, schedule in (("dip", signals.trades), ("buy_and_hold", benchmark)):
            result = simulate(evaluation, schedule, fee, capital)
            stem = f"{name}_{fee}bps"
            for suffix, records in (("equity", result.equity), ("trades", result.trades)):
                from .backtest import EquityPoint, ExecutedTrade
                columns = tuple((EquityPoint if suffix == "equity" else ExecutedTrade).__dataclass_fields__)
                with (output / f"{stem}_{suffix}.csv").open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(asdict(record) for record in records)
            summaries.append(dict(strategy=name, cost_bps_per_side=str(fee), primary=fee == primary,
                                  total_return=str(result.total_return), max_close_drawdown=str(result.max_drawdown),
                                  trades=len(result.trades), total_cost_usd=str(result.total_cost),
                                  terminal_liquidations=result.terminal_liquidations))
    provenance = json.loads((root / "outputs/signals/run.json").read_text())
    metadata = dict(stage="development_descriptive_backtest", signal_run=provenance,
                    execution=execution, execution_sha256=hashlib.sha256(execution_bytes).hexdigest(),
                    evaluation_start=str(evaluation[0].date), evaluation_end=str(evaluation[-1].date),
                    initial_capital_usd=str(capital), scenarios=summaries,
                    limitations=["Development results only; not evidence of a trading edge.",
                                 "Buy-and-hold exposure and risk are not matched to the signal strategy.",
                                 "Costs are illustrative scenarios, not empirically calibrated fills.",
                                 "Random-entry references are reported separately; no significance test or validation performance.",
                                 "Default entry point checks the XNYS model calendar; daily drawdown misses intraday extremes."])
    (output / "summary.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return summaries, output
def write_control_artifacts(root: Path, snapshot: Snapshot, signals):
    """Descriptive random-entry comparison, conditional on observed trade count."""
    from .backtest import simulate
    from .controls import sample_calendar, mean_entry_volatility
    from .signals import ScheduledTrade
    from .diagnostics import period_metrics, quantiles
    import random
    import math

    config_bytes = (root / "research/controls.json").read_bytes()
    control = json.loads(config_bytes)
    if (control.get("version") != 1 or control.get("sampler") != "uniform_nonoverlapping_fixed_count_v1"
            or control.get("scope") != "development_only" or control.get("cost_scenario") != "primary_only"
            or control.get("interpretation") != "descriptive_retrospective_reference_not_a_p_value"):
        raise ValueError("Unsupported random-reference specification")
    if type(control["calendars"]) is not int or control["calendars"] < 1 or type(control["seed"]) is not int:
        raise ValueError("Require positive calendar count and integer seed")
    if not signals.trades or any(t.status != "scheduled" for t in signals.trades):
        raise ValueError("This reference requires at least one trade and no pending/truncated primary trades")
    plan = json.loads((root / "research/data_plan.json").read_text())
    strategy = json.loads((root / "research/strategy.json").read_text())
    execution = json.loads((root / "research/execution.json").read_text())
    start, end = (date.fromisoformat(plan["development"][k]) for k in ("start", "end_exclusive"))
    if start >= end or end > date.fromisoformat(plan["validation"]["start"]):
        raise ValueError("Controls must exclude validation")
    bars = tuple(b for b in snapshot.bars if start <= b.date < end)
    first_entry = strategy["lookback_sessions"] + 2
    evaluation = bars[first_entry:]
    positions = {bar.date: i for i, bar in enumerate(bars)}
    holding = strategy["holding_open_intervals"]
    if any(positions[t.exit_date] - positions[t.entry_date] != holding for t in signals.trades):
        raise ValueError("Primary trades do not have the specified fixed duration")
    fee, capital = Decimal(execution["primary_cost_bps_per_side"]), Decimal(execution["initial_capital_usd"])
    dip = simulate(evaluation, signals.trades, fee, capital)
    if dip.terminal_liquidations:
        raise ValueError("Terminal primary trades cannot be compared with fixed-duration controls")
    output = root / "outputs/controls"
    output.mkdir(parents=True, exist_ok=True)
    diagnostic_bytes = (root / "research/diagnostics.json").read_bytes()
    diagnostic = json.loads(diagnostic_bytes)
    if (diagnostic.get("version") != 1 or diagnostic.get("scope") != "development_only"
            or diagnostic.get("cost_scenario") != "primary_only" or diagnostic.get("annual") is not True
            or diagnostic.get("interpretation") != "exploratory_calendar_stability_not_regime_identification"):
        raise ValueError("Unsupported diagnostic specification")
    blocks = diagnostic["blocks"]
    if not blocks or len({b["label"] for b in blocks}) != len(blocks):
        raise ValueError("Require distinct diagnostic blocks")
    boundary = start
    for block in blocks:
        if date.fromisoformat(block["start"]) != boundary:
            raise ValueError("Diagnostic blocks must partition development chronologically")
        boundary = date.fromisoformat(block["end_exclusive"])
        if boundary <= date.fromisoformat(block["start"]) or boundary > end:
            raise ValueError("Diagnostic blocks must exclude validation")
    if boundary != end:
        raise ValueError("Diagnostic blocks must cover all development")
    rng = random.Random(control["seed"])
    rows, control_periods = [], []
    with (output / "calendars.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("draw", "trade", "decision_date", "entry_date", "exit_date"))
        for draw in range(control["calendars"]):
            calendar = sample_calendar(bars, first_entry, len(signals.trades), holding, rng)
            result = simulate(evaluation, calendar, fee, capital)
            if len(result.trades) != len(signals.trades) or result.terminal_liquidations:
                raise ValueError("Control failed count/duration matching")
            control_periods.extend(dict(draw=draw, **metric) for metric in period_metrics(result, capital, blocks))
            for number, trade in enumerate(calendar):
                writer.writerow((draw, number, trade.signal_date, trade.entry_date, trade.exit_date))
            rows.append(dict(draw=draw, total_return=str(result.total_return),
                             max_close_drawdown=str(result.max_drawdown),
                             total_cost_usd=str(result.total_cost), trades=len(result.trades),
                             holding_open_intervals=holding,
                             mean_entry_daily_volatility=str(mean_entry_volatility(bars, calendar, strategy["lookback_sessions"]))))
    with (output / "draws.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    values = sorted(Decimal(row["total_return"]) for row in rows)
    quantile = lambda p: str(values[max(0, math.ceil(p * len(values)) - 1)])
    backtest = json.loads((root / "outputs/backtest/summary.json").read_text())
    summary = dict(stage="development_descriptive_random_reference", config=control,
                   config_sha256=hashlib.sha256(config_bytes).hexdigest(), backtest_run=backtest,
                   matched_trades=len(signals.trades), holding_open_intervals=holding,
                   exposure_open_intervals=len(signals.trades)*holding,
                   primary_cost_bps_per_side=str(fee), dip_total_return=str(dip.total_return),
                   dip_mean_entry_daily_volatility=str(mean_entry_volatility(bars, signals.trades, strategy["lookback_sessions"])),
                   control_return_quantiles_nearest_rank={"p05": quantile(.05), "p50": quantile(.5), "p95": quantile(.95)},
                   fraction_controls_strictly_below_dip=sum(v < dip.total_return for v in values) / len(values),
                   controls_tied_with_dip=sum(v == dip.total_return for v in values),
                   limitations=["Exploratory retrospective comparison conditional on primary trade count, not a live policy.",
                                "Fraction below dip is not a p-value or a probability of future success.",
                                "Volatility, regimes, calendar-day exposure and dollar turnover are not matched.",
                                "No validation, final-evaluation results, alpha estimate or significance test."])
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    diagnostic_output = root / "outputs/diagnostics"
    diagnostic_output.mkdir(parents=True, exist_ok=True)
    benchmark_schedule = (ScheduledTrade(
        bars[first_entry-1].date, evaluation[0].date, None, "awaiting_exit"),)
    buy_and_hold = simulate(evaluation, benchmark_schedule, fee, capital)
    primary_periods = [dict(strategy=name, **metric) for name, result in (("dip", dip), ("buy_and_hold", buy_and_hold))
                       for metric in period_metrics(result, capital, blocks)]
    for filename, records in (("primary_periods.csv", primary_periods), ("control_periods.csv", control_periods)):
        with (diagnostic_output / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=tuple(records[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(records)
    comparisons = []
    for metric in primary_periods:
        if metric["strategy"] != "dip":
            continue
        group = [r for r in control_periods if (r["period_kind"], r["period"]) == (metric["period_kind"], metric["period"])]
        fields = ("total_return", "local_max_close_drawdown", "daily_portfolio_volatility", "close_exposure_fraction", "entries")
        distributions = {key: quantiles(r[key] for r in group if r[key] is not None) for key in fields
                         if any(r[key] is not None for r in group)}
        comparisons.append(dict(period_kind=metric["period_kind"], period=metric["period"], dip=metric,
                                control_quantiles=distributions))
    risk = dict(dip_mean_entry_daily_volatility=summary["dip_mean_entry_daily_volatility"],
                control_mean_entry_daily_volatility_quantiles=quantiles(r["mean_entry_daily_volatility"] for r in rows))
    diagnostic_summary = dict(stage="development_exploratory_temporal_diagnostics", config=diagnostic,
                              config_sha256=hashlib.sha256(diagnostic_bytes).hexdigest(),
                              controls_run=summary, comparisons=comparisons, entry_risk=risk,
                              limitations=["Calendar blocks are not identified economic regimes.",
                                           "Years and blocks are exploratory, overlapping descriptions, not independent tests.",
                                           "Position and equity history carry across boundaries; local drawdown resets its peak.",
                                           "Close exposure is not a full intraday/overnight risk measure.",
                                           "Control count/duration matches apply globally, not within each year or block.",
                                           "No significance test, alpha estimate, validation or final-evaluation performance."])
    (diagnostic_output / "summary.json").write_text(json.dumps(diagnostic_summary, indent=2) + "\n", encoding="utf-8")
    return summary, output
