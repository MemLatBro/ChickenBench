# ChickenBench shared formula specification

Formula version **1.1.0** · analyzer **1.2.0** · capture package **1.0.7**

This version defines a separate workload-wide aggregate and retention score for
each native metric, alongside per-load retention, degradation, local rate, frame-time
dispersion and repeatability. Workload integration is uniform in the native load
coordinate. Different metrics and sweep modes are never combined.

## 1. Reference and aggregation

For each configuration label and sweep mode, the default reference is the **first
workload level recorded in the first manifest read for that configuration/mode**.
Runs are read in sorted folder order, and manifest rows retain their original order.
Thus the normal low-to-high chicken sweep uses its starting chicken count, and the
normal timescale sweep uses its starting multiplier. Zero chickens is not hardcoded.
If run folders have been renamed, that ordering can change; choose a reference
explicitly when folder order does not represent the intended first run.

The reference is a workload level, not the first individual noisy frame or lap.
All eligible repeated laps at that same level, across the selected runs, contribute
to its arithmetic mean. If there is only one such lap, its value is the reference.
A failed starting level is retained as the reference and produces missing derived
values; the analyzer does not silently move the reference to a later successful level.

`--reference-chickens N` and `--reference-timescale N` override this rule for that
mode. An absent explicit reference remains absent. Different configurations may
start at different levels; the report displays and warns about this situation.

For a native lap statistic x, the level estimate is

    mu(L) = sum(x_j(L) for eligible laps j) / n(L).

Each eligible lap has equal weight, regardless of frame count or capture duration.
Within each lap, average FPS remains the original frames/time statistic. A ratio
of level means is calculated **after** aggregation; it is not a mean of lap ratios.
These estimands differ when the reference varies between laps.

The existing `--baseline JEDEC` option remains unchanged: it compares configuration
labels at the same workload in the legacy comparison export. It is separate from
the starting-workload reference used for retention.

## 2. Independent formula definitions

Let b = mu(L0), x = mu(L), and let x and b be positive and finite.

| Quantity | Definition | Units |
| --- | --- | --- |
| Higher-is-better retention | R = x / b | dimensionless ratio |
| Lower-is-better retention | R = b / x | dimensionless ratio |
| Retention percent | 100 R | percent |
| Relative degradation | D = 100 (1 - R) | percentage points of retained performance |
| Local degradation rate | G_i = (D_i - D_(i-1)) / (L_i - L_(i-1)) | percentage points / native workload unit |

No values are clipped to 0–100%. Improvements retain R > 1, D < 0, and potentially
negative local rates. There is no monotonicity enforcement or smoothing.

For lower-is-better metrics, reciprocal retention is a deliberate
**throughput-equivalent** convention. If latency doubles from 10 to 20 ms, R = 0.5
and D = 50; the latency increase itself is 100%. This convention is suitable when
the question concerns retained inverse-latency performance. It is not a universal
claim that all application utility is reciprocal in latency. Export native values
alongside it so another interpretation can be reconstructed.

Rates use actual adjacent workload coordinates, including irregular spacing. They
are secant/finite-difference estimates, not directly observed continuous derivatives.
The first scheduled coordinate has no preceding interval. Rates require two valid
adjacent endpoints and a valid common reference. A failed or missing scheduled level
blocks both adjoining rates; the analyzer never draws a slope across that gap.
Rows from manifest unions and, when available, `run_info.txt` schedules preserve
these missing levels. If neither source lists an omitted level, the analyzer cannot
discover that it was intended.

Duplicate `(run, pass, mode, configuration, level)` manifest rows are individually
retained in the audit and all excluded from the new calculations. Repeated
measurements at the same load in different passes are legitimate repetitions.

## 2.1. Singular aggregate values for each metric (new in 1.1.0)

Let the complete declared load grid be L_0 < ... < L_k, with span H = L_k - L_0.
The default summary uses the entire scheduled/manifest-union range for that mode,
including missing declared levels. The reference remains the first recorded load
for each configuration unless explicitly overridden; it need not equal L_0.

The level means mu_i and retention ratios R_i are computed first, as above.
For each metric independently:

    Native workload average = sum[(L_i-L_(i-1)) * (mu_(i-1)+mu_i)/2] / H
    Retention score (%)     = 100 * sum[(L_i-L_(i-1)) * (R_(i-1)+R_i)/2] / H
    Mean degradation (pp)   = 100 - Retention score
    End-to-end loss rate    = [D(L_k)-D(L_0)] / H

The native aggregate retains the metric's units (FPS, ms or percent). The retention
score is a single percentage for that metric: 90% means 90% of reference performance
was retained on average across the tested workload range. It can exceed 100%; no
clipping is applied. For lower-is-better metrics, integrate the pointwise reciprocal
retentions; the result is not generally the reciprocal of the native aggregate.
SD/CV receive native aggregates only, including valid zero values.

