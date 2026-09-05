#!/usr/bin/env python3
"""Build an offline Stage-2 prototype for LiDAR fault classification.

This script deliberately separates two concepts:

1. online_proxy evidence: computed only from the navigation-consumed scan
   features already present in scan_signature_features.csv. This is the only
   evidence used by the default classifier.
2. oracle_reference evidence: computed from raw-vs-faulted reference-change
   features. This is kept only as a diagnostic upper-bound and must not be used
   as a deployable online classifier input.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import median, mean

LABELS = ('NORMAL', 'MASKING', 'DROPOUT', 'UNKNOWN')
FAULT_LABELS = {'normal': 'NORMAL', 'masking': 'MASKING', 'dropout': 'DROPOUT'}
COLORS = {'NORMAL': '#6b7280', 'MASKING': '#0f766e', 'DROPOUT': '#f97316', 'UNKNOWN': '#9ca3af'}
FAULT_TYPES = {'MASKING', 'DROPOUT'}


def parse_windows(spec: str) -> list[float]:
    values = [float(part.strip()) for part in spec.split(',') if part.strip()]
    if not values:
        raise ValueError('At least one window size is required')
    return values


def parse_float_list(spec: str) -> list[float]:
    values = [float(part.strip()) for part in spec.split(',') if part.strip()]
    if not values:
        raise ValueError('At least one numeric value is required')
    return values


def f(value: object, default: float = float('nan')) -> float:
    try:
        if value in ('', None):
            return default
        return float(value)
    except Exception:
        return default


def b(value: object) -> bool:
    return str(value).strip().lower() in {'true', '1', 'yes'}


def safe_mean(values: list[float]) -> float:
    values = [x for x in values if math.isfinite(x)]
    return mean(values) if values else float('nan')


def safe_max(values: list[float]) -> float:
    values = [x for x in values if math.isfinite(x)]
    return max(values) if values else float('nan')


def longest_streak_s(times: list[float], flags: list[bool], target: bool) -> float:
    if not times or not flags:
        return 0.0
    best = 0.0
    start: float | None = None
    last_t = times[0]
    for t, flag in zip(times, flags):
        if flag == target:
            if start is None:
                start = t
            last_t = t
        else:
            if start is not None:
                best = max(best, last_t - start)
                start = None
    if start is not None:
        best = max(best, last_t - start)
    return max(0.0, best)


def switching_rate_per_s(times: list[float], flags: list[bool]) -> float:
    if len(times) < 2 or len(flags) < 2:
        return 0.0
    switches = sum(1 for prev, cur in zip(flags, flags[1:]) if prev != cur)
    duration = max(1e-6, times[-1] - times[0])
    return switches / duration


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        writer.writerows(rows)


def is_fault_label(label: object) -> bool:
    return str(label) in FAULT_TYPES


def detection_prediction(label: object) -> str:
    return 'FAULT' if is_fault_label(label) else 'NO_FAULT'


def detection_truth(label: object) -> str:
    return 'FAULT' if is_fault_label(label) else 'NO_FAULT'


def fraction(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else float('nan')


@dataclass
class RunData:
    world_idx: int
    condition: str
    run_dir: Path
    metadata: dict[str, object]
    rows: list[dict[str, str]]


def load_run(run_dir: Path) -> RunData:
    metadata = json.loads((run_dir / 'metadata.json').read_text())
    csv_path = run_dir / 'features' / 'scan_signature_features.csv'
    with csv_path.open('r', encoding='utf-8') as file:
        rows = list(csv.DictReader(file))
    return RunData(
        world_idx=int(metadata['world_idx']),
        condition=str(metadata['condition']),
        run_dir=run_dir,
        metadata=metadata,
        rows=rows,
    )


def discover_runs(diagnostic_dir: Path) -> list[RunData]:
    run_dirs = []
    for world_dir in sorted((diagnostic_dir / 'runs').glob('world_*')):
        for condition in ('normal', 'masking', 'dropout'):
            run_dir = world_dir / condition
            if (run_dir / 'metadata.json').exists() and (run_dir / 'features' / 'scan_signature_features.csv').exists():
                run_dirs.append(run_dir)
    return [load_run(path) for path in run_dirs]


def ground_truth_for_time(run: RunData, elapsed_s: float) -> str:
    if run.condition == 'normal':
        return 'NORMAL'
    start = f(run.metadata.get('fault_start_s'))
    duration = f(run.metadata.get('fault_duration_s'))
    if start <= elapsed_s < start + duration:
        return FAULT_LABELS[run.condition]
    return 'NORMAL'


def build_scan_features(run: RunData, args: argparse.Namespace) -> list[dict[str, object]]:
    times = [f(row.get('elapsed_s')) for row in run.rows]
    baseline_rows = [row for row, t in zip(run.rows, times) if math.isfinite(t) and t <= args.baseline_calibration_s]
    if not baseline_rows:
        baseline_rows = run.rows[: max(1, min(20, len(run.rows)))]

    baseline_range_values = [f(row.get('frontal_range_max_ratio')) for row in baseline_rows]
    baseline_span_values = [f(row.get('frontal_largest_range_max_span_ratio')) for row in baseline_rows]
    baseline_range_values = [x for x in baseline_range_values if math.isfinite(x)]
    baseline_span_values = [x for x in baseline_span_values if math.isfinite(x)]
    baseline_range = median(baseline_range_values) if baseline_range_values else 0.0
    baseline_span = median(baseline_span_values) if baseline_span_values else 0.0

    out: list[dict[str, object]] = []
    for row in run.rows:
        elapsed_s = f(row.get('elapsed_s'))
        range_max_ratio = f(row.get('frontal_range_max_ratio'))
        span_ratio = f(row.get('frontal_largest_range_max_span_ratio'))
        finite_ratio = f(row.get('frontal_finite_ratio'))
        changed_ratio = f(row.get('changed_to_range_max_ratio'))

        range_delta = max(0.0, range_max_ratio - baseline_range) if math.isfinite(range_max_ratio) else float('nan')
        span_delta = max(0.0, span_ratio - baseline_span) if math.isfinite(span_ratio) else float('nan')
        delta_score = max(
            x for x in [range_delta, span_delta] if math.isfinite(x)
        ) if any(math.isfinite(x) for x in [range_delta, span_delta]) else float('nan')
        absolute_score = max(
            x for x in [range_max_ratio, span_ratio] if math.isfinite(x)
        ) if any(math.isfinite(x) for x in [range_max_ratio, span_ratio]) else float('nan')
        degraded_by_delta = math.isfinite(delta_score) and delta_score >= args.online_evidence_threshold
        degraded_by_absolute = (
            (math.isfinite(range_max_ratio) and range_max_ratio >= args.absolute_range_max_ratio_threshold)
            or (math.isfinite(span_ratio) and span_ratio >= args.absolute_span_ratio_threshold)
        )
        online_degraded = degraded_by_delta or degraded_by_absolute
        online_score = absolute_score if degraded_by_absolute else delta_score
        oracle_degraded = math.isfinite(changed_ratio) and changed_ratio >= args.oracle_evidence_threshold

        out.append({
            'world_idx': run.world_idx,
            'condition': run.condition,
            'elapsed_s': elapsed_s,
            'ground_truth': ground_truth_for_time(run, elapsed_s),
            'fault_active_topic': b(row.get('fault_active')),
            'range_max_ratio': range_max_ratio,
            'span_ratio': span_ratio,
            'finite_ratio': finite_ratio,
            'baseline_range_max_ratio': baseline_range,
            'baseline_span_ratio': baseline_span,
            'online_range_delta': range_delta,
            'online_span_delta': span_delta,
            'online_delta_score': delta_score,
            'online_absolute_score': absolute_score,
            'online_degraded_by_delta': degraded_by_delta,
            'online_degraded_by_absolute': degraded_by_absolute,
            'online_evidence_score': online_score,
            'online_degraded': online_degraded,
            'oracle_reference_changed_ratio': changed_ratio,
            'oracle_reference_degraded': oracle_degraded,
        })
    return out


def classify_window(metrics: dict[str, float], args: argparse.Namespace) -> str:
    degraded_fraction = metrics['degraded_fraction']
    switching_rate = metrics['switching_rate_per_s']
    bad_streak_s = metrics['longest_degraded_streak_s']
    good_streak_s = metrics['longest_healthy_streak_s']

    if degraded_fraction < args.normal_max_degraded_fraction:
        return 'NORMAL'
    if (
        degraded_fraction >= args.dropout_min_degraded_fraction
        and switching_rate >= args.dropout_min_switching_rate_per_s
        and bad_streak_s >= args.dropout_min_degraded_streak_s
        and good_streak_s >= args.dropout_min_healthy_streak_s
    ):
        return 'DROPOUT'
    if (
        degraded_fraction >= args.masking_min_degraded_fraction
        and switching_rate <= args.masking_max_switching_rate_per_s
        and bad_streak_s >= args.masking_min_degraded_streak_s
    ):
        return 'MASKING'
    return 'UNKNOWN'


def build_window_rows(scan_rows: list[dict[str, object]], window_s: float, args: argparse.Namespace, evidence_mode: str) -> list[dict[str, object]]:
    if evidence_mode not in {'online', 'oracle'}:
        raise ValueError(f'Unsupported evidence_mode: {evidence_mode}')
    degraded_key = 'online_degraded' if evidence_mode == 'online' else 'oracle_reference_degraded'
    evidence_key = 'online_evidence_score' if evidence_mode == 'online' else 'oracle_reference_changed_ratio'
    out: list[dict[str, object]] = []
    by_run: dict[tuple[int, str], list[dict[str, object]]] = {}
    for row in scan_rows:
        by_run.setdefault((int(row['world_idx']), str(row['condition'])), []).append(row)

    step_s = args.window_step_s
    for (world_idx, condition), rows in by_run.items():
        rows = sorted(rows, key=lambda row: f(row['elapsed_s']))
        if not rows:
            continue
        min_t = f(rows[0]['elapsed_s'])
        max_t = f(rows[-1]['elapsed_s'])
        t_end = min_t + window_s
        while t_end <= max_t + 1e-9:
            t_start = t_end - window_s
            members = [row for row in rows if t_start <= f(row['elapsed_s']) <= t_end]
            if len(members) >= args.min_window_samples:
                times = [f(row['elapsed_s']) for row in members]
                degraded_flags = [bool(row[degraded_key]) for row in members]
                oracle_flags = [bool(row['oracle_reference_degraded']) for row in members]
                online_flags = [bool(row['online_degraded']) for row in members]
                gt_counts: dict[str, int] = {}
                for row in members:
                    gt_counts[str(row['ground_truth'])] = gt_counts.get(str(row['ground_truth']), 0) + 1
                gt_label = max(gt_counts.items(), key=lambda item: item[1])[0]
                metrics = {
                    'degraded_fraction': safe_mean([float(flag) for flag in degraded_flags]),
                    'switching_rate_per_s': switching_rate_per_s(times, degraded_flags),
                    'longest_degraded_streak_s': longest_streak_s(times, degraded_flags, True),
                    'longest_healthy_streak_s': longest_streak_s(times, degraded_flags, False),
                    'oracle_degraded_fraction': safe_mean([float(flag) for flag in oracle_flags]),
                    'online_degraded_fraction': safe_mean([float(flag) for flag in online_flags]),
                    'evidence_mean': safe_mean([f(row[evidence_key]) for row in members]),
                    'evidence_max': safe_max([f(row[evidence_key]) for row in members]),
                    'online_evidence_mean': safe_mean([f(row['online_evidence_score']) for row in members]),
                    'online_evidence_max': safe_max([f(row['online_evidence_score']) for row in members]),
                    'oracle_evidence_mean': safe_mean([f(row['oracle_reference_changed_ratio']) for row in members]),
                    'oracle_evidence_max': safe_max([f(row['oracle_reference_changed_ratio']) for row in members]),
                    'range_max_ratio_mean': safe_mean([f(row['range_max_ratio']) for row in members]),
                    'span_ratio_mean': safe_mean([f(row['span_ratio']) for row in members]),
                }
                predicted = classify_window(metrics, args)
                gt_binary = detection_truth(gt_label)
                predicted_binary = detection_prediction(predicted)
                out.append({
                    'world_idx': world_idx,
                    'condition': condition,
                    'evidence_mode': evidence_mode,
                    'window_s': window_s,
                    't_start_s': t_start,
                    't_end_s': t_end,
                    'sample_count': len(members),
                    'ground_truth': gt_label,
                    'predicted_label': predicted,
                    'ground_truth_binary': gt_binary,
                    'predicted_binary': predicted_binary,
                    'detection_correct': gt_binary == predicted_binary,
                    'type_correct': predicted == gt_label if is_fault_label(gt_label) else '',
                    'correct': predicted == gt_label,
                    **metrics,
                })
            t_end += step_s
    return out


def build_episode_rows(window_rows: list[dict[str, object]], args: argparse.Namespace) -> list[dict[str, object]]:
    """Add lightweight hysteresis to window-level labels.

    The key behaviour is that DROPOUT does not clear on a single healthy phase;
    it clears only after a clearance window without recurrent dropout evidence.
    """
    out: list[dict[str, object]] = []
    by_run_window: dict[tuple[str, int, str, float], list[dict[str, object]]] = {}
    for row in window_rows:
        by_run_window.setdefault((str(row['evidence_mode']), int(row['world_idx']), str(row['condition']), f(row['window_s'])), []).append(row)

    for key, rows in by_run_window.items():
        state = 'NORMAL'
        active_type = 'NORMAL'
        last_fault_like_t: float | None = None
        consecutive_type_count = 0
        previous_window_label = 'NORMAL'
        for row in sorted(rows, key=lambda item: f(item['t_end_s'])):
            label = str(row['predicted_label'])
            t_end = f(row['t_end_s'])
            if label == previous_window_label:
                consecutive_type_count += 1
            else:
                consecutive_type_count = 1
            previous_window_label = label

            if label in {'MASKING', 'DROPOUT'}:
                last_fault_like_t = t_end
                if active_type != label and consecutive_type_count >= args.confirm_windows:
                    active_type = label
                    state = 'ACTIVE'
                elif active_type == label:
                    state = 'PROLONGED' if consecutive_type_count >= args.prolonged_windows else 'ACTIVE'
            elif label == 'NORMAL':
                if active_type == 'DROPOUT' and last_fault_like_t is not None and (t_end - last_fault_like_t) < args.dropout_clearance_s:
                    state = 'PROLONGED'
                    label = 'DROPOUT_HEALTHY_PHASE'
                elif active_type in {'MASKING', 'DROPOUT'} and last_fault_like_t is not None and (t_end - last_fault_like_t) < args.clearance_s:
                    state = 'ACTIVE'
                    label = f'{active_type}_CLEARING'
                else:
                    active_type = 'NORMAL'
                    state = 'NORMAL'
            else:
                if active_type in {'MASKING', 'DROPOUT'}:
                    state = 'ACTIVE'
                else:
                    state = 'UNKNOWN'

            out.append({
                **row,
                'episode_observation_label': label,
                'episode_active_type': active_type,
                'episode_state': state,
            })
    return out


def summarise_windows(window_rows: list[dict[str, object]], episode_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    grouped: dict[tuple[str, float, str, int, str], list[dict[str, object]]] = {}
    for row in window_rows:
        grouped.setdefault((str(row['evidence_mode']), f(row['window_s']), str(row['condition']), int(row['world_idx']), str(row['ground_truth'])), []).append(row)
    for (evidence_mode, window_s, condition, world_idx, ground_truth), rows in sorted(grouped.items()):
        known_rows = [row for row in rows if str(row['predicted_label']) != 'UNKNOWN']
        correct_rows = [row for row in rows if bool(row['correct'])]
        fault_rows = [row for row in rows if str(row['ground_truth']) in {'MASKING', 'DROPOUT'}]
        correct_fault_rows = [row for row in fault_rows if str(row['predicted_label']) == str(row['ground_truth'])]
        first_detection_latency = float('nan')
        if fault_rows and correct_fault_rows:
            onset = min(f(row['t_start_s']) for row in fault_rows)
            first_detection_latency = min(f(row['t_end_s']) for row in correct_fault_rows) - onset
        summaries.append({
            'evidence_mode': evidence_mode,
            'window_s': window_s,
            'world_idx': world_idx,
            'condition': condition,
            'ground_truth': ground_truth,
            'window_count': len(rows),
            'accuracy_including_unknown': len(correct_rows) / len(rows) if rows else float('nan'),
            'known_fraction': len(known_rows) / len(rows) if rows else float('nan'),
            'unknown_fraction': 1.0 - (len(known_rows) / len(rows)) if rows else float('nan'),
            'first_correct_fault_detection_latency_s': first_detection_latency,
            'predicted_normal_count': sum(1 for row in rows if str(row['predicted_label']) == 'NORMAL'),
            'predicted_masking_count': sum(1 for row in rows if str(row['predicted_label']) == 'MASKING'),
            'predicted_dropout_count': sum(1 for row in rows if str(row['predicted_label']) == 'DROPOUT'),
            'predicted_unknown_count': sum(1 for row in rows if str(row['predicted_label']) == 'UNKNOWN'),
        })

    episode_grouped: dict[tuple[str, float, str, int], list[dict[str, object]]] = {}
    for row in episode_rows:
        episode_grouped.setdefault((str(row['evidence_mode']), f(row['window_s']), str(row['condition']), int(row['world_idx'])), []).append(row)
    for summary in summaries:
        key = (str(summary['evidence_mode']), f(summary['window_s']), str(summary['condition']), int(summary['world_idx']))
        rows = episode_grouped.get(key, [])
        summary['episode_masking_windows'] = sum(1 for row in rows if str(row['episode_active_type']) == 'MASKING')
        summary['episode_dropout_windows'] = sum(1 for row in rows if str(row['episode_active_type']) == 'DROPOUT')
        summary['episode_unknown_windows'] = sum(1 for row in rows if str(row['episode_state']) == 'UNKNOWN')
    return summaries



def group_rows(rows: list[dict[str, object]], fields: tuple[str, ...]) -> dict[tuple[object, ...], list[dict[str, object]]]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(tuple(row[field] for field in fields), []).append(row)
    return grouped


def summarise_detection(window_rows: list[dict[str, object]], group_fields: tuple[str, ...]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for key, rows in sorted(group_rows(window_rows, group_fields).items()):
        normal_rows = [row for row in rows if not is_fault_label(row['ground_truth'])]
        fault_rows = [row for row in rows if is_fault_label(row['ground_truth'])]
        predicted_fault_rows = [row for row in rows if is_fault_label(row['predicted_label'])]
        unknown_rows = [row for row in rows if str(row['predicted_label']) == 'UNKNOWN']
        true_positive = [row for row in fault_rows if is_fault_label(row['predicted_label'])]
        false_negative = [row for row in fault_rows if not is_fault_label(row['predicted_label'])]
        false_positive = [row for row in normal_rows if is_fault_label(row['predicted_label'])]
        true_negative = [row for row in normal_rows if not is_fault_label(row['predicted_label'])]

        summary = {field: value for field, value in zip(group_fields, key)}
        summary.update({
            'window_count': len(rows),
            'normal_window_count': len(normal_rows),
            'fault_window_count': len(fault_rows),
            'predicted_fault_window_count': len(predicted_fault_rows),
            'unknown_window_count': len(unknown_rows),
            'true_positive_fault_detection_count': len(true_positive),
            'false_negative_fault_miss_count': len(false_negative),
            'false_positive_fault_alarm_count': len(false_positive),
            'true_negative_no_fault_count': len(true_negative),
            'fault_detection_recall': fraction(len(true_positive), len(fault_rows)),
            'normal_false_alarm_rate': fraction(len(false_positive), len(normal_rows)),
            'fault_detection_precision': fraction(len(true_positive), len(predicted_fault_rows)),
            'normal_specificity': fraction(len(true_negative), len(normal_rows)),
            'detection_accuracy': fraction(len(true_positive) + len(true_negative), len(rows)),
            'unknown_fraction': fraction(len(unknown_rows), len(rows)),
        })
        summaries.append(summary)
    return summaries


def summarise_typing(window_rows: list[dict[str, object]], group_fields: tuple[str, ...]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for key, rows in sorted(group_rows(window_rows, group_fields).items()):
        fault_rows = [row for row in rows if is_fault_label(row['ground_truth'])]
        if not fault_rows:
            continue
        predicted_fault_rows = [row for row in fault_rows if is_fault_label(row['predicted_label'])]
        correct_type_rows = [row for row in fault_rows if str(row['predicted_label']) == str(row['ground_truth'])]
        masking_rows = [row for row in fault_rows if str(row['ground_truth']) == 'MASKING']
        dropout_rows = [row for row in fault_rows if str(row['ground_truth']) == 'DROPOUT']
        masking_correct = [row for row in masking_rows if str(row['predicted_label']) == 'MASKING']
        dropout_correct = [row for row in dropout_rows if str(row['predicted_label']) == 'DROPOUT']
        masking_as_dropout = [row for row in masking_rows if str(row['predicted_label']) == 'DROPOUT']
        dropout_as_masking = [row for row in dropout_rows if str(row['predicted_label']) == 'MASKING']
        missed_or_unknown = [row for row in fault_rows if not is_fault_label(row['predicted_label'])]

        summary = {field: value for field, value in zip(group_fields, key)}
        summary.update({
            'fault_window_count': len(fault_rows),
            'predicted_fault_window_count': len(predicted_fault_rows),
            'correct_type_count': len(correct_type_rows),
            'missed_or_unknown_fault_count': len(missed_or_unknown),
            'type_exact_recall': fraction(len(correct_type_rows), len(fault_rows)),
            'type_accuracy_when_fault_predicted': fraction(len(correct_type_rows), len(predicted_fault_rows)),
            'masking_window_count': len(masking_rows),
            'masking_recall': fraction(len(masking_correct), len(masking_rows)),
            'masking_as_dropout_rate': fraction(len(masking_as_dropout), len(masking_rows)),
            'dropout_window_count': len(dropout_rows),
            'dropout_recall': fraction(len(dropout_correct), len(dropout_rows)),
            'dropout_as_masking_rate': fraction(len(dropout_as_masking), len(dropout_rows)),
        })
        summaries.append(summary)
    return summaries


def summarise_latency(window_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    group_fields = ('evidence_mode', 'window_s', 'world_idx', 'condition')
    for key, rows in sorted(group_rows(window_rows, group_fields).items()):
        fault_rows = [row for row in rows if is_fault_label(row['ground_truth'])]
        if not fault_rows:
            continue
        onset = min(f(row['t_start_s']) for row in fault_rows)
        any_detection = [row for row in fault_rows if is_fault_label(row['predicted_label'])]
        correct_type = [row for row in fault_rows if str(row['predicted_label']) == str(row['ground_truth'])]
        summary = {field: value for field, value in zip(group_fields, key)}
        summary.update({
            'fault_onset_window_start_s': onset,
            'first_any_fault_detection_latency_s': min(f(row['t_end_s']) for row in any_detection) - onset if any_detection else float('nan'),
            'first_correct_type_detection_latency_s': min(f(row['t_end_s']) for row in correct_type) - onset if correct_type else float('nan'),
        })
        summaries.append(summary)
    return summaries



def summarise_threshold_trigger(
    window_rows: list[dict[str, object]],
    thresholds: list[float],
    group_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for key, rows in sorted(group_rows(window_rows, group_fields).items()):
        for threshold in thresholds:
            normal_rows = [row for row in rows if not is_fault_label(row['ground_truth'])]
            fault_rows = [row for row in rows if is_fault_label(row['ground_truth'])]
            predicted_fault_rows = [row for row in rows if f(row['degraded_fraction']) >= threshold]
            true_positive = [row for row in fault_rows if f(row['degraded_fraction']) >= threshold]
            false_negative = [row for row in fault_rows if f(row['degraded_fraction']) < threshold]
            false_positive = [row for row in normal_rows if f(row['degraded_fraction']) >= threshold]
            true_negative = [row for row in normal_rows if f(row['degraded_fraction']) < threshold]
            summary = {field: value for field, value in zip(group_fields, key)}
            summary.update({
                'trigger_degraded_fraction_threshold': threshold,
                'window_count': len(rows),
                'normal_window_count': len(normal_rows),
                'fault_window_count': len(fault_rows),
                'predicted_fault_window_count': len(predicted_fault_rows),
                'true_positive_fault_detection_count': len(true_positive),
                'false_negative_fault_miss_count': len(false_negative),
                'false_positive_fault_alarm_count': len(false_positive),
                'true_negative_no_fault_count': len(true_negative),
                'fault_detection_recall': fraction(len(true_positive), len(fault_rows)),
                'normal_false_alarm_rate': fraction(len(false_positive), len(normal_rows)),
                'fault_detection_precision': fraction(len(true_positive), len(predicted_fault_rows)),
                'normal_specificity': fraction(len(true_negative), len(normal_rows)),
                'detection_accuracy': fraction(len(true_positive) + len(true_negative), len(rows)),
            })
            summaries.append(summary)
    return summaries


def select_trigger_candidates(
    sweep_rows: list[dict[str, object]],
    max_false_alarm_rate: float,
    min_precision: float,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    group_fields = ('evidence_mode', 'window_s')
    for key, rows in sorted(group_rows(sweep_rows, group_fields).items()):
        viable = [
            row for row in rows
            if f(row['normal_false_alarm_rate']) <= max_false_alarm_rate
            and f(row['fault_detection_precision']) >= min_precision
        ]
        ranked = viable if viable else rows
        ranked = sorted(
            ranked,
            key=lambda row: (
                f(row['fault_detection_recall']),
                -f(row['normal_false_alarm_rate']),
                f(row['fault_detection_precision']),
            ),
            reverse=True,
        )
        if not ranked:
            continue
        selected = ranked[0]
        best = dict(selected)
        best['selection_rule'] = (
            f'false_alarm<={max_false_alarm_rate:g} and precision>={min_precision:g}; '
            'fallback=max_recall_if_no_viable_candidate'
        )
        best['candidate_viable'] = selected in viable
        candidates.append(best)
    return candidates



def summarise_fault_active_semantics(scan_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows_out: list[dict[str, object]] = []
    for key, rows in sorted(group_rows(scan_rows, ('world_idx', 'condition')).items()):
        world_idx, condition = key
        if condition == 'normal':
            continue
        fault_rows = [row for row in rows if is_fault_label(row['ground_truth'])]
        if not fault_rows:
            continue
        fault_rows = sorted(fault_rows, key=lambda row: f(row['elapsed_s']))
        flags = [bool(row['fault_active_topic']) for row in fault_rows]
        switches = sum(1 for prev, cur in zip(flags, flags[1:]) if prev != cur)
        true_fraction = fraction(sum(1 for flag in flags if flag), len(flags))
        # One edge transition can occur from timestamp alignment at the start/end of
        # the labelled window. Burst-phase leakage would produce repeated toggling.
        burst_phase_leak_suspected = switches > 2
        rows_out.append({
            'world_idx': world_idx,
            'condition': condition,
            'ground_truth_type': FAULT_LABELS[str(condition)],
            'fault_window_sample_count': len(fault_rows),
            'fault_window_start_s': f(fault_rows[0]['elapsed_s']),
            'fault_window_end_s': f(fault_rows[-1]['elapsed_s']),
            'fault_active_true_fraction': true_fraction,
            'fault_active_switch_count': switches,
            'burst_phase_leak_suspected': burst_phase_leak_suspected,
            'semantics_ok_episode_level': true_fraction >= 0.95 and not burst_phase_leak_suspected,
        })
    return rows_out


def classify_stage2b_episode(metrics: dict[str, float], args: argparse.Namespace) -> tuple[str, str]:
    degraded_fraction = metrics['degraded_fraction']
    switching_rate = metrics['switching_rate_per_s']
    bad_streak_s = metrics['longest_degraded_streak_s']
    good_streak_s = metrics['longest_healthy_streak_s']

    dropout_like = (
        degraded_fraction >= args.stage2b_dropout_min_degraded_fraction
        and switching_rate >= args.stage2b_dropout_min_switching_rate_per_s
        and bad_streak_s >= args.stage2b_dropout_min_degraded_streak_s
        and good_streak_s >= args.stage2b_dropout_min_healthy_streak_s
    )
    masking_like = (
        degraded_fraction >= args.stage2b_masking_min_degraded_fraction
        and switching_rate <= args.stage2b_masking_max_switching_rate_per_s
        and bad_streak_s >= args.stage2b_masking_min_degraded_streak_s
    )

    if dropout_like and not masking_like:
        return 'DROPOUT', 'clear_dropout_switching'
    if masking_like and not dropout_like:
        return 'MASKING', 'clear_sustained_masking'
    if dropout_like and masking_like:
        if switching_rate >= args.stage2b_dropout_override_switching_rate_per_s:
            return 'DROPOUT', 'both_patterns_switching_override'
        return 'UNKNOWN', 'ambiguous_both_patterns'
    if degraded_fraction >= args.stage2b_min_degraded_fraction:
        return 'UNKNOWN', 'degraded_but_pattern_unclear'
    return 'UNKNOWN', 'insufficient_degradation_evidence'


def build_stage2b_episode_rows(
    scan_rows: list[dict[str, object]],
    evidence_modes: list[str],
    observation_windows_s: list[float],
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    rows_out: list[dict[str, object]] = []
    for key, rows in sorted(group_rows(scan_rows, ('world_idx', 'condition')).items()):
        world_idx, condition = key
        if condition == 'normal':
            continue
        truth = FAULT_LABELS[str(condition)]
        rows = sorted(rows, key=lambda row: f(row['elapsed_s']))
        fault_rows = [row for row in rows if is_fault_label(row['ground_truth'])]
        if not fault_rows:
            continue
        fault_start_s = min(f(row['elapsed_s']) for row in fault_rows)
        for evidence_mode in evidence_modes:
            if evidence_mode == 'online':
                degraded_key = 'online_degraded'
                evidence_key = 'online_evidence_score'
            elif evidence_mode == 'oracle':
                degraded_key = 'oracle_reference_degraded'
                evidence_key = 'oracle_reference_changed_ratio'
            else:
                raise ValueError(f'Unsupported evidence_mode: {evidence_mode}')

            for observation_window_s in observation_windows_s:
                t_start = fault_start_s
                t_end = fault_start_s + observation_window_s
                members = [row for row in rows if t_start <= f(row['elapsed_s']) < t_end]
                if len(members) < args.min_window_samples:
                    predicted, reason = 'UNKNOWN', 'insufficient_samples'
                    metrics = {
                        'degraded_fraction': float('nan'),
                        'switching_rate_per_s': float('nan'),
                        'longest_degraded_streak_s': float('nan'),
                        'longest_healthy_streak_s': float('nan'),
                        'evidence_mean': float('nan'),
                        'evidence_max': float('nan'),
                        'fault_active_true_fraction': float('nan'),
                        'fault_active_switch_count': float('nan'),
                    }
                else:
                    times = [f(row['elapsed_s']) for row in members]
                    degraded_flags = [bool(row[degraded_key]) for row in members]
                    fault_active_flags = [bool(row['fault_active_topic']) for row in members]
                    metrics = {
                        'degraded_fraction': safe_mean([float(flag) for flag in degraded_flags]),
                        'switching_rate_per_s': switching_rate_per_s(times, degraded_flags),
                        'longest_degraded_streak_s': longest_streak_s(times, degraded_flags, True),
                        'longest_healthy_streak_s': longest_streak_s(times, degraded_flags, False),
                        'evidence_mean': safe_mean([f(row[evidence_key]) for row in members]),
                        'evidence_max': safe_max([f(row[evidence_key]) for row in members]),
                        'fault_active_true_fraction': fraction(sum(1 for flag in fault_active_flags if flag), len(fault_active_flags)),
                        'fault_active_switch_count': sum(1 for prev, cur in zip(fault_active_flags, fault_active_flags[1:]) if prev != cur),
                    }
                    predicted, reason = classify_stage2b_episode(metrics, args)

                wrong_type = predicted in FAULT_TYPES and predicted != truth
                rows_out.append({
                    'world_idx': world_idx,
                    'condition': condition,
                    'evidence_mode': evidence_mode,
                    'observation_window_s': observation_window_s,
                    'fault_episode_start_s': fault_start_s,
                    'decision_time_s': fault_start_s + observation_window_s,
                    'identification_latency_s': observation_window_s,
                    'sample_count': len(members),
                    'ground_truth_type': truth,
                    'predicted_type': predicted,
                    'decision_reason': reason,
                    'correct_type': predicted == truth,
                    'wrong_type': wrong_type,
                    'unknown': predicted == 'UNKNOWN',
                    **metrics,
                })
    return rows_out


def summarise_stage2b_episode_rows(rows: list[dict[str, object]], group_fields: tuple[str, ...]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for key, group in sorted(group_rows(rows, group_fields).items()):
        masking_rows = [row for row in group if str(row['ground_truth_type']) == 'MASKING']
        dropout_rows = [row for row in group if str(row['ground_truth_type']) == 'DROPOUT']
        correct = [row for row in group if bool(row['correct_type'])]
        wrong = [row for row in group if bool(row['wrong_type'])]
        unknown = [row for row in group if bool(row['unknown'])]
        correct_known = [row for row in group if str(row['predicted_type']) in FAULT_TYPES and bool(row['correct_type'])]
        known = [row for row in group if str(row['predicted_type']) in FAULT_TYPES]
        summary = {field: value for field, value in zip(group_fields, key)}
        summary.update({
            'episode_count': len(group),
            'correct_count': len(correct),
            'wrong_type_count': len(wrong),
            'unknown_count': len(unknown),
            'known_decision_count': len(known),
            'correct_identification_rate': fraction(len(correct), len(group)),
            'wrong_type_rate': fraction(len(wrong), len(group)),
            'unknown_rate': fraction(len(unknown), len(group)),
            'accuracy_when_known': fraction(len(correct_known), len(known)),
            'masking_episode_count': len(masking_rows),
            'masking_correct_rate': fraction(sum(1 for row in masking_rows if bool(row['correct_type'])), len(masking_rows)),
            'masking_wrong_type_rate': fraction(sum(1 for row in masking_rows if bool(row['wrong_type'])), len(masking_rows)),
            'masking_unknown_rate': fraction(sum(1 for row in masking_rows if bool(row['unknown'])), len(masking_rows)),
            'dropout_episode_count': len(dropout_rows),
            'dropout_correct_rate': fraction(sum(1 for row in dropout_rows if bool(row['correct_type'])), len(dropout_rows)),
            'dropout_wrong_type_rate': fraction(sum(1 for row in dropout_rows if bool(row['wrong_type'])), len(dropout_rows)),
            'dropout_unknown_rate': fraction(sum(1 for row in dropout_rows if bool(row['unknown'])), len(dropout_rows)),
            'mean_identification_latency_s': safe_mean([f(row['identification_latency_s']) for row in group if str(row['predicted_type']) != 'UNKNOWN']),
        })
        summaries.append(summary)
    return summaries


def make_plots(output_dir: Path, window_rows: list[dict[str, object]], episode_rows: list[dict[str, object]], window_s: float) -> list[str]:
    try:
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except Exception as exc:
        (output_dir / 'plot_warning.txt').write_text(f'matplotlib unavailable: {exc}\n')
        return []

    plot_paths: list[str] = []
    by_run: dict[tuple[str, int, str], list[dict[str, object]]] = {}
    for row in window_rows:
        if abs(f(row['window_s']) - window_s) < 1e-9:
            by_run.setdefault((str(row['evidence_mode']), int(row['world_idx']), str(row['condition'])), []).append(row)

    for (evidence_mode, world_idx, condition), rows in sorted(by_run.items()):
        rows = sorted(rows, key=lambda row: f(row['t_end_s']))
        if not rows:
            continue
        fig, ax = plt.subplots(figsize=(9, 2.6), constrained_layout=True)
        xs = [f(row['t_end_s']) for row in rows]
        evidence = [f(row['evidence_mean']) for row in rows]
        degraded_fraction = [f(row['degraded_fraction']) for row in rows]
        ax.plot(xs, evidence, color='#111827', linewidth=1.2, label=f'{evidence_mode} evidence mean')
        ax.plot(xs, degraded_fraction, color='#2563eb', linewidth=1.2, label='degraded fraction')
        for row in rows:
            label = str(row['predicted_label'])
            ax.axvspan(f(row['t_start_s']), f(row['t_end_s']), color=COLORS.get(label, '#9ca3af'), alpha=0.10)
        ax.set_ylim(-0.05, 1.05)
        ax.set_xlabel('elapsed time (s)')
        ax.set_ylabel('window feature')
        ax.grid(alpha=0.25)
        legend_handles = [Patch(color=COLORS[label], alpha=0.20, label=label) for label in LABELS]
        ax.legend(handles=legend_handles, loc='upper right', fontsize=8, ncol=4)
        out_path = output_dir / f'{evidence_mode}_world_{world_idx:03d}_{condition}_window{window_s:g}s_classifier_timeline.png'
        fig.savefig(out_path, dpi=180)
        plt.close(fig)
        plot_paths.append(str(out_path))
    return plot_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic-dir', type=Path, required=True, help='Stage-1 diagnostic directory')
    parser.add_argument('--output-dir', type=Path, default=None, help='Output directory; default diagnostic_dir/stage2_classifier')
    parser.add_argument('--windows-s', default='1,2,3', help='Comma-separated sliding window sizes in seconds')
    parser.add_argument('--evidence-mode', choices=['online', 'oracle', 'both'], default='both', help='Evidence source for temporal classification')
    parser.add_argument('--window-step-s', type=float, default=0.25, help='Sliding window step in seconds')
    parser.add_argument('--min-window-samples', type=int, default=3, help='Minimum scan samples per window')
    parser.add_argument('--baseline-calibration-s', type=float, default=4.5, help='Initial seconds used for online baseline proxy')
    parser.add_argument('--online-evidence-threshold', type=float, default=0.25, help='Threshold for baseline-delta scan-level online degraded evidence')
    parser.add_argument('--absolute-range-max-ratio-threshold', type=float, default=0.55, help='Final selector threshold for absolute frontal range-max evidence')
    parser.add_argument('--absolute-span-ratio-threshold', type=float, default=0.55, help='Final selector threshold for absolute contiguous max-range span evidence')
    parser.add_argument('--oracle-evidence-threshold', type=float, default=0.55, help='Diagnostic-only threshold for raw-vs-faulted reference evidence')
    parser.add_argument('--normal-max-degraded-fraction', type=float, default=0.12, help='Below this window degraded fraction, classify NORMAL')
    parser.add_argument('--trigger-thresholds', default='0.15,0.25,0.35,0.45,0.55,0.65,0.75,0.85,0.95', help='Stage-2.2 recovery-trigger degraded-fraction thresholds to sweep')
    parser.add_argument('--trigger-max-false-alarm-rate', type=float, default=0.10, help='Preferred maximum false alarm rate for trigger candidate selection')
    parser.add_argument('--trigger-min-precision', type=float, default=0.80, help='Preferred minimum trigger precision for candidate selection')
    parser.add_argument('--masking-min-degraded-fraction', type=float, default=0.55, help='Masking minimum degraded fraction')
    parser.add_argument('--masking-max-switching-rate-per-s', type=float, default=0.55, help='Masking maximum switching rate')
    parser.add_argument('--masking-min-degraded-streak-s', type=float, default=0.75, help='Masking minimum degraded streak')
    parser.add_argument('--dropout-min-degraded-fraction', type=float, default=0.15, help='Dropout minimum degraded fraction')
    parser.add_argument('--dropout-min-switching-rate-per-s', type=float, default=0.75, help='Dropout minimum switching rate')
    parser.add_argument('--dropout-min-degraded-streak-s', type=float, default=0.15, help='Dropout minimum degraded streak')
    parser.add_argument('--dropout-min-healthy-streak-s', type=float, default=0.15, help='Dropout minimum healthy streak')
    parser.add_argument('--confirm-windows', type=int, default=2, help='Consecutive windows needed to confirm active type')
    parser.add_argument('--prolonged-windows', type=int, default=5, help='Consecutive windows needed for prolonged state')
    parser.add_argument('--clearance-s', type=float, default=1.5, help='General clearance duration')
    parser.add_argument('--dropout-clearance-s', type=float, default=2.5, help='Dropout-specific clearance duration')
    parser.add_argument('--plot-window-s', type=float, default=2.0, help='Window size to plot')
    parser.add_argument('--stage2b-observation-windows-s', default='1,2,3', help='Stage-2B episode-level observation windows after controlled fault-active onset')
    parser.add_argument('--stage2b-min-degraded-fraction', type=float, default=0.15, help='Minimum degraded fraction before returning a non-normal Stage-2B pattern')
    parser.add_argument('--stage2b-masking-min-degraded-fraction', type=float, default=0.55, help='Stage-2B sustained masking minimum degraded fraction')
    parser.add_argument('--stage2b-masking-max-switching-rate-per-s', type=float, default=0.55, help='Stage-2B masking maximum switching rate')
    parser.add_argument('--stage2b-masking-min-degraded-streak-s', type=float, default=0.75, help='Stage-2B masking minimum degraded streak')
    parser.add_argument('--stage2b-dropout-min-degraded-fraction', type=float, default=0.15, help='Stage-2B dropout minimum degraded fraction')
    parser.add_argument('--stage2b-dropout-min-switching-rate-per-s', type=float, default=0.75, help='Stage-2B dropout minimum switching rate')
    parser.add_argument('--stage2b-dropout-min-degraded-streak-s', type=float, default=0.15, help='Stage-2B dropout minimum degraded streak')
    parser.add_argument('--stage2b-dropout-min-healthy-streak-s', type=float, default=0.15, help='Stage-2B dropout minimum healthy streak')
    parser.add_argument('--stage2b-dropout-override-switching-rate-per-s', type=float, default=0.75, help='Stage-2B choose dropout when both patterns match but switching is this high')
    return parser


def main() -> int:
    args = build_parser().parse_args()
    diagnostic_dir = args.diagnostic_dir.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else diagnostic_dir / 'stage2_classifier_modes'
    output_dir.mkdir(parents=True, exist_ok=True)

    runs = discover_runs(diagnostic_dir)
    scan_rows: list[dict[str, object]] = []
    for run in runs:
        scan_rows.extend(build_scan_features(run, args))

    windows = parse_windows(args.windows_s)
    evidence_modes = ['online', 'oracle'] if args.evidence_mode == 'both' else [args.evidence_mode]
    window_rows: list[dict[str, object]] = []
    for evidence_mode in evidence_modes:
        for window_s in windows:
            window_rows.extend(build_window_rows(scan_rows, window_s, args, evidence_mode))
    episode_rows = build_episode_rows(window_rows, args)
    summary_rows = summarise_windows(window_rows, episode_rows)
    detection_by_window = summarise_detection(window_rows, ('evidence_mode', 'window_s'))
    detection_by_run = summarise_detection(window_rows, ('evidence_mode', 'window_s', 'world_idx', 'condition'))
    typing_by_window = summarise_typing(window_rows, ('evidence_mode', 'window_s'))
    typing_by_run = summarise_typing(window_rows, ('evidence_mode', 'window_s', 'world_idx', 'condition'))
    latency_by_run = summarise_latency(window_rows)
    trigger_thresholds = parse_float_list(args.trigger_thresholds)
    trigger_sweep_by_window = summarise_threshold_trigger(window_rows, trigger_thresholds, ('evidence_mode', 'window_s'))
    trigger_sweep_by_run = summarise_threshold_trigger(window_rows, trigger_thresholds, ('evidence_mode', 'window_s', 'world_idx', 'condition'))
    trigger_candidates = select_trigger_candidates(trigger_sweep_by_window, args.trigger_max_false_alarm_rate, args.trigger_min_precision)
    stage2b_observation_windows = parse_float_list(args.stage2b_observation_windows_s)
    fault_active_semantics = summarise_fault_active_semantics(scan_rows)
    stage2b_episode_rows = build_stage2b_episode_rows(scan_rows, evidence_modes, stage2b_observation_windows, args)
    stage2b_summary_by_window = summarise_stage2b_episode_rows(stage2b_episode_rows, ('evidence_mode', 'observation_window_s'))
    stage2b_summary_by_run = summarise_stage2b_episode_rows(stage2b_episode_rows, ('evidence_mode', 'observation_window_s', 'world_idx', 'condition'))
    plot_paths = make_plots(output_dir, window_rows, episode_rows, args.plot_window_s)

    write_csv(output_dir / 'scan_level_online_features.csv', scan_rows)
    write_csv(output_dir / 'window_classifier_output.csv', window_rows)
    write_csv(output_dir / 'episode_classifier_output.csv', episode_rows)
    write_csv(output_dir / 'classifier_summary_by_run.csv', summary_rows)
    write_csv(output_dir / 'classifier_detection_summary_by_window.csv', detection_by_window)
    write_csv(output_dir / 'classifier_detection_summary_by_run.csv', detection_by_run)
    write_csv(output_dir / 'classifier_typing_summary_by_window.csv', typing_by_window)
    write_csv(output_dir / 'classifier_typing_summary_by_run.csv', typing_by_run)
    write_csv(output_dir / 'classifier_latency_by_run.csv', latency_by_run)
    write_csv(output_dir / 'classifier_trigger_sweep_by_window.csv', trigger_sweep_by_window)
    write_csv(output_dir / 'classifier_trigger_sweep_by_run.csv', trigger_sweep_by_run)
    write_csv(output_dir / 'classifier_trigger_candidates.csv', trigger_candidates)
    write_csv(output_dir / 'fault_active_semantics.csv', fault_active_semantics)
    write_csv(output_dir / 'stage2b_episode_identification.csv', stage2b_episode_rows)
    write_csv(output_dir / 'stage2b_episode_summary_by_window.csv', stage2b_summary_by_window)
    write_csv(output_dir / 'stage2b_episode_summary_by_run.csv', stage2b_summary_by_run)

    overall_by_window = []
    for evidence_mode in evidence_modes:
        for window_s in windows:
            rows = [
                row
                for row in window_rows
                if str(row['evidence_mode']) == evidence_mode and abs(f(row['window_s']) - window_s) < 1e-9
            ]
            known = [row for row in rows if str(row['predicted_label']) != 'UNKNOWN']
            correct = [row for row in rows if bool(row['correct'])]
            normal_rows = [row for row in rows if str(row['ground_truth']) == 'NORMAL']
            normal_false_fault = [row for row in normal_rows if str(row['predicted_label']) in {'MASKING', 'DROPOUT'}]
            fault_rows = [row for row in rows if str(row['ground_truth']) in {'MASKING', 'DROPOUT'}]
            correct_fault = [row for row in fault_rows if str(row['predicted_label']) == str(row['ground_truth'])]
            overall_by_window.append({
                'evidence_mode': evidence_mode,
                'window_s': window_s,
                'window_count': len(rows),
                'accuracy_including_unknown': len(correct) / len(rows) if rows else float('nan'),
                'known_fraction': len(known) / len(rows) if rows else float('nan'),
                'unknown_fraction': 1.0 - len(known) / len(rows) if rows else float('nan'),
                'normal_false_fault_fraction': len(normal_false_fault) / len(normal_rows) if normal_rows else float('nan'),
                'fault_correct_fraction': len(correct_fault) / len(fault_rows) if fault_rows else float('nan'),
            })
    write_csv(output_dir / 'classifier_summary_by_window.csv', overall_by_window)

    report = {
        'diagnostic_dir': str(diagnostic_dir),
        'output_dir': str(output_dir),
        'run_count': len(runs),
        'scan_row_count': len(scan_rows),
        'window_row_count': len(window_rows),
        'windows_s': windows,
        'evidence_modes': evidence_modes,
        'rules': {
            'baseline_calibration_s': args.baseline_calibration_s,
            'online_evidence_threshold': args.online_evidence_threshold,
            'absolute_range_max_ratio_threshold': args.absolute_range_max_ratio_threshold,
            'absolute_span_ratio_threshold': args.absolute_span_ratio_threshold,
            'normal_max_degraded_fraction': args.normal_max_degraded_fraction,
            'trigger_thresholds': trigger_thresholds,
            'trigger_max_false_alarm_rate': args.trigger_max_false_alarm_rate,
            'trigger_min_precision': args.trigger_min_precision,
            'stage2b_observation_windows_s': stage2b_observation_windows,
            'stage2b_min_degraded_fraction': args.stage2b_min_degraded_fraction,
            'stage2b_masking_min_degraded_fraction': args.stage2b_masking_min_degraded_fraction,
            'stage2b_masking_max_switching_rate_per_s': args.stage2b_masking_max_switching_rate_per_s,
            'stage2b_dropout_min_switching_rate_per_s': args.stage2b_dropout_min_switching_rate_per_s,
            'masking_min_degraded_fraction': args.masking_min_degraded_fraction,
            'masking_max_switching_rate_per_s': args.masking_max_switching_rate_per_s,
            'masking_min_degraded_streak_s': args.masking_min_degraded_streak_s,
            'dropout_min_degraded_fraction': args.dropout_min_degraded_fraction,
            'dropout_min_switching_rate_per_s': args.dropout_min_switching_rate_per_s,
            'dropout_min_degraded_streak_s': args.dropout_min_degraded_streak_s,
            'dropout_min_healthy_streak_s': args.dropout_min_healthy_streak_s,
        },
        'overall_by_window': overall_by_window,
        'detection_by_window': detection_by_window,
        'typing_by_window': typing_by_window,
        'latency_by_run': latency_by_run,
        'trigger_sweep_by_window': trigger_sweep_by_window,
        'trigger_candidates': trigger_candidates,
        'fault_active_semantics': fault_active_semantics,
        'stage2b_episode_summary_by_window': stage2b_summary_by_window,
        'plots': plot_paths,
        'caveat': 'online evidence is deployable proxy evidence; oracle evidence is a reference-assisted diagnostic upper bound and is not deployable.',
    }
    (output_dir / 'summary.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f'Wrote {output_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
