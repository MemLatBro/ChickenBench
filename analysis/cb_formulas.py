"""Portable formula layer. Standard library only; no benchmark or presentation imports.

The estimand is a ratio of equal-lap arithmetic means, not a mean of lap ratios.
Sweep/run identifiers express experimental dependence; frames are never repetitions.
"""
from dataclasses import dataclass
import hashlib
import math
import random
import statistics

FORMULA_VERSION = '1.1.0'
HIGHER = 'higher_is_better'
LOWER = 'lower_is_better'
MIN_CI_UNITS = 3


def finite(value):
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError, OverflowError):
        return False


def retention(value, baseline, direction=HIGHER):
    """Dimensionless throughput-equivalent retention. Positive finite inputs only."""
    if direction not in (HIGHER, LOWER):
        raise ValueError('unknown metric direction: %s' % direction)
    if not finite(value) or not finite(baseline) or float(value) <= 0 or float(baseline) <= 0:
        return None
    value, baseline = float(value), float(baseline)
    result = value / baseline if direction == HIGHER else baseline / value
    return result if finite(result) else None


def degradation(retention_ratio):
    """Percentage points of lost retention; improvements remain negative."""
    if not finite(retention_ratio):
        return None
    result = 100.0 * (1.0 - float(retention_ratio))
    return result if finite(result) else None


def local_rate(previous_degradation, current_degradation, previous_load, load):
    """Secant slope, in retention percentage points per native load unit."""
    if not all(finite(v) for v in
               (previous_degradation, current_degradation, previous_load, load)):
        return None
    previous_degradation, current_degradation, previous_load, load = map(
        float, (previous_degradation, current_degradation, previous_load, load))
    if load <= previous_load:
        return None
    result = (current_degradation - previous_degradation) / (load - previous_load)
    return result if finite(result) else None


def percentile(values, probability):
    """Linear order-statistic interpolation (probability in [0, 1])."""
    if not values:
        return None
    if not 0 <= probability <= 1:
        raise ValueError('probability must be in [0, 1]')
    ordered = sorted(values)
    k = (len(ordered) - 1) * probability
    lo, hi = math.floor(k), math.ceil(k)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


@dataclass(frozen=True)
class Observation:
    load: float
    value: float
    run_id: str
    sweep_id: str


def _seed(seed, tag):
    # Stable across interpreter invocations (Python's built-in hash is salted).
    digest = hashlib.sha256(('%s|%s' % (seed, tag)).encode('utf-8')).digest()
    return int.from_bytes(digest[:8], 'big')


def _bounds(values):
    return percentile(values, 0.025), percentile(values, 0.975)


