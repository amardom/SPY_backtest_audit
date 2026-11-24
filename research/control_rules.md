# Random-entry reference - version 1

Recorded before examining random-reference outcomes. The strategy's development
performance has already been observed; this control is exploratory development
research, not a confirmatory test.

Generate 500 independent calendar draws with Python random.Random(1729). Each
calendar contains the same number of trades as the primary dip strategy. Each
trade holds for the same five open-to-open intervals, with no overlaps, and uses
the same initial capital, accounting, primary per-side cost and evaluation window.
No prices, dividends, returns or volatility enter the calendar sampler.

For N eligible sessions, n trades and h holding intervals, sample n distinct
integers y from range(N - n*h), sort them and set entry[j] = y[j] + j*h.
Exit[j] = entry[j] + h. This is a bijection between subsets and feasible calendars
with entry[j+1] >= exit[j]+1: no exit-open immediate re-entry, matching the primary
strategy's scheduling rule. All feasible fixed-count calendars are equiprobable.
Each control's decision_date is the preceding observed session, a bookkeeping
field rather than a price-generated signal.

The number of trades and sample length are conditioned on the completed study.
These are retrospective controls, not live trading policies. If the primary has
pending or terminally truncated trades, this version stops rather than quietly
claiming equal holding duration. All controls exit within the development window.

Counts, open-to-open intervals and cost RATES match. Dollar turnover, total cost
in dollars, risk, years of exposure and calendar-day durations do not necessarily
match. In particular, random entries do not reproduce the crisis concentration
or volatility at dip entries. Comparisons cannot by themselves establish alpha.

Use the existing simulate() accounting engine for every draw. Retain all calendar
entry/exit dates, each draw's result and drawdown; do not report only the best draw.
Record mean trailing 20-session dividend-inclusive volatility known at each entry
(includes the preceding close, unlike the signal's pre-shock volatility estimate)
as a descriptive risk-composition diagnostic, not a matching or selection rule.

The summary reports nearest-rank 5th/50th/95th percentiles of control returns and
the fraction strictly below the dip result. This fraction is NOT a p-value, an
alpha estimate, a confidence level, or a probability of future outperformance.
Drawdown is descriptive daily-close drawdown. No significance claim is made.
Random draws may repeat. Record the seed, algorithm version, Python version,
config and source hashes; use the same environment to reproduce exact calendars.
No validation or final-evaluation data are used.
