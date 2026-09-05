#!/usr/bin/env python3
"""Build a dissertation-friendly analysis pack from merged BARN baseline results."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_MARGIN = 60.0

CATEGORY_ORDER = [
    'class1_stable_success',
    'class2_tune_dependent_recovered',
    'class3_marginal_success',
    'class4_persistent_hard',
]

CATEGORY_LABELS = {
    'class1_stable_success': 'Stable success: original and tuned both succeed, with comfortable tuned timing margin',
    'class2_tune_dependent_recovered': 'Tune-dependent recovered: original fails, tuned succeeds',
    'class3_marginal_success': 'Marginal success: tuned succeeds, but remains close to timeout boundary',
    'class4_persistent_hard': 'Persistent hard: tuned baseline still fails, so unsuitable for first-round fault injection',
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--merged-csv', type=Path, required=True, help='merged_world_metrics.csv from select_fault_worlds.py')
    parser.add_argument('--recommended-csv', type=Path, required=False, help='recommended_worlds.csv from select_fault_worlds.py')
    parser.add_argument('--margin-threshold', type=float, default=DEFAULT_MARGIN, help='Seconds of tuned timing margin considered comfortable')
    parser.add_argument('--output-dir', type=Path, required=False, help='Output directory for analysis pack; defaults beside merged csv')
    return parser


def maybe_float(value: str) -> float:
    if value is None or value == '':
        return float('nan')
    lower = value.lower()
    if lower == 'nan':
        return float('nan')
    if lower == 'inf':
        return float('inf')
    if lower == '-inf':
        return float('-inf')
    return float(value)


def maybe_bool(value: str) -> bool:
    return str(value).strip().lower() in {'true', '1', 'yes'}


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open() as f:
        raw_rows = list(csv.DictReader(f))
    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        out: dict[str, Any] = {}
        for key, value in row.items():
            if key == 'world_idx':
                out[key] = int(value)
            elif key.endswith('_candidate'):
                out[key] = maybe_bool(value)
            elif key.endswith('_s') or key.endswith('_m') or key.endswith('_m2') or key.endswith('_deg') or key.endswith('_ratio') or key in {
                'bbox_area_m2', 'obstacle_density_per_m2', 'path_length_m', 'path_tortuosity',
                'obstacle_count', 'selection_score'
            }:
                if key == 'obstacle_count':
                    out[key] = int(float(value))
                else:
                    out[key] = maybe_float(value)
            else:
                out[key] = value
        rows.append(out)
    return rows


def classify_row(row: dict[str, Any], margin_threshold: float) -> str:
    tuned_status = row.get('tuned_status')
    original_status = row.get('original_status')
    tuned_margin = row.get('tuned_margin_s', float('-inf'))

    if tuned_status != 'succeeded':
        return 'class4_persistent_hard'
    if original_status != 'succeeded':
        return 'class2_tune_dependent_recovered'
    if math.isnan(tuned_margin) or tuned_margin < margin_threshold:
        return 'class3_marginal_success'
    return 'class1_stable_success'


def safe_mean(values: list[float]) -> float:
    finite = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    return sum(finite) / len(finite) if finite else float('nan')


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        with path.open('w', newline='') as f:
            f.write('')
        return
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_markdown(rows: list[dict[str, Any]], categories: dict[str, list[dict[str, Any]]], recommended: list[dict[str, Any]], margin_threshold: float) -> str:
    lines: list[str] = []
    lines.append('# BARN 600-Run Analysis Pack')
    lines.append('')
    lines.append('## Overall Result')
    lines.append('')
    orig_success = sum(r['original_status'] == 'succeeded' for r in rows)
    tuned_success = sum(r['tuned_status'] == 'succeeded' for r in rows)
    tune_dep = len(categories['class2_tune_dependent_recovered'])
    persistent_hard = len(categories['class4_persistent_hard'])
    marginal = len(categories['class3_marginal_success'])
    stable = len(categories['class1_stable_success'])
    lines.append(f'- Total worlds analysed: {len(rows)}')
    lines.append(f'- Original baseline success count: {orig_success}')
    lines.append(f'- Tuned baseline success count: {tuned_success}')
    lines.append(f'- Stable success worlds: {stable}')
    lines.append(f'- Tune-dependent recovered worlds: {tune_dep}')
    lines.append(f'- Marginal success worlds: {marginal}')
    lines.append(f'- Persistent hard worlds: {persistent_hard}')
    lines.append(f'- Comfortable tuned margin threshold: {margin_threshold:.1f} s')
    lines.append('')
    lines.append('## Four-Class World Taxonomy')
    lines.append('')
    for category in CATEGORY_ORDER:
        class_rows = sorted(categories[category], key=lambda r: r['world_idx'])
        world_ids = ', '.join(str(r['world_idx']) for r in class_rows)
        lines.append(f'### {category}')
        lines.append('')
        lines.append(f'- Meaning: {CATEGORY_LABELS[category]}')
        lines.append(f'- Count: {len(class_rows)}')
        lines.append(f'- World IDs: {world_ids if world_ids else "None"}')
        lines.append(f'- Mean tuned completion time (successful worlds only): {safe_mean([r.get("tuned_completion_time_s", float("nan")) for r in class_rows]):.2f} s')
        lines.append(f'- Mean time gain from tuning: {safe_mean([r.get("time_gain_s", float("nan")) for r in class_rows]):.2f} s')
        lines.append('')
    lines.append('## Why The 8 Candidate Worlds Were Chosen')
    lines.append('')
    if recommended:
        lines.append('| World | Category | Original | Tuned | Original Time (s) | Tuned Time (s) | Time Gain (s) | Tuned Margin (s) | Stress Case | Selection Reason |')
        lines.append('| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |')
        for row in recommended:
            lines.append(
                f"| {row['world_idx']} | {row['analysis_category']} | {row['original_status']} | {row['tuned_status']} | "
                f"{row.get('original_completion_time_s', float('nan')):.2f} | {row.get('tuned_completion_time_s', float('nan')):.2f} | "
                f"{row.get('time_gain_s', float('nan')):.2f} | {row.get('tuned_margin_s', float('nan')):.2f} | "
                f"{row.get('stress_case', '')} | {row.get('selection_reason', '')} |"
            )
        lines.append('')
        lines.append('Interpretation: the final candidate set intentionally mixes stable baseline worlds, moderate cases, near-threshold worlds, and at least one tune-dependent recovery case, rather than only selecting the fastest worlds.')
    else:
        lines.append('No recommended worlds CSV was provided.')
    lines.append('')
    return '\n'.join(lines)


def main() -> None:
    args = build_parser().parse_args()
    merged_csv = args.merged_csv.resolve()
    rows = load_csv(merged_csv)

    if args.output_dir is None:
        output_dir = merged_csv.parent / 'analysis_pack'
    else:
        output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    categories: dict[str, list[dict[str, Any]]] = {name: [] for name in CATEGORY_ORDER}
    for row in rows:
        category = classify_row(row, args.margin_threshold)
        row['analysis_category'] = category
        categories[category].append(row)

    for category in CATEGORY_ORDER:
        write_csv(output_dir / f'{category}.csv', sorted(categories[category], key=lambda r: r['world_idx']))

    world_lists = {category: [r['world_idx'] for r in sorted(class_rows, key=lambda x: x['world_idx'])] for category, class_rows in categories.items()}
    (output_dir / 'category_world_lists.json').write_text(json.dumps(world_lists, indent=2))

    summary = {
        'world_count_total': len(rows),
        'original_success_count': sum(r['original_status'] == 'succeeded' for r in rows),
        'tuned_success_count': sum(r['tuned_status'] == 'succeeded' for r in rows),
        'stable_success_count': len(categories['class1_stable_success']),
        'tune_dependent_recovered_count': len(categories['class2_tune_dependent_recovered']),
        'marginal_success_count': len(categories['class3_marginal_success']),
        'persistent_hard_count': len(categories['class4_persistent_hard']),
        'margin_threshold_s': args.margin_threshold,
    }
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2))

    recommended_rows: list[dict[str, Any]] = []
    if args.recommended_csv:
        rec_rows = load_csv(args.recommended_csv.resolve())
        merged_by_world = {r['world_idx']: r for r in rows}
        for rec in rec_rows:
            base = dict(merged_by_world[rec['world_idx']])
            base['selection_reason'] = rec.get('selection_reason', '')
            recommended_rows.append(base)
        write_csv(output_dir / 'recommended_with_analysis.csv', recommended_rows)

    report = build_markdown(rows, categories, recommended_rows, args.margin_threshold)
    (output_dir / 'analysis_report.md').write_text(report)

    print(json.dumps(summary, indent=2))
    print(f'Wrote analysis pack to {output_dir}')


if __name__ == '__main__':
    main()
