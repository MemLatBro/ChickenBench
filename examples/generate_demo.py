#!/usr/bin/env python3
"""Generate deterministic synthetic manifests/captures. This never starts CS2."""
import argparse
import csv
from pathlib import Path
import sys

FIELDS = ['label', 'mode', 'level', 'pass', 'timescale', 'chickens_expected', 'chickens_found',
          'chickens_after_restart', 'chickens_after_spawn', 'round_start_detected',
          'capture_seconds', 'frames_csv', 'status', 'note']


def generate(destination):
    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('demo destination must be empty')
    for mode, loads in [('chickens', [0, 50, 100, 200, 350, 500]), ('timescale', [1, 2, 4, 8, 12])]:
        for label, base, loss in [('Demo-A', 210.0, .65), ('Demo-B', 165.0, .38)]:
            run = destination / ('synthetic_%s_%s' % (label, mode))
            (run / 'frames').mkdir(parents=True)
            manifest = []
            for repeat in range(1, 4):
                for level in loads:
                    progress = level / 500 if mode == 'chickens' else (level - 1) / 11
                    fps = base * (1 - loss * progress) * (1 + (repeat - 2) * (.008 + .006 * progress))
                    frame_times = [(1000.0 / fps) * (1 + (-.12, -.04, 0, .04, .12)[i % 5])
                                   for i in range(3600)]
                    filename = '%s_%s_%s_p%s.csv' % (label, mode, level, repeat)
                    with (run / 'frames' / filename).open('w', newline='', encoding='utf-8') as stream:
                        writer = csv.writer(stream)
                        writer.writerow(['Application', 'SwapChainAddress', 'MsBetweenPresents'])
                        writer.writerows(('cs2.exe', 'demo_chain', '%.10f' % v) for v in frame_times)
                    manifest.append(dict(label=label, mode=mode, level=level, **{'pass':repeat},
                        timescale=level if mode == 'timescale' else 1,
                        chickens_expected=level if mode == 'chickens' else '',
                        chickens_found=level if mode == 'chickens' else '',
                        chickens_after_restart=level if mode == 'chickens' else '',
                        chickens_after_spawn=level if mode == 'chickens' else '',
                        round_start_detected=1, capture_seconds=sum(frame_times) / 1000.0,
                        frames_csv='frames/' + filename, status='ok', note='SYNTHETIC: no game was run'))
            with (run / 'laps.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, FIELDS)
                writer.writeheader()
                writer.writerows(manifest)
            (run / 'run_info.txt').write_text('ChickenBench v1.0.7\nSYNTHETIC DATA: no CS2 or PresentMon execution\n'
                'Mode: %s   Label: %s   Passes: 3   Levels: %s\nSettings: ChickenTolerancePct=10\n'
                % (mode, label, ','.join(map(str, loads))), encoding='utf-8')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    args = parser.parse_args()
    print(generate(args.destination))
