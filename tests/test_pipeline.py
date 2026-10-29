import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cb_analyze import load_frametimes, svg_chart, svg_timeline

PROJECT = Path(__file__).resolve().parents[1] / "analysis"
GOLDEN = Path(__file__).parent / 'fixtures' / 'legacy_csv'


def make_fixture(root):
    root = Path(root)
    for mode, levels in [('chickens',[0,50,150]),('timescale',[1,2,4])]:
        for label, offset in [('Ref',0),('Faster',-2)]:
            run = root / ('test_' + mode + '_' + label)
            (run/'frames').mkdir(parents=True)
            rows=[]
            for repeat in [1,2,3]:
                for level in levels:
                    stem='level%s_pass%s.csv'%(level,repeat)
                    ft=[10+offset+level*.01+repeat*.1+(i%3)*.2 for i in range(600)]
                    with (run/'frames'/stem).open('w',newline='') as stream:
                        writer=csv.writer(stream)
                        writer.writerow(['SwapChainAddress','MsBetweenPresents'])
                        writer.writerows(('main','%.4f'%value) for value in ft)
                    rows.append(dict(label=label,mode=mode,level=level,**{'pass':repeat},
                                     timescale=level if mode=='timescale' else 1,
                                     chickens_expected=level if mode=='chickens' else '',
                                     chickens_found=level if mode=='chickens' else '',
                                     chickens_after_spawn=level if mode=='chickens' else '',
                                     capture_seconds=sum(ft)/1000,frames_csv='frames/'+stem,status='ok'))
            with (run/'laps.csv').open('w',newline='') as stream:
                writer=csv.DictWriter(stream,list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    return root


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.root=make_fixture(Path(cls.tmp.name)/'inputs')
        cls.out=Path(cls.tmp.name)/'outputs'
        cls.before={str(p.relative_to(cls.root)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in cls.root.rglob('*') if p.is_file()}
        cls.result=subprocess.run([sys.executable,str(PROJECT/'cb_analyze.py'),str(cls.root),
                                   '--output-dir',str(cls.out),'--baseline','Ref','--stability-bootstrap','200'],
                                  capture_output=True,text=True)
        if cls.result.returncode:
            raise RuntimeError(cls.result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_original_csvs_match_golden_bytes(self):
        for name in ['lap_metrics.csv','summary.csv','comparison.csv']:
            with self.subTest(name=name):
                self.assertEqual((self.out/name).read_bytes(),(GOLDEN/name).read_bytes())

    def test_inputs_are_unchanged(self):
        after={str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest()
               for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.before,after)

    def test_legacy_report_graphs_remain(self):
        text=(self.out/'report.html').read_text()
        for heading in ['Gap vs Ref','Absolute results (log scale)',
                        'Frame-time spread inside each lap (log scale)','FPS through the lap',
                        'Excluded or flagged laps','id="stability"']:
            self.assertIn(heading,text)

    def test_expected_new_exports(self):
        for name in ['stability_metrics.csv','stability_laps.csv','stability_metadata.json','stability_report.html','stability_summary.csv']:
            self.assertTrue((self.out/name).is_file())
        with (self.out/'stability_laps.csv').open(newline='') as stream:
            self.assertEqual(len(list(csv.DictReader(stream))),36)

    def test_prior_outputs_backed_up_exactly(self):
        old={name:(self.out/name).read_bytes() for name in ['report.html','lap_metrics.csv','summary.csv','comparison.csv','stability_summary.csv']}
        rerun=subprocess.run([sys.executable,str(PROJECT/'cb_analyze.py'),str(self.root),
                              '--output-dir',str(self.out),'--baseline','Ref','--stability-bootstrap','0'],
                             capture_output=True,text=True)
        self.assertEqual(rerun.returncode,0,rerun.stderr)
        metadata=json.loads((self.out/'stability_metadata.json').read_text())
        backup=self.out/metadata['previous_output_backup']
        for name,content in old.items():
            self.assertEqual((backup/name).read_bytes(),content)

    def test_invalid_reference_rejected_before_output_changes(self):
        bad=subprocess.run([sys.executable,str(PROJECT/'cb_analyze.py'),str(self.root),
                            '--output-dir',str(self.out),'--reference-timescale','nan'],capture_output=True,text=True)
        self.assertNotEqual(bad.returncode,0)
        self.assertIn('invalid reference workload',bad.stderr)

    def test_csv_provenance_and_missing_cells(self):
        with (self.out/'stability_metrics.csv').open(newline='') as stream:
            rows=list(csv.DictReader(stream))
        self.assertTrue(all(r['formula_version']=='1.1.0' for r in rows))
        self.assertTrue(all(r['included_lap_ids'] for r in rows))
        missing=[r for r in rows if r['metric_name']=='p01_fps']
        self.assertTrue(all(r['measured_value']=='' for r in missing))


class InputAndRenderEdgeTests(unittest.TestCase):
    def test_invalid_rows_and_other_chains_are_counted(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'frames.csv'
            path.write_text('SwapChainAddress,MsBetweenPresents\na,10\na,20\nb,5\na,nan\na,0\na,bad\n')
            diagnostics={}
            ft,col=load_frametimes(path,diagnostics)
        self.assertEqual(ft,[10,20])
        self.assertEqual(col,'MsBetweenPresents')
        self.assertEqual(diagnostics,dict(total_rows=6,rejected_rows=3,other_chain_rows=1,
                                          selected_chain_rejected_rows=3))

    def test_flat_log_chart_and_timeline_do_not_divide_by_zero(self):
        self.assertIn('<svg',svg_chart('flat',['0','50'],[dict(name='flat',slot=1,points=[(100,None),(100,None)])],
                                      ('fps','load'),log=True))
        self.assertIn('<svg',svg_timeline('flat',[('flat',[100]*5)],'seconds'))

    def test_missing_frame_column_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'frames.csv'
            path.write_text('wrong_column\n10\n')
            values,reason=load_frametimes(path,{})
        self.assertIsNone(values)
        self.assertIn('no frame-time column',reason)


if __name__ == '__main__':
    unittest.main()
