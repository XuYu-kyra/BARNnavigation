#!/usr/bin/env python3
"""Evaluate paired baseline-vs-fault runs with CI-based stopping checks."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean, stdev

import numpy as np

import analyze_fault_pipeline as fault_analysis


T_CRIT_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log-dir', type=Path, required=True, help='Directory containing paired manual fault study logs')
    parser.add_argument('--path-root', type=Path, default=Path(__file__).resolve().parents[1] / 'jackal_helper/worlds/BARN/path_files', help='Directory containing BARN path_*.npy files')
    parser.add_argument('--output-dir', type=Path, default=None, help='Output directory; defaults to <log-dir>/paired_analysis')
    parser.add_argument('--metric', default='completion_time_s', help='Run-level metric to compare between fault and baseline')
    parser.add_argument('--stop-speed-threshold', type=float, default=0.05, help='Speed below this threshold counts as a stop interval')
    parser.add_argument('--ci-halfwidth-abs-threshold', type=float, default=5.0, help='Absolute stopping target for 95%% CI half-width')
    parser.add_argument('--ci-halfwidth-rel-threshold', type=float, default=0.25, help='Relative stopping target for 95%% CI half-width as a fraction of |mean difference|')
    return parser


def t_crit_95(df: int) -> float:
    if df <= 0:
        return float('nan')
    if df in T_CRIT_95:
        return T_CRIT_95[df]
    if df < 40:
        return 2.021
    if df < 60:
        return 2.000
    if df < 120:
        return 1.980
    return 1.960


def safe_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float('nan')


def build_run_rows(log_dir: Path, path_root: Path, stop_speed_threshold: float) -> list[dict[str, object]]:
    run_rows: list[dict[str, object]] = []
    for log_path in sorted(log_dir.glob('*.log')):
        row, _ = fault_analysis.analyze_log(log_path, path_root, stop_speed_threshold)
        run_rows.append(row)
    run_rows.sort(key=lambda row: (int(row['world_idx']), int(row['run_id']), str(row['condition'])))
    return run_rows


def build_pair_rows(run_rows: list[dict[str, object]], metric: str) -> list[dict[str, object]]:
    grouped: dict[tuple[int, int], dict[str, dict[str, object]]] = {}
    for row in run_rows:
        key = (int(row['world_idx']), int(row['run_id']))
        grouped.setdefault(key, {})[str(row['condition'])] = row

    pair_rows: list[dict[str, object]] = []
    for (world_idx, run_id), by_condition in sorted(grouped.items()):
        baseline = by_condition.get('baseline')
        fault = by_condition.get('fault')
        if not baseline or not fault:
            continue
        baseline_value = safe_float(baseline.get(metric))
        fault_value = safe_float(fault.get(metric))
        difference = fault_value - baseline_value if math.isfinite(baseline_value) and math.isfinite(fault_value) else float('nan')
        pair_rows.append({
            'world_idx': world_idx,
            'run_id': run_id,
            'metric': metric,
            'baseline_status': baseline['status'],
            'fault_status': fault['status'],
            'baseline_value': baseline_value,
            'fault_value': fault_value,
            'difference_fault_minus_baseline': difference,
            'baseline_whole_mean_speed_mps': baseline.get('whole_mean_speed_mps', float('nan')),
            'fault_whole_mean_speed_mps': fault.get('whole_mean_speed_mps', float('nan')),
            'baseline_whole_stop_ratio': baseline.get('whole_stop_ratio', float('nan')),
            'fault_whole_stop_ratio': fault.get('whole_stop_ratio', float('nan')),
        })
    return pair_rows


def slope_against_run_id(rows: list[dict[str, object]], field: str) -> float:
    points = [(int(row['run_id']), safe_float(row.get(field))) for row in rows]
    xs = [x for x, y in points if math.isfinite(y)]
    ys = [y for _, y in points if math.isfinite(y)]
    if len(xs) < 2:
        return float('nan')
    return float(np.polyfit(xs, ys, 1)[0])


def build_pair_summary(pair_rows: list[dict[str, object]], abs_threshold: float, rel_threshold: float) -> dict[str, object]:
    differences = [safe_float(row['difference_fault_minus_baseline']) for row in pair_rows]
    differences = [value for value in differences if math.isfinite(value)]
    pair_count = len(differences)
    if pair_count == 0:
        return {
            'pair_count': 0,
            'mean_difference': float('nan'),
            'sd_difference': float('nan'),
            'ci95_halfwidth': float('nan'),
            'relative_ci95_halfwidth': float('nan'),
            'passes_abs_rule': False,
            'passes_rel_rule': False,
            'recommended_stop': False,
        }

    mean_difference = mean(differences)
    sd_difference = stdev(differences) if pair_count >= 2 else 0.0
    halfwidth = t_crit_95(pair_count - 1) * sd_difference / math.sqrt(pair_count) if pair_count >= 2 else float('inf')
    relative_halfwidth = abs(halfwidth / mean_difference) if pair_count >= 2 and mean_difference != 0 else float('inf')
    t_stat = mean_difference / (sd_difference / math.sqrt(pair_count)) if pair_count >= 2 and sd_difference > 0 else float('nan')

    passes_abs_rule = math.isfinite(halfwidth) and halfwidth < abs_threshold
    passes_rel_rule = math.isfinite(relative_halfwidth) and relative_halfwidth < rel_threshold
    return {
        'pair_count': pair_count,
        'mean_difference': mean_difference,
        'sd_difference': sd_difference,
        't_statistic': t_stat,
        'ci95_halfwidth': halfwidth,
        'ci95_lower': mean_difference - halfwidth if math.isfinite(halfwidth) else float('nan'),
        'ci95_upper': mean_difference + halfwidth if math.isfinite(halfwidth) else float('nan'),
        'relative_ci95_halfwidth': relative_halfwidth,
        'passes_abs_rule': passes_abs_rule,
        'passes_rel_rule': passes_rel_rule,
        'recommended_stop': passes_abs_rule or passes_rel_rule,
        'abs_threshold_s': abs_threshold,
        'rel_threshold_fraction': rel_threshold,
    }


def build_condition_drift(run_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in run_rows:
        grouped.setdefault(str(row['condition']), []).append(row)

    out: list[dict[str, object]] = []
    for condition, rows in sorted(grouped.items()):
        out.append({
            'condition': condition,
            'run_count': len(rows),
            'completion_time_slope_s_per_run': slope_against_run_id(rows, 'completion_time_s'),
            'whole_mean_speed_slope_mps_per_run': slope_against_run_id(rows, 'whole_mean_speed_mps'),
            'whole_stop_ratio_slope_per_run': slope_against_run_id(rows, 'whole_stop_ratio'),
        })
    return out


def build_resource_summary(log_dir: Path) -> list[dict[str, object]]:
    resource_dir = log_dir / 'resource_logs'
    if not resource_dir.exists():
        return []

    summaries: list[dict[str, object]] = []
    for csv_path in sorted(resource_dir.glob('*.csv')):
        rows = list(csv.DictReader(csv_path.open()))
        if not rows:
            continue
        cpu_values = [float(row['pg_cpu_percent']) for row in rows if row.get('pg_cpu_percent')]
        rss_values = [float(row['pg_rss_mb']) for row in rows if row.get('pg_rss_mb')]
        mem_avail_values = [float(row['mem_available_mb']) for row in rows if row.get('mem_available_mb')]
        summaries.append({
            'resource_file': csv_path.name,
            'sample_count': len(rows),
            'peak_pg_cpu_percent': max(cpu_values) if cpu_values else float('nan'),
            'peak_pg_rss_mb': max(rss_values) if rss_values else float('nan'),
            'min_mem_available_mb': min(mem_avail_values) if mem_avail_values else float('nan'),
        })
    return summaries


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = build_parser().parse_args()
    log_dir = args.log_dir.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else (log_dir / 'paired_analysis')
    output_dir.mkdir(parents=True, exist_ok=True)

    run_rows = build_run_rows(log_dir, args.path_root.resolve(), args.stop_speed_threshold)
    pair_rows = build_pair_rows(run_rows, args.metric)
    pair_summary = build_pair_summary(pair_rows, args.ci_halfwidth_abs_threshold, args.ci_halfwidth_rel_threshold)
    drift_rows = build_condition_drift(run_rows)
    resource_rows = build_resource_summary(log_dir)

    summary = {
        'log_dir': str(log_dir),
        'metric': args.metric,
        'run_count': len(run_rows),
        'pair_summary': pair_summary,
        'condition_drift': drift_rows,
        'resource_summary_available': bool(resource_rows),
    }

    write_csv(output_dir / 'run_summary.csv', run_rows)
    write_csv(output_dir / 'pair_differences.csv', pair_rows)
    write_csv(output_dir / 'condition_drift.csv', drift_rows)
    write_csv(output_dir / 'resource_summary.csv', resource_rows)
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print(f'Wrote {output_dir / "run_summary.csv"}')
    print(f'Wrote {output_dir / "pair_differences.csv"}')
    print(f'Wrote {output_dir / "condition_drift.csv"}')
    print(f'Wrote {output_dir / "resource_summary.csv"}')
    print(f'Wrote {output_dir / "summary.json"}')


if __name__ == '__main__':
    main()
