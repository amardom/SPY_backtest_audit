# Execution assumptions - version 1

Recorded before computing strategy performance. These are explicit modeling
assumptions, not estimates calibrated to a broker or claims of executable fills.
No parameter is selected using the resulting performance.

- Evaluate only the development window. The evaluation starts at the first
  possible entry after the required signal warmup (bar index lookback + 2).
- Initial capital: USD 100,000. One long position, no leverage or borrowing.
- At each entry, invest all available cash; fractional shares are permitted.
- Buy at the next session's reported open plus a proportional cost. Sell at the
  scheduled open less the same proportional cost. The cost scenarios are 0, 5,
  and 10 basis points per side; 5 is the primary illustrative assumption.
- Costs bundle spread, slippage and commissions as a scenario, not an observed
  estimate. There is no separate commission, liquidity or capacity model yet.
- Cash earns zero. Cash dividends are added to cash and are not reinvested while
  the position remains open. They are available at the next entry.
- Credit a dividend on its ex-date only to shares held before that session's
  open: an entry that morning receives none; an exit that morning retains the
  entitlement. Cash is assumed available immediately on the ex-date rather than
  the later payment date. This simplification remains explicit.
- Split events are rejected. Current SPY research data report none.
- Mark portfolio equity at daily close. Drawdown is close-to-close and does not
  capture intraday or between-observation extremes.
- To compare on a common terminal horizon, liquidate any remaining position at
  the last development close, charging exit costs. Such trades are explicitly
  labeled terminal_close and may be shorter than five open intervals. This is a
  finite-study liquidation rule, not an adaptive trading exit.
- A signal on the last close has no available next open and is not executed.
- The benchmark buys at the first eligible evaluation open, receives dividends
  under identical accounting, and liquidates at the final close. Its capital,
  cost scenario and evaluation window match the strategy. Its exposure and risk
  do NOT match the strategy; it is descriptive context, not a test of timing alpha.

No annualized Sharpe, significance test, random-entry control or validation/OOS
performance is reported at this stage. A defensible control procedure remains
necessary before concluding that timing adds value.

The command produces per-trade accounting, daily equity and a descriptive summary
for each cost scenario under outputs/backtest/. Amounts use 28-digit Decimal
arithmetic; there is no broker cash/share rounding. No files contain 2016+ results.
