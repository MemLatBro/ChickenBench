import csv
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

from cb_stability import build_metrics, write_outputs
from cb_stability_report import chart, render_stability


def lap(level=0, repeat=1, label='Chip', **kwargs):
    data = dict(run='run', label=label, mode='chickens', level=level,
                timescale=1, chickens_expected=level, chickens_found=level,
                chickens_after_spawn=level, status='ok', capture_seconds=40,
                seconds=40, frames=4000, avg_fps=100-level*.1, p1_fps=80,
                p01_fps=60, ft_p50_ms=10, ft_p90_ms=12, ft_p99_ms=12.5,
                ft_p999_ms=1000/60, ft_max_ms=20, ft_sd_ms=2, cov_pct=20)
    data['pass'] = repeat
    data.update(kwargs)
    return data


def result(laps, **kwargs):
    with tempfile.TemporaryDirectory() as root:
        return build_metrics(laps,root,'test',bootstrap_samples=0,**kwargs)


class AdapterTests(unittest.TestCase):
    def test_first_workload_is_per_configuration(self):
        rows, _, _ = result([lap(50,label='A'),lap(0,label='A'),lap(150,label='A'),
                             lap(0,label='B'),lap(50,label='B')])
        a = [r for r in rows if r['configuration_id']=='A' and r['metric_name']=='avg_fps']
        self.assertTrue(all(r['baseline_workload']==50 for r in a))
        self.assertEqual(a[0]['baseline_selection'],'first_manifest_workload_for_configuration')
        self.assertAlmostEqual(a[0]['retention_ratio'],100/95)

    def test_repeated_starting_laps_averaged(self):
        rows, _, _ = result([lap(0,1,avg_fps=100),lap(50,1),lap(0,2,avg_fps=120),lap(50,2)])
        row = next(r for r in rows if r['metric_name']=='avg_fps' and r['workload_level']==50)
        self.assertEqual(row['baseline_value'],110)
        self.assertEqual(row['baseline_sample_count_laps'],2)

    def test_failed_first_lap_not_replaced_by_later_load(self):
        rows, _, _ = result([lap(0,status='no_frames'),lap(50)])
        row = next(r for r in rows if r['metric_name']=='avg_fps' and r['workload_level']==50)
        self.assertIsNone(row['retention_ratio'])
        self.assertIn('missing_or_invalid_baseline',row['flags'])

    def test_explicit_reference_override(self):
        rows, _, _ = result([lap(0),lap(50)],references={'chickens':50})
        self.assertTrue(all(r['baseline_workload']==50 for r in rows))

    def test_short_capture_is_excluded(self):
        rows,audit,_ = result([lap(0),lap(50,seconds=20)])
        row = next(r for r in rows if r['metric_name']=='avg_fps' and r['workload_level']==50)
        self.assertFalse(row['measurement_valid'])
        self.assertEqual(audit[1]['capture_completeness'],'short_capture')

    def test_count_contradiction_excludes_lap(self):
        rows,audit,_ = result([lap(0),lap(50,chickens_found=10)])
        row = next(r for r in rows if r['metric_name']=='avg_fps' and r['workload_level']==50)
        self.assertFalse(row['measurement_valid'])
        self.assertIn('observed_count_outside_tolerance',row['excluded_reasons'])
        self.assertEqual(audit[1]['workload_integrity'],'contradicted')

    def test_count_tolerance_is_explicit(self):
        rows, _, _ = result([lap(0),lap(50,chickens_found=44)],fallback_count_tolerance=20)
        row = next(r for r in rows if r['metric_name']=='avg_fps' and r['workload_level']==50)
        self.assertTrue(row['measurement_valid'])

    def test_missing_counts_remain_unverified(self):
        rows,audit,_ = result([lap(0,chickens_found='',chickens_after_spawn='')])
        row = next(r for r in rows if r['metric_name']=='avg_fps')
        self.assertTrue(row['measurement_valid'])
        self.assertEqual(row['validity'],'provisional_unverified_metadata')
        self.assertEqual(audit[0]['workload_integrity'],'unverified')

    def test_unverified_baseline_propagates_to_later_ratio(self):
        rows, _, _ = result([lap(0,chickens_found=''),lap(50)])
        row = next(r for r in rows if r['metric_name']=='avg_fps' and r['workload_level']==50)
        self.assertEqual(row['validity'],'provisional_unverified_metadata')

    def test_unverified_previous_endpoint_propagates_to_slope(self):
        rows,_,_=result([lap(0),lap(50,chickens_found=''),lap(100)])
        row=next(r for r in rows if r['metric_name']=='avg_fps' and r['workload_level']==100)
        self.assertEqual(row['validity'],'eligible_with_documented_assumptions')
        self.assertEqual(row['slope_validity'],'provisional_unverified_metadata')
        self.assertIn('slope_uses_unverified_metadata',row['flags'])

    def test_import_does_not_claim_known_capture_version(self):
        rows,_,_=result([lap(0,status='imported_unverified')])
        self.assertTrue(all(r['benchmark_version']=='unknown' for r in rows))
        self.assertTrue(all(r['benchmark_version_source']=='unverified_import' for r in rows))

    def test_duplicate_manifest_rows_preserved_and_excluded(self):
        rows,audit,_ = result([lap(0),lap(0),lap(50)])
        self.assertEqual(len(audit),3)
        self.assertNotEqual(audit[0]['lap_id'],audit[1]['lap_id'])
        self.assertTrue(audit[0]['duplicate_sweep_coordinate'])
        self.assertTrue(audit[1]['duplicate_sweep_coordinate'])
        row = next(r for r in rows if r['metric_name']=='avg_fps' and r['workload_level']==0)
        self.assertEqual(row['sample_count_laps'],0)

    def test_tail_support_is_metric_specific(self):
        rows, _, _ = result([lap(0,frames=500)])
        by_name = {r['metric_name']:r for r in rows}
        self.assertTrue(by_name['avg_fps']['measurement_valid'])
        self.assertTrue(by_name['p1_fps']['measurement_valid'])
        self.assertFalse(by_name['p01_fps']['measurement_valid'])
        self.assertTrue(by_name['cov_pct']['measurement_valid'])

    def test_zero_dispersion_is_not_normalized_as_speed(self):
        rows, _, _ = result([lap(0,ft_sd_ms=0,cov_pct=0)])
        row = next(r for r in rows if r['metric_name']=='cov_pct')
        self.assertEqual(row['measured_value'],0)
        self.assertIsNone(row['retention_ratio'])

    def test_nonfinite_values_export_as_missing(self):
        rows,audit,metadata = result([lap(0,avg_fps=math.nan)])
        with tempfile.TemporaryDirectory() as output:
            write_outputs(output,rows,audit,metadata)
            with (Path(output)/'stability_metrics.csv').open(newline='') as stream:
                data=list(csv.DictReader(stream))
            self.assertEqual(next(r for r in data if r['metric_name']=='avg_fps')['measured_value'],'')
            for r in data:
                self.assertFalse(any(v in ('nan','inf','-inf') for v in r.values()))

    def test_contradictory_timescale_excluded(self):
        rows,_,_ = result([lap(1,mode='timescale',timescale=2)])
        self.assertTrue(all(not r['measurement_valid'] for r in rows))

    def test_timescale_and_chicken_units_never_mix(self):
        rows,_,_ = result([lap(0),lap(1,mode='timescale',timescale=1)])
        self.assertEqual({r['workload_units'] for r in rows},
                         {'intended_chickens','host_timescale_multiplier'})

    def test_run_schedule_retains_unattempted_level(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root)/'run').mkdir()
            (Path(root)/'run'/'run_info.txt').write_text('Mode: chickens   Label: Chip   Passes: 3   Levels: 0,50,100\n')
            rows,_,_ = build_metrics([lap(0),lap(100)],root,'test',bootstrap_samples=0)
        row=next(r for r in rows if r['metric_name']=='avg_fps' and r['workload_level']==100)
        self.assertIsNone(row['local_degradation_rate'])
        self.assertEqual(row['previous_workload'],50)


