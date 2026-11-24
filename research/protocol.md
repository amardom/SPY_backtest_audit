# Research protocol

## Question and specification

Does buying SPY after a large negative daily return improve performance relative
to entering without that price signal?

The primary rule uses the previous 20 dividend-inclusive daily returns to
calculate sample volatility. A return at or below -2 times that volatility
schedules entry at the next open. The position exits five open-to-open intervals
later. One position is allowed; signals while holding are ignored.

The portfolio uses all available cash, fractional shares and zero cash yield.
Dividends belong to shares held before the ex-date open and are credited to cash
that day. Costs are 0/5/10 bps per side, with 5 bps primary. Development liquidates
remaining positions at its final close. Validation starts flat and excludes new
entries that cannot complete their holding period before the window ends.

## Data and evaluation

| Window | Use |
| --- | --- |
| 2000-2015 | Development and diagnostics |
| 2016-2021 | Fixed retrospective temporal validation; results observed |
| 2022-2025 | Reserved; not acquired or evaluated |

The archived Yahoo Finance snapshot, its original response and metadata are in
`data/raw/`. The workflow checks CSV identity, row integrity, corporate actions
and dates against a pinned XNYS session calendar. These checks do not certify
vendor prices or executable fills. Split-event accounting is unsupported and
such inputs are rejected.

This is a fixed temporal split, not walk-forward training. Historical separation
does not make the study prospective or remove the effects of earlier design
choices. Any later use of the reserved period needs a recorded decision rule
before its results are inspected.

## Comparisons and interpretation

Each window has 500 seeded random-entry calendars matching the observed trade
count, holding horizon, eligible dates, position limit and cost rate. Their
median return is a descriptive comparator. They are not matched for beta,
volatility or regimes. Buy-and-hold is also shown, with its greater exposure.

The original sign-based validation screen is specified in `validation.json`.
It fails when primary net return or the control-median contrast is nonpositive.
Passing would justify further research, not deployment or a claim of alpha.
The primary rule failed. Its first observation is retained on subsequent runs.

Two extensions followed observation of validation:

- Paired stationary-bootstrap intervals for mean daily net log-growth difference
  from the fixed control ensemble. The primary expected block length is 20
  sessions; 5 and 60 are also reported, with 5,000 resamples for each.
- All 27 combinations of lookback 15/20/30, threshold 1.5/2/2.5 and holding
  horizon 3/5/10, with 500 controls per cell. No replacement rule is selected.

Both extensions were recorded before their own results were computed. They are
exploratory and do not supply selection-adjusted inference or a new holdout.
Detailed assumptions are in `uncertainty_rules.md` and `parameter_family_rules.md`.

## Decision history

| Stage | Information already observed | Recorded decision |
| --- | --- | --- |
| Initial design | No strategy results | Daily SPY, long only; chronological development and later evaluation |
| Acquisition | No strategy results | Free Yahoo data through 2021; reserve 2022-2025 |
| Primary signal | No signal counts or performance | 20-return sample volatility, -2 threshold, next-open entry, five-interval exit |
| Accounting | No portfolio performance | Cash, dividend entitlement, fractional sizing and 0/5/10 bps costs |
| Random controls | Primary development performance | 500 uniform feasible calendars, seed 1729 |
| Diagnostics | Development controls | All calendar years, fixed multi-year blocks and entry-volatility summaries |
| Validation freeze | Development results | Fixed primary rule, boundary handling, controls and descriptive screen |
| Validation execution | Recorded freeze | Run 2016-2021 once and preserve the first observation |
| Reporting | Validation results | Generate the PDF from the recorded analysis outputs |
| Sampling uncertainty | Development and validation results | Record the paired-log-growth estimand and block-bootstrap settings |
| Parameter grid | Validation and uncertainty results | Record and report the complete 27-cell family |
| Review distribution | Completed study | Include archived data and all report dependencies in the review ZIP |

## Reproduction and records

Use `python3 run.py` after `--setup`. The command checks inputs and the recorded
configuration hashes, reproduces the analysis and generates the report. The
launcher also provides `--tests`, `--check` and `--summary`.

The original method files and hashes are listed in `validation_freeze.json`.
`validation_first_observation.json` records the first validation outcome.
The uncertainty and parameter-family plan records separately hash their original
specifications. These records are not replaced when the code, documentation or
report presentation changes. Discrepancies fail rather than overwrite the result.

Each analysis exports its configuration, data identity, code hashes and seeds.
The report records its input hashes and dependency versions. The review archive
includes every report dependency and a per-file package manifest.

Synthetic tests cover the stated accounting, timing, sampling and boundary
cases. They do not prove the absence of every implementation error or bias.
Any further experiment should retain its configuration and results, including
unfavorable outcomes, and state which data had already been inspected.
