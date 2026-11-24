# Research status

## Primary validation result

The fixed rule fails the 2016-2021 descriptive screen:
`NOT_SUPPORTED_BY_VALIDATION_SCREEN`.

| Validation metric | Value |
| --- | ---: |
| Completed trades | 40 |
| Net return, zero costs | 4.06% |
| Net return, 5 bps per side | -0.02% |
| Net return, 10 bps per side | -3.94% |
| Median of 500 controls, 5 bps | 9.00% |
| Strategy minus control median | -9.02 percentage points |

These are cumulative returns over the validation window. The nonpositive primary
return and negative control contrast fail the recorded sign-based screen. The
comparison does not establish a causal mechanism or rule out every reversal
strategy. Controls are not risk-matched and their ranks are not p-values.

## Analyses added after validation

The paired stationary bootstrap estimates the difference in mean daily net log
growth from the fixed control ensemble. It is a different quantity from the
median cumulative-return contrast above. Its approximate intervals depend on
resampling assumptions and do not account for parameter selection.

The parameter grid contains 27 combinations. Positive control-relative returns
occur in 25/27 development cases and 6/27 validation cases. All combinations are
reported; the original 20/2/5 rule is unchanged and no replacement is selected.

## Records and outputs

The pre-execution freeze and first observed validation result are preserved in
`validation_freeze.json` and `validation_first_observation.json`. The status in
the freeze describes when it was recorded, not whether validation has since run.

`python3 run.py` generates the 11-page report and its supporting files. The review
ZIP includes those outputs and the archived input snapshot. **2022-2025 remains
unacquired and unevaluated.**
