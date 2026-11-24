# Exploratory sampling uncertainty - addendum 1

This method is specified AFTER development and temporal-validation outcomes were
observed, but BEFORE computing these intervals. It is not a confirmatory
preregistration. Original strategy parameters, random calendars, cost assumptions,
validation classification and first-observation record remain unchanged.

## A distinct, explicit estimand

For every observed session t, compute net daily portfolio log growth for the dip
and each of the M=500 recorded random-calendar portfolios, using the identical
valuation dates and initial capital. Costs and cash days remain included.

    d[t] = log(NAV_dip[t] / NAV_dip[t-1])
           - (1/M) sum_j log(NAV_control_j[t] / NAV_control_j[t-1])
    Delta = mean_t d[t]

NAV before the first observation is the initial capital. Delta estimates the
difference in mean daily log growth from the equal-weighted average of control
log-growth series. This is the growth of a geometric comparison, NOT the return
of an investable equally weighted portfolio and NOT risk-adjusted alpha.

It differs from the original descriptive contrast (dip cumulative return minus
median control cumulative return). Do not replace that contrast or its screen.
Display Delta in basis points per observed session; do not annualize it.

## Paired stationary bootstrap

Generate 5,000 resamples of length N, using random contiguous blocks of the paired
difference series. Each new block begins at a uniform original session; block
lengths are geometric with mean L; continuation wraps circularly at the sample
end. Using the same sampled dates for both sides preserves their observed joint
dependence. Cash days are not discarded and trades are not sampled independently.

Primary L=20 sessions. Also report L=5 and L=60, without selecting whichever
interval is most favorable. Seed=314159; independent PCG64 streams use SeedSequence
[seed, period_code, L], where development=0 and validation=1. Fixed batch size 128;
record NumPy/Python versions. Quantiles use linear interpolation.

Report the observed Delta, bootstrap standard error and the 2.5th/97.5th
percentiles: an APPROXIMATE nominal 95% percentile interval under the resampling
assumptions. Do not turn the fraction above zero into a p-value. Do not change the
original screening classification based on these intervals.

## What uncertainty is and is not covered

This calculation treats the realized strategy and finite calendar ensemble as
fixed, and resamples their already realized paired daily growth series. It does
not regenerate signals, positions, market prices, costs or random-calendar counts
on new simulated market histories. It does not include calendar-ensemble Monte
Carlo uncertainty, parameter/model selection, vendor errors or economic-model
uncertainty. No new risk matching is introduced.

Stationary bootstrap theory requires suitable weak dependence and stationarity
conditions. Blocks preserve only local observed dependence; they do not make
financial regimes stationary or guarantee finite-sample coverage. There are only
40 validation trades despite many daily observations. Report all block lengths
and acknowledge possible instability, limited information and post-selection bias.
An interval containing zero is not proof of no effect. An interval excluding zero
is not confirmatory evidence after this study's development/validation inspection.

## Implementation checks and provenance

Reconstruct all 500 recorded calendars with the same accounting engine. Verify
that each terminal result agrees with its recorded draw and all daily dates align.
Retain the paired growth series, every bootstrap mean, configuration and hashes.
Check constant/identical cases, circular continuation, seed reproducibility,
parameter rejection, and a synthetic serially correlated series. Such checks
verify specified implementation properties, not empirical confidence coverage.

Method source: Dimitris N. Politis and Joseph P. Romano, The Stationary Bootstrap,
Journal of the American Statistical Association 89(428), 1994, 1303-1313.
https://doi.org/10.1080/01621459.1994.10476870
Author technical report: https://www.stat.purdue.edu/docs/research/tech-reports/1991/tr91-03.pdf
