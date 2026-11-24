# Exploratory parameter family, specified before execution

This addendum follows observation of validation and the uncertainty addendum.
It is not a new holdout, parameter search for deployment, or selection-adjusted
inference. Report all 27 combinations in both already observed windows. Retain
the original 20/2/5 reference and original validation classification. Never access
2022-2025. No automatic winner, significance test or additional bootstrap family.

Grid: prior-return sample volatility windows 15/20/30, negative-return thresholds
1.5/2/2.5 sigma, open-to-open holding horizons 3/5/10. Use existing causal signals,
nonoverlap, all-cash fractional sizing, dividend entitlement, zero cash yield and
5 bps per side. Development retains its existing terminal-close liquidation
policy; report truncated trade counts. Validation uses existing prior-close warmup
and horizon-specific entry cutoff, admitting only full trades. Development starts
after each lookback's warmup, so its first evaluation date varies; validation
starts at the same second session for each lookback. Report dates explicitly.

Each cell receives 500 seeded uniform feasible calendars from sample_calendar,
matching its executed count, nominal holding horizon, eligible dates, costs and
one-position rule. Development terminal truncation, where present, is not matched
by full-horizon controls. Controls are not risk/regime/exposure matched. Empty
strategies receive no controls and null contrasts, never a favorable zero rank.
Use seed 1729 separately in every cell, as in the original primary runs. Results
across cells share data and random streams and are not independent experiments.

Record net cumulative return, daily-close drawdown, trade count, terminal exits,
nearest-rank p50 control return and difference in percentage points. Preserve every
control return and its entry indices relative to the recorded evaluation window;
exit index is entry index plus holding. Preserve dip trade ledgers. No annualized
comparison between windows. A map is descriptive, not a probability of an edge.

Control acceleration: precompute each feasible unit-capital isolated trade using
the unchanged simulate engine. With all cash allocated at entry, fractional
shares, proportional fees, no intratrade dividend reinvestment and zero cash
yield, multiply trade wealth factors for nonoverlapping calendars. Decimal
rounding need not be bitwise identical: reconcile the first control in every
nonempty cell with full simulation within 1e-20 absolute return. Tests cover all
calendars on synthetic dividend data. Primary dip and control p50 must reproduce
archived primary results within that tolerance or execution fails.

Output metadata hashes this plan, configuration, original observation, data plan,
execution and original strategy, plus the generating code and snapshot identity.
Changes to the recorded plan require a new explicit version. The report shows
all grid cells with a common color scale, highlights the original reference,
and reports counts of positive net returns/contrasts without choosing a winner.
