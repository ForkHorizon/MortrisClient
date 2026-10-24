# Multi-objective scientific evidence (WP5)

## What is measured and stored (per paired repeat)
Payload bytes/event (candidate and its paired reference), encode ns and decode ns of both, event count, wall time, correctness (`ok`/`rejection`: the exact typed round trip and the independent Go decode run inside the measurement; a mismatch is a recorded failure). Missing metrics stay NULL and are reported as `not_measured`; nothing is imputed.

## Derived on read (reproducible from persisted rows)
* n, mean, sd for bytes, encode ratio and decode ratio (candidate ns / its paired reference ns); `bytes_saved_vs_ref`.
* `cpu_vs_ref` verdict per CPU metric, descriptive only: `not_measured | single_run | too_few_repeats | slower | faster | indistinguishable` (mean +- 2 standard errors against 1.0, only for n >= 3). It is **not a p-value** and no bootstrap number is called one.
* Evidence level ladder: `not_measured -> exploratory_single_run -> repeated_measurement (n 2-4) -> repeated_measurement_n5+`. Nothing in development data reaches `independent_confirmation`; the exposed holdout stays exposed.
* Pareto frontier over (bytes/event, encode ratio, decode ratio), computed from means; deterministic order. A candidate dominates another only if it is at least as good on every objective the other has measured, so an unmeasured CPU metric can never make a candidate look better (`dominates`, tested).

## Director access and requests
The Director sees the frontier with uncertainty and `frontier_needing_repeats`, and can ask for more evidence with `measure` purposes `replicate`/`investigate`/`compare` and `repeats` up to 5 (trusted code trims by budget/time). Repeats are paired adjacent measurements with randomized order within each pair; they are repeats of one workload, **not** independent datasets.

## Declared MORTRIS metric coverage
| Metric | Status |
|---|---|
| payload bytes/event, encode CPU, decode CPU, correctness | measured (host, development cohort) |
| complete framed bytes/event | not separated from payload here (M7 framing is included in the measured payload; request/TLS bytes are modelled elsewhere) - not yet qualified |
| dictionary delivery cost | reported by the helper as asset bytes but not yet stored/compared - not yet qualified |
| allocations/GC, device (Android) performance, server processing | not measured by this pipeline; remain explicit gaps (the Android report has an unresolved provenance contradiction) |

## Not done
A generic domain-declared objective specification (directions, practical thresholds, replication requirements) as data; the M7 objectives are constants in `campaign_knowledge.OBJECTIVES`. No statistical test is implemented; practical thresholds are not defined, so "statistically supported effect" is not yet an evidence level. Status: Implemented + locally tested; **not scientifically validated**.