def analyze_series(observations, baseline_load, direction, declared_loads=None,
                   normalize=True, allow_zero=False, bootstrap_samples=2000, seed=1729):
    """Return one dict per declared load, including absent/invalid endpoints.

    Units: whole runs when >1 run exists, otherwise sweeps conditional on that run.
    CIs for ratios/slopes require identical unit support at every dependency load.
    Missing support is reported, never silently imputed or paired by row order.
    Duplicate (run, sweep, load) observations are rejected rather than averaged.
    Callers must not collapse distinct metrics/configurations into one call.
    """
    if direction not in (HIGHER, LOWER):
        raise ValueError('unknown direction')
    if not finite(baseline_load):
        raise ValueError('reference load must be finite')
    if bootstrap_samples != 0 and bootstrap_samples < 200:
        raise ValueError('bootstrap_samples must be zero or at least 200')
    obs = list(observations)
    if any(not finite(o.load) for o in obs):
        raise ValueError('nonfinite workload coordinate')
    loads = sorted(set(declared_loads if declared_loads is not None else [o.load for o in obs]))
    if any(not finite(x) for x in loads):
        raise ValueError('nonfinite declared workload coordinate')
    keys = [(o.run_id, o.sweep_id, o.load) for o in obs]
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate workload coordinate within a sweep')
    accepted = [o for o in obs if finite(o.value) and
                (float(o.value) >= 0 if allow_zero else float(o.value) > 0)]
    multi_run = len({o.run_id for o in obs}) > 1
    unit_name = 'run' if multi_run else 'sweep_within_single_run'
    by_load = {load: {} for load in loads}
    for o in accepted:
        if o.load in by_load:
            unit = o.run_id if multi_run else (o.run_id, o.sweep_id)
            by_load[o.load].setdefault(unit, []).append(float(o.value))
    values = {load: [v for vs in units.values() for v in vs]
              for load, units in by_load.items()}
    means = {load: statistics.mean(vs) if vs else None for load, vs in values.items()}
    base = means.get(baseline_load)
    ci_cache = {}

    def ci(dependencies, kind):
        deps = tuple(dict.fromkeys(dependencies))
        key = deps, kind
        if key in ci_cache:
            return ci_cache[key]
        supports = [set(by_load.get(load, {})) for load in deps]
        n = min((len(s) for s in supports), default=0)
        result = {'low': None, 'high': None, 'units': n, 'draws': 0,
                  'status': 'bootstrap_disabled' if not bootstrap_samples else 'insufficient_units'}
        if not supports or any(s != supports[0] for s in supports[1:]):
            result['status'] = 'unmatched_unit_support'
        elif bootstrap_samples and n >= MIN_CI_UNITS:
            units = sorted(supports[0], key=str)
            rng = random.Random(_seed(seed, repr(key)))
            draws = []
            for _ in range(bootstrap_samples):
                selected = [units[rng.randrange(n)] for _ in range(n)]
                bm = {load: statistics.mean(v for unit in selected for v in by_load[load][unit])
                      for load in deps}
                if kind == 'value':
                    value = bm[deps[0]]
                elif kind == 'retention':
                    value = retention(bm[deps[0]], bm[baseline_load], direction)
                else:
                    prev, current = deps[:2]
                    d0 = degradation(retention(bm[prev], bm[baseline_load], direction))
                    d1 = degradation(retention(bm[current], bm[baseline_load], direction))
                    value = local_rate(d0, d1, prev, current)
                if value is None or not finite(value):
                    result['status'] = 'invalid_bootstrap_draw'
                    break
                draws.append(value)
            result['draws'] = len(draws)
            if len(draws) == bootstrap_samples:
                result['low'], result['high'] = _bounds(draws)
                result['status'] = 'exploratory_small_n' if n < 10 else 'approximate'
        ci_cache[key] = result
        return result

    rows = []
    for i, load in enumerate(loads):
        vs, value = values[load], means[load]
        sd = statistics.stdev(vs) if len(vs) > 1 else None
        ratio = retention(value, base, direction) if normalize else None
        d = degradation(ratio)
        prev = loads[i - 1] if i else None
        pd = degradation(retention(means.get(prev), base, direction)) if normalize else None
        g = local_rate(pd, d, prev, load)
        row = {'load': load, 'measured_value': value, 'baseline_value': base,
               'sample_count_laps': len(vs), 'between_lap_sd': sd,
               'between_lap_cv_pct': 100.0 * sd / value if sd is not None and value else None,
               'retention_ratio': ratio, 'retention_pct': 100.0 * ratio if ratio is not None else None,
               'degradation_pct': d, 'previous_load': prev,
               'previous_value': means.get(prev), 'local_degradation_rate': g,
               'uncertainty_unit': unit_name, 'value_ci_low': None, 'value_ci_high': None,
               'retention_ci_low': None, 'retention_ci_high': None,
               'degradation_ci_low': None, 'degradation_ci_high': None,
               'rate_ci_low': None, 'rate_ci_high': None,
               'value_ci_status': 'no_measurement', 'retention_ci_status': 'not_applicable',
               'rate_ci_status': 'not_applicable', 'value_ci_units': 0,
               'retention_ci_units': 0, 'rate_ci_units': 0,
               'value_ci_draws': 0, 'retention_ci_draws': 0, 'rate_ci_draws': 0}
        if value is not None:
            result = ci((load,), 'value')
            for field, src in [('value_ci_low','low'), ('value_ci_high','high'),
                               ('value_ci_status','status'), ('value_ci_units','units'),
                               ('value_ci_draws','draws')]:
                row[field] = result[src]
        if ratio is not None:
            if load == baseline_load:
                result = {'low': 1.0, 'high': 1.0, 'status': 'algebraic_identity',
                          'units': len(by_load[load]), 'draws': 0}
            else:
                result = ci((load, baseline_load), 'retention')
            for field, src in [('retention_ci_low','low'), ('retention_ci_high','high'),
                               ('retention_ci_status','status'), ('retention_ci_units','units'),
                               ('retention_ci_draws','draws')]:
                row[field] = result[src]
            if result['low'] is not None:
                row['degradation_ci_low'] = degradation(result['high'])
                row['degradation_ci_high'] = degradation(result['low'])
        if g is not None:
            result = ci((prev, load, baseline_load), 'rate')
            for field, src in [('rate_ci_low','low'), ('rate_ci_high','high'),
                               ('rate_ci_status','status'), ('rate_ci_units','units'),
                               ('rate_ci_draws','draws')]:
                row[field] = result[src]
        rows.append(row)
    return rows