These are trapezoidal integrals of piecewise-linear curves, uniformly weighted in
the native workload coordinate. This is an explicit workload-weighting convention,
not a claim about workload frequency or consumer utility. It avoids weighting an
interval more simply because it contains more test points. Adding a point on an
existing straight segment leaves the aggregate unchanged; a point showing new
curvature can change it. Uniform-per-level arithmetic averaging is different.

Example: FPS [100, 90, 50] at loads [0, 10, 100] gives a native aggregate of
72.5 FPS and a retention score of 72.5%, rather than the unweighted point mean of
80 FPS. A linear fall from 100 to 60 FPS over [0, 100] gives 80 FPS, an 80% score,
20 pp mean loss, and an end-to-end loss rate of 0.4 pp per load unit.

The 1% low is 1000 / p99 frame time in ms. The 0.1% low is 1000 / p99.9 in ms.
A 0.01% low would use p99.99 and is not added by this release. Each aggregate
averages the per-load reciprocal-percentile FPS measurements after eligible laps
have been averaged at that load. It is neither a percentile of pooled frames nor
the reciprocal of an averaged frame-time percentile.

Full-range area aggregates require at least two distinct load levels and an eligible
measurement at every scheduled level. A missing level withholds the full-range
aggregate; gaps are never bridged and partial coverage is not renormalized into a
full-range score. Coverage is the fraction of the span whose adjacent endpoints are
both valid. A missing reference withholds retention but can leave the native aggregate
available. The end-to-end rate depends only on its two endpoints and reference, so
it may remain available despite a missing interior measurement. It describes net
loss and can hide intermediate falls/recoveries; the area score and curves retain
that information.

Compare matching workload ranges, native coordinates and reference loads. Every
summary exports these, the load grid and a comparison-domain identifier. Changing
the ending load can change a score. Chicken-count and timescale scores remain separate.

Aggregate 95% percentile intervals jointly resample whole sweeps (one run) or whole
runs (multiple runs), recomputing all required level means, the reference and the
complete statistic per draw. No pointwise bounds are averaged. Native areas require
identical unit support over the full grid; retention adds the reference dependency;
end-to-end rates require just both endpoints and reference. Fewer than three units
withholds an interval; 3–9 units remain exploratory. A single sweep still provides
point estimates, with no inferred repeatability interval.

## 3. Native metrics and temporal consistency

Native calculations remain those of `cb_analyze.lap_metrics`:

| Metric | Definition / role | New-layer minimum frames |
| --- | --- | --- |
| `avg_fps` | 1000 * frames / sum(frame times in ms); higher is better | 2 |
| `p1_fps` | 1000 / empirical p99 frame time; tail-performance measure | 300 |
| `p01_fps` | 1000 / empirical p99.9 frame time; tail-performance measure | 3000 |
| `ft_p50_ms`, `ft_p90_ms` | empirical interpolated frame-time percentiles | 2 |
| `ft_p99_ms` | empirical p99 frame time | 300 |
| `ft_p999_ms` | empirical p99.9 frame time | 3000 |
| `ft_max_ms` | maximum observed frame time in this capture | 2 |
| `ft_sd_ms` | population SD of the observed frame times within one lap | 2 |
| `cov_pct` | 100 * within-lap SD / within-lap mean frame time | 2 |

The 300/3000 thresholds adopt the existing analyzer's warning thresholds as
metric-specific eligibility rules in the new export. They are heuristic minimum
tail support, not proof that a percentile is precisely estimated. Historical CSVs
retain their previous values and warning behavior.

Within-lap SD/CV describe **distributional dispersion**, not chronological
predictability, and do not detect every stutter pattern. Reordering frames leaves
them unchanged. The original per-second timelines are retained for temporal context.
`p1_fps` is not equated with a complete temporal-consistency measure.

SD and CV are exported in native units, including valid zero dispersion. Retention,
degradation and slopes are intentionally not calculated for these dispersion metrics;
a percentage reduction in dispersion is not the same quantity as performance retention.

Between-lap SD is the sample SD (n-1 denominator) of repeated eligible lap statistics.
Its CV is 100 * sample SD / level mean. These are descriptive repeatability measures,
not the within-lap SD and not the standard error of the level mean. With one lap,
between-lap SD/CV are missing.

A maximum is a maximum **observed in a finite capture**, not a bound on future
frame times. Comparisons of tails/maxima must consider capture duration and frame
count, especially across timescales. The bootstrap resamples lap summaries, never
individual frames or order statistics within one capture.

## 4. Uncertainty and shared references

The bootstrap estimand is the same equal-lap mean used for the point estimate.
Frames are never treated as independent experimental repetitions.

* With one run, the resampling unit is a complete recorded pass/sweep, conditional
  on that run. Corresponding levels retain the same pass identifier.