class ReportTests(unittest.TestCase):
    def test_labels_escaped_and_report_self_contained(self):
        label = '</script><img src=x onerror="bad()">'
        rows,_,meta=result([lap(0,label=label),lap(50,label=label)])
        text=render_stability(rows,meta)
        self.assertNotIn('<img',text)
        self.assertIn('&lt;img',text)
        self.assertNotIn('<script src=',text)
        self.assertIn('data:text/csv;charset=utf-8;base64,',text)
        self.assertIn('data-metric-control',text)

    def test_chart_stops_at_missing_endpoint(self):
        rows,_,_=result([lap(0),lap(50,status='no_frames'),lap(100)])
        selected=[r for r in rows if r['metric_name']=='avg_fps']
        text=chart(selected,['Chip'],'measured_value','Absolute','fps','chickens')
        self.assertNotIn('<polyline',text)

    def test_irregular_x_coordinates_are_numeric(self):
        rows,_,_=result([lap(0),lap(50),lap(200)])
        selected=[r for r in rows if r['metric_name']=='avg_fps']
        text=chart(selected,['Chip'],'measured_value','Absolute','fps','chickens')
        # Plot: left x=72, width=626; x=50 is one quarter, not the middle.
        self.assertIn('cx="228.50"',text)

    def test_near_constant_axis_does_not_magnify_roundoff(self):
        rows,_,_=result([lap(0,cov_pct=8),lap(50,cov_pct=8+1e-10)])
        selected=[r for r in rows if r['metric_name']=='cov_pct']
        text=chart(selected,['Chip'],'measured_value','CV','percent','chickens')
        import re
        ticks=re.findall(r'text-anchor="end" dy=".32em">([^<]+)</text>',text)
        self.assertGreater(len(set(ticks)),2)
        self.assertTrue(any(float(t)<7.9 for t in ticks))


if __name__ == '__main__':
    unittest.main()