def aggregate_curve(loads, values, baseline_value, direction=HIGHER, normalize=True):
    """One summary per metric over a piecewise-linear workload curve.

    Integration is uniform in the native load coordinate, using trapezoids. A
    missing scheduled level withholds the full-span area, never bridges a gap.
    The endpoint secant is separate and can exist despite a missing interior.
    """
    if direction not in (HIGHER, LOWER):
        raise ValueError('unknown direction')
    if len(loads) != len(values):
        raise ValueError('load/value lengths differ')
    if any(not finite(x) for x in loads):
        raise ValueError('nonfinite workload coordinate')
    pairs = sorted(zip(loads, values))
    xs, vs = [x for x, _ in pairs], [v for _, v in pairs]
    if len(set(xs)) != len(xs):
        raise ValueError('duplicate workload coordinate')
    span = xs[-1] - xs[0] if xs else 0
    intervals = list(zip(xs, xs[1:], vs, vs[1:]))
    covered = sum(b-a for a, b, v0, v1 in intervals if finite(v0) and finite(v1))
    result = dict(workload_start=xs[0] if xs else None, workload_end=xs[-1] if xs else None,
                  workload_span=span, workload_levels=len(xs),
                  eligible_workload_levels=sum(finite(v) for v in vs),
                  workload_coverage_pct=100*covered/span if span > 0 else None,
                  workload_average=None, retention_score_pct=None, mean_degradation_pct=None,
                  endpoint_retention_pct=None, mean_degradation_rate=None,
                  summary_status='insufficient_workload_span' if span <= 0 else 'complete')
    if span <= 0:
        return result

    def area_mean(ys):
        if any(not finite(y) for y in ys):
            return None
        # Half before adding avoids unnecessary overflow for large inputs.
        value = math.fsum((b-a)/span * (v0/2+v1/2)
                          for a, b, v0, v1 in zip(xs, xs[1:], ys, ys[1:]))
        return value if finite(value) else None

    result['workload_average'] = area_mean(vs)
    if result['workload_average'] is None:
        result['summary_status'] = 'missing_or_invalid_workload_levels'
    if normalize:
        ratios = [retention(v, baseline_value, direction) for v in vs]
        mean_ratio = area_mean(ratios)
        if mean_ratio is not None:
            result['retention_score_pct'] = 100*mean_ratio
            result['mean_degradation_pct'] = degradation(mean_ratio)
        elif result['summary_status'] == 'complete':
            result['summary_status'] = 'missing_or_invalid_baseline'
        if ratios[-1] is not None:
            result['endpoint_retention_pct'] = 100*ratios[-1]
        result['mean_degradation_rate'] = local_rate(degradation(ratios[0]),
                                                    degradation(ratios[-1]), xs[0], xs[-1])
    return result


