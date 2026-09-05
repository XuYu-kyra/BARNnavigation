#!/usr/bin/env python3
"""Summarize a completed fault campaign into campaign-level tables and JSON."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Iterable

import analyze_fault_pipeline as fault_analysis
import evaluate_paired_fault_study as paired_eval


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-dir', type=Path, required=True, help='Fault campaign directory created by run_fault_campaign.py')
    parser.add_argument('--path-root', type=Path, default=Path(__file__).resolve().parents[1] / 'jackal_helper/worlds/BARN/path_files', help='Directory containing BARN path_*.npy files')
    parser.add_argument('--output-dir', type=Path, default=None, help='Output directory; defaults to <campaign-dir>/summaries/campaign_analysis')
    parser.add_argument('--metric', default='completion_time_s', help='Primary paired metric')
    parser.add_argument('--stop-speed-threshold', type=float, default=0.05, help='Speed below this threshold counts as a stop interval')
    parser.add_argument('--ci-halfwidth-abs-threshold', type=float, default=5.0, help='Absolute stopping target for 95%% CI half-width')
    parser.add_argument('--ci-halfwidth-rel-threshold', type=float, default=0.25, help='Relative stopping target for 95%% CI half-width as a fraction of |mean difference|')
    return parser


def safe_float(value: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float('nan')
    return out if math.isfinite(out) else float('nan')


def finite_mean(values: Iterable[object]) -> float:
    vals = [safe_float(v) for v in values]
    vals = [v for v in vals if math.isfinite(v)]
    return sum(vals) / len(vals) if vals else float('nan')


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_manifest(campaign_dir: Path) -> dict[str, object]:
    manifest_path = campaign_dir / 'manifest.json'
    if not manifest_path.exists():
        raise SystemExit(f'Missing manifest: {manifest_path}')
    return json.loads(manifest_path.read_text())


def load_campaign_status(campaign_dir: Path) -> dict[str, object]:
    status_path = campaign_dir / 'summaries' / 'campaign_status.json'
    if not status_path.exists():
        raise SystemExit(f'Missing campaign status: {status_path}')
    return json.loads(status_path.read_text())


def load_attempt_rows(campaign_dir: Path) -> list[dict[str, object]]:
    csv_path = campaign_dir / 'summaries' / 'run_attempts.csv'
    if not csv_path.exists():
        return []
    return list(csv.DictReader(csv_path.open()))


def world_dir(campaign_dir: Path, world_idx: int) -> Path:
    return campaign_dir / 'worlds' / f'world_{world_idx:03d}'


def summarize_world(world_idx: int, campaign_dir: Path, args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    log_dir = world_dir(campaign_dir, world_idx) / 'logs'
    if not log_dir.exists():
        raise SystemExit(f'Missing log directory for world {world_idx}: {log_dir}')

    run_rows = paired_eval.build_run_rows(log_dir, args.path_root.resolve(), args.stop_speed_threshold)
    pair_rows = paired_eval.build_pair_rows(run_rows, args.metric)
    pair_summary = paired_eval.build_pair_summary(pair_rows, args.ci_halfwidth_abs_threshold, args.ci_halfwidth_rel_threshold)
    drift_rows = paired_eval.build_condition_drift(run_rows)
    condition_summary = fault_analysis.build_condition_summary(run_rows)
    comparison = fault_analysis.build_comparison(condition_summary)

    by_condition = {str(row['condition']): row for row in condition_summary}
    baseline = by_condition.get('baseline', {})
    fault = by_condition.get('fault', {})

    summary_row = {
        'world_idx': world_idx,
        'run_count': len(run_rows),
        'pair_count': pair_summary.get('pair_count', 0),
        'baseline_success_count': baseline.get('success_count', 0),
        'baseline_timeout_count': baseline.get('timeout_count', 0),
        'baseline_collision_count': baseline.get('collision_count', 0),
        'fault_success_count': fault.get('success_count', 0),
        'fault_timeout_count': fault.get('timeout_count', 0),
        'fault_collision_count': fault.get('collision_count', 0),
        'baseline_completion_time_mean_s': baseline.get('completion_time_s_mean', float('nan')),
        'fault_completion_time_mean_s': fault.get('completion_time_s_mean', float('nan')),
        'completion_slowdown_mean_s': comparison.get('mean_completion_slowdown_s', float('nan')),
        'completion_slowdown_ratio': comparison.get('mean_completion_slowdown_ratio', float('nan')),
        'baseline_path_length_mean_m': baseline.get('actual_path_length_m_mean', float('nan')),
        'fault_path_length_mean_m': fault.get('actual_path_length_m_mean', float('nan')),
        'path_length_delta_mean_m': comparison.get('mean_actual_path_length_delta_m', float('nan')),
        'baseline_stop_ratio_mean': baseline.get('whole_stop_ratio_mean', float('nan')),
        'fault_stop_ratio_mean': fault.get('whole_stop_ratio_mean', float('nan')),
        'stop_ratio_delta_mean': comparison.get('mean_stop_ratio_delta', float('nan')),
        'baseline_mean_speed_mean_mps': baseline.get('whole_mean_speed_mps_mean', float('nan')),
        'fault_mean_speed_mean_mps': fault.get('whole_mean_speed_mps_mean', float('nan')),
        'mean_speed_delta_mps': comparison.get('mean_speed_delta_mps', float('nan')),
        'baseline_during_fault_stop_ratio_mean': baseline.get('during_fault_stop_ratio_mean', float('nan')),
        'fault_during_fault_stop_ratio_mean': fault.get('during_fault_stop_ratio_mean', float('nan')),
        'during_fault_stop_ratio_delta_mean': comparison.get('mean_during_fault_stop_ratio_delta', float('nan')),
        'baseline_controller_new_path_count_mean': baseline.get('controller_new_path_count_mean', float('nan')),
        'fault_controller_new_path_count_mean': fault.get('controller_new_path_count_mean', float('nan')),
        'controller_new_path_delta_mean': comparison.get('mean_controller_new_path_delta', float('nan')),
        'pair_mean_difference_s': pair_summary.get('mean_difference', float('nan')),
        'pair_sd_difference_s': pair_summary.get('sd_difference', float('nan')),
        'pair_ci95_halfwidth_s': pair_summary.get('ci95_halfwidth', float('nan')),
        'pair_ci95_lower_s': pair_summary.get('ci95_lower', float('nan')),
        'pair_ci95_upper_s': pair_summary.get('ci95_upper', float('nan')),
        'pair_relative_ci95_halfwidth': pair_summary.get('relative_ci95_halfwidth', float('nan')),
        'pair_recommended_stop': pair_summary.get('recommended_stop', False),
        'baseline_completion_slope_s_per_run': next((row['completion_time_slope_s_per_run'] for row in drift_rows if row['condition'] == 'baseline'), float('nan')),
        'fault_completion_slope_s_per_run': next((row['completion_time_slope_s_per_run'] for row in drift_rows if row['condition'] == 'fault'), float('nan')),
    }
    return summary_row, run_rows, pair_rows


def build_campaign_comparison(world_rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        'world_count': len(world_rows),
        'mean_completion_slowdown_s': finite_mean(row.get('completion_slowdown_mean_s') for row in world_rows),
        'mean_completion_slowdown_ratio': finite_mean(row.get('completion_slowdown_ratio') for row in world_rows),
        'mean_path_length_delta_m': finite_mean(row.get('path_length_delta_mean_m') for row in world_rows),
        'mean_stop_ratio_delta': finite_mean(row.get('stop_ratio_delta_mean') for row in world_rows),
        'mean_speed_delta_mps': finite_mean(row.get('mean_speed_delta_mps') for row in world_rows),
        'mean_during_fault_stop_ratio_delta': finite_mean(row.get('during_fault_stop_ratio_delta_mean') for row in world_rows),
        'mean_controller_new_path_delta': finite_mean(row.get('controller_new_path_delta_mean') for row in world_rows),
        'mean_pair_difference_s': finite_mean(row.get('pair_mean_difference_s') for row in world_rows),
        'mean_pair_ci95_halfwidth_s': finite_mean(row.get('pair_ci95_halfwidth_s') for row in world_rows),
    }


def build_attempt_audit(attempt_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[int, int, str], list[dict[str, object]]] = {}
    for row in attempt_rows:
        key = (int(row['world_idx']), int(row['pair_id']), str(row['condition']))
        grouped.setdefault(key, []).append(row)

    audit_rows: list[dict[str, object]] = []
    for (world_idx, pair_id, condition), rows in sorted(grouped.items()):
        rows_sorted = sorted(rows, key=lambda row: int(row['attempt_idx']))
        final_row = rows_sorted[-1]
        audit_rows.append({
            'world_idx': world_idx,
            'pair_id': pair_id,
            'condition': condition,
            'attempt_count': len(rows_sorted),
            'had_retry': len(rows_sorted) > 1,
            'any_invalid_attempt': any(str(row.get('valid', '')).lower() == 'false' for row in rows_sorted),
            'final_valid': final_row.get('valid', ''),
            'final_navigation_status': final_row.get('navigation_status', ''),
            'final_completion_time_s': final_row.get('completion_time_s', ''),
            'final_returncode': final_row.get('returncode', ''),
            'final_cleanup_ok': final_row.get('cleanup_ok', ''),
        })
    return audit_rows


def main() -> None:
    args = build_parser().parse_args()
    campaign_dir = args.campaign_dir.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else (campaign_dir / 'summaries' / 'campaign_analysis')
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(campaign_dir)
    campaign_status = load_campaign_status(campaign_dir)
    attempt_rows = load_attempt_rows(campaign_dir)
    worlds = [int(world_idx) for world_idx in manifest.get('worlds', [])]
    if not worlds:
        raise SystemExit(f'No worlds listed in {campaign_dir / "manifest.json"}')

    world_rows: list[dict[str, object]] = []
    all_run_rows: list[dict[str, object]] = []
    all_pair_rows: list[dict[str, object]] = []
    for world_idx in worlds:
        world_summary, run_rows, pair_rows = summarize_world(world_idx, campaign_dir, args)
        world_rows.append(world_summary)
        all_run_rows.extend(run_rows)
        all_pair_rows.extend(pair_rows)

    all_run_rows.sort(key=lambda row: (int(row['world_idx']), int(row['run_id']), str(row['condition'])))
    all_pair_rows.sort(key=lambda row: (int(row['world_idx']), int(row['run_id'])))
    world_rows.sort(key=lambda row: int(row['world_idx']))

    condition_summary = fault_analysis.build_condition_summary(all_run_rows)
    comparison = fault_analysis.build_comparison(condition_summary)
    retry_audit_rows = build_attempt_audit(attempt_rows)
    campaign_world_aggregate = build_campaign_comparison(world_rows)

    overview = {
        'campaign_dir': str(campaign_dir),
        'campaign_label': manifest.get('campaign_label', ''),
        'fault_label': manifest.get('fault_label', ''),
        'setup_path': manifest.get('setup_path', ''),
        'world_count': len(worlds),
        'world_ids': worlds,
        'target_pairs': manifest.get('target_pairs', ''),
        'validation_pairs': manifest.get('validation_pairs', ''),
        'campaign_status': {
            'worlds_completed': campaign_status.get('worlds_completed', 0),
            'worlds_retry_needed': campaign_status.get('worlds_retry_needed', 0),
            'worlds_pending_validation': campaign_status.get('worlds_pending_validation', 0),
            'worlds_in_progress': campaign_status.get('worlds_in_progress', 0),
        },
        'run_count_total': len(all_run_rows),
        'pair_count_total': len(all_pair_rows),
        'attempt_count_total': len(attempt_rows),
        'retry_case_count': sum(bool(row['had_retry']) for row in retry_audit_rows),
        'invalid_attempt_case_count': sum(bool(row['any_invalid_attempt']) for row in retry_audit_rows),
        'condition_summary': condition_summary,
        'campaign_run_aggregate': comparison,
        'campaign_world_aggregate': campaign_world_aggregate,
    }

    write_csv(output_dir / 'world_fault_summary.csv', world_rows)
    write_csv(output_dir / 'campaign_run_summary.csv', all_run_rows)
    write_csv(output_dir / 'campaign_pair_differences.csv', all_pair_rows)
    write_csv(output_dir / 'retry_audit.csv', retry_audit_rows)
    write_csv(output_dir / 'condition_summary.csv', condition_summary)
    (output_dir / 'overview.json').write_text(json.dumps(overview, indent=2))

    print(json.dumps(overview, indent=2))
    print(f'Wrote {output_dir / "world_fault_summary.csv"}')
    print(f'Wrote {output_dir / "campaign_run_summary.csv"}')
    print(f'Wrote {output_dir / "campaign_pair_differences.csv"}')
    print(f'Wrote {output_dir / "retry_audit.csv"}')
    print(f'Wrote {output_dir / "condition_summary.csv"}')
    print(f'Wrote {output_dir / "overview.json"}')


if __name__ == '__main__':
    main()
