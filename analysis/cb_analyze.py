#!/usr/bin/env python3
"""ChickenBench analyzer v1.2.0 (capture package v1.0.7)

Reads every run folder under Results/ (each has laps.csv + frames/*.csv from PresentMon),
computes per-lap metrics, aggregates per config label / mode / load level, compares every
label against a baseline label, and writes:

  Results/lap_metrics.csv   one row per lap
  Results/summary.csv       one row per label / mode / level (mean, SD, 95% CI)
  Results/comparison.csv    gap vs baseline per level
  Results/report.html       charts + tables

Additional versioned stability exports preserve legacy CSV schemas and report sections.
Standard library only. Usage:  py -3 cb_analyze.py Results --baseline JEDEC
"""
import argparse
import csv
import html
import math
import os
import statistics
import hashlib
import shutil
import sys
from datetime import datetime

VERSION = '1.2.0'

from cb_stability import build_metrics, write_outputs
from cb_stability_report import render_stability, write_standalone
FT_COLUMNS = ['MsBetweenPresents', 'msBetweenPresents', 'FrameTime']
USABLE_STATUS = {'ok'}
MIN_FRAMES_P01 = 3000   # below this the 0.1% low rests on fewer than 3 frames
MIN_FRAMES_P1 = 300
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
       9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 30: 2.042}


def t95(df):
    if df <= 0:
        return float('nan')
    if df in T95:
        return T95[df]
    keys = sorted(T95)
    for k in keys:
        if k > df:
            return T95[k]
    return 1.96


# ---------------------------------------------------------------- frame data
def load_frametimes(path, diagnostics=None):
    """Return (list of frame times in ms, column used) or (None, reason)."""
    with open(path, newline='', encoding='utf-8-sig', errors='replace') as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        col = next((c for c in FT_COLUMNS if c in fields), None)
        if col is None:
            return None, 'no frame-time column (expected one of %s)' % ', '.join(FT_COLUMNS)
        sc_col = 'SwapChainAddress' if 'SwapChainAddress' in fields else None
        rows = []
        rejected = {}
        total_rows = 0
        for row in reader:
            total_rows += 1
            chain = row.get(sc_col, '') if sc_col else ''
            try:
                v = float(row[col])
            except (TypeError, ValueError):
                rejected[chain] = rejected.get(chain, 0) + 1
                continue
            if 0 < v < 120000:      # keep freezes (up to 2 min); dropping them would inflate the FPS
                rows.append((chain, v))
            else:
                rejected[chain] = rejected.get(chain, 0) + 1
    if diagnostics is not None:
        diagnostics.update(total_rows=total_rows, rejected_rows=sum(rejected.values()),
                           other_chain_rows=0, selected_chain_rejected_rows=0)
    if not rows:
        return None, 'no valid frames'
    if sc_col:   # keep the swap chain with the most presents (the game's)
        counts = {}
        for k, _ in rows:
            counts[k] = counts.get(k, 0) + 1
        main = max(counts, key=counts.get)
        ft = [v for k, v in rows if k == main]
        if diagnostics is not None:
            diagnostics.update(other_chain_rows=len(rows) - len(ft),
                               selected_chain_rejected_rows=rejected.get(main, 0))
    else:
        ft = [v for _, v in rows]
        if diagnostics is not None:
            diagnostics['selected_chain_rejected_rows'] = sum(rejected.values())
    return ft, col


def percentile(sorted_vals, p):
    """Linear-interpolated percentile, p in 0..100."""
    if not sorted_vals:
        return float('nan')
    k = (len(sorted_vals) - 1) * p / 100.0
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def timeline(ft, bin_s=1.0):
    """Average FPS per bin of capture time (frames in bin / bin length)."""
    out, t, n, edge = [], 0.0, 0, bin_s * 1000.0
    for v in ft:
        t += v
        n += 1
        while t >= edge:
            out.append(n / bin_s)
            n = 0
            edge += bin_s * 1000.0
    return out


