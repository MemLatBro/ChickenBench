#!/usr/bin/env python3
"""Copy flat captures into an explicitly UNVERIFIED offline replay dataset.

Workload coordinates and pass IDs come only from filenames, never verified game state.
The replay is opt-in in cb_analyze.py and excluded from the legacy summaries.
"""
import argparse
import csv
from pathlib import Path
import re
import shutil

PATTERN = re.compile(r'^(?P<label>.+)_(?P<mode>chickens|timescale)_(?P<level>\d+)_p(?P<pass>\d+)\.csv$')


def import_captures(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('import destination must be empty; original files are never overwritten')
    grouped = {}
    for path in source.glob('*.csv'):
        match = PATTERN.fullmatch(path.name)
        if match:
            row = match.groupdict()
            grouped.setdefault((row['label'], row['mode']), []).append((path, row))
    if not grouped:
        raise ValueError('no captures matched <label>_<mode>_<load>_p<pass>.csv')
    for (label, mode), files in grouped.items():
        run = destination / ('unverified_replay_' + label + '_' + mode)
        (run / 'frames').mkdir(parents=True)
        rows = []
        for path, row in sorted(files, key=lambda pair: (int(pair[1]['pass']), int(pair[1]['level']))):
            shutil.copy2(path, run / 'frames' / path.name)
            rows.append(dict(row, frames_csv='frames/' + path.name, status='imported_unverified',
                             capture_seconds='', timescale='', chickens_expected='', chickens_found='',
                             note='UNVERIFIED OFFLINE REPLAY: coordinates inferred from filename; manifest, counts and capture window unavailable'))
        with (run / 'laps.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (run / 'IMPORT_NOTE.txt').write_text('UNVERIFIED OFFLINE REPLAY\n'
            'No CS2 or PresentMon execution occurred. Only capture bytes were copied.\n'
            'Workload coordinates and pass IDs came from filenames; true load and capture completeness are unknown.\n'
            'Run cb_analyze.py with --include-unverified-imports to analyze provisionally.\n', encoding='utf-8')
    return sum(map(len, grouped.values()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination')
    args = parser.parse_args()
    print('Imported %d unverified offline captures.' % import_captures(args.source, args.destination))
