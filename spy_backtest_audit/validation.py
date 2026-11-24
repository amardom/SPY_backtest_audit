"""Run the fixed temporal-validation specification."""
import csv
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import platform
import random
import statistics

from .backtest import simulate, EquityPoint, ExecutedTrade
from .controls import sample_calendar, mean_entry_volatility
from .diagnostics import period_metrics, quantiles
from .protocol import verify_validation_freeze
from .signals import Strategy, ScheduledTrade, generate_signals
def prepare_validation(bars, start, end, strategy):
    """Warm up using prior closes, but start flat and never trade warmup dates."""
    validation = tuple(b for b in bars if start <= b.date < end)
    warmup = tuple(b for b in bars if b.date < start)[-(strategy.lookback_sessions+1):]
    if len(warmup) != strategy.lookback_sessions + 1:
        raise ValueError("Insufficient preceding sessions for validation warmup")
    if len(validation) < strategy.holding_open_intervals + 2:
        raise ValueError("Insufficient validation sessions for a full holding horizon")
    context = warmup + validation
    first_entry = len(warmup) + 1
    last_entry = len(context) - 1 - strategy.holding_open_intervals
    signals = generate_signals(context, strategy, last_entry_index=last_entry)
    if any(t.signal_date < start or t.entry_date is None or t.exit_date is None or t.exit_date >= end for t in signals.trades):
        raise ValueError("Validation trade crosses its administrative window")
    return context, first_entry, signals
def classify_screen(net_primary, contrast, net_stress, trades):
    """Frozen sign-based reporting screen, never a statistical significance test."""
    if trades == 0:
        return "INCONCLUSIVE"
    if contrast is None:
        raise ValueError("A nonempty comparison requires a control contrast")
    if net_primary <= 0 or contrast <= 0:
        return "NOT_SUPPORTED_BY_VALIDATION_SCREEN"
    if net_stress <= 0:
        return "INCONCLUSIVE_COST_FRAGILE"
    return "PROMISING_MORE_RESEARCH"
