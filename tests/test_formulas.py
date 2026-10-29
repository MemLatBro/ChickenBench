import math
import unittest

from cb_formulas import (HIGHER, LOWER, Observation, analyze_series, degradation,
                         local_rate, retention)


def curve(loads, values, **kwargs):
    observations = [Observation(load, value, 'run', '1') for load, value in zip(loads, values)]
    return analyze_series(observations, kwargs.pop('baseline_load', loads[0]),
                          kwargs.pop('direction', HIGHER), loads, bootstrap_samples=0, **kwargs)


class FormulaTests(unittest.TestCase):
    def test_higher_retention(self):
        self.assertEqual(retention(80, 100), .8)
        self.assertAlmostEqual(degradation(.8), 20)

    def test_reciprocal_retention(self):
        self.assertEqual(retention(20, 10, LOWER), .5)
        self.assertEqual(degradation(.5), 50)

    def test_improvement_is_not_clipped(self):
        self.assertEqual(retention(125, 100), 1.25)
        self.assertEqual(degradation(1.25), -25)
        self.assertAlmostEqual(retention(8, 10, LOWER), 1.25)

    def test_invalid_denominators_and_values(self):
        for value, baseline in [(0,100), (100,0), (-1,10), (1,-1), (math.inf,1),
                                (1,math.nan), (None,1), ('bad',10), (1e308,1e-308)]:
            self.assertIsNone(retention(value, baseline))
        self.assertIsNone(degradation(math.nan))

    def test_unknown_direction_rejected(self):
        with self.assertRaises(ValueError):
            retention(1, 1, 'guess')

    def test_actual_irregular_intervals(self):
        rows = curve([0,50,150], [100,80,50])
        self.assertIsNone(rows[0]['local_degradation_rate'])
        self.assertAlmostEqual(rows[1]['local_degradation_rate'], .4)
        self.assertAlmostEqual(rows[2]['local_degradation_rate'], .3)

    def test_flat_curve(self):
        rows = curve([0,50,100], [80,80,80])
        self.assertEqual([r['retention_ratio'] for r in rows], [1,1,1])
        self.assertEqual([r['degradation_pct'] for r in rows], [0,0,0])
        self.assertEqual([r['local_degradation_rate'] for r in rows[1:]], [0,0])

    def test_linear_degradation(self):
        rows = curve([0,20,40], [100,90,80])
        for row in rows[1:]:
            self.assertAlmostEqual(row['local_degradation_rate'], .5)

    def test_nonlinear_degradation(self):
        rows = curve([0,100,200], [100,99,84])
        self.assertAlmostEqual(rows[1]['local_degradation_rate'], .01)
        self.assertAlmostEqual(rows[2]['local_degradation_rate'], .15)

    def test_improving_curve_has_negative_slope(self):
        rows = curve([0,50,100], [100,110,125])
        self.assertAlmostEqual(rows[1]['local_degradation_rate'], -.2)
        self.assertAlmostEqual(rows[2]['local_degradation_rate'], -.3)

    def test_different_baseline(self):
        rows = curve([0,50,100], [100,80,60], baseline_load=50)
        self.assertEqual([r['retention_ratio'] for r in rows], [1.25,1,.75])
        self.assertEqual([r['degradation_pct'] for r in rows], [-25,0,25])

    def test_missing_baseline_is_not_replaced(self):
        rows = curve([0,50,100], [None,80,60])
        self.assertIsNone(rows[1]['retention_ratio'])
        self.assertEqual(rows[1]['measured_value'], 80)
        self.assertIsNone(rows[2]['local_degradation_rate'])

    def test_absent_reference_coordinate(self):
        rows = curve([50,100], [80,60], baseline_load=0)
        self.assertTrue(all(r['retention_ratio'] is None for r in rows))

    def test_invalid_middle_level_blocks_slope(self):
        rows = curve([0,50,100], [100,None,60])
        self.assertIsNone(rows[2]['local_degradation_rate'])
        self.assertAlmostEqual(rows[2]['retention_ratio'], .6)

    def test_duplicate_coordinate_within_sweep_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            analyze_series([Observation(0,100,'r','1'), Observation(0,101,'r','1')], 0, HIGHER)

    def test_repetitions_at_same_load_are_not_duplicates(self):
        rows = analyze_series([Observation(0,100,'r','1'), Observation(0,110,'r','2')],
                              0, HIGHER, bootstrap_samples=0)
        self.assertEqual(rows[0]['sample_count_laps'], 2)
        self.assertEqual(rows[0]['measured_value'], 105)

    def test_nonfinite_coordinate_rejected(self):
        with self.assertRaises(ValueError):
            analyze_series([Observation(math.inf,1,'r','1')], 0, HIGHER)

    def test_invalid_intervals_rejected(self):
        self.assertIsNone(local_rate(0,10,50,50))
        self.assertIsNone(local_rate(0,10,100,50))
        self.assertIsNone(local_rate(0,None,0,50))

    def test_zero_dispersion_is_a_valid_observation(self):
        row = curve([0], [0], normalize=False, allow_zero=True)[0]
        self.assertEqual(row['measured_value'], 0)
        self.assertIsNone(row['retention_ratio'])