* With multiple runs for a configuration/mode, the resampling unit is the entire
  run, including all its passes. Six laps from two runs do not become six
  independent runs.
* For each derived ratio or slope, the required levels must have **identical
  sets of eligible resampling units**. When support differs, point estimates can
  still be shown, but the derived CI is withheld as `unmatched_unit_support`.
* Each bootstrap draw resamples units with replacement and recomputes all required
  level means, the reference, the ratio and/or slope together. This preserves shared
  reference uncertainty and within-unit covariance. There is no independent-error
  approximation between adjacent ratios.
* The interval is the linearly interpolated 2.5th and 97.5th percentiles of the
  resulting bootstrap statistic, with 2000 draws and deterministic seed 1729 by
  default. The RNG substream is SHA-256-derived from the seed and dependency set,
  so interpreter hash randomization does not affect reproducibility.
* Fewer than 3 eligible independent units: no inferred interval. This is a
  conservative implementation threshold, not a statistical theorem. With 3–9 units,
  intervals are explicitly exploratory; small-sample coverage has not been validated.
  `--stability-bootstrap 0` disables inferred intervals. Otherwise at least 200 draws
  are required; the default remains 2000.
* At the reference itself R = b/b = 1 exactly, with displayed identity bounds [1,1]
  and D bounds [0,0]. This is an algebraic identity. The native reference mean
  retains its own uncertainty; it has not become a perfectly known measurement.

Intervals are **pointwise**, not simultaneous confidence bands over all workloads.
They assume exchangeability/independence of the chosen sweep/run units and cannot
correct systematic thermal drift, fixed stage order, background processes,
nonrandom missingness, chicken age/location differences, or count-measurement error.
One run cannot estimate variation between runs. Unmatched support is not imputed,
and an invalid bootstrap draw causes the interval to be withheld rather than silently
discarded. Units, accepted draw counts and availability reasons are exported.

For methodological comparison, first-order propagation would require covariance.
Writing V_i = Var(mu_i), V_b = Var(b), C_ib = Cov(mu_i,b):

    Higher: Var(R_i) ~= V_i/b^2 + mu_i^2 V_b/b^4 - 2 mu_i C_ib/b^3
    Lower:  Var(R_i) ~= b^2 V_i/mu_i^4 + V_b/mu_i^2 - 2 b C_ib/mu_i^3
    Var(G_i) ~= 10000 / delta_L^2 * [Var(R_i-1) + Var(R_i) - 2 Cov(R_i-1,R_i)]

These equations explain the dependence that the joint resampling preserves. They
are documented for review and are **not** an additional implemented CI method.
Small adjacent intervals amplify noise through division by delta_L. Local-rate
intervals crossing zero do not establish a monotonic local performance loss.

Primary methodological references, consulted 2026-10-28:

