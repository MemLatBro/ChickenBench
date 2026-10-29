"""Self-contained HTML/SVG presentation. This module never calculates formulas."""
import base64
import csv
import html
import io
import json
import math
from pathlib import Path

from cb_stability import FIELDS, SUMMARY_FIELDS, METRICS, write_csv
from cb_formulas import finite

COLORS = ['#176ac7', '#cc4d16', '#16845e', '#8b52bd', '#ad275d', '#987000',
          '#008594', '#755a43', '#525b9c', '#517418']
CSS = """
.stability { color:#172b42; background:#f6f8fc; padding:28px; margin:40px 0 0; border:1px solid #d6deeb; border-radius:16px;
  font:14px/1.6 system-ui,-apple-system,'Segoe UI',sans-serif; color-scheme:light }
.stability * { box-sizing:border-box }
.stability h2 { font-size:26px; line-height:1.25; margin:0 0 12px; color:#102a47 }
.stability h3 { font-size:21px; margin:36px 0 12px; color:#102a47 }
.stability h4 { margin:0 0 8px; font-size:16px; color:#15314f }
.stability p { margin:8px 0 12px }
.stability .eyebrow { text-transform:uppercase; letter-spacing:.12em; font-size:11px; font-weight:700; color:#537192 }
.stability .intro { font-size:15px; max-width:850px }
.stability .callout { background:#e8eff9; border-left:4px solid #176ac7; padding:12px 16px; border-radius:0 8px 8px 0 }
.stability .notice { background:#fff5df; border-left-color:#ba7900 }
.stability .stats { display:flex; flex-wrap:wrap; gap:12px; margin:20px 0 }
.stability .stat { background:white; border:1px solid #d6deeb; border-radius:9px; padding:12px 18px; min-width:150px }
.stability .stat strong { display:block; font-size:24px; line-height:1.3; color:#102a47 }
.stability .stat span { font-size:12px; color:#52667e }
.stability a { color:#155eb2 }
.stability .links { display:flex; gap:10px; flex-wrap:wrap; margin:16px 0 }
.stability .links a { display:inline-block; background:#fff; border:1px solid #c2d1e4; border-radius:6px; padding:6px 12px; text-decoration:none; font-weight:600; font-size:12px }
.stability .controls { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin:18px 0 }
.stability select { padding:9px 12px; font:inherit; max-width:100%; background:#fff; color:#172b42; border:1px solid #a8bad0; border-radius:6px }
.stability .plots { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px }
.stability figure { min-width:0; margin:0; background:#fff; padding:14px 12px 10px; border:1px solid #d6deeb; border-radius:10px }
.stability figcaption { font-weight:700; font-size:14px; margin-bottom:4px }
.stability .plot-note { font-size:11px; color:#52667e; margin:0 0 5px }
.stability .legend { display:flex; flex-wrap:wrap; gap:6px 14px; font-size:11px; margin:4px 0 }
.stability .key { display:inline-flex; gap:5px; align-items:center }
.stability .swatch { width:10px; height:10px; display:inline-block; border-radius:2px }
.stability svg { width:100%; height:auto; display:block }
.stability .gridline { stroke:#e5eaf1; stroke-width:1 }
.stability .refline { stroke:#8195ac; stroke-width:1; stroke-dasharray:5 4 }
.stability .tick { font-size:12px; fill:#536a83 }
.stability .axis-label { font-size:12px; fill:#385470 }
.stability .none { padding:45px 10px; color:#677b91; text-align:center }
.stability .scroll { overflow:auto; max-height:540px; border:1px solid #d6deeb; border-radius:6px; background:#fff }
.stability table { border-collapse:collapse; min-width:100%; font-size:12px; margin:0 }
.stability th,.stability td { padding:8px 10px; border-bottom:1px solid #e5eaf1; white-space:nowrap; text-align:right; vertical-align:top }
.stability th { position:sticky; top:0; background:#eaf0f8; color:#2a4665; font-weight:600 }
.stability th:first-child,.stability td:first-child { text-align:left }
.stability td.wrap { white-space:normal; min-width:230px; text-align:left }
.stability .small { color:#52667e; font-size:12px }
.stability .pill { border-radius:12px; padding:2px 8px; background:#e8eff9; color:#305579; font-size:11px }
.stability details { margin-top:16px }
.stability summary { cursor:pointer; font-weight:600 }
.stability .metric-panel[hidden] { display:none }
.stability .score-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:14px 0 22px }
.stability .score-card { background:white; border:1px solid #c9d8ec; border-top:4px solid #176ac7; border-radius:10px; padding:18px; min-width:0 }
.stability .score-card h4 { font-size:16px; margin:0 0 10px }
.stability .score-card .score { color:#102a47; font-size:36px; font-weight:750; line-height:1.1; margin:8px 0 4px }
.stability .score-card .native { font-size:17px; font-weight:650; color:#2c4e72; margin-top:14px }
.stability .score-card .small { margin:4px 0 }
.stability .score-group h3 { margin:24px 0 4px }
@media(max-width:760px) { .stability .score-grid { grid-template-columns:1fr } }
@media(max-width:760px) { .stability { padding:18px 12px } .stability .plots { grid-template-columns:1fr } }
@media print { .stability { padding:8px; margin:20px 0; border:0 } .stability .plots { grid-template-columns:1fr }
 .stability figure { break-inside:avoid } .stability .links,.stability .controls { display:none }
 .stability .scroll { max-height:none; overflow:visible } }
"""


