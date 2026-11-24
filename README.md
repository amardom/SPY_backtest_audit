# SPY_backtest_audit

**Buying the Dip: Does Timing Add Value?**

A Python study of short-term mean reversion in SPY. The strategy buys at the next
open after a daily return below -2 times prior volatility. Volatility uses the
previous 20 returns; each position lasts five open-to-open intervals.

## Results

| At 5 bps per side | Development, 2000-2015 | Validation, 2016-2021 |
| --- | ---: | ---: |
| Strategy net cumulative return | 49.44% | -0.02% |
| Median of 500 random-entry controls | 2.06% | 9.00% |
| Completed strategy trades | 124 | 40 |

The original rule fails its descriptive validation screen. Its development
advantage over random entries does not persist in the later period.

Two analyses were added after observing validation: paired stationary-bootstrap
intervals for relative daily log growth, and a 27-combination parameter grid.
The grid has positive control-relative returns in 25/27 development cases and
6/27 validation cases. Neither analysis changes the original screen or selects a
replacement rule. **2022-2025 has not been acquired or evaluated.**

## Report

**[Read the research report (PDF)](reports/spy-backtest-audit.pdf)**

The PDF is included in the repository and can be read without installing anything.
Running the study refreshes this copy as well as the detailed outputs.

The complete review ZIP contains `outputs/report/spy-backtest-audit-research.pdf` and all
files needed to check its inputs. Extract the whole archive, then run:

```bash
python3 run.py --summary
```

This checks the report and its input hashes without installing dependencies or
recalculating results. The report contains:

- Page 1: primary results and conclusion.
- Pages 2-7: trading rule, data, equity and drawdown, controls, yearly results and costs.
- Page 8: bootstrap intervals and assumptions.
- Pages 9-10: parameter sensitivity.
- Page 11: interpretation and reproduction details.

## Run

Use Python **3.12**; the recorded runs use 3.12.3. From the project directory:

```bash
python3 run.py --setup
python3 run.py
```

Setup installs `requirements.lock` into `.venv`. The study then runs offline using
the included snapshot and writes the PDF and supporting files to `outputs/`.
Allow several minutes. The launcher selects `.venv` automatically and also works
when called by absolute path from another directory.

Other commands:

```bash
python3 run.py --tests    # Synthetic tests; no market data required
python3 run.py --check    # Environment, snapshot, calendar and method checks
python3 run.py --summary  # Read verified existing results
```

A Git checkout includes source, research records and the input snapshot. Generated
outputs are excluded from Git; run the study before using `--summary` in a new
checkout. The review ZIP already includes those outputs. The report in `reports/spy-backtest-audit.pdf`
is available in both deliveries.

## Data

`data/raw/` contains the original Yahoo Finance response, acquisition record,
normalized CSV and manifest for 2000-2021. These are the exact input files used
in the recorded study. A new vendor request can return revised values and may
not reproduce the frozen snapshot.

No subscription or API key is needed. The explicit acquisition command is
`python3 -m spy_backtest_audit --fetch` inside the prepared environment. Existing archives
are reused. Normal runs do not request market data or install packages.

## Code

| File | Responsibility |
| --- | --- |
| `spy_backtest_audit/signals.py` | Causal signals and position dates |
| `spy_backtest_audit/backtest.py` | Fractional shares, costs, dividends and daily equity |
| `spy_backtest_audit/controls.py` | Uniform feasible random-entry calendars |
| `spy_backtest_audit/validation.py` | Fixed validation window and first-observation checks |
| `spy_backtest_audit/uncertainty.py` | Paired stationary-bootstrap intervals |
| `spy_backtest_audit/family.py` | Parameter grid and original-result reconciliation |
| `spy_backtest_audit/report.py` | Figures and PDF from recorded outputs |
| `tests/` | Synthetic accounting, timing, boundary and provenance checks |

Outputs include trade ledgers, equity paths, control calendars and returns,
bootstrap draws, parameter-grid metrics and report facts. Configurations, seeds,
code hashes and dependency versions accompany the results.

To build the review ZIP after running the study:

```bash
python3 scripts/package_release.py
```

The archive is written to `dist/spy-backtest-audit-review.zip`. Packaging checks the
snapshot and report dependencies, includes the source, data and results, and
excludes Git metadata, environments and caches. `package_manifest.json` lists the
SHA-256 hash of each included file. Git preserves file bytes through `.gitattributes`
so checkout does not change the hashes of archived data or method records.

## Interpretation

This is independent portfolio research using a fixed retrospective temporal
split, not walk-forward optimization. Controls match trade count and duration,
not market risk or regimes. Ranks are not p-values. Costs are illustrative;
daily-close drawdown omits intraday extremes. Historical vendor prices are not a
point-in-time corporate-action database. No risk-adjusted alpha or deployment
recommendation is established.

Current results are summarized in `research/current_status.md`; the method and
decision history are in `research/protocol.md`. Detailed rule documents and the
original configuration/observation records remain in `research/`. Their earlier
stage descriptions refer to when each record was made.

The engine can also be called directly as `python3 -m spy_backtest_audit` after activating
the environment. Supplying `--data` and `--manifest` explicitly performs only
schema validation on those files.
