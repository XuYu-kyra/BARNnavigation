#!/usr/bin/env python3
"""Summarise and plot Stage-1 scan-signature diagnostic CSVs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean


def f(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return float('nan')


def b(value: str) -> bool:
    return str(value).strip().lower() in {'true', '1', 'yes'}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic-dir', type=Path, required=True, help='Output directory from run_scan_signature_diagnostics.py')
    parser.add_argument('--output-dir', type=Path, default=None, help='Analysis output directory; default diagnostic_dir/analysis')
    parser.add_argument('--degraded-ratio-threshold', type=float, default=0.55, help='Threshold for binary degraded evidence')
    parser.add_argument('--min-active-elapsed-s', type=float, default=0.0, help='Optional crop after fault onset when summarising active windows')
    return parser


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open('r', encoding='utf-8') as file:
        return list(csv.DictReader(file))


def phase_for(row: dict[str, str], metadata: dict[str, object]) -> str:
    elapsed = f(row.get('elapsed_s', 'nan'))
    condition = str(metadata['condition'])
    if condition == 'normal':
        return 'normal'
    start = float(metadata['fault_start_s'])
    duration = float(metadata['fault_duration_s'])
    if elapsed < start:
        return 'pre_fault'
    if elapsed < start + duration:
        return 'fault_window'
    return 'post_fault'


def primary_ratio(row: dict[str, str]) -> float:
    changed = f(row.get('changed_to_range_max_ratio', 'nan'))
    if math.isfinite(changed):
        return changed
    return f(row.get('frontal_range_max_ratio', 'nan'))


def summarise_run(run_dir: Path, threshold: float) -> dict[str, object]:
    metadata = json.loads((run_dir / 'metadata.json').read_text())
    rows = load_rows(run_dir / 'features' / 'scan_signature_features.csv')
    phases: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        phases.setdefault(phase_for(row, metadata), []).append(row)

    summary: dict[str, object] = {
        'world_idx': metadata['world_idx'],
        'condition': metadata['condition'],
        'run_dir': str(run_dir),
        'sample_count': len(rows),
        'fault_start_s': metadata.get('fault_start_s'),
        'fault_duration_s': metadata.get('fault_duration_s'),
        'fault_mode': metadata.get('fault_mode'),
        'scan_topic_recorded': metadata.get('scan_topic_recorded'),
    }
    for phase, phase_rows in phases.items():
        ratios = [primary_ratio(r) for r in phase_rows]
        ratios = [x for x in ratios if math.isfinite(x)]
        max_ratios = [f(r.get('frontal_range_max_ratio', 'nan')) for r in phase_rows]
        max_ratios = [x for x in max_ratios if math.isfinite(x)]
        spans = [f(r.get('changed_to_range_max_span_ratio', 'nan')) for r in phase_rows]
        spans = [x for x in spans if math.isfinite(x)]
        degraded_flags = [x >= threshold for x in ratios]
        switches = sum(1 for prev, cur in zip(degraded_flags, degraded_flags[1:]) if prev != cur)
        summary[f'{phase}_samples'] = len(phase_rows)
        summary[f'{phase}_primary_ratio_mean'] = mean(ratios) if ratios else float('nan')
        summary[f'{phase}_primary_ratio_max'] = max(ratios) if ratios else float('nan')
        summary[f'{phase}_range_max_ratio_mean'] = mean(max_ratios) if max_ratios else float('nan')
        summary[f'{phase}_changed_span_mean'] = mean(spans) if spans else float('nan')
        summary[f'{phase}_degraded_fraction'] = mean([float(x) for x in degraded_flags]) if degraded_flags else float('nan')
        summary[f'{phase}_degraded_switch_count'] = switches
    return summary


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text('')
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def make_plots(diagnostic_dir: Path, output_dir: Path, threshold: float) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        (output_dir / 'plot_warning.txt').write_text(f'matplotlib unavailable: {exc}\n')
        return []

    plot_paths: list[str] = []
    colors = {'normal': '#6b7280', 'masking': '#0f766e', 'dropout': '#f97316'}
    for world_dir in sorted((diagnostic_dir / 'runs').glob('world_*')):
        fig, axes = plt.subplots(3, 1, figsize=(9, 6), sharex=True, constrained_layout=True)
        plotted = False
        for ax, condition in zip(axes, ['normal', 'masking', 'dropout']):
            run_dir = world_dir / condition
            if not run_dir.exists():
                ax.set_visible(False)
                continue
            metadata = json.loads((run_dir / 'metadata.json').read_text())
            rows = load_rows(run_dir / 'features' / 'scan_signature_features.csv')
            xs = [f(r['elapsed_s']) for r in rows]
            primary = [primary_ratio(r) for r in rows]
            max_ratio = [f(r.get('frontal_range_max_ratio', 'nan')) for r in rows]
            ax.plot(xs, max_ratio, color='#9ca3af', linewidth=1.0, alpha=0.8, label='range_max ratio')
            ax.plot(xs, primary, color=colors[condition], linewidth=1.6, label='reference-change ratio')
            ax.axhline(threshold, color='#111827', linestyle='--', linewidth=0.8)
            if condition != 'normal':
                start = float(metadata['fault_start_s'])
                end = start + float(metadata['fault_duration_s'])
                ax.axvspan(start, end, color=colors[condition], alpha=0.10)
            ax.set_ylim(-0.05, 1.05)
            ax.set_ylabel(condition)
            ax.grid(alpha=0.25)
            plotted = True
        if not plotted:
            plt.close(fig)
            continue
        axes[-1].set_xlabel('elapsed time from first recorded scan (s)')
        axes[0].legend(loc='upper right', fontsize=8)
        out = output_dir / f'{world_dir.name}_scan_signature_timeseries.png'
        fig.savefig(out, dpi=180)
        plt.close(fig)
        plot_paths.append(str(out))
    return plot_paths


def main() -> int:
    args = build_parser().parse_args()
    diagnostic_dir = args.diagnostic_dir.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else diagnostic_dir / 'analysis'
    output_dir.mkdir(parents=True, exist_ok=True)

    run_dirs = sorted((diagnostic_dir / 'runs').glob('world_*/normal'))
    run_dirs += sorted((diagnostic_dir / 'runs').glob('world_*/masking'))
    run_dirs += sorted((diagnostic_dir / 'runs').glob('world_*/dropout'))
    summaries = [summarise_run(path, args.degraded_ratio_threshold) for path in run_dirs]
    write_csv(output_dir / 'scan_signature_summary.csv', summaries)

    plot_paths = make_plots(diagnostic_dir, output_dir, args.degraded_ratio_threshold)
    report = {
        'diagnostic_dir': str(diagnostic_dir),
        'output_dir': str(output_dir),
        'run_count': len(summaries),
        'degraded_ratio_threshold': args.degraded_ratio_threshold,
        'plots': plot_paths,
    }
    (output_dir / 'summary.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f'Wrote {output_dir / "scan_signature_summary.csv"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
