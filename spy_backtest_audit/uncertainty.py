"""Calculate paired stationary-bootstrap intervals for daily log-growth differences."""
import csv
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import platform

import numpy as np

from .backtest import simulate
from .protocol import verify_validation_freeze
from .signals import ScheduledTrade
def daily_log_growth(equity, initial_capital):
    values = np.asarray([float(p.equity) for p in equity], dtype=np.float64)
    capital = float(initial_capital)
    if not len(values) or not np.all(np.isfinite(values)) or np.any(values <= 0) or not np.isfinite(capital) or capital <= 0:
        raise ValueError("Require finite positive equity and initial capital")
    return np.diff(np.log(np.concatenate(([capital], values))))
def stationary_indices(observations, replicates, mean_block, rng):
    if type(observations) is not int or observations < 2 or type(replicates) is not int or replicates < 1:
        raise ValueError("Require at least two observations and positive replicates")
    if type(mean_block) is not int or not 1 <= mean_block <= observations:
        raise ValueError("Mean block length must be an integer between 1 and sample length")
    indices = np.empty((replicates, observations), dtype=np.int64)
    indices[:, 0] = rng.integers(0, observations, size=replicates)
    for t in range(1, observations):
        restart = rng.random(replicates) < 1 / mean_block
        new_start = rng.integers(0, observations, size=replicates)
        indices[:, t] = np.where(restart, new_start, (indices[:, t-1]+1) % observations)
    return indices
def bootstrap_mean(values, *, mean_block, resamples, seed, period_code, batch_size=128):
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1 or len(values) < 2 or not np.all(np.isfinite(values)):
        raise ValueError("Require a finite one-dimensional series with at least two observations")
    if type(resamples) is not int or resamples < 2 or type(batch_size) is not int or batch_size < 1:
        raise ValueError("Require at least two resamples and a positive batch size")
    if type(seed) is not int or seed < 0 or type(period_code) is not int or period_code < 0:
        raise ValueError("Require nonnegative integer seed and period code")
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, period_code, mean_block])))
    means = np.empty(resamples, dtype=np.float64)
    for first in range(0, resamples, batch_size):
        size = min(batch_size, resamples-first)
        indices = stationary_indices(len(values), size, mean_block, rng)
        means[first:first+size] = np.mean(values[indices], axis=1)
    low, high = np.quantile(means, [.025, .975], method="linear")
    return dict(point=float(np.mean(values)), lower=float(low), upper=float(high),
                bootstrap_standard_error=float(np.std(means, ddof=1)), means=means)
def paired_difference(dip_dates, dip_growth, control_dates, control_growth):
    if tuple(dip_dates) != tuple(control_dates):
        raise ValueError("Paired portfolio dates do not align")
    dip, control = np.asarray(dip_growth, dtype=float), np.asarray(control_growth, dtype=float)
    if dip.ndim != 1 or control.ndim != 1 or len(dip) != len(control) or len(dip) != len(dip_dates):
        raise ValueError("Paired portfolio shapes do not align")
    if not np.all(np.isfinite(dip)) or not np.all(np.isfinite(control)):
        raise ValueError("Paired growth must be finite")
    return dip-control
