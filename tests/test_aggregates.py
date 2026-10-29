import base64
import csv
import io
import json
import math
from pathlib import Path
import re
import tempfile
import unittest

from cb_formulas import HIGHER, LOWER, Observation, aggregate_curve, summarize_series
from cb_stability import build_metrics, write_outputs
from cb_stability_report import render_stability
from test_adapter import lap


class AggregateFormulaTests(unittest.TestCase):
    def test_flat_curve_retains_one_hundred_percent(self):
        r = aggregate_curve([0, 50, 500], [180, 180, 180], 180)
        self.assertEqual(r['workload_average'], 180)
        self.assertEqual(r['retention_score_pct'], 100)
        self.assertEqual(r['mean_degradation_pct'], 0)
        self.assertEqual(r['mean_degradation_rate'], 0)

    def test_linear_curve_has_known_average_and_rate(self):
        r = aggregate_curve([0, 50, 100], [100, 80, 60], 100)
        self.assertEqual(r['workload_average'], 80)
        self.assertEqual(r['retention_score_pct'], 80)
        self.assertAlmostEqual(r['mean_degradation_pct'], 20)
        self.assertAlmostEqual(r['mean_degradation_rate'], .4)

    def test_irregular_intervals_do_not_count_points_equally(self):
        r = aggregate_curve([0, 10, 100], [100, 90, 50], 100)
        self.assertEqual(r['workload_average'], 72.5)
        self.assertEqual(r['retention_score_pct'], 72.5)
        self.assertNotAlmostEqual(r['workload_average'], (100+90+50)/3)

    def test_extra_collinear_point_does_not_reweight_the_curve(self):
        a = aggregate_curve([0, 100], [100, 50], 100)
        b = aggregate_curve([0, 1, 10, 100], [100, 99.5, 95, 50], 100)
        self.assertAlmostEqual(a['retention_score_pct'], b['retention_score_pct'])

    def test_improvements_are_not_clipped(self):
        r = aggregate_curve([0, 100], [100, 120], 100)
        self.assertAlmostEqual(r['retention_score_pct'], 110)
        self.assertAlmostEqual(r['mean_degradation_pct'], -10)
        self.assertLess(r['mean_degradation_rate'], 0)

    def test_missing_interior_withholds_area_without_bridging(self):
        r = aggregate_curve([0, 50, 100, 200], [100, None, 80, 60], 100)
        self.assertIsNone(r['workload_average'])
        self.assertIsNone(r['retention_score_pct'])
        self.assertEqual(r['workload_coverage_pct'], 50)
        self.assertEqual(r['summary_status'], 'missing_or_invalid_workload_levels')
        self.assertAlmostEqual(r['mean_degradation_rate'], .2)

    def test_missing_reference_keeps_native_aggregate(self):
        r = aggregate_curve([50, 100], [80, 60], None)
        self.assertEqual(r['workload_average'], 70)
        self.assertIsNone(r['retention_score_pct'])
        self.assertEqual(r['summary_status'], 'missing_or_invalid_baseline')

    def test_single_level_has_no_workload_span_score(self):
        r = aggregate_curve([0], [100], 100)
        self.assertIsNone(r['workload_average'])
        self.assertIsNone(r['retention_score_pct'])
        self.assertEqual(r['summary_status'], 'insufficient_workload_span')

    def test_lower_metric_averages_pointwise_reciprocal_retention(self):
        r = aggregate_curve([0, 100], [10, 20], 10, LOWER)
        self.assertEqual(r['workload_average'], 15)
        self.assertEqual(r['retention_score_pct'], 75)
        self.assertNotAlmostEqual(r['retention_score_pct'], 100*10/15)

    def test_zero_dispersion_keeps_native_units_without_normalization(self):
        r = aggregate_curve([0, 50], [0, 0], 0, LOWER, normalize=False)
        self.assertEqual(r['workload_average'], 0)
        self.assertIsNone(r['retention_score_pct'])

    def test_curve_recovers_at_end_but_area_records_intermediate_loss(self):
        r = aggregate_curve([0, 50, 100], [100, 50, 100], 100)
        self.assertEqual(r['retention_score_pct'], 75)
        self.assertEqual(r['endpoint_retention_pct'], 100)
        self.assertEqual(r['mean_degradation_rate'], 0)

    def test_invalid_coordinates_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            aggregate_curve([0, 0], [100, 90], 100)
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            aggregate_curve([0, math.inf], [100, 90], 100)