* [NIST TN 1297 Appendix A: propagation of uncertainty and covariance](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-law-propagation-uncertainty)
* [Wang, Iyer and Hannig (2003), uncertainty for ratios of dependent measurements](https://www.nist.gov/publications/uncertainty-calculation-ratio-dependent-measurements)
* [NIST/SEMATECH bootstrap overview and cautions](https://www.itl.nist.gov/div898/handbook/eda/section3/bootplot.htm)

These sources support the general treatment of dependence and resampling, not a
claim that the particular ChickenBench interval procedure or thresholds are validated.

## 5. Validity and missing data

New calculations exclude nonpositive/nonfinite performance values, invalid workload
coordinates, duplicated sweep coordinates, disallowed runner statuses, contradictory
count/timescale metadata, short captures, missing metric data, and insufficient
metric-specific frame support. Native zero SD/CV remain valid.

The original duration rule is retained: a recorded capture shorter than 80% of
its positive requested duration is excluded. Passing this check means only
`duration_consistent`, not that every expected frame or simulation step is verified.

Chicken counts are checked at the recorded pre-capture/post-capture endpoints
against the intended count and the runner's tolerance from `run_info.txt`. If
unavailable, the explicit analyzer fallback defaults to 10% and is recorded in
the audit. Count boundaries use the runner's floor/ceiling convention. A non-unit
timescale in a chicken sweep is incomparable. Intended count, pre-capture count,
post-capture count and source status are retained separately.

Slope validity also propagates unverified metadata from the previous endpoint. Known contradictions exclude the lap. Missing counts or missing capture-window
metadata allow **provisional** numerical estimates but are conspicuously marked
unverified, including when the unverified metadata belongs to the reference. Endpoint
counts do not prove continuous workload integrity. Timescale metadata records the
requested setting, not measured work completed by the engine.

Missing measurements are empty cells in new CSVs, never invented zeros or literal
NaN/Infinity. Original exports retain their historical serialization for compatibility.
All lap rows remain identifiable in `stability_laps.csv`, including excluded rows;
per-metric exclusion reasons and source hashes permit independent checking.

## 6. CSV interface

`stability_metrics.csv` contains one row per configuration/mode/declared-load/native
metric. Its per-load field names are unchanged in formula version 1.1.0. Groups of fields:

| Fields | Meaning |
| --- | --- |
| `benchmark_id`, `benchmark_version`, `benchmark_version_source`, `analyzer_version`, `formula_version` | producer identities; explicit source identifies a package assumption, original run metadata, or unknown capture version for unverified imports |
| `configuration_id`, `configuration_identity`, `mode`, `metric_name`, `metric_role` | configuration label, identity caveat, separate sweep/metric domains |
| `metric_units`, `metric_direction`, `workload_units`, `workload_coordinate_source` | native measurement and workload definitions |
| `workload_level`, `baseline_workload`, `baseline_selection`, `baseline_value` | coordinate and reference rule/value |
| `measured_value`, `aggregation` | equal-lap native mean before normalization |
| `sample_count_laps`, `baseline_sample_count_laps`, `attempted_laps`, `excluded_laps` | actual per-metric repeated-lap support |
| `sample_count_frames`, `min_frames_per_lap` | descriptive frame support, never the CI repetition count |
| `between_lap_sd`, `between_lap_cv_pct` | descriptive repeated-lap dispersion |
| `retention_ratio`, `retention_pct` | ratio and its percentage equivalent |
| `degradation_pct` | 100(1-R), with negative improvements retained |
| `previous_workload`, `previous_value`, `local_degradation_rate`, `slope_units` | exact preceding interval and secant slope |
| `value_ci_*`, `retention_ci_*`, `degradation_ci_*`, `rate_ci_*` | bounds; statuses, unit counts and draw counts for estimated intervals |
| `confidence_level`, `uncertainty_method`, `uncertainty_unit`, `bootstrap_samples`, `bootstrap_seed` | reproducibility and interpretation |
| `measurement_valid`, `normalization_valid`, `slope_valid`, `validity`, `slope_validity`, integrity fields, `flags`, `excluded_reasons` | numerical availability separate from workload evidence |
| `source_lap_ids`, `included_lap_ids`, `baseline_lap_ids` | JSON arrays referencing the lap audit |
| `scope_id` | SHA-256 identity of the analytical scope/inputs/options |

Retention CI bounds are **ratios**, degradation bounds are **percentage points**, and
rate bounds use `slope_units`. `stability_laps.csv` retains native lap values, identity,
counts, statuses, requested/observed durations, rejected-row counts, SHA-256 hashes
and JSON per-metric exclusions. `stability_metadata.json` retains schedules,
reference choices, run/manifest context hashes, options and limitations.

`stability_summary.csv` contains one row per configuration/mode/metric. It exports
`workload_average`, `retention_score_pct`, `mean_degradation_pct`,
`endpoint_retention_pct`, `mean_degradation_rate`, native and rate units,
`workload_start/end/span`, `workload_coordinates`, `workload_coverage_pct`,
reference/producer identities, `comparison_domain_id`, sample counts, flags and
availability. Bounds/status/unit-count/draw-count columns accompany the native
aggregate, retention score and mean rate. Retention-score bounds are percentages,
whereas per-load `retention_ci_*` bounds in `stability_metrics.csv` remain ratios.
`aggregate_metrics` in metadata carries the same summary records. The HTML embeds
both CSV downloads and shows FPS summary cards before the per-load curves.

## 7. Portable analytical interface

`cb_formulas.py` has no ChickenBench, PresentMon, HTML or CSV dependency:

```python
from cb_formulas import Observation, LOWER, analyze_series

rows = analyze_series(
    observations=[
        Observation(load=10, value=80, run_id='r1', sweep_id='p1'),
        Observation(load=20, value=120, run_id='r1', sweep_id='p1'),
    ],
    baseline_load=10,
    direction=LOWER,
    declared_loads=[10, 20],
)
```

This example yields 2/3 retention at load 20, with no inferred CI from one sweep.
A future MemLat Pro adapter can supply its own latency statistic, native workload
coordinate/unit, experiment identifiers, validity rules and baseline. It must never
treat chicken counts, timescale multipliers and bandwidth contention as interchangeable
workload units. Compatible analytical operations do not establish physically equivalent
workloads or justify combining latency, FPS and temporal dispersion into one score.

## 8. Interpretation boundaries

Formula 1.1.0 implements per-metric native aggregates and retention-area scores
using the explicitly stated domain, reference, interpolation and weighting above.
It does not combine different native data types or sweep modes into one index.
Normalized rates depend on native workload units and are not automatically comparable
between benchmarks. Chronological predictability beyond distributional dispersion
would require explicit temporal methods and validation.