def _rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))
def _write(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
def reconstruct_paired_series(root, snapshot, period, capital, fee, expected_controls):
    """Reprice archived calendars, verify terminal results, align all daily growth."""
    if period == "development":
        folder = root / "outputs/backtest"
        calendar_file = root / "outputs/controls/calendars.csv"
        draws_file = root / "outputs/controls/draws.csv"
        summary = json.loads((folder / "summary.json").read_text())
    else:
        folder = root / "outputs/validation"
        calendar_file, draws_file = folder / "control_calendars.csv", folder / "control_draws.csv"
        summary = json.loads((folder / "summary.json").read_text())
    if str(fee) != str(summary.get("primary_cost_bps_per_side", summary.get("execution", {}).get("primary_cost_bps_per_side"))):
        raise ValueError("Uncertainty cost differs from recorded primary cost")
    dip_rows = _rows(folder / f"dip_{fee}bps_equity.csv")
    dates = tuple(date.fromisoformat(r["date"]) for r in dip_rows)
    if not dates or any(dates[i] <= dates[i-1] for i in range(1, len(dates))):
        raise ValueError("Require ordered unique portfolio dates")
    from types import SimpleNamespace
    dip = daily_log_growth(tuple(SimpleNamespace(equity=Decimal(r["equity"])) for r in dip_rows), capital)
    bars_by_date = {b.date:b for b in snapshot.bars}
    bars = tuple(bars_by_date[d] for d in dates)
    calendars = {}
    for row in _rows(calendar_file):
        decision_key = "decision_date"
        calendars.setdefault(int(row["draw"]), []).append(ScheduledTrade(
            date.fromisoformat(row[decision_key]), date.fromisoformat(row["entry_date"]),
            date.fromisoformat(row["exit_date"]), "scheduled"))
    recorded = {int(r["draw"]):r for r in _rows(draws_file)}
    if set(calendars) != set(range(expected_controls)) or set(recorded) != set(calendars):
        raise ValueError("Control ensemble differs from the recorded full draw set")
    aggregate = np.zeros(len(dates), dtype=np.float64)
    log_terminal = []
    for draw, schedule in sorted(calendars.items()):
        if len(schedule) != int(recorded[draw]["trades"]):
            raise ValueError("Archived control count differs")
        result = simulate(bars, tuple(schedule), fee, capital)
        if result.terminal_liquidations or abs(float(result.total_return)-float(recorded[draw]["total_return"])) > 1e-12:
            raise ValueError("Reconstructed calendar does not reproduce its recorded result")
        if tuple(p.date for p in result.equity) != dates:
            raise ValueError("Reconstructed portfolio dates differ")
        aggregate += daily_log_growth(result.equity, capital)
        log_terminal.append(np.log1p(float(result.total_return)))
    average = aggregate / expected_controls
    delta = paired_difference(dates, dip, dates, average)
    dip_scenario = next(r for r in summary["scenarios"] if r["strategy"] == "dip" and r["cost_bps_per_side"] == str(fee))
    expected_sum = np.log1p(float(dip_scenario["total_return"])) - float(np.mean(log_terminal))
    if not np.isclose(delta.sum(), expected_sum, rtol=0, atol=1e-11):
        raise ValueError("Daily paired contrast does not reconcile with terminal wealth")
    return dates, dip, average, delta
def write_uncertainty_artifacts(root, snapshot):
    freeze = verify_validation_freeze(root)
    if snapshot.sha256 != freeze["snapshot_sha256"]:
        raise ValueError("Uncertainty snapshot differs from the frozen dataset")
    config_path = root / "research/uncertainty.json"
    config = json.loads(config_path.read_text())
    record = json.loads((root / "research/uncertainty_plan_record.json").read_text())
    for relative, expected in record["file_sha256"].items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Uncertainty addendum or original observation changed; document a new version")
    if (config["bootstrap"] != "paired_stationary_circular_geometric_blocks" or config["interval"] != "percentile"
            or config["confidence_level"] != .95 or config["quantile_method"] != "linear"
            or config["estimand"] != "mean_daily_log_growth_dip_minus_mean_of_fixed_random_calendars"):
        raise ValueError("Unsupported uncertainty specification")
    execution = json.loads((root / "research/execution.json").read_text())
    control = json.loads((root / "research/controls.json").read_text())
    plan = json.loads((root / "research/data_plan.json").read_text())
    capital, fee = Decimal(execution["initial_capital_usd"]), Decimal(config["cost_bps_per_side"])
    output = root / "outputs/uncertainty"
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for period, period_code in config["period_codes"].items():
        if period not in ("development", "validation"):
            raise ValueError("Uncertainty must not access the final evaluation")
        dates, dip, average, delta = reconstruct_paired_series(root, snapshot, period, capital, fee, control["calendars"])
        start, end = (date.fromisoformat(plan[period][k]) for k in ("start", "end_exclusive"))
        if any(not start <= d < end for d in dates):
            raise ValueError("Uncertainty dates cross the declared period")
        _write(output / f"{period}_paired_growth.csv", ("date", "dip_net_log_growth", "mean_control_net_log_growth", "difference"),
               zip(dates, dip, average, delta))
        for block in config["mean_block_sensitivity_sessions"]:
            result = bootstrap_mean(delta, mean_block=block, resamples=config["resamples"], seed=config["seed"],
                                    period_code=period_code, batch_size=config["batch_size"])
            _write(output / f"{period}_block_{block}_bootstrap.csv", ("draw", "mean_daily_log_growth_difference"),
                   enumerate(result["means"]))
            summaries.append(dict(period=period, observations=len(dates), controls=control["calendars"],
                                  mean_block_sessions=block, primary=block==config["primary_mean_block_sessions"],
                                  point_bps_per_session=result["point"]*10000,
                                  lower_bps_per_session=result["lower"]*10000,
                                  upper_bps_per_session=result["upper"]*10000,
                                  bootstrap_standard_error_bps=result["bootstrap_standard_error"]*10000,
                                  interval_contains_zero=result["lower"] <= 0 <= result["upper"]))
    source_paths = [root / "research/uncertainty.json", root / "research/uncertainty_rules.md", root / "research/uncertainty_plan_record.json",
                    root / "outputs/backtest/summary.json", root / "outputs/backtest/dip_5bps_equity.csv",
                    root / "outputs/controls/calendars.csv", root / "outputs/controls/draws.csv",
                    root / "outputs/validation/summary.json", root / "outputs/validation/dip_5bps_equity.csv",
                    root / "outputs/validation/control_calendars.csv", root / "outputs/validation/control_draws.csv"]
    summary = dict(stage=config["stage"], config=config, snapshot_sha256=snapshot.sha256,
                   python=platform.python_version(), numpy=np.__version__, results=summaries,
                   source_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
                   code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   original_validation_screen="unchanged", final_evaluation="not_accessed",
                   limitations=["Approximate percentile intervals under weak-dependence/stationarity assumptions; coverage is not guaranteed.",
                                "Method added after observing validation, not confirmatory or selection-adjusted.",
                                "Conditional on the fixed realized calendar ensemble; does not include its finite Monte Carlo uncertainty.",
                                "Resamples realized paired growth, not prices or a strategy rerun on new market paths.",
                                "Log-growth difference is not the original median cumulative-return contrast, investable portfolio return or risk-adjusted alpha."])
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return summary, output