def lap_metrics(ft):
    s = sorted(ft)
    total = sum(ft)
    mean = total / len(ft)
    return {
        'frames': len(ft),
        'seconds': total / 1000.0,
        'avg_fps': 1000.0 * len(ft) / total,                 # frames / time (time-weighted)
        'p1_fps': 1000.0 / percentile(s, 99.0),              # 1% low = 99th percentile frame time
        'p01_fps': 1000.0 / percentile(s, 99.9),             # 0.1% low = 99.9th percentile frame time
        'ft_p50_ms': percentile(s, 50.0),
        'ft_p99_ms': percentile(s, 99.0),
        'ft_sd_ms': statistics.pstdev(ft),
        'ft_p90_ms': percentile(s, 90.0),
        'ft_p999_ms': percentile(s, 99.9),
        'ft_max_ms': s[-1],
        'cov_pct': statistics.pstdev(ft) / mean * 100.0,   # frame-time spread relative to its mean
    }


# ---------------------------------------------------------------- aggregation
def summarize(values):
    n = len(values)
    m = statistics.mean(values) if n else float('nan')
    sd = statistics.stdev(values) if n > 1 else float('nan')
    ci = t95(n - 1) * sd / math.sqrt(n) if n > 1 else float('nan')
    return {'n': n, 'mean': m, 'sd': sd, 'ci95': ci}


def gap(test, base):
    """Percent difference of means (test vs base) with an approximate 95% CI."""
    if not test['n'] or not base['n'] or base['mean'] == 0:
        return None
    g = (test['mean'] / base['mean'] - 1.0) * 100.0
    ci = float('nan')
    if test['n'] > 1 and base['n'] > 1:
        se_t = test['sd'] / math.sqrt(test['n'])
        se_b = base['sd'] / math.sqrt(base['n'])
        rel_se = math.sqrt((se_t / test['mean']) ** 2 + (se_b / base['mean']) ** 2)
        df = min(test['n'], base['n']) - 1        # conservative
        ci = t95(df) * rel_se * (test['mean'] / base['mean']) * 100.0
    return {'gap_pct': g, 'ci95_pct': ci}


# ---------------------------------------------------------------- report (SVG)
def fmt(v, d=1):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return '-'
    return ('{:,.%df}' % d).format(v)


