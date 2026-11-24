# Temporal validation protocol - version 1

Status: rules frozen; validation execution not yet implemented or performed.
The 2000-2015 development outcomes have been observed. The 2016-2021 prices were
acquired for data integrity checks, but no strategy/control performance has been
calculated on them. This is retrospective temporal validation, not prospective
research or an assertion that these market episodes are unknown to the researcher.

## What is frozen

The existing primary signal (20 previous returns, negative 2 prior standard
deviations, five open-to-open intervals), execution accounting, 0/5/10 bps cost
scenarios (primary 5), 500 random calendars and seed 1729. No strategy variants
will be selected on validation. No search for a better seed, date range or cost.
The frozen file hashes and input/calendar identity are in validation_freeze.json.
A methodological change must create a documented new protocol version and explain
which data/outcomes were already viewed; do not silently replace this freeze.

## Boundary handling

- Begin flat, with initial capital reset to USD 100,000. Development positions do
  not cross the validation boundary.
- Read 21 prior sessions only to calculate the first validation close's signal.
  Do not report these warmup dates as validation outcomes or run historical entries.
- First possible validation signal: first validation session's close; first
  eligible strategy/control/benchmark entry: second session's open.
- The validation end is a fixed known calendar boundary. Permit new entries only
  if the five scheduled open intervals can finish within validation. Log excluded
  tail signals explicitly. Do not invent 2022 exit prices or silently drop trades
  after seeing their returns. This administrative entry cutoff is fixed now.
- Primary strategy and all random calendars have identical completed-trade counts
  and holding intervals. Buy-and-hold uses the same evaluation start and final
  validation close, with the previously specified dividend/cash/cost accounting.
- Report fixed annual decompositions. Do not restart positions at year boundaries.

## What the comparison means

Report primary net terminal return and its difference from the median random
calendar's net terminal return at 5 bps per side, alongside all cost scenarios,
drawdown, trade count, time exposure and entry-volatility differences.
This is a descriptive comparator conditional on observed trade count. It does not
match volatility, market beta or regimes and is not a statistical hypothesis test.
A high rank among controls is not a p-value or evidence of causal market reversal.

## Fixed screening labels

Apply the ordered descriptive rules in validation.json: no executable trades is
INCONCLUSIVE; a nonpositive primary return or comparator difference is
NOT_SUPPORTED_BY_VALIDATION_SCREEN; positive primary return/difference that fails
at 10 bps is INCONCLUSIVE_COST_FRAGILE; positive values on all three conditions is
PROMISING_MORE_RESEARCH. Zero is treated as nonpositive. These sign-based gates
are pragmatic reporting rules, not power calculations or confidence statements.
Report sample size and uncertainty limitations even if the screen is positive.
A failed screen does not prove no market effect exists; a passed screen does not
support paper/live deployment or show risk-adjusted alpha.

## What remains outside this freeze

No formal significance claim, bootstrap confidence interval, factor-adjusted alpha
or risk-matched null distribution is specified. They require an appropriate
separate design before implementation; do not bolt on whichever test looks best.
No neighbor-parameter selection, retraining, or optimization is included here.
Report negative validation unchanged. Any post-validation strategy revision makes
validation part of development for that revision. 2022-2025 remains unacquired.

Before later evaluating 2022-2025, fix any additional inferential methods and the
final decision protocol while explicitly acknowledging development/validation
already inspected. Preserve all original observations and methodological changes.
