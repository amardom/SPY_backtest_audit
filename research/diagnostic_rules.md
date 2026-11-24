# Temporal and risk diagnostics - version 1

After observing full-development strategy and random-reference results, examine
stability without altering the signal, controls, seed or cost assumption.
This is exploratory decomposition, not additional independent evidence.

Use primary costs and the existing 2000-2015 development sample only. Report each
calendar year plus three predetermined calendar blocks: 2000-2004, 2005-2009,
2010-2015. They are calendar partitions, not inferred economic regimes. The first
year starts after signal warmup. No favorable block or year is omitted.

- Carry equity and positions continuously over boundaries; do not restart capital
  or force trades to close at a year/block boundary.
- Period return = ending equity / equity before the first period observation - 1.
  The first observed period begins with the initial capital before initial costs.
- Period USD P&L = ending equity minus equity at period start. Annual USD P&Ls add
  to full-study P&L; annual returns compound, not sum.
- Local close drawdown resets its reference peak to period-start equity. This is
  distinct from drawdown measured against the full-history high-water mark.
- Daily volatility is sample standard deviation of daily portfolio returns,
  including cash days. It is not annualized and not a significance statistic.
- Close exposure = fraction of observed closes with shares held. This snapshot
  measure excludes exit-day overnight risk and is not a complete risk measure.
- Entry count is attributed to the entry date. A year without new entries can
  have returns from positions carried across its boundary.

For all 500 existing random calendars, save every year/block/all-period metric.
Compare primary dip metrics against nearest-rank 5/50/95 percentiles of controls.
Report counts and exposure as well as return, drawdown and volatility. Year-level
counts and risk are not matched even though full-study trade counts are.

Also compare mean trailing daily volatility observable before entry. The dip and
controls may have different volatility distributions. No matching, regression
alpha estimate, p-value or risk-adjusted superiority claim is introduced here.
Repeated and overlapping diagnostics are not independent hypothesis tests.
Calendar completeness and vendor accuracy remain separate pending checks.
