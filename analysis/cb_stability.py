"""ChickenBench adapter, diagnostics and CSV exports for cb_formulas v1.

No capture commands are run here. Native lap statistics arrive from cb_analyze.
"""
import collections
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re

from cb_formulas import (FORMULA_VERSION, HIGHER, LOWER, Observation,
                         analyze_series, summarize_series, finite)

BENCHMARK_VERSION = '1.0.7'
METRICS = {
    'avg_fps': ('Average FPS', 'fps', HIGHER, 'performance', 2),
    'p1_fps': ('1% low FPS (reciprocal p99 frame time)', 'fps', HIGHER, 'tail_performance', 300),
    'p01_fps': ('0.1% low FPS (reciprocal p99.9 frame time)', 'fps', HIGHER, 'tail_performance', 3000),
    'ft_p50_ms': ('Median frame time', 'ms', LOWER, 'frame_time', 2),
    'ft_p90_ms': ('90th percentile frame time', 'ms', LOWER, 'frame_time', 2),
    'ft_p99_ms': ('99th percentile frame time', 'ms', LOWER, 'tail_frame_time', 300),
    'ft_p999_ms': ('99.9th percentile frame time', 'ms', LOWER, 'tail_frame_time', 3000),
    'ft_max_ms': ('Maximum frame time', 'ms', LOWER, 'tail_frame_time', 2),
    'ft_sd_ms': ('Within-lap frame-time SD', 'ms', LOWER, 'temporal_dispersion', 2),
    'cov_pct': ('Within-lap frame-time coefficient of variation', 'percent', LOWER, 'temporal_dispersion', 2),
}
MODES = {'chickens': ('intended_chickens', 'percentage_points/intended_chicken'),
         'timescale': ('host_timescale_multiplier', 'percentage_points/host_timescale_multiplier')}

FIELDS = [
    'benchmark_id', 'benchmark_version', 'benchmark_version_source', 'analyzer_version', 'formula_version',
    'configuration_id', 'configuration_identity', 'mode', 'metric_name', 'metric_label',
    'metric_units', 'metric_direction', 'metric_role', 'workload_level', 'workload_units',
    'workload_coordinate_source', 'baseline_workload', 'baseline_selection', 'baseline_value',
    'baseline_sample_count_laps', 'measured_value', 'aggregation', 'sample_count_laps',
    'attempted_laps', 'excluded_laps', 'sample_count_frames', 'min_frames_per_lap',
    'between_lap_sd', 'between_lap_cv_pct', 'value_ci_low', 'value_ci_high',
    'retention_ratio', 'retention_pct', 'retention_units', 'retention_ci_low', 'retention_ci_high',
    'degradation_pct', 'degradation_units', 'degradation_ci_low', 'degradation_ci_high',
    'previous_workload', 'previous_value', 'local_degradation_rate', 'slope_units',
    'rate_ci_low', 'rate_ci_high', 'confidence_level', 'uncertainty_method', 'uncertainty_unit',
    'value_ci_status', 'value_ci_units', 'value_ci_draws',
    'retention_ci_status', 'retention_ci_units', 'retention_ci_draws',
    'rate_ci_status', 'rate_ci_units', 'rate_ci_draws', 'bootstrap_samples', 'bootstrap_seed',
    'measurement_valid', 'normalization_valid', 'slope_valid', 'validity', 'slope_validity',
    'workload_integrity', 'baseline_workload_integrity', 'slope_workload_integrity',
    'flags', 'excluded_reasons', 'source_lap_ids', 'included_lap_ids', 'baseline_lap_ids',
    'scope_id',
]

SUMMARY_FIELDS = [
    'benchmark_id', 'benchmark_version', 'benchmark_version_source',
    'analyzer_version', 'formula_version', 'configuration_id', 'mode',
    'metric_name', 'metric_label', 'metric_units', 'metric_direction', 'metric_role',
    'baseline_workload', 'baseline_selection', 'baseline_value', 'baseline_sample_count_laps',
    'workload_start', 'workload_end', 'workload_span', 'workload_units',
    'workload_levels', 'eligible_workload_levels', 'workload_coordinates', 'workload_coverage_pct',
    'workload_average', 'workload_average_ci_low', 'workload_average_ci_high',
    'retention_score_pct', 'retention_score_pct_ci_low', 'retention_score_pct_ci_high',
    'mean_degradation_pct', 'mean_degradation_pct_ci_low', 'mean_degradation_pct_ci_high',
    'endpoint_retention_pct', 'mean_degradation_rate', 'slope_units',
    'mean_degradation_rate_ci_low', 'mean_degradation_rate_ci_high',
    'aggregation', 'workload_weighting', 'comparison_domain_id', 'sample_count_laps',
    'confidence_level', 'uncertainty_method', 'uncertainty_unit',
    'workload_average_ci_status', 'workload_average_ci_units', 'workload_average_ci_draws',
    'retention_score_pct_ci_status', 'retention_score_pct_ci_units', 'retention_score_pct_ci_draws',
    'mean_degradation_rate_ci_status', 'mean_degradation_rate_ci_units', 'mean_degradation_rate_ci_draws',
    'bootstrap_samples', 'bootstrap_seed', 'summary_status', 'validity', 'flags', 'scope_id',
]