class UncertaintyTests(unittest.TestCase):
    def test_single_lap_does_not_gain_frame_level_confidence(self):
        row = analyze_series([Observation(0,100,'r','1')], 0, HIGHER)[0]
        self.assertEqual(row['sample_count_laps'], 1)
        self.assertIsNone(row['value_ci_low'])
        self.assertEqual(row['retention_ci_low'], 1)
        self.assertEqual(row['retention_ci_status'], 'algebraic_identity')

    def test_two_repeats_show_sd_without_inferred_interval(self):
        obs = [Observation(0,90,'r','1'),Observation(0,110,'r','2')]
        row = analyze_series(obs,0,HIGHER)[0]
        self.assertAlmostEqual(row['between_lap_sd'], math.sqrt(200))
        self.assertIsNone(row['value_ci_low'])
        self.assertEqual(row['value_ci_units'], 2)

    def test_ratio_of_means_not_mean_of_ratios(self):
        obs = [Observation(0,100,'r','1'),Observation(50,100,'r','1'),
               Observation(0,200,'r','2'),Observation(50,100,'r','2')]
        row = analyze_series(obs,0,HIGHER,bootstrap_samples=0)[1]
        self.assertAlmostEqual(row['retention_ratio'], 2/3)
        self.assertNotEqual(row['retention_ratio'], .75)

    def test_shared_baseline_and_curve_covariance_preserved(self):
        obs = [Observation(load, factor * value, 'r', str(i))
               for i, factor in enumerate([.8,1,1.2])
               for load, value in [(0,100),(50,80),(100,60)]]
        rows = analyze_series(obs,0,HIGHER,bootstrap_samples=400)
        self.assertLess(rows[0]['value_ci_low'], rows[0]['value_ci_high'])
        self.assertAlmostEqual(rows[1]['retention_ci_low'], .8)
        self.assertAlmostEqual(rows[1]['retention_ci_high'], .8)
        self.assertAlmostEqual(rows[2]['rate_ci_low'], .4)
        self.assertAlmostEqual(rows[2]['rate_ci_high'], .4)

    def test_known_bootstrap_mean_bounds(self):
        # Three draws from {90,100,110}: each extreme has probability 1/27 > 2.5%.
        obs = [Observation(0,v,'r',str(i)) for i,v in enumerate([90,100,110])]
        row = analyze_series(obs,0,HIGHER,bootstrap_samples=2000)[0]
        self.assertEqual((row['value_ci_low'],row['value_ci_high']), (90,110))
        self.assertEqual(row['value_ci_status'], 'exploratory_small_n')

    def test_lower_metric_transforms_bounds_in_correct_order(self):
        obs = [Observation(load,value,'r',str(i)) for i,values in enumerate([(10,15),(11,18),(9,22)])
               for load,value in zip([0,50],values)]
        row = analyze_series(obs,0,LOWER,bootstrap_samples=400)[1]
        self.assertLess(row['retention_ci_low'], row['retention_ci_high'])
        self.assertAlmostEqual(row['degradation_ci_low'],100*(1-row['retention_ci_high']))
        self.assertAlmostEqual(row['degradation_ci_high'],100*(1-row['retention_ci_low']))

    def test_repeatable_seed(self):
        obs = [Observation(load,100 + i - load*.2,'r',str(i)) for i in range(3) for load in [0,50]]
        self.assertEqual(analyze_series(obs,0,HIGHER,bootstrap_samples=200),
                         analyze_series(obs,0,HIGHER,bootstrap_samples=200))

    def test_unmatched_support_does_not_invent_paired_interval(self):
        obs = [Observation(0,100+i,'r',str(i)) for i in range(4)]
        obs += [Observation(50,80+i,'r',str(i)) for i in range(3)]
        row = analyze_series(obs,0,HIGHER,bootstrap_samples=200)[1]
        self.assertIsNotNone(row['retention_ratio'])
        self.assertIsNone(row['retention_ci_low'])
        self.assertEqual(row['retention_ci_status'], 'unmatched_unit_support')

    def test_multiple_runs_cluster_at_run_level(self):
        obs = [Observation(0,100+run+repeat,str(run),str(repeat)) for run in range(3) for repeat in range(3)]
        row = analyze_series(obs,0,HIGHER,bootstrap_samples=200)[0]
        self.assertEqual(row['uncertainty_unit'], 'run')
        self.assertEqual(row['sample_count_laps'], 9)
        self.assertEqual(row['value_ci_units'], 3)

    def test_two_runs_do_not_become_six_independent_laps(self):
        obs = [Observation(0,100+run+repeat,str(run),str(repeat)) for run in range(2) for repeat in range(3)]
        row = analyze_series(obs,0,HIGHER,bootstrap_samples=200)[0]
        self.assertEqual(row['value_ci_units'], 2)
        self.assertIsNone(row['value_ci_low'])


if __name__ == '__main__':
    unittest.main()