def nice_ticks(lo, hi, n=5):
    if hi <= lo:
        hi = lo + 1
    span = hi - lo
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=mag * 10)
    start = math.floor(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 0.001:
        ticks.append(round(v, 10))
        v += step
    return ticks


def log_ticks(lo, hi):
    ticks = []
    k = math.floor(math.log10(lo))
    while 10 ** k <= hi * 1.0001:
        for m in (1, 2, 5):
            v = m * 10 ** k
            if lo * 0.9999 <= v <= hi * 1.0001:
                ticks.append(v)
        k += 1
    return ticks


def svg_chart(title, x_labels, series, y_title, zero_line=False, include_zero=True, log=False):
    """series: list of dicts {name, slot, points:[(mean, ci) or None per x]}"""
    W, H = 640, 300
    ml, mr, mt, mb = 64, 20, 16, 44
    pw, ph = W - ml - mr, H - mt - mb
    vals = []
    for s in series:
        for p in s['points']:
            if p and not math.isnan(p[0]):
                c = p[1] if p[1] is not None and not math.isnan(p[1]) else 0
                vals += [p[0] - c, p[0] + c]
    if not vals:
        return '<p class="muted">No data for this chart.</p>'
    lo, hi = min(vals), max(vals)
    if log:
        lo = max(min(v for v in vals if v > 0), 1e-3)
        steps = log_ticks(10 ** math.floor(math.log10(lo)), 10 ** math.ceil(math.log10(hi)))
        y0 = max([t for t in steps if t <= lo] or [steps[0]])
        y1 = min([t for t in steps if t >= hi] or [steps[-1]])
        if y1 <= y0:  # A flat power-of-ten curve still needs a nonzero axis span.
            y0, y1 = y0 / 10.0, y1 * 10.0
        ticks = log_ticks(y0, y1)
        tr = math.log10
    else:
        if include_zero:
            lo, hi = min(lo, 0), max(hi, 0)
        pad = (hi - lo) * 0.08 or 1
        ticks = nice_ticks(lo - pad if lo - pad < 0 < lo or lo < 0 else max(0.0, lo - pad), hi + pad)
        y0, y1 = ticks[0], ticks[-1]
        tr = (lambda v: v)

    def X(i):
        return ml + (pw * (i + 0.5) / len(x_labels))

    def Y(v):
        v = max(v, y0) if log else v
        return mt + ph - (tr(v) - tr(y0)) / (tr(y1) - tr(y0)) * ph

    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s" class="chart">' % (W, H, html.escape(title))]
    for t in ticks:
        out.append('<line class="grid" x1="%d" x2="%d" y1="%.1f" y2="%.1f"/>' % (ml, W - mr, Y(t), Y(t)))
        out.append('<text class="tick" x="%d" y="%.1f" text-anchor="end" dy="0.32em">%s</text>' % (ml - 8, Y(t), fmt(t, 0 if abs(t) >= 10 or t == 0 else 1)))
    if zero_line and y0 < 0 < y1:
        out.append('<line class="zero" x1="%d" x2="%d" y1="%.1f" y2="%.1f"/>' % (ml, W - mr, Y(0), Y(0)))
    for i, lab in enumerate(x_labels):
        out.append('<text class="tick" x="%.1f" y="%d" text-anchor="middle">%s</text>' % (X(i), H - mb + 18, html.escape(lab)))
    out.append('<text class="axis-title" x="%d" y="%d" text-anchor="middle">%s</text>' % (ml + pw / 2, H - 6, html.escape(y_title[1])))
    out.append('<text class="axis-title" x="14" y="%d" text-anchor="middle" transform="rotate(-90 14 %d)">%s</text>' % (mt + ph / 2, mt + ph / 2, html.escape(y_title[0])))
    for s in series:
        cls = 's%d' % s['slot']
        pts = [(X(i), Y(p[0]), p) for i, p in enumerate(s['points']) if p and not math.isnan(p[0])]
        for x, y, p in pts:   # CI whiskers
            if p[1] is not None and not math.isnan(p[1]):
                out.append('<line class="ci %s" x1="%.1f" x2="%.1f" y1="%.1f" y2="%.1f"/>' % (cls, x, x, Y(p[0] - p[1]), Y(p[0] + p[1])))
        if len(pts) > 1:
            out.append('<polyline class="line %s" points="%s"/>' % (cls, ' '.join('%.1f,%.1f' % (x, y) for x, y, _ in pts)))
        for x, y, p in pts:
            tip = '%s: %s%s' % (s['name'], fmt(p[0]), '' if p[1] is None or math.isnan(p[1]) else ' +/- ' + fmt(p[1]))
            out.append('<circle class="dot %s" cx="%.1f" cy="%.1f" r="4.5"><title>%s</title></circle>' % (cls, x, y, html.escape(tip)))
            out.append('<circle class="hit" cx="%.1f" cy="%.1f" r="12"><title>%s</title></circle>' % (x, y, html.escape(tip)))
    out.append('</svg>')
    legend = ''.join('<span class="key"><span class="swatch s%d"></span>%s</span>' % (s['slot'], html.escape(s['name'])) for s in series)
    return '<figure><figcaption>%s</figcaption><div class="legend">%s</div>%s</figure>' % (html.escape(title), legend, ''.join(out))


SEQ_RAMP = ['#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab', '#184f95', '#104281', '#0d366b']


def seq_colors(n):
    if n <= 1:
        return [SEQ_RAMP[4]]
    return [SEQ_RAMP[round(i * (len(SEQ_RAMP) - 1) / (n - 1))] for i in range(n)]


def svg_timeline(title, series, x_title):
    """series: list of (name, [fps per second]); drawn light->dark in order (sequential = more load)."""
    W, H = 640, 300
    ml, mr, mt, mb = 64, 20, 16, 44
    pw, ph = W - ml - mr, H - mt - mb
    vals = [v for _, ys in series for v in ys if v > 0]
    if not vals:
        return '<p class="muted">No data for this chart.</p>'
    lo, hi = min(vals), max(vals)
    steps = log_ticks(10 ** math.floor(math.log10(lo)), 10 ** math.ceil(math.log10(hi)))
    y0 = max([t for t in steps if t <= lo] or [steps[0]])
    y1 = min([t for t in steps if t >= hi] or [steps[-1]])
    if y1 <= y0:
        y0, y1 = y0 / 10.0, y1 * 10.0
    xmax = max(len(ys) for _, ys in series)

    def X(i):
        return ml + pw * i / max(1, xmax - 1)

    def Y(v):
        v = min(max(v, y0), y1)
        return mt + ph - (math.log10(v) - math.log10(y0)) / (math.log10(y1) - math.log10(y0)) * ph

    out = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s" class="chart">' % (W, H, html.escape(title))]
    for t in log_ticks(y0, y1):
        out.append('<line class="grid" x1="%d" x2="%d" y1="%.1f" y2="%.1f"/>' % (ml, W - mr, Y(t), Y(t)))
        out.append('<text class="tick" x="%d" y="%.1f" text-anchor="end" dy="0.32em">%s</text>' % (ml - 8, Y(t), fmt(t, 0 if t >= 10 else 1)))
    for sec in range(0, xmax, 20):
        out.append('<text class="tick" x="%.1f" y="%d" text-anchor="middle">%d</text>' % (X(sec), H - mb + 18, sec))
    out.append('<text class="axis-title" x="%d" y="%d" text-anchor="middle">%s</text>' % (ml + pw / 2, H - 6, 'Seconds into the capture'))
    out.append('<text class="axis-title" x="14" y="%d" text-anchor="middle" transform="rotate(-90 14 %d)">FPS (per second, log)</text>' % (mt + ph / 2, mt + ph / 2))
    cols = seq_colors(len(series))
    for (name, ys), c in zip(series, cols):
        pts = ' '.join('%.1f,%.1f' % (X(i), Y(v)) for i, v in enumerate(ys) if v > 0)
        out.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"><title>%s</title></polyline>' % (c, pts, html.escape(name)))
    out.append('</svg>')
    legend = ''.join('<span class="key"><span class="swatch" style="background:%s"></span>%s</span>' % (c, html.escape(n)) for (n, _), c in zip(series, cols))
    return '<figure><figcaption>%s</figcaption><div class="legend">%s</div>%s</figure>' % (html.escape(title), legend, ''.join(out))


CSS = """
:root { --surface:#fcfcfb; --surface-2:#f3f2ef; --text:#0b0b0b; --text-2:#52514e; --muted:#7a7975;
  --grid:#e4e3df; --axis:#b9b8b3; --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --warn:#9a6200; color-scheme:light; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --surface:#1a1a19; --surface-2:#242423;
  --text:#f0efec; --text-2:#c3c2b7; --muted:#8f8e88; --grid:#2f2f2d; --axis:#55544f; --s1:#3987e5; --s2:#d95926;
  --s3:#199e70; --warn:#e0a640; color-scheme:dark; } }
:root[data-theme="dark"] { --surface:#1a1a19; --surface-2:#242423; --text:#f0efec; --text-2:#c3c2b7; --muted:#8f8e88;
  --grid:#2f2f2d; --axis:#55544f; --s1:#3987e5; --s2:#d95926; --s3:#199e70; --warn:#e0a640; color-scheme:dark; }
body { background:var(--surface); color:var(--text); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
  margin:0 auto; max-width:1000px; padding:24px 16px 64px; }
h1 { font-size:24px; margin:0 0 4px; } h2 { font-size:19px; margin:40px 0 8px; } h3 { font-size:16px; margin:24px 0 8px; }
p.muted, .muted { color:var(--text-2); }
.grid2, .stack { display:grid; grid-template-columns:1fr; gap:20px; }
figure { margin:0; background:var(--surface-2); border-radius:10px; padding:14px; }
figcaption { font-weight:600; margin-bottom:4px; }
.legend { display:flex; gap:16px; flex-wrap:wrap; font-size:13px; color:var(--text-2); margin-bottom:6px; }
.key { display:inline-flex; align-items:center; gap:6px; }
.swatch { width:12px; height:12px; border-radius:3px; display:inline-block; }
.swatch.s1 { background:var(--s1); } .swatch.s2 { background:var(--s2); } .swatch.s3 { background:var(--s3); }
svg.chart { width:100%; height:auto; display:block; }
.grid { stroke:var(--grid); stroke-width:1; } .zero { stroke:var(--axis); stroke-width:1.5; }
.tick { fill:var(--text-2); font-size:12px; } .axis-title { fill:var(--muted); font-size:12px; }
.line { fill:none; stroke-width:2; } .ci { stroke-width:2; opacity:.45; }
.dot { stroke:var(--surface-2); stroke-width:2; } .hit { fill:transparent; cursor:default; }
.line.s1,.ci.s1 { stroke:var(--s1); } .line.s2,.ci.s2 { stroke:var(--s2); } .line.s3,.ci.s3 { stroke:var(--s3); }
.dot.s1 { fill:var(--s1); } .dot.s2 { fill:var(--s2); } .dot.s3 { fill:var(--s3); }
.table-wrap { overflow-x:auto; }
table { border-collapse:collapse; font-size:13px; margin:8px 0; min-width:100%; }
th, td { text-align:right; padding:5px 10px; border-bottom:1px solid var(--grid); white-space:nowrap; }
th:first-child, td:first-child, th.l, td.l { text-align:left; }
th { color:var(--text-2); font-weight:600; }
.flag { color:var(--warn); }
"""


def write_csv(path, rows, fields):
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)