def summarize_series(observations, baseline_load, direction, declared_loads=None,
                     normalize=True, allow_zero=False, bootstrap_samples=2000,
                     seed=1729, point_rows=None):
    """Summarize one metric/configuration; resample dependent levels jointly."""
    obs = list(observations)
    points = point_rows if point_rows is not None else analyze_series(
        obs, baseline_load, direction, declared_loads, normalize=normalize,
        allow_zero=allow_zero, bootstrap_samples=0, seed=seed)
    if bootstrap_samples != 0 and bootstrap_samples < 200:
        raise ValueError('bootstrap_samples must be zero or at least 200')
    loads = [r['load'] for r in points]
    base = next((r['measured_value'] for r in points if r['load'] == baseline_load), None)
    result = aggregate_curve(loads, [r['measured_value'] for r in points], base, direction, normalize)
    multi_run = len({o.run_id for o in obs}) > 1
    result['uncertainty_unit'] = 'run' if multi_run else 'sweep_within_single_run'
    units_by_load = {x: {} for x in loads}
    for o in obs:
        if o.load not in units_by_load or not finite(o.value):
            continue
        if (float(o.value) < 0 if allow_zero else float(o.value) <= 0):
            continue
        unit = o.run_id if multi_run else (o.run_id, o.sweep_id)
        units_by_load[o.load].setdefault(unit, []).append(float(o.value))
    cache = {}

    def interval(field, deps):
        deps = tuple(dict.fromkeys(deps))
        supports = [set(units_by_load.get(x, {})) for x in deps]
        n = min((len(s) for s in supports), default=0)
        info = dict(low=None, high=None, units=n, draws=0,
                    status='bootstrap_disabled' if not bootstrap_samples else 'insufficient_units')
        if not supports or any(s != supports[0] for s in supports[1:]):
            info['status'] = 'unmatched_unit_support'
        elif bootstrap_samples and n >= MIN_CI_UNITS:
            if deps not in cache:
                units = sorted(supports[0], key=str)
                rng = random.Random(_seed(seed, repr(('workload_summary', deps))))
                draws = []
                for _ in range(bootstrap_samples):
                    selected = [units[rng.randrange(n)] for _ in range(n)]
                    means = {x: statistics.mean(v for u in selected for v in units_by_load[x][u])
                             for x in deps}
                    draws.append(aggregate_curve(loads, [means.get(x) for x in loads],
                                                 means.get(baseline_load), direction, normalize))
                cache[deps] = draws
            values = [d[field] for d in cache[deps]]
            info['draws'] = sum(finite(v) for v in values)
            if info['draws'] != bootstrap_samples:
                info['status'] = 'invalid_bootstrap_draw'
            else:
                info['low'], info['high'] = _bounds(values)
                info['status'] = 'exploratory_small_n' if n < 10 else 'approximate'
        return info

    fields = ['workload_average', 'retention_score_pct', 'mean_degradation_rate']
    for field in fields:
        deps = (loads[:1] + loads[-1:] + [baseline_load] if field == 'mean_degradation_rate'
                else loads + ([baseline_load] if field == 'retention_score_pct' else []))
        ci = interval(field, deps) if result[field] is not None else dict(
            low=None, high=None, units=0, draws=0, status='unavailable')
        for suffix in ['low', 'high', 'status', 'units', 'draws']:
            result[field + '_ci_' + suffix] = ci[suffix]
    result['mean_degradation_pct_ci_low'] = (100-result['retention_score_pct_ci_high']
        if result['retention_score_pct_ci_high'] is not None else None)
    result['mean_degradation_pct_ci_high'] = (100-result['retention_score_pct_ci_low']
        if result['retention_score_pct_ci_low'] is not None else None)
    return result