def write_rows(path, records, columns):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
def write_validation_artifacts(root, snapshot):
    freeze = verify_validation_freeze(root)
    if freeze["snapshot_sha256"] != snapshot.sha256:
        raise ValueError("Loaded snapshot differs from frozen dataset")
    config = json.loads((root / "research/validation.json").read_text())
    # The original freeze is a historical pre-execution record; it is not rewritten.
    if config["status"] != "RULES_FROZEN_NOT_EXECUTED" or config["inference"] != "descriptive_screen_no_p_value_no_alpha_claim":
        raise ValueError("Unsupported frozen validation method")
    plan = json.loads((root / "research/data_plan.json").read_text())
    specification = json.loads((root / "research/strategy.json").read_text())
    execution = json.loads((root / "research/execution.json").read_text())
    control = json.loads((root / "research/controls.json").read_text())
    start, end = (date.fromisoformat(plan["validation"][k]) for k in ("start", "end_exclusive"))
    if end > date.fromisoformat(plan["final_evaluation"]["start"]):
        raise ValueError("Validation must not use final-evaluation dates")
    strategy = Strategy(specification["lookback_sessions"], Decimal(specification["threshold_sigma"]), specification["holding_open_intervals"])
    context, first_entry, signals = prepare_validation(snapshot.bars, start, end, strategy)
    evaluation = context[first_entry:]
    capital = Decimal(execution["initial_capital_usd"])
    fees = [Decimal(v) for v in config["cost_bps_per_side"]]
    primary = Decimal(config["primary_cost_bps_per_side"])
    if [str(v) for v in fees] != execution["cost_scenarios_bps_per_side"] or primary != Decimal(execution["primary_cost_bps_per_side"]):
        raise ValueError("Validation costs differ from frozen execution")
    output = root / "outputs/validation"
    output.mkdir(parents=True, exist_ok=True)
    write_rows(output / "signal_events.csv", (asdict(e) for e in signals.events),
               ("signal_date", "daily_return", "prior_volatility", "decision"))
    write_rows(output / "trade_schedule.csv", (asdict(t) for t in signals.trades),
               ("signal_date", "entry_date", "exit_date", "status"))
    benchmark = (ScheduledTrade(context[first_entry-1].date, evaluation[0].date, None, "awaiting_exit"),)
    scenarios, primary_results, primary_periods = [], {}, []
    for fee in fees:
        for name, calendar in (("dip", signals.trades), ("buy_and_hold", benchmark)):
            result = simulate(evaluation, calendar, fee, capital)
            if name == "dip" and result.terminal_liquidations:
                raise ValueError("Frozen validation forbids truncated dip trades")
            stem = f"{name}_{fee}bps"
            write_rows(output / f"{stem}_equity.csv", (asdict(v) for v in result.equity), tuple(EquityPoint.__dataclass_fields__))
            write_rows(output / f"{stem}_trades.csv", (asdict(v) for v in result.trades), tuple(ExecutedTrade.__dataclass_fields__))
            scenarios.append(dict(strategy=name, cost_bps_per_side=str(fee), primary=fee == primary,
                                  total_return=str(result.total_return), max_close_drawdown=str(result.max_drawdown),
                                  trades=len(result.trades), total_cost_usd=str(result.total_cost),
                                  terminal_liquidations=result.terminal_liquidations))
            if fee == primary:
                primary_results[name] = result
                primary_periods.extend(dict(strategy=name, **row) for row in period_metrics(result, capital, []))
    write_rows(output / "primary_periods.csv", primary_periods, tuple(primary_periods[0]))
    rows, control_periods = [], []
    rng = random.Random(control["seed"])
    with (output / "control_calendars.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("draw", "trade", "decision_date", "entry_date", "exit_date"))
        if signals.trades:
            for draw in range(control["calendars"]):
                calendar = sample_calendar(context, first_entry, len(signals.trades), strategy.holding_open_intervals, rng)
                result = simulate(evaluation, calendar, primary, capital)
                if len(result.trades) != len(signals.trades) or result.terminal_liquidations:
                    raise ValueError("Validation control failed count/duration matching")
                for number, trade in enumerate(calendar):
                    writer.writerow((draw, number, trade.signal_date, trade.entry_date, trade.exit_date))
                control_periods.extend(dict(draw=draw, **row) for row in period_metrics(result, capital, []))
                rows.append(dict(draw=draw, total_return=str(result.total_return), max_close_drawdown=str(result.max_drawdown),
                                 trades=len(result.trades), total_cost_usd=str(result.total_cost),
                                 mean_entry_daily_volatility=str(mean_entry_volatility(context, calendar, strategy.lookback_sessions))))
    write_rows(output / "control_draws.csv", rows,
               ("draw", "total_return", "max_close_drawdown", "trades", "total_cost_usd", "mean_entry_daily_volatility"))
    write_rows(output / "control_periods.csv", control_periods,
               tuple(control_periods[0]) if control_periods else ("draw", "period_kind", "period", "total_return"))
    dip = primary_results["dip"]
    control_values = sorted(Decimal(row["total_return"]) for row in rows)
    # Match the frozen comparator's nearest-rank p50; no interpolated median.
    median = Decimal(quantiles(control_values)["p50"]) if control_values else None
    contrast = dip.total_return - median if median is not None else None
    stress = next(Decimal(s["total_return"]) for s in scenarios if s["strategy"] == "dip" and s["cost_bps_per_side"] == "10")
    classification = classify_screen(dip.total_return, contrast, stress, len(signals.trades))
    code = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((root / "spy_backtest_audit").glob("*.py"))}
    summary = dict(stage="retrospective_temporal_validation", period=plan["validation"],
                   classification=classification, classification_kind="descriptive_screen_not_statistical_proof",
                   snapshot_sha256=snapshot.sha256, freeze_sha256=hashlib.sha256((root / "research/validation_freeze.json").read_bytes()).hexdigest(),
                   frozen_files=freeze["file_sha256"], python=platform.python_version(), code_sha256=code,
                   evaluation_start=str(evaluation[0].date), evaluation_end=str(evaluation[-1].date),
                   warmup_sessions=strategy.lookback_sessions+1, initial_capital_usd=str(capital),
                   primary_cost_bps_per_side=str(primary), scenarios=scenarios,
                   controls_count=len(rows), control_seed=control["seed"],
                   control_return_quantiles=quantiles(control_values) if control_values else None,
                   primary_control_contrast=str(contrast) if contrast is not None else None,
                   fraction_controls_strictly_below_dip=sum(v < dip.total_return for v in control_values)/len(control_values) if control_values else None,
                   excluded_tail_signals=sum(e.decision == "excluded_tail" for e in signals.events),
                   dip_mean_entry_daily_volatility=str(mean_entry_volatility(context, signals.trades, strategy.lookback_sessions)) if signals.trades else None,
                   control_mean_entry_daily_volatility_quantiles=quantiles(r["mean_entry_daily_volatility"] for r in rows) if rows else None,
                   final_evaluation="2022-2025_not_acquired_or_evaluated",
                   limitations=["Retrospective temporal validation; not a prospective market experiment.",
                                "Controls match counts and durations, not risk, regimes or dollar turnover.",
                                "The fraction of controls below dip is not a p-value.",
                                "Costs are illustrative; no significance test, power calculation or risk-adjusted alpha is reported.",
                                "Screening labels do not authorize paper/live deployment."])
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    # Keep first observation separate from the immutable pre-execution freeze.
    observation_path = root / "research/validation_first_observation.json"
    evidence = dict(period=summary["period"], snapshot_sha256=snapshot.sha256,
                    freeze_sha256=summary["freeze_sha256"], classification=classification,
                    scenarios=scenarios, primary_control_contrast=summary["primary_control_contrast"],
                    control_return_quantiles=summary["control_return_quantiles"])
    if observation_path.exists():
        original = json.loads(observation_path.read_text())
        if original["evidence"] != evidence:
            raise ValueError("Validation differs from its first recorded observation; document the discrepancy, do not overwrite")
    else:
        record = dict(status="VALIDATION_OBSERVED", observed_at_utc=datetime.now(timezone.utc).isoformat(),
                      evidence=evidence, first_execution_code_sha256=code)
        observation_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return summary, output