LAP_FIELDS = [
    'lap_id', 'run', 'configuration_id', 'mode', 'workload_level', 'pass', 'frames_csv',
    'source_status', 'analyzed_status', 'source_note', 'analyzer_note',
    'timescale', 'chickens_expected', 'chickens_after_restart', 'chickens_after_spawn',
    'chickens_found', 'round_start_detected', 'capture_seconds_requested', 'seconds',
    'capture_coverage_ratio', 'count_tolerance_pct', 'count_tolerance_source',
    'workload_integrity', 'capture_completeness', 'duplicate_sweep_coordinate',
    'frame_time_column', 'frame_rows_total', 'frame_rows_rejected', 'frame_rows_other_chain',
    'selected_chain_rejected_rows', 'frames_csv_sha256', 'metric_eligibility',
] + ['frames'] + list(METRICS)


def write_csv(path, rows, fields):
    """Missing/nonfinite values are empty cells, never NaN/Infinity or invented zeros."""
    with open(path, 'w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for source in rows:
            row = {}
            for key in fields:
                value = source.get(key)
                if isinstance(value, (float, int)) and not finite(value):
                    value = None
                row[key] = value
            writer.writerow(row)


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _number(value):
    return float(value) if finite(value) else None


def _hash(path):
    if not Path(path).is_file():
        return ''
    hasher = hashlib.sha256()
    with open(path, 'rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(part)
    return hasher.hexdigest()


def _run_metadata(root, run):
    path = Path(root) / run / 'run_info.txt'
    result = {'path': str(Path(run) / 'run_info.txt'), 'sha256': _hash(path)}
    if path.is_file():
        text = path.read_text(encoding='utf-8-sig', errors='replace')
        m = re.search(r'ChickenTolerancePct=([\d.]+)', text)
        if m and finite(m[1]) and 0 <= float(m[1]) <= 100:
            result['count_tolerance_pct'] = float(m[1])
        m = re.search(r'Mode:\s*(\w+).*?Levels:\s*([0-9., ]+)', text)
        if m:
            levels = [_number(x.strip()) for x in m[2].strip().split(',')]
            if all(x is not None for x in levels):
                result.update(mode=m[1], scheduled_levels=levels)
        lines = [x for x in text.splitlines() if x.startswith(('CPU:', 'GPU:', 'RAM:', 'Windows:', 'Settings:'))]
        result['context_fingerprint'] = hashlib.sha256('\n'.join(lines).encode()).hexdigest() if lines else ''
        match = re.search(r'ChickenBench v([\d.]+)', text)
        result['declared_benchmark_version'] = match[1] if match else 'unknown'
    return result


def _assess(lap, tolerance, tolerance_source, duplicate):
    """Endpoint count checks support intended load; they never prove continuous integrity."""
    mode, level = lap['mode'], float(lap['level'])
    found = _number(lap.get('chickens_found'))
    spawn = _number(lap.get('chickens_after_spawn'))
    expected = _number(lap.get('chickens_expected'))
    scale = _number(lap.get('timescale'))
    requested = _number(lap.get('capture_seconds'))
    seconds = _number(lap.get('seconds'))
    integrity = 'unverified'
    reasons = []
    if mode not in MODES or level < 0 or (mode == 'timescale' and level <= 0):
        reasons.append('invalid_workload_coordinate')
    if mode == 'chickens':
        # The chicken sweep is defined at normal timescale.
        if scale is not None and scale != 1:
            reasons.append('incomparable_timescale')
        if expected is not None and expected != level:
            reasons.append('expected_count_coordinate_mismatch')
        lower = math.floor(level * (1 - tolerance / 100.0))
        upper = math.ceil(level * (1 + tolerance / 100.0))
        if any(x is not None and (x < lower or x > upper) for x in (spawn, found)):
            integrity = 'contradicted'
            reasons.append('observed_count_outside_tolerance')
        elif spawn is not None and found is not None and expected == level and scale == 1:
            integrity = 'endpoint_counts_consistent'
    elif mode == 'timescale':
        if scale is not None and scale != level:
            integrity = 'contradicted'
            reasons.append('timescale_metadata_mismatch')
        elif scale == level:
            integrity = 'timescale_setting_recorded_only'
    status = lap.get('status', '')
    if status not in ('ok', 'imported_unverified'):
        reasons.append('status_' + (status or 'missing'))
    if duplicate:
        reasons.append('duplicate_sweep_coordinate')
    completeness = 'unverified'
    if requested is not None and requested > 0 and seconds is not None:
        completeness = 'duration_consistent' if seconds >= 0.8 * requested else 'short_capture'
        if completeness == 'short_capture':
            reasons.append('short_capture')
    else:
        if requested is not None and requested < 0:
            reasons.append('invalid_capture_duration')
    diagnostics = lap.get('_frame_diagnostics', {})
    audit = {
        'lap_id': lap['_lap_id'], 'run': lap.get('run', ''),
        'configuration_id': lap.get('label', ''), 'mode': mode,
        'workload_level': level, 'pass': lap.get('pass', ''),
        'frames_csv': lap.get('frames_csv', ''),
        'source_status': lap.get('_source_status', status), 'analyzed_status': status,
        'source_note': lap.get('_source_note', ''), 'analyzer_note': lap.get('note', ''),
        'capture_seconds_requested': requested, 'capture_coverage_ratio': seconds / requested
        if seconds is not None and requested is not None and requested > 0 else None,
        'count_tolerance_pct': tolerance, 'count_tolerance_source': tolerance_source,
        'workload_integrity': integrity, 'capture_completeness': completeness,
        'duplicate_sweep_coordinate': duplicate, 'frame_time_column': lap.get('_frame_column', ''),
        'frame_rows_total': diagnostics.get('total_rows'),
        'frame_rows_rejected': diagnostics.get('rejected_rows'),
        'frame_rows_other_chain': diagnostics.get('other_chain_rows'),
        'selected_chain_rejected_rows': diagnostics.get('selected_chain_rejected_rows'),
        'frames_csv_sha256': lap.get('_frames_sha256', ''),
    }
    for field in ['timescale', 'chickens_expected', 'chickens_after_restart', 'chickens_after_spawn',
                  'chickens_found', 'round_start_detected', 'seconds', 'frames'] + list(METRICS):
        audit[field] = lap.get(field)
    eligibility = {}
    for metric, (_, _, _, role, min_frames) in METRICS.items():
        excluded = list(reasons)
        value = _number(lap.get(metric))
        frames = _number(lap.get('frames')) or 0
        if value is None or (value < 0 if role == 'temporal_dispersion' else value <= 0):
            excluded.append('missing_or_invalid_metric')
        if frames < min_frames:
            excluded.append('insufficient_frames_for_metric')
        eligibility[metric] = excluded
    audit['metric_eligibility'] = json.dumps(eligibility, sort_keys=True, separators=(',', ':'))
    return audit, eligibility


def build_metrics(laps, root, analyzer_version, references=None, bootstrap_samples=2000,
                  seed=1729, fallback_count_tolerance=10.0):
    """Return aggregate rows, per-lap audit rows, and reproducibility metadata."""
    references = references or {}
    if not finite(fallback_count_tolerance) or not 0 <= fallback_count_tolerance <= 100:
        raise ValueError('count tolerance must be between 0 and 100 percent')
    copied = [dict(lap) for lap in laps]
    runs = {run: _run_metadata(root, run) for run in sorted({x['run'] for x in copied})}
    duplicates = collections.Counter((x['run'], str(x.get('pass', '')), x['mode'], x['label'], x['level'])
                                     for x in copied)
    # Row number makes even duplicate manifest rows independently traceable.
    for i, lap in enumerate(copied):
        lap['_lap_id'] = '%s:row%d:pass%s:%s:%s' % (lap['run'], i + 1, lap.get('pass', ''), lap['mode'], lap['level'])
    audits, eligibility = [], {}
    for lap in copied:
        meta = runs[lap['run']]
        tolerance = meta.get('count_tolerance_pct', fallback_count_tolerance)
        source = 'run_info.txt' if 'count_tolerance_pct' in meta else 'analyzer_fallback_explicit'
        key = lap['run'], str(lap.get('pass', '')), lap['mode'], lap['label'], lap['level']
        audit, elig = _assess(lap, tolerance, source, duplicates[key] > 1)
        audits.append(audit)
        eligibility[lap['_lap_id']] = elig
    audit_by_id = {x['lap_id']: x for x in audits}
    layouts = {}
    for mode in sorted({x['mode'] for x in copied}):
        levels = {float(x['level']) for x in copied if x['mode'] == mode}
        for meta in runs.values():
            if meta.get('mode') == mode:
                levels.update(meta.get('scheduled_levels', []))
        layouts[mode] = sorted(levels)
    chosen = {}
    for mode, label in sorted({(x['mode'], x['label']) for x in copied}):
        first = next(x for x in copied if x['mode'] == mode and x['label'] == label)
        # Preserve the starting workload even if its capture failed: no quiet rebaselining.
        chosen.setdefault(mode, {})[label] = (references[mode] if references.get(mode) is not None
                                             else float(first['level']))
    scope = {'formula_version': FORMULA_VERSION, 'analyzer_version': analyzer_version,
             'references': chosen, 'bootstrap_samples': bootstrap_samples, 'seed': seed,
             'fallback_count_tolerance_pct': fallback_count_tolerance,
             'lap_inputs': [{k: x.get(k) for k in LAP_FIELDS} for x in audits]}
    scope_id = hashlib.sha256(json.dumps(_json_safe(scope), sort_keys=True, allow_nan=False,
                                       default=str).encode()).hexdigest()
    rows, summaries = [], []
    for mode, label in sorted({(x['mode'], x['label']) for x in copied}):
        if mode not in MODES:
            continue
        group = [x for x in copied if x['mode'] == mode and x['label'] == label]
        baseline = chosen[mode][label]
        levels = layouts[mode]
        versions = {runs[x['run']].get('declared_benchmark_version') for x in group}
        versions.discard(None)
        if len(versions) == 1:
            capture_version = next(iter(versions))
            version_source = 'run_info.txt'
        elif not versions and all(x.get('_source_status', x.get('status')) == 'imported_unverified' for x in group):
            capture_version, version_source = 'unknown', 'unverified_import'
        else:
            capture_version = BENCHMARK_VERSION if not versions else 'mixed:' + ';'.join(sorted(versions))
            version_source = 'package_assumption' if not versions else 'mixed_run_metadata'
        fingerprints = {runs[x['run']].get('context_fingerprint') for x in group}
        fingerprints.discard(None)
        fingerprints.discard('')
        for metric, (title, units, direction, role, _) in METRICS.items():
            observations, included = [], {}
            for lap in group:
                key = lap['run'], str(lap.get('pass', '')), lap['mode'], lap['label'], lap['level']
                if duplicates[key] > 1:
                    continue  # Explicitly rejected in audit; never collapse duplicate coordinates.
                reasons = eligibility[lap['_lap_id']][metric]
                if not reasons:
                    included.setdefault(float(lap['level']), []).append(lap)
                observations.append(Observation(float(lap['level']), None if reasons else float(lap[metric]),
                                                lap['run'], str(lap.get('pass') or ('unknown:' + lap['_lap_id']))))
            derived = analyze_series(observations, baseline, direction, levels,
                                     normalize=role != 'temporal_dispersion',
                                     allow_zero=role == 'temporal_dispersion',
                                     bootstrap_samples=bootstrap_samples, seed=seed)
            for calc in derived:
                level = calc['load']
                attempts = [lap for lap in group if float(lap['level']) == level]
                valid = included.get(level, [])
                baseline_laps = included.get(baseline, [])
                prev_laps = included.get(calc['previous_load'], [])
                flags = []
                missing_base = calc['baseline_value'] is None
                if missing_base and role != 'temporal_dispersion':
                    flags.append('missing_or_invalid_baseline')
                if role != 'temporal_dispersion' and calc['retention_ratio'] is None and not missing_base:
                    flags.append('normalization_undefined')
                if not valid:
                    flags.append('no_eligible_laps')
                if calc['previous_load'] is not None and not prev_laps:
                    flags.append('invalid_previous_endpoint_no_slope_bridge')
                if len(valid) < len(attempts):
                    flags.append('excluded_laps')
                if any(x.get('_frame_diagnostics', {}).get('rejected_rows', 0) for x in valid):
                    flags.append('rejected_frame_rows')

                def integrity_of(ls):
                    states = {audit_by_id[x['_lap_id']]['workload_integrity'] for x in ls}
                    if not ls:
                        return 'no_eligible_laps'
                    if states == {'endpoint_counts_consistent'}:
                        return 'endpoint_counts_consistent'
                    if states == {'timescale_setting_recorded_only'}:
                        return 'timescale_setting_recorded_only'
                    return 'unverified_or_partial_metadata'

                integrity = integrity_of(valid)
                baseline_integrity = integrity_of(baseline_laps)
                slope_integrity = integrity_of(valid + prev_laps + baseline_laps)
                dependency_laps = valid + (baseline_laps if role != 'temporal_dispersion' else [])
                unverified = any(audit_by_id[x['_lap_id']]['workload_integrity'] == 'unverified'
                                 or audit_by_id[x['_lap_id']]['capture_completeness'] == 'unverified'
                                 for x in dependency_laps)
                if unverified:
                    flags.append('unverified_workload_or_capture_metadata')
                slope_unverified = any(audit_by_id[x['_lap_id']]['workload_integrity'] == 'unverified'
                                       or audit_by_id[x['_lap_id']]['capture_completeness'] == 'unverified'
                                       for x in valid + prev_laps + baseline_laps)
                if slope_unverified and calc['local_degradation_rate'] is not None:
                    flags.append('slope_uses_unverified_metadata')
                if any(not x.get('pass') for x in valid):
                    flags.append('missing_sweep_identifier')
                if len(fingerprints) > 1:
                    flags.append('configuration_context_differs_across_runs')
                if calc['value_ci_status'] in ('insufficient_units', 'exploratory_small_n', 'unmatched_unit_support'):
                    flags.append(calc['value_ci_status'])
                if calc['retention_ci_status'] == 'unmatched_unit_support' or calc['rate_ci_status'] == 'unmatched_unit_support':
                    flags.append('unmatched_dependency_support')
                reasons = collections.Counter(reason for lap in attempts
                                              for reason in eligibility[lap['_lap_id']][metric])
                row = dict(calc)
                row.update({
                    'benchmark_id': 'ChickenBench', 'benchmark_version': capture_version,
                    'benchmark_version_source': version_source,
                    'analyzer_version': analyzer_version, 'formula_version': FORMULA_VERSION,
                    'configuration_id': label, 'configuration_identity': 'user_supplied_label_unverified',
                    'mode': mode, 'metric_name': metric, 'metric_label': title, 'metric_units': units,
                    'metric_direction': direction, 'metric_role': role, 'workload_level': level,
                    'workload_units': MODES[mode][0], 'workload_coordinate_source': 'intended_manifest_or_schedule',
                    'baseline_workload': baseline,
                    'baseline_selection': 'explicit_cli' if references.get(mode) is not None else 'first_manifest_workload_for_configuration',
                    'baseline_sample_count_laps': len(baseline_laps),
                    'aggregation': 'equal_lap_arithmetic_mean_before_normalization',
                    'attempted_laps': len(attempts), 'excluded_laps': len(attempts) - len(valid),
                    'sample_count_frames': sum(x.get('frames', 0) for x in valid),
                    'min_frames_per_lap': min((x.get('frames', 0) for x in valid), default=None),
                    'retention_units': 'ratio;retention_pct=100*ratio',
                    'degradation_units': 'percentage_points_of_retention',
                    'previous_workload': calc['previous_load'], 'slope_units': MODES[mode][1],
                    'confidence_level': 0.95,
                    'uncertainty_method': 'percentile_cluster_bootstrap;identity_at_reference',
                    'bootstrap_samples': bootstrap_samples, 'bootstrap_seed': seed,
                    'measurement_valid': bool(valid), 'normalization_valid': calc['retention_ratio'] is not None,
                    'slope_valid': calc['local_degradation_rate'] is not None,
                    'validity': 'no_eligible_measurement' if not valid else
                    ('provisional_unverified_metadata' if unverified else 'eligible_with_documented_assumptions'),
                    'slope_validity': 'unavailable' if calc['local_degradation_rate'] is None else
                    ('provisional_unverified_metadata' if slope_unverified else 'eligible_with_documented_assumptions'),
                    'workload_integrity': integrity, 'baseline_workload_integrity': baseline_integrity,
                    'slope_workload_integrity': slope_integrity,
                    'flags': ';'.join(flags), 'excluded_reasons': json.dumps(reasons, sort_keys=True),
                    'source_lap_ids': json.dumps([x['_lap_id'] for x in attempts]),
                    'included_lap_ids': json.dumps([x['_lap_id'] for x in valid]),
                    'baseline_lap_ids': json.dumps([x['_lap_id'] for x in baseline_laps]), 'scope_id': scope_id,
                })
                rows.append(row)
            summary = summarize_series(observations, baseline, direction, levels,
                                       normalize=role != 'temporal_dispersion',
                                       allow_zero=role == 'temporal_dispersion',
                                       bootstrap_samples=bootstrap_samples, seed=seed,
                                       point_rows=derived)
            context_fields = ['benchmark_id', 'benchmark_version', 'benchmark_version_source',
                              'analyzer_version', 'formula_version', 'configuration_id', 'mode',
                              'metric_name', 'metric_label', 'metric_units', 'metric_direction',
                              'metric_role', 'baseline_workload', 'baseline_selection', 'baseline_value',
                              'baseline_sample_count_laps', 'workload_units', 'slope_units',
                              'aggregation', 'confidence_level', 'bootstrap_samples', 'bootstrap_seed', 'scope_id']
            summary.update({k: row[k] for k in context_fields})
            metric_rows = rows[-len(derived):]
            flags = sorted({flag for r in metric_rows for flag in r['flags'].split(';') if flag})
            summary.update(workload_coordinates=json.dumps(levels),
                           workload_weighting='uniform_native_workload_trapezoidal',
                           sample_count_laps=sum(r['sample_count_laps'] for r in metric_rows),
                           uncertainty_method='percentile_cluster_bootstrap_joint_curve',
                           comparison_domain_id=hashlib.sha256(json.dumps(
                               [mode, levels, baseline, 'uniform_native_workload_trapezoidal']).encode()).hexdigest(),
                           validity=('unavailable_incomplete_curve' if summary['workload_average'] is None else
                                     ('provisional_unverified_metadata' if any('unverified' in r['validity'] for r in metric_rows)
                                      else 'eligible_with_documented_assumptions')),
                           flags=';'.join(flags))
            summaries.append(summary)
    metadata = {
        'benchmark_id': 'ChickenBench', 'benchmark_version_assumed_from_package': BENCHMARK_VERSION,
        'analyzer_version': analyzer_version, 'formula_version': FORMULA_VERSION,
        'scope_id': scope_id, 'references': chosen, 'scheduled_layouts': layouts,
        'bootstrap_samples': bootstrap_samples, 'bootstrap_seed': seed,
        'run_metadata': runs,
        'aggregate_metrics': summaries,
        'aggregate_method': 'trapezoidal_area_divided_by_full_native_workload_span',
        'manifest_sha256': {run: _hash(Path(root) / run / 'laps.csv') for run in runs},
        'metric_schema': {key: dict(zip(('label','units','direction','role','minimum_frames'), value))
                          for key, value in METRICS.items()},
        'notes': [
            'Each metric has a separate workload-average retention score; different metrics and modes are never combined.',
            'Aggregate scores use uniform native workload weighting and require the complete scheduled curve; compare matching domains and references.',
            'Native tail-FPS aggregates average the per-level reciprocal-percentile FPS values; they are not pooled-frame percentiles.',
            'Configuration labels are user supplied; identical labels are assumed comparable.',
            'Counts are endpoint checks, not proof of continuous workload integrity.',
            'Timescale metadata records a requested setting, not measured simulation work.',
            'A single run supports conditional sweep uncertainty only; between-run drift is not estimated.',
            'Bootstrap intervals with fewer than 10 independent units are exploratory; fewer than 3 are withheld.',
            'Missingness is not imputed; CIs require identical cluster support across dependent loads.',
            'Frame dispersion describes the distribution, not chronological predictability.',
        ],
    }
    return rows, audits, metadata


def write_outputs(directory, rows, laps, metadata):
    directory = Path(directory)
    write_csv(directory / 'stability_metrics.csv', rows, FIELDS)
    write_csv(directory / 'stability_laps.csv', laps, LAP_FIELDS)
    write_csv(directory / 'stability_summary.csv', metadata['aggregate_metrics'], SUMMARY_FIELDS)
    with (directory / 'stability_metadata.json').open('w', encoding='utf-8') as stream:
        json.dump(metadata, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