def level_name(mode, lv):
    return ('%dx' % lv) if mode == 'timescale' else ('%d' % lv)


def main():
    ap = argparse.ArgumentParser(description='ChickenBench analyzer v' + VERSION)
    ap.add_argument('results', nargs='?', default='Results')
    ap.add_argument('--baseline', default='JEDEC')
    ap.add_argument('--include-test', action='store_true', help='include TEST runs')
    ap.add_argument('--output-dir', help='write reports here instead of the input Results folder')
    ap.add_argument('--reference-chickens', type=float, help='reference workload for retention, independently of --baseline')
    ap.add_argument('--reference-timescale', type=float, help='reference timescale for retention')
    ap.add_argument('--stability-bootstrap', type=int, default=2000, metavar='N',
                    help='whole-sweep/run resamples (default 2000); 0 disables intervals')
    ap.add_argument('--stability-seed', type=int, default=1729)
    ap.add_argument('--stability-count-tolerance-pct', type=float, default=10.0,
                    help='explicit fallback only when run_info.txt lacks the runner tolerance')
    ap.add_argument('--include-unverified-imports', action='store_true',
                    help='analyze imported_unverified laps provisionally; never add them to legacy summaries')
    args = ap.parse_args()
    for mode, ref in [('chickens', args.reference_chickens), ('timescale', args.reference_timescale)]:
        if ref is not None and (not math.isfinite(ref) or ref < 0 or (mode == 'timescale' and ref == 0)):
            ap.error('invalid reference workload for ' + mode)
    if args.stability_bootstrap != 0 and args.stability_bootstrap < 200:
        ap.error('--stability-bootstrap must be zero or at least 200')
    if not math.isfinite(args.stability_count_tolerance_pct) or not 0 <= args.stability_count_tolerance_pct <= 100:
        ap.error('count tolerance must be between 0 and 100 percent')

    root = args.results
    if not os.path.isdir(root):
        sys.exit('Results folder not found: %s' % root)

    laps = []
    for d in sorted(os.listdir(root)):
        run = os.path.join(root, d)
        lp = os.path.join(run, 'laps.csv')
        if not os.path.isfile(lp):
            continue
        with open(lp, newline='', encoding='utf-8-sig') as fh:
            for r in csv.DictReader(fh):
                if r['label'] == 'TEST' and not args.include_test:
                    continue
                if r.get('status') == 'imported_unverified' and not args.include_unverified_imports:
                    continue
                r['_source_status'] = r.get('status', '')
                r['_source_note'] = r.get('note', '')
                r['run'] = d
                try:
                    r['level'] = int(r['level'])
                except (ValueError, TypeError, KeyError):
                    ap.error('invalid workload coordinate in %s; preserve and correct the manifest before analysis' % lp)
                fpath = os.path.join(run, *r['frames_csv'].replace('\\', '/').split('/'))
                metrics, note = {}, ''
                if r['status'] in ('ok', 'chickens_lost', 'imported_unverified') and os.path.isfile(fpath):
                    diagnostics = {}
                    ft, col = load_frametimes(fpath, diagnostics)
                    r['_frame_diagnostics'] = diagnostics
                    r['_frame_column'] = col if ft is not None else ''
                    hasher = hashlib.sha256()
                    with open(fpath, 'rb') as frame_stream:
                        for part in iter(lambda: frame_stream.read(1024 * 1024), b''):
                            hasher.update(part)
                    r['_frames_sha256'] = hasher.hexdigest()
                    if ft is None:
                        note = col
                    else:
                        metrics = lap_metrics(ft)
                        metrics['_timeline'] = timeline(ft)
                        try:
                            want = float(r.get('capture_seconds') or 0)
                        except ValueError:
                            want = 0
                        if want and metrics['seconds'] < 0.8 * want:
                            note = 'capture ended early (%.0f s of %.0f s) - CS2 hung, crashed or the lap ended' % (metrics['seconds'], want)
                            r['status'] = 'short_capture'
                        elif metrics['frames'] < MIN_FRAMES_P1:
                            note = 'too few frames for 1% low'
                        elif metrics['frames'] < MIN_FRAMES_P01:
                            note = 'too few frames for 0.1% low'
                elif r['status'] in ('ok', 'chickens_lost', 'imported_unverified'):
                    note = 'frames file missing'
                r.update(metrics)
                r['note'] = note
                laps.append(r)

    if not laps:
        sys.exit('No laps found under %s (each run folder needs a laps.csv).' % root)

    output = args.output_dir or root
    os.makedirs(output, exist_ok=True)
    # Snapshot prior analytical files before replacing them; capture inputs are untouched.
    names = ('lap_metrics.csv', 'summary.csv', 'comparison.csv', 'report.html',
             'stability_metrics.csv', 'stability_laps.csv', 'stability_metadata.json', 'stability_report.html',
             'stability_summary.csv')
    existing = [name for name in names if os.path.isfile(os.path.join(output, name))]
    backup = None
    if existing:
        stamp = datetime.now().strftime('%Y%m%dT%H%M%S%f')
        backup = os.path.join('analysis_backups', stamp)
        backup_path = os.path.join(output, backup)
        os.makedirs(backup_path)
        for name in existing:
            shutil.copy2(os.path.join(output, name), os.path.join(backup_path, name))
        print('Preserved previous analytical outputs in %s' % backup_path)
    stability_rows, stability_laps, stability_meta = build_metrics(
        laps, root, VERSION,
        references={'chickens': args.reference_chickens, 'timescale': args.reference_timescale},
        bootstrap_samples=args.stability_bootstrap, seed=args.stability_seed,
        fallback_count_tolerance=args.stability_count_tolerance_pct)
    stability_meta['previous_output_backup'] = backup
    stability_meta['previous_report_backup'] = backup if 'report.html' in existing else None
    write_outputs(output, stability_rows, stability_laps, stability_meta)

    lap_fields = ['run', 'label', 'mode', 'level', 'pass', 'timescale', 'chickens_expected', 'chickens_found',
                  'status', 'note', 'frames', 'seconds', 'avg_fps', 'p1_fps', 'p01_fps', 'ft_p50_ms', 'ft_p90_ms',
                  'ft_p99_ms', 'ft_p999_ms', 'ft_max_ms', 'ft_sd_ms', 'cov_pct']
    write_csv(os.path.join(output, 'lap_metrics.csv'), laps, lap_fields)

    # Aggregate usable laps
    groups = {}
    for r in laps:
        if r['status'] not in USABLE_STATUS or 'avg_fps' not in r:
            continue
        groups.setdefault((r['mode'], r['label'], r['level']), []).append(r)

    summary = []
    agg = {}
    for (mode, label, lv), rs in sorted(groups.items()):
        a = {'mode': mode, 'label': label, 'level': lv, 'laps': len(rs),
             'min_frames': min(x['frames'] for x in rs)}
        for m in ('avg_fps', 'p1_fps', 'p01_fps', 'ft_p50_ms', 'ft_p99_ms', 'ft_p999_ms', 'cov_pct'):
            s = summarize([x[m] for x in rs])
            agg[(mode, label, lv, m)] = s
            a[m + '_mean'], a[m + '_sd'], a[m + '_ci95'] = s['mean'], s['sd'], s['ci95']
        summary.append(a)
    sum_fields = ['mode', 'label', 'level', 'laps', 'min_frames'] + [m + k for m in ('avg_fps', 'p1_fps', 'p01_fps', 'ft_p50_ms', 'ft_p99_ms', 'ft_p999_ms', 'cov_pct') for k in ('_mean', '_sd', '_ci95')]
    write_csv(os.path.join(output, 'summary.csv'), summary, sum_fields)

    comparison = []
    modes = sorted({k[0] for k in groups})
    for mode in modes:
        labels = sorted({k[1] for k in groups if k[0] == mode})
        levels = sorted({k[2] for k in groups if k[0] == mode})
        if args.baseline not in labels:
            continue
        for label in labels:
            if label == args.baseline:
                continue
            for lv in levels:
                row = {'mode': mode, 'label': label, 'baseline': args.baseline, 'level': lv}
                ok = False
                for m in ('avg_fps', 'p1_fps', 'p01_fps'):
                    t, b = agg.get((mode, label, lv, m)), agg.get((mode, args.baseline, lv, m))
                    g = gap(t, b) if t and b else None
                    if g:
                        ok = True
                        row[m + '_gap_pct'], row[m + '_gap_ci95'] = g['gap_pct'], g['ci95_pct']
                if ok:
                    comparison.append(row)
    cmp_fields = ['mode', 'label', 'baseline', 'level'] + [m + k for m in ('avg_fps', 'p1_fps', 'p01_fps') for k in ('_gap_pct', '_gap_ci95')]
    write_csv(os.path.join(output, 'comparison.csv'), comparison, cmp_fields)

    # ------------------------------------------------------------ HTML
    H = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
         '<title>ChickenBench Report</title><style>%s</style></head><body>' % CSS,
         '<h1>ChickenBench report</h1>',
         '<p class="muted">Generated %s by cb_analyze.py v%s. Baseline: <b>%s</b>. Averages are frames / time; '
         '1%% low and 0.1%% low are 1000 / 99th and 99.9th percentile frame time. Whiskers are 95%% confidence intervals across passes.</p>'
         % (datetime.now().strftime('%Y-%m-%d %H:%M'), VERSION, html.escape(args.baseline))]

    H.append('<p><a href="#stability">Performance retention and stability measures</a> | '
             '<a href="stability_report.html">Standalone analysis report</a></p>')

    for mode in modes:
        labels = sorted({k[1] for k in groups if k[0] == mode})
        if args.baseline in labels:   # baseline first so it always gets slot 1
            labels.remove(args.baseline)
            labels.insert(0, args.baseline)
        labels = labels[:3]
        levels = sorted({k[2] for k in groups if k[0] == mode})
        xl = [level_name(mode, lv) for lv in levels]
        x_title = 'Timescale' if mode == 'timescale' else 'Chickens on the route'
        H.append('<h2>%s sweep</h2>' % ('Timescale' if mode == 'timescale' else 'Chicken'))

        cmp_rows = [c for c in comparison if c['mode'] == mode]
        if cmp_rows:
            H.append('<h3>Gap vs %s (the main result)</h3><div class="grid2">' % html.escape(args.baseline))
            for label in [l for l in labels if l != args.baseline]:
                ser = []
                for slot, (m, nm) in enumerate((('avg_fps', 'Average FPS'), ('p1_fps', '1% low')), start=1):
                    pts = []
                    for lv in levels:
                        c = next((c for c in cmp_rows if c['label'] == label and c['level'] == lv), None)
                        pts.append((c[m + '_gap_pct'], c[m + '_gap_ci95']) if c and (m + '_gap_pct') in c else None)
                    ser.append({'name': nm, 'slot': slot, 'points': pts})
                H.append(svg_chart('%s vs %s' % (label, args.baseline), xl, ser, ('Difference (%)', x_title), zero_line=True))
            H.append('</div>')

        H.append('<h3>Absolute results (log scale)</h3><div class="stack">')
        for m, nm in (('avg_fps', 'Average FPS'), ('p1_fps', '1% low FPS')):
            ser = []
            for slot, label in enumerate(labels, start=1):
                pts = []
                for lv in levels:
                    s = agg.get((mode, label, lv, m))
                    pts.append((s['mean'], s['ci95']) if s else None)
                ser.append({'name': label, 'slot': slot, 'points': pts})
            H.append(svg_chart(nm, xl, ser, ('FPS', x_title), include_zero=False, log=True))
        H.append('</div>')

        H.append('<h3>Frame-time spread inside each lap (log scale)</h3>'
                 '<p class="muted">Median, 99th and 99.9th percentile frame time. The gap between the lines is the '
                 'within-lap variance; it widening with load means the slow frames grow faster than the typical frame.</p><div class="stack">')
        for label in labels:
            ser = []
            for slot, (m, nm) in enumerate((('ft_p50_ms', 'Median frame time'), ('ft_p99_ms', '99th percentile'), ('ft_p999_ms', '99.9th percentile')), start=1):
                pts = []
                for lv in levels:
                    s = agg.get((mode, label, lv, m))
                    pts.append((s['mean'], s['ci95']) if s else None)
                ser.append({'name': nm, 'slot': slot, 'points': pts})
            H.append(svg_chart('%s: frame time percentiles' % label, xl, ser, ('Frame time (ms)', x_title), include_zero=False, log=True))
            # per-second timeline, first pass of this label
            tl = []
            for lv in levels:
                lap = next((x for x in laps if x['mode'] == mode and x['label'] == label and x['level'] == lv
                            and x['status'] in USABLE_STATUS and x.get('_timeline')), None)
                if lap:
                    tl.append(('%s (pass %s)' % (level_name(mode, lv), lap['pass']), lap['_timeline']))
            if tl:
                H.append(svg_timeline('%s: FPS through the lap, one line per level (darker = more load)' % label, tl, x_title))
        H.append('</div>')

        H.append('<h3>Table</h3><div class="table-wrap"><table><tr><th>Config</th><th>Level</th><th>Laps</th><th>Min frames</th>'
                 '<th>Avg FPS</th><th>&plusmn;95%</th><th>1% low</th><th>&plusmn;95%</th><th>0.1% low</th><th>&plusmn;95%</th>'
                 '<th>p50 ms</th><th>p99 ms</th><th>p99.9 ms</th><th>CoV %</th></tr>')
        for a in [s for s in summary if s['mode'] == mode]:
            flag = ' <span class="flag">(few frames)</span>' if a['min_frames'] < MIN_FRAMES_P01 else ''
            H.append('<tr><td>%s</td><td>%s</td><td>%d</td><td>%s%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                html.escape(a['label']), level_name(mode, a['level']), a['laps'], fmt(a['min_frames'], 0), flag,
                fmt(a['avg_fps_mean']), fmt(a['avg_fps_ci95']), fmt(a['p1_fps_mean']), fmt(a['p1_fps_ci95']),
                fmt(a['p01_fps_mean']), fmt(a['p01_fps_ci95']),
                fmt(a['ft_p50_ms_mean'], 2), fmt(a['ft_p99_ms_mean'], 2), fmt(a['ft_p999_ms_mean'], 2), fmt(a['cov_pct_mean'], 1)))
        H.append('</table></div>')
        if cmp_rows:
            H.append('<div class="table-wrap"><table><tr><th>Config</th><th>Level</th><th>Avg gap %</th><th>&plusmn;95%</th>'
                     '<th>1% low gap %</th><th>&plusmn;95%</th><th>0.1% low gap %</th><th>&plusmn;95%</th></tr>')
            for c in cmp_rows:
                H.append('<tr><td>%s</td><td>%s</td>%s</tr>' % (html.escape(c['label']), level_name(mode, c['level']), ''.join(
                    '<td>%s</td><td>%s</td>' % (fmt(c.get(m + '_gap_pct'), 2), fmt(c.get(m + '_gap_ci95'), 2)) for m in ('avg_fps', 'p1_fps', 'p01_fps'))))
            H.append('</table></div>')

    bad = [r for r in laps if r['status'] not in USABLE_STATUS or r['note']]
    if bad:
        H.append('<h2>Excluded or flagged laps</h2><div class="table-wrap"><table><tr><th>Run</th><th>Config</th><th>Level</th><th>Pass</th>'
                 '<th class="l">Status</th><th class="l">Note</th><th>Chickens found</th></tr>')
        for r in bad:
            H.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class="l">%s</td><td class="l">%s</td><td>%s</td></tr>' % (
                html.escape(r['run']), html.escape(r['label']), level_name(r['mode'], r['level']), html.escape(r['pass']),
                html.escape(r['status']), html.escape(r['note']), html.escape(str(r.get('chickens_found', '')))))
        H.append('</table></div>')
    H.append(render_stability(stability_rows, stability_meta))
    H.append('</body></html>')
    write_standalone(os.path.join(output, 'stability_report.html'), stability_rows, stability_meta)
    with open(os.path.join(output, 'report.html'), 'w', encoding='utf-8', newline='\r\n') as fh:
        fh.write('\n'.join(H))

    print('ChickenBench analyzer v%s: %d laps read, %d usable groups.' % (VERSION, len(laps), len(summary)))
    print('Wrote %s' % os.path.join(output, 'report.html'))


if __name__ == '__main__':
    main()