class AggregateUncertaintyTests(unittest.TestCase):
    def test_shared_reference_resampled_with_whole_curve(self):
        obs = [Observation(load, factor*value, 'r', str(i))
               for i, factor in enumerate([.8, 1, 1.2])
               for load, value in [(0, 100), (50, 80), (100, 60)]]
        r = summarize_series(obs, 0, HIGHER, bootstrap_samples=200)
        self.assertLess(r['workload_average_ci_low'], r['workload_average_ci_high'])
        self.assertAlmostEqual(r['retention_score_pct_ci_low'], 80)
        self.assertAlmostEqual(r['retention_score_pct_ci_high'], 80)
        self.assertAlmostEqual(r['mean_degradation_rate_ci_low'], .4)
        self.assertAlmostEqual(r['mean_degradation_rate_ci_high'], .4)

    def test_single_sweep_has_point_estimate_without_inferred_interval(self):
        obs = [Observation(0, 100, 'r', '1'), Observation(100, 60, 'r', '1')]
        r = summarize_series(obs, 0, HIGHER)
        self.assertEqual(r['retention_score_pct'], 80)
        self.assertIsNone(r['retention_score_pct_ci_low'])
        self.assertEqual(r['retention_score_pct_ci_status'], 'insufficient_units')

    def test_unmatched_sweep_support_withholds_interval(self):
        obs = [Observation(0, 100+i, 'r', str(i)) for i in range(4)]
        obs += [Observation(100, 60+i, 'r', str(i)) for i in range(3)]
        r = summarize_series(obs, 0, HIGHER)
        self.assertIsNotNone(r['retention_score_pct'])
        self.assertIsNone(r['retention_score_pct_ci_low'])
        self.assertEqual(r['retention_score_pct_ci_status'], 'unmatched_unit_support')

    def test_multiple_runs_resample_runs_and_keep_ratio_of_level_means(self):
        obs = [Observation(load, v, str(run), str(repeat))
               for run, values in enumerate([(100, 80), (200, 100), (300, 120)])
               for repeat in range(2) for load, v in zip([0, 100], values)]
        r = summarize_series(obs, 0, HIGHER, bootstrap_samples=200)
        self.assertEqual(r['retention_score_pct'], 75)
        self.assertEqual(r['uncertainty_unit'], 'run')
        self.assertEqual(r['retention_score_pct_ci_units'], 3)


class AggregateOutputTests(unittest.TestCase):
    def test_csv_and_html_expose_separate_scores_and_embedded_csv_matches(self):
        laps = [lap(load, p, avg_fps=fps, p1_fps=p1, p01_fps=p01)
                for p in [1, 2, 3] for load, fps, p1, p01 in [(0,100,80,60),(50,80,56,30)]]
        with tempfile.TemporaryDirectory() as tmp:
            rows, audits, meta = build_metrics(laps, tmp, 'test', bootstrap_samples=200)
            write_outputs(tmp, rows, audits, meta)
            page = render_stability(rows, meta)
            summaries = {r['metric_name']:r for r in meta['aggregate_metrics']}
            self.assertEqual(summaries['avg_fps']['retention_score_pct'], 90)
            self.assertEqual(summaries['p1_fps']['retention_score_pct'], 85)
            self.assertEqual(summaries['p01_fps']['retention_score_pct'], 75)
            self.assertEqual(summaries['p1_fps']['workload_average'], 68)
            for metric in ['avg_fps','p1_fps','p01_fps']:
                self.assertIn('data-summary-metric="'+metric+'"', page)
            self.assertLess(page.index('One value per metric'), page.index('Reading the curves'))
            match = re.search('download="stability_summary.csv" href="data:text/csv;charset=utf-8;base64,([^"]+)"',page)
            self.assertIsNotNone(match)
            self.assertEqual(base64.b64decode(match[1]), (Path(tmp)/'stability_summary.csv').read_bytes())

    def test_invalid_tail_support_does_not_create_a_low_fps_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, meta = build_metrics([lap(0,frames=400),lap(50,frames=400)],tmp,'test',bootstrap_samples=0)
        summary = next(r for r in meta['aggregate_metrics'] if r['metric_name']=='p01_fps')
        self.assertIsNone(summary['retention_score_pct'])
        self.assertEqual(summary['summary_status'],'missing_or_invalid_workload_levels')

    def test_unverified_metadata_is_propagated_to_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,_,meta = build_metrics([lap(0,chickens_found=''),lap(50)],tmp,'test',bootstrap_samples=0)
        summary = next(r for r in meta['aggregate_metrics'] if r['metric_name']=='p1_fps')
        self.assertEqual(summary['validity'], 'provisional_unverified_metadata')


if __name__ == '__main__':
    unittest.main()