def escape(value):
    return html.escape(str(value), quote=True)


def number(value, decimals=2):
    if not finite(value):
        return '\u2014'
    if value == 0:
        return '0'
    if abs(value) < 0.01 or abs(value) >= 1e6:
        return ('%.*g' % (3, value))
    return ('%.*f' % (decimals, value)).rstrip('0').rstrip('.')


def _ticks(lo, hi, count=5):
    if hi <= lo:
        lo, hi = lo - 1, hi + 1
    raw = (hi - lo) / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next(x * mag for x in (1, 2, 2.5, 5, 10) if x * mag >= raw)
    start, end = math.floor(lo / step) * step, math.ceil(hi / step) * step
    return [start + i * step for i in range(round((end - start) / step) + 1)]


def chart(rows, labels, value_key, title, y_label, x_label,
          low_key=None, high_key=None, reference=None, slope=False, scale=1.0):
    """Numeric x coordinates, asymmetric error bars, and explicit gaps at missing levels."""
    w, h = 720, 330
    ml, mr, mt, mb = 72, 22, 20, 58
    pw, ph = w - ml - mr, h - mt - mb
    all_levels = sorted({r['workload_level'] for r in rows})
    lookup = {(r['configuration_id'], r['workload_level']): r for r in rows}
    points = {}
    ys, xs = [], []
    for label in labels:
        series = []
        for load in all_levels:
            row = lookup.get((label, load))
            value = row.get(value_key) if row else None
            if row is None or not finite(value):
                series.append(None)
                continue
            x = (row['previous_workload'] + load) / 2 if slope else load
            lo = row.get(low_key) if low_key else None
            hi = row.get(high_key) if high_key else None
            value *= scale
            lo = lo * scale if finite(lo) else None
            hi = hi * scale if finite(hi) else None
            ys.extend([value] + ([lo, hi] if lo is not None and hi is not None else []))
            xs.append(x)
            series.append((x, value, lo, hi, row))
        points[label] = series
    legend = ''.join('<span class="key"><i class="swatch" style="background:%s"></i>%s</span>'
                     % (COLORS[i % len(COLORS)], escape(label)) for i, label in enumerate(labels))
    out = ['<figure><figcaption>%s</figcaption><div class="legend">%s</div>' % (escape(title), legend)]
    if not ys:
        return ''.join(out) + '<p class="none">No eligible values. See the validity table.</p></figure>'
    if reference is not None:
        ys.append(reference)
    ylo, yhi = min(ys), max(ys)
    span = yhi - ylo
    # Do not magnify floating-point/serialization noise into a visibly unstable curve.
    near_flat = span <= 1e-6 * max(abs(ylo), abs(yhi), 1.0)
    pad = max(.05 * abs(yhi), .1) if near_flat else span * .08
    ticks = _ticks(ylo - pad, yhi + pad)
    y0, y1 = ticks[0], ticks[-1]
    domain = [(a + b) / 2 for a, b in zip(all_levels, all_levels[1:])] if slope else all_levels
    x0, x1 = min(domain), max(domain)
    if x0 == x1:
        x0, x1 = x0 - .5, x1 + .5

    def X(x):
        return ml + pw * (x - x0) / (x1 - x0)

    def Y(y):
        return mt + ph * (1 - (y - y0) / (y1 - y0))

    out.append('<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (w, h, escape(title)))
    tick_step = ticks[1] - ticks[0] if len(ticks) > 1 else 1
    tick_decimals = min(8, max(2, 1 - math.floor(math.log10(abs(tick_step)))))
    for tick in ticks:
        out.append('<line class="gridline" x1="%d" x2="%d" y1="%.2f" y2="%.2f"/>' % (ml, w - mr, Y(tick), Y(tick)))
        out.append('<text class="tick" x="%d" y="%.2f" text-anchor="end" dy=".32em">%s</text>' % (ml - 8, Y(tick), number(tick, tick_decimals)))
    xticks = sorted(set(domain))
    if len(xticks) > 12:
        xticks = [xticks[round(i * (len(xticks) - 1) / 8)] for i in range(9)]
    for tick in xticks:
        out.append('<text class="tick" x="%.2f" y="%d" text-anchor="middle">%s</text>' % (X(tick), h - mb + 20, number(tick)))
    out.append('<text class="axis-label" x="%d" y="%d" text-anchor="middle">%s</text>' % (ml + pw / 2, h - 6, escape(x_label)))
    out.append('<text class="axis-label" x="16" y="%d" text-anchor="middle" transform="rotate(-90 16 %d)">%s</text>' % (mt + ph / 2, mt + ph / 2, escape(y_label)))
    if reference is not None:
        out.append('<line class="refline" x1="%d" x2="%d" y1="%.2f" y2="%.2f"/>' % (ml, w - mr, Y(reference), Y(reference)))
    for i, label in enumerate(labels):
        color = COLORS[i % len(COLORS)]
        segments, current = [], []
        for point in points[label] + [None]:
            if point is None:
                if current:
                    segments.append(current)
                    current = []
            else:
                current.append(point)
        for segment in segments:
            if len(segment) > 1:
                xy = ' '.join('%.2f,%.2f' % (X(p[0]), Y(p[1])) for p in segment)
                out.append('<polyline fill="none" stroke="%s" stroke-width="2.5" points="%s"/>' % (color, xy))
        for p in points[label]:
            if p is None:
                continue
            x, value, lo, hi, row = p
            tip = '%s; load %s; %s %s; %d laps; %s' % (label, number(row['workload_level']),
                  title, number(value), row['sample_count_laps'], row['validity'])
            if slope:
                tip += '; interval %s to %s' % (number(row['previous_workload']), number(row['workload_level']))
            if lo is not None and hi is not None:
                tip += '; interval [%s, %s]' % (number(lo), number(hi))
                out.append('<path stroke="%s" opacity=".6" stroke-width="1.8" fill="none" d="M %.2f %.2f V %.2f M %.2f %.2f H %.2f M %.2f %.2f H %.2f"/>'
                           % (color, X(x), Y(lo), Y(hi), X(x)-4, Y(lo), X(x)+4, X(x)-4, Y(hi), X(x)+4))
            if row['flags']:
                tip += '; ' + row['flags']
            validity = row['slope_validity'] if slope else row['validity']
            fill = 'white' if validity.startswith('provisional') else color
            out.append('<circle cx="%.2f" cy="%.2f" r="4" fill="%s" stroke="%s" stroke-width="2"><title>%s</title></circle>'
                       % (X(x), Y(value), fill, color, escape(tip)))
    out.append('</svg></figure>')
    return ''.join(out)


def _csv_uri(rows, fields=FIELDS):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows({k: r.get(k) for k in fields} for r in rows)
    return 'data:text/csv;charset=utf-8;base64,' + base64.b64encode(stream.getvalue().encode('utf-8')).decode('ascii')


def render_aggregate_summary(summaries):
    """Display precomputed single-metric scores prominently, before the curves."""
    if not summaries:
        return ''
    out = ['<div id="metric-summary"><h3>One value per metric</h3>',
           '<p class="intro">The <b>retention score</b> is average retained performance across the full workload range. '
           'A score of 90% means this metric retained 90% of its reference performance on average across that range. '
           'Each metric also has an aggregate value in its original units.</p>',
           '<p class="small">Scores use the area under each metric\u2019s retention curve divided by the workload span, '
           'with straight lines between adjacent measured levels. Actual workload spacing determines the weights. '
           'Compare scores over the same range, coordinate and reference. Values above 100% remain possible.</p>']
    for mode, label in sorted({(r['mode'], r['configuration_id']) for r in summaries}):
        rs = [r for r in summaries if r['mode'] == mode and r['configuration_id'] == label]
        first = rs[0]
        unit = 'intended chickens' if mode == 'chickens' else 'host_timescale'
        out.append('<div class="score-group"><h3>%s <span class="pill">%s sweep</span></h3>'
                   '<p class="small">Range %s\u2013%s %s &middot; reference load %s</p>' %
                   (escape(label), escape('Chicken count' if mode == 'chickens' else 'Timescale'),
                    number(first['workload_start']), number(first['workload_end']), unit,
                    number(first['baseline_workload'])))
        if any('unverified' in r['validity'] for r in rs):
            out.append('<p class="callout notice"><b>Provisional scores.</b> Original workload or capture metadata is incomplete.</p>')
        out.append('<div class="score-grid">')
        for metric, title in [('avg_fps','Average FPS'), ('p1_fps','1% low FPS'), ('p01_fps','0.1% low FPS')]:
            row = next((r for r in rs if r['metric_name'] == metric), None)
            if row is None:
                continue
            score = number(row['retention_score_pct'])
            suffix = '%' if row['retention_score_pct'] is not None else ''
            out.append('<article class="score-card" data-summary-metric="%s"><h4>%s</h4>'
                       '<div class="score">%s%s</div><div class="small">workload-average retention score</div>'
                       '<div class="native">%s FPS</div><div class="small">aggregate across workload</div>' %
                       (metric, escape(title), score, suffix, number(row['workload_average'])))
            if row['retention_score_pct_ci_low'] is not None:
                out.append('<p class="small">95%% interval: %s\u2013%s%% (%s)</p>' %
                           (number(row['retention_score_pct_ci_low']), number(row['retention_score_pct_ci_high']),
                            'exploratory' if row['retention_score_pct_ci_status'] == 'exploratory_small_n' else 'approximate'))
            elif row['retention_score_pct'] is not None:
                out.append('<p class="small">Point estimate; no inferred retention interval.</p>')
            rate = row['mean_degradation_rate']
            multiplier, rate_unit = (100, '100 chickens') if mode == 'chickens' else (1, 'timescale unit')
            out.append('<p class="small">End-to-end loss rate: %s pp / %s</p>' %
                       (number(rate*multiplier if rate is not None else None), rate_unit))
            if row['summary_status'] != 'complete':
                reason = {'insufficient_workload_span':'At least two distinct workload levels are required.',
                          'missing_or_invalid_workload_levels':'Full-range aggregate unavailable: a scheduled level has no eligible measurement.',
                          'missing_or_invalid_baseline':'Retention score unavailable: the reference measurement is missing or invalid.'}
                out.append('<p class="small">%s Coverage: %s%%.</p>' %
                           (reason.get(row['summary_status'], escape(row['summary_status'])), number(row['workload_coverage_pct'])))
            out.append('</article>')
        out.append('</div></div>')
    out.append('<div class="links"><a download="stability_summary.csv" href="%s">Download aggregate scores CSV</a></div>'
               % _csv_uri(summaries, SUMMARY_FIELDS))
    out.append('<details><summary>Aggregate values for every metric, intervals &amp; validity</summary>'
               '<div class="scroll"><table><thead><tr>')
    headers = ['Configuration','Sweep','Metric','Native aggregate','Units','Retention score %',
               'Mean loss pp','End retention %','End-to-end loss pp/unit','Coverage %','Status / validity']
    out.extend('<th>%s</th>' % escape(s) for s in headers)
    out.append('</tr></thead><tbody>')
    for r in summaries:
        native = number(r['workload_average'])
        if r['workload_average_ci_low'] is not None:
            native += ' [%s, %s]' % (number(r['workload_average_ci_low']), number(r['workload_average_ci_high']))
        score = number(r['retention_score_pct'])
        if r['retention_score_pct_ci_low'] is not None:
            score += ' [%s, %s]' % (number(r['retention_score_pct_ci_low']), number(r['retention_score_pct_ci_high']))
        cells = [r['configuration_id'],r['mode'],r['metric_label'],native,r['metric_units'],score,
                 number(r['mean_degradation_pct']), number(r['endpoint_retention_pct']),
                 number(r['mean_degradation_rate']),number(r['workload_coverage_pct']),
                 r['summary_status']+'; '+r['validity']+'; '+r['retention_score_pct_ci_status']]
        out.append('<tr>' + ''.join('<td>%s</td>' % escape(v) for v in cells) + '</tr>')
    out.append('</tbody></table></div></details><p class="small">FPS lows are reciprocal frame-time percentiles: '
               '1% low = 1000 / p99(ms); 0.1% low = 1000 / p99.9(ms). A 0.01% low would require p99.99. '
               'The aggregate averages each load\u2019s low-FPS statistic; it is not a percentile of pooled frames. '
               'An end-to-end rate describes net loss and can hide intermediate rises and falls; the curves below retain that detail. '
               'Single-point runs and incomplete curves have no full-range score. Native SD/CV aggregates retain their own units.</p></div>')
    return '\n'.join(out)


def render_stability(rows, metadata):
    out = ['<section class="stability" id="stability"><style>%s</style>' % CSS,
           '<p class="eyebrow">Loaded performance / formula %s</p>' % escape(metadata['formula_version']),
           '<h2>Performance retention &amp; stability measures</h2>',
           '<p class="intro">Each metric has its own aggregate value and workload-average retention score. '
           'Each configuration is normalized to its own first workload level unless an explicit reference is selected. '
           'Native measurements, loss under load and frame-time dispersion remain available below.</p>']
    modes = sorted({r['mode'] for r in rows})
    configs = {r['configuration_id'] for r in rows}
    laps = {lap for r in rows for lap in json.loads(r['source_lap_ids'])}
    out.append(render_aggregate_summary(metadata.get('aggregate_metrics', [])))
    out.append('<div class="stats"><div class="stat"><strong>%d</strong><span>configurations</span></div>'
               '<div class="stat"><strong>%d</strong><span>recorded laps</span></div>'
               '<div class="stat"><strong>%s</strong><span>formula version</span></div></div>'
               % (len(configs), len(laps), escape(metadata['formula_version'])))
    out.append('<div class="callout"><b>Reading the curves.</b> Retention is P/P<sub>0</sub> for FPS and T<sub>0</sub>/T for frame time. '
               'Degradation is 100(1 &minus; retention); negative degradation means improvement. Local degradation rate is the '
               'change in degradation divided by the actual load interval. Its points sit at interval midpoints. '
               'A slope near zero can occur at either high or low absolute performance.</div>')
    unverified = any('unverified' in r['validity'] for r in rows)
    if unverified:
        out.append('<p class="callout notice"><b>Provisional measurements are present.</b> Hollow points have missing workload or capture metadata '
                   '(including missing reference metadata). These curves describe the supplied captures at intended load coordinates; '
                   'they do not verify true workload integrity or complete captures. Inspect the validity table and lap audit before comparing hardware.</p>')
    out.append('<p class="small">Native per-lap measurements are summarized as equal-lap arithmetic means. Ratios and slopes are calculated afterward. '
               'Whiskers in this section are approximate 95% cluster-bootstrap intervals, not frame-level sampling errors. '
               'One run resamples whole sweeps; multiple runs resample whole runs. Fewer than 3 independent units: no inferred interval. '
               '3&ndash;9 units: exploratory interval. Identical cluster support is required across dependent loads. '
               'The reference retention of 100% is an algebraic identity, not a claim of zero measurement uncertainty.</p>')
    out.append('<div class="links"><a download="stability_metrics.csv" href="%s">Download analytical CSV</a>' % _csv_uri(rows))
    out.append('<a href="stability_laps.csv">Per-lap audit CSV</a><a href="stability_metadata.json">Analysis metadata</a>')
    if metadata.get('previous_report_backup'):
        previous = str(metadata['previous_report_backup']).replace('\\', '/')
        out.append('<a href="%s/report.html">Preserved previous report</a>' % escape(previous))
    out.append('</div>')
    for mode_index, mode in enumerate(modes):
        mr = [r for r in rows if r['mode'] == mode]
        labels = sorted({r['configuration_id'] for r in mr})
        x_label = 'Intended chicken count' if mode == 'chickens' else 'Requested host_timescale multiplier'
        out.append('<h3>%s sweep</h3>' % ('Chicken count' if mode == 'chickens' else 'Timescale'))
        out.append('<div class="scroll"><table><thead><tr><th>Configuration</th><th>Reference load</th>'
                   '<th>Reference average FPS</th><th>Reference laps</th><th>Reference selection</th></tr></thead><tbody>')
        for label in labels:
            row = next(r for r in mr if r['configuration_id'] == label and r['metric_name'] == 'avg_fps')
            out.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' %
                       tuple(escape(v) for v in (label, number(row['baseline_workload']), number(row['baseline_value']),
                                                 row['baseline_sample_count_laps'], row['baseline_selection'])))
        out.append('</tbody></table></div>')
        if len({r['baseline_workload'] for r in mr}) > 1:
            out.append('<p class="callout notice">Configurations have different reference loads. Retention uses each configuration\u2019s own reference; '
                       'these percentages do not describe a common starting workload.</p>')
        if mode == 'timescale':
            out.append('<p class="small">Timescale changes simulation speed and capture duration. It is a native workload coordinate, '
                       'not a chicken-count equivalent or a verified amount of completed simulation work.</p>')
        out.append('<div class="controls"><label for="metric-%d"><b>Inspect metric</b></label>'
                   '<select id="metric-%d" data-metric-control="mode-%d">' % (mode_index, mode_index, mode_index))
        for key, metric in METRICS.items():
            out.append('<option value="%s">%s (%s)</option>' % (key, escape(metric[0]), metric[1]))
        out.append('</select></div><div id="mode-%d">' % mode_index)
        for key, metric in METRICS.items():
            selected = [r for r in mr if r['metric_name'] == key]
            hidden = '' if key == 'avg_fps' else ' hidden'
            out.append('<div class="metric-panel" data-metric="%s"%s><h4>%s</h4><div class="plots">' % (key, hidden, escape(metric[0])))
            out.append(chart(selected, labels, 'measured_value', 'Absolute native measurements (lap means)',
                             metric[1], x_label, 'value_ci_low', 'value_ci_high'))
            if metric[3] != 'temporal_dispersion':
                # Retention bounds in the schema are ratios; render percentage equivalents.
                out.append(chart([dict(r, retention_ci_low=(r['retention_ci_low'] * 100 if r['retention_ci_low'] is not None else None),
                                         retention_ci_high=(r['retention_ci_high'] * 100 if r['retention_ci_high'] is not None else None)) for r in selected],
                                labels, 'retention_pct', 'Calculated performance retention', 'Retention (%)', x_label,
                                'retention_ci_low', 'retention_ci_high', reference=100))
                out.append(chart(selected, labels, 'degradation_pct', 'Calculated relative degradation', 'Lost retention (percentage points)', x_label,
                                 'degradation_ci_low', 'degradation_ci_high', reference=0))
                out.append(chart(selected, labels, 'local_degradation_rate', 'Calculated local degradation rate',
                                 'Percentage points / %s' % ('chicken' if mode == 'chickens' else 'timescale unit'), x_label,
                                 'rate_ci_low', 'rate_ci_high', reference=0, slope=True))
            out.append(chart(selected, labels, 'between_lap_cv_pct', 'Between-lap variation (descriptive)',
                             'CV of repeated lap values (%)', x_label))
            out.append('</div><p class="small">Higher retention indicates less loss relative to this metric\u2019s reference; it does not imply higher '
                       'absolute speed. A 1% low measures a distribution tail and is not a complete measure of temporal consistency. '
                       'Lines stop at missing or invalid levels. See the table for sample counts and uncertainty availability.</p></div>')
        out.append('</div><h4>Within-lap frame-time dispersion</h4><div class="plots">')
        for key, title, unit in [('cov_pct','Mean within-lap frame-time CV','Frame-time CV (%)'),
                                 ('ft_sd_ms','Mean within-lap frame-time standard deviation','Frame-time SD (ms)')]:
            selected = [r for r in mr if r['metric_name'] == key]
            out.append(chart(selected, labels, 'measured_value', title, unit, x_label, 'value_ci_low', 'value_ci_high'))
        out.append('</div><p class="small">Within-lap SD and CV describe frame-time distribution spread. They are not chronological '
                   'predictability measures. Between-lap variation above describes repeatability of the selected lap statistic; '
                   'its SD is distinct from uncertainty in the mean.</p>')
        out.append('<details><summary>Numerical results, sample counts &amp; validity (all metrics)</summary><div class="scroll"><table><thead><tr>')
        headers = ['Config', 'Metric', 'Load', 'Native mean', 'Retained %', 'Degraded pp', 'Rate pp/unit',
                   'Laps used / recorded', 'Value interval', 'Retention interval (ratio)', 'Slope interval', 'Validity & flags']
        out.extend('<th>%s</th>' % escape(hd) for hd in headers)
        out.append('</tr></thead><tbody>')
        for row in mr:
            def interval(lo, hi, status):
                return ('[%s, %s] ' % (number(row[lo]), number(row[hi])) if row[lo] is not None else '') + row[status]
            cells = [row['configuration_id'], row['metric_name'], number(row['workload_level']), number(row['measured_value']),
                     number(row['retention_pct']), number(row['degradation_pct']), number(row['local_degradation_rate']),
                     '%s / %s' % (row['sample_count_laps'], row['attempted_laps']),
                     interval('value_ci_low','value_ci_high','value_ci_status'),
                     interval('retention_ci_low','retention_ci_high','retention_ci_status'),
                     interval('rate_ci_low','rate_ci_high','rate_ci_status'), row['validity'] + '; ' + row['flags']]
            out.append('<tr>' + ''.join('<td%s>%s</td>' % (' class="wrap"' if j >= 8 else '', escape(v)) for j, v in enumerate(cells)) + '</tr>')
        out.append('</tbody></table></div></details>')
    out.append('<details><summary>Definitions &amp; limits</summary><p>Reciprocal retention for lower-is-better metrics expresses '
               'throughput-equivalent performance loss. A latency increase of 100% corresponds to 50% retention, not zero retention. '
               'It is not the same as percentage latency increase. Negative degradation and retention above 100% are preserved.</p>'
               '<p>Aggregate scores use uniform weighting in the native workload coordinate and trapezoidal integration. '
               'Different metrics and sweep modes are reported separately. '
               'Slopes depend on native workload units, baseline, and interval size; they are observed secants, not a continuous derivative. '
               'Small adjacent differences can be noisy. Confidence intervals do not model systematic drift or workload-count error.</p>'
               '<p>Hardware/configuration labels are supplied by the user. Endpoint chicken counts are consistency checks, '
               'not verification of every moment of the capture. The original report section retains its historical calculations; '
               'this section can exclude additional laps when metric sample support or metadata contradicts the workload.</p>'
               '<p class="small">Analysis scope: SCOPE_ID. See FORMULAS.md, AUDIT.md and stability_metadata.json for the versioned interface and assumptions.</p></details>'.replace('SCOPE_ID', escape(metadata['scope_id'])))
    out.append('''<script>
document.querySelectorAll('.stability [data-metric-control]').forEach(function(control) {
  control.addEventListener('change', function() {
    var panel = document.getElementById(control.dataset.metricControl);
    panel.querySelectorAll('[data-metric]').forEach(function(item) {
      item.hidden = item.dataset.metric !== control.value;
    });
  });
});
</script></section>''')
    return '\n'.join(out)


def write_standalone(path, rows, metadata):
    body = render_stability(rows, metadata)
    title = 'ChickenBench \u2014 loaded performance analysis'
    page = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    page += '<title>%s</title><style>body{margin:0 auto;padding:0 16px 40px;max-width:1360px;background:#edf2f9}</style></head><body>' % title
    page += body + '</body></html>'
    Path(path).write_text(page, encoding='utf-8')
