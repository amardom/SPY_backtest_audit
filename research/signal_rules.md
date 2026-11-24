# Primary signal and calendar - version 1

Recorded before calculating signal counts or any strategy performance.
Numeric decisions below were agreed as an initial specification, not optimized.
The full research protocol remains a draft: controls, costs and inference are open.

## Signal

Let C[t] be session t's close and D[t] its ex-date cash dividend, both expressed
in the same share units. Define r[t] = (C[t] + D[t]) / C[t-1] - 1.
The dividend correction avoids treating a cash distribution as a price-only loss.
The current implementation rejects any split-event input: cross-split handling
must be specified before extending this dataset or accepting a different instrument.
Provider adjusted_close is not used to generate signals.

Compute sample standard deviation (n-1 denominator) of r[t-20], ..., r[t-1].
Do not include r[t]. A signal occurs when r[t] <= -2 * prior standard deviation.
Zero-volatility windows generate no signal. The mean is not subtracted from
r[t]; this is a volatility-scaled negative return, not a centered z-score.
At least 21 earlier closes are necessary to obtain the 20 prior returns.
All calculations use a local 28-digit Decimal context.

## Calendar

- Observe the signal at close t; schedule entry at open t+1.
- Exit at open t+6: five open-to-open intervals after entry. Session counts are
  row positions, not calendar-day additions.
- One position at a time; signals before its exit open are recorded as ignored.
- At the exit session's close, a fresh signal can schedule next-session entry.
- No stop, profit target, short selling, leverage or holding-period extension.
- Position sizing and cash treatment are not implemented at this stage.
- End-of-sample signals remain visible as awaiting_entry or awaiting_exit. No
  future date, price or availability determines whether the signal is accepted.

## Development boundary and artifacts

Only the development window from data_plan.json is passed to signal generation.
Validation data are not used to complete late development trades. Positions with
an unavailable exit remain pending and are not presented as completed operations.
No signal is generated for 2016-2021 and no 2022-2025 data have been acquired.
Boundary handling for later performance comparisons still needs specification.

`python3 -m spy_backtest_audit` validates the default snapshot and writes:

- outputs/signals/signal_events.csv: threshold events, including ignored signals.
- outputs/signals/trade_schedule.csv: accepted signals and known execution dates.
- outputs/signals/run.json: configuration, dataset and code hashes, Python version
  and stage limitations. Hashes identify working code even before a Git commit.

Explicit --data/--manifest paths remain validation-only to avoid accidentally
running strategy research on a different sample. No performance or report is
produced. Outputs can be regenerated; vendor data and outputs stay untracked.

Parameter-neighborhood variants are intentionally not implemented yet. Specify
the complete family and selection/inference policy before testing any of them.
