#!/usr/bin/env python3
"""Merge original/tuned BARN batch results, derive world geometry features, and recommend worlds for fault injection."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import numpy as np

import analyze_barn_batch as batch_analysis

WORLD_RE = re.compile(r"world_(\d+)\.log$")
POSE_RE = re.compile(r'<model name="unit_cylinder_[^"]+">\s*<static>1</static>\s*<pose frame="">([^<]+)</pose>')
OBSTACLE_RADIUS = 0.075
DEFAULT_TIMEOUT = 300.0


@dataclass
class WorldGeometry:
    obstacle_count: int
    bbox_area_m2: float
    obstacle_density_per_m2: float
    path_length_m: float
    path_tortuosity: float
    turn_sum_deg: float
    max_turn_deg: float
    min_clearance_m: float
    p10_clearance_m: float
    mean_clearance_m: float
    narrow_fraction_lt_03: float
    narrow_fraction_lt_05: float
    stress_case: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-batch-dir', type=Path, required=True, help='Batch directory for original baseline, containing logs/world_*.log')
    parser.add_argument('--tuned-batch-dir', type=Path, required=True, help='Batch directory for tuned baseline, containing logs/world_*.log')
    parser.add_argument('--world-root', type=Path, default=Path(__file__).resolve().parents[1] / 'jackal_helper' / 'worlds' / 'BARN', help='BARN world root containing world_*.world and path_files/')
    parser.add_argument('--timeout-threshold', type=float, default=DEFAULT_TIMEOUT, help='Primary benchmark timeout used for margin calculations')
    parser.add_argument('--margin-threshold', type=float, default=60.0, help='Minimum tuned timing margin to mark a world as a main-study candidate')
    parser.add_argument('--target-count', type=int, default=8, help='Target number of recommended worlds for the main experimental set')
    parser.add_argument('--output-dir', type=Path, default=None, help='Directory for CSV/JSON outputs; defaults to <original-batch-dir>/../selection_<original>__<tuned>')
    return parser


def list_log_paths(batch_dir: Path) -> dict[int, Path]:
    out: dict[int, Path] = {}
    candidates: list[Path] = []

    direct_logs_dir = batch_dir / 'logs'
    if direct_logs_dir.is_dir():
        candidates.extend(sorted(direct_logs_dir.glob('world_*.log')))

    candidates.extend(sorted(batch_dir.glob('world_*.log')))

    if not candidates:
        # Support aggregate directories that contain multiple batch subfolders.
        candidates.extend(sorted(batch_dir.rglob('world_*.log')))

    for log_path in candidates:
        match = WORLD_RE.search(log_path.name)
        if not match:
            continue
        world_idx = int(match.group(1))
        previous = out.get(world_idx)
        if previous is None or log_path.stat().st_mtime >= previous.stat().st_mtime:
            out[world_idx] = log_path
    return out


def wrap_angle_deg(angle_deg: float) -> float:
    wrapped = (angle_deg + 180.0) % 360.0 - 180.0
    return wrapped


def sample_polyline(poly: np.ndarray, spacing: float = 0.1) -> np.ndarray:
    pts = [poly[0]]
    for i in range(len(poly) - 1):
        a = poly[i]
        b = poly[i + 1]
        seg = b - a
        seg_len = float(np.linalg.norm(seg))
        if seg_len == 0.0:
            continue
        steps = max(1, int(math.ceil(seg_len / spacing)))
        for step in range(1, steps + 1):
            t = min(1.0, step / steps)
            pts.append(a + t * seg)
    return np.array(pts, dtype=float)


def parse_world_obstacles(world_file: Path) -> np.ndarray:
    text = world_file.read_text(errors='ignore')
    matches = POSE_RE.findall(text)
    centers = []
    for pose_text in matches:
        parts = pose_text.split()
        if len(parts) >= 2:
            centers.append((float(parts[0]), float(parts[1])))
    return np.array(centers, dtype=float) if centers else np.zeros((0, 2), dtype=float)


def compute_turning_metrics(poly: np.ndarray) -> tuple[float, float]:
    segs = poly[1:] - poly[:-1]
    headings = []
    for seg in segs:
        if float(np.linalg.norm(seg)) > 0.0:
            headings.append(math.degrees(math.atan2(float(seg[1]), float(seg[0]))))
    if len(headings) < 2:
        return 0.0, 0.0
    diffs = [abs(wrap_angle_deg(headings[i + 1] - headings[i])) for i in range(len(headings) - 1)]
    return float(sum(diffs)), float(max(diffs))


def compute_clearance_metrics(samples: np.ndarray, obstacles: np.ndarray) -> tuple[float, float, float, float, float]:
    if len(obstacles) == 0 or len(samples) == 0:
        return float('inf'), float('inf'), float('inf'), 0.0, 0.0
    clearances = []
    for p in samples:
        dists = np.linalg.norm(obstacles - p, axis=1) - OBSTACLE_RADIUS
        clearances.append(float(np.min(dists)))
    arr = np.array(clearances, dtype=float)
    return (
        float(np.min(arr)),
        float(np.percentile(arr, 10)),
        float(np.mean(arr)),
        float(np.mean(arr < 0.3)),
        float(np.mean(arr < 0.5)),
    )


def classify_stress_case(obstacle_density: float, tortuosity: float, turn_sum_deg: float, min_clearance: float, frac03: float, frac05: float) -> str:
    if min_clearance < 0.18 or frac03 > 0.35:
        return 'narrow_gap_corridor' if turn_sum_deg < 220.0 else 'narrow_turning'
    if tortuosity > 1.35 or turn_sum_deg > 300.0:
        return 'turning_slalom'
    if obstacle_density > 6.5 or frac05 > 0.45:
        return 'dense_clutter'
    if min_clearance > 0.55 and tortuosity < 1.10 and turn_sum_deg < 120.0:
        return 'open_straight'
    return 'mixed_moderate'


def compute_geometry(world_root: Path, world_idx: int) -> WorldGeometry:
    world_file = world_root / f'world_{world_idx}.world'
    path_root = world_root / 'path_files'
    obstacles = parse_world_obstacles(world_file)
    poly, cumulative, path_length = batch_analysis.load_world_path(path_root, world_idx)
    samples = sample_polyline(poly, spacing=0.1)
    turn_sum_deg, max_turn_deg = compute_turning_metrics(poly)
    min_clear, p10_clear, mean_clear, frac03, frac05 = compute_clearance_metrics(samples, obstacles)
    if len(obstacles) > 0:
        x_span = float(np.max(obstacles[:, 0]) - np.min(obstacles[:, 0]))
        y_span = float(np.max(obstacles[:, 1]) - np.min(obstacles[:, 1]))
        bbox_area = max(1e-6, x_span * y_span)
    else:
        bbox_area = 1e-6
    density = float(len(obstacles) / bbox_area)
    tortuosity = float(path_length / max(1e-6, batch_analysis.compute_distance(batch_analysis.INIT, batch_analysis.GOAL)))
    stress_case = classify_stress_case(density, tortuosity, turn_sum_deg, min_clear, frac03, frac05)
    return WorldGeometry(
        obstacle_count=int(len(obstacles)),
        bbox_area_m2=float(bbox_area),
        obstacle_density_per_m2=density,
        path_length_m=float(path_length),
        path_tortuosity=tortuosity,
        turn_sum_deg=turn_sum_deg,
        max_turn_deg=max_turn_deg,
        min_clearance_m=min_clear,
        p10_clearance_m=p10_clear,
        mean_clearance_m=mean_clear,
        narrow_fraction_lt_03=frac03,
        narrow_fraction_lt_05=frac05,
        stress_case=stress_case,
    )


def tuned_margin(row: dict, timeout_threshold: float) -> float:
    if row.get('tuned_status') != 'succeeded':
        return float('-inf')
    return float(timeout_threshold - row.get('tuned_completion_time_s', timeout_threshold))


def original_margin(row: dict, timeout_threshold: float) -> float:
    if row.get('original_status') != 'succeeded':
        return float('-inf')
    return float(timeout_threshold - row.get('original_completion_time_s', timeout_threshold))


def selection_score(row: dict, timeout_threshold: float) -> float:
    t_margin = tuned_margin(row, timeout_threshold)
    o_margin = original_margin(row, timeout_threshold)
    gain = row.get('time_gain_s')
    gain_term = 0.0 if gain is None or math.isnan(gain) else max(0.0, float(gain)) * 0.25
    robust_bonus = 20.0 if row.get('original_status') == 'succeeded' else 0.0
    return max(-999.0, t_margin) + max(-40.0, o_margin * 0.2) + gain_term + robust_bonus


def row_selection_flags(row: dict, timeout_threshold: float, margin_threshold: float) -> tuple[bool, bool]:
    tuned_ok = row.get('tuned_status') == 'succeeded'
    tuned_margin_ok = tuned_margin(row, timeout_threshold) >= margin_threshold
    original_ok = row.get('original_status') == 'succeeded'
    main_candidate = tuned_ok and tuned_margin_ok
    supplemental_candidate = tuned_ok and not main_candidate or (not original_ok and tuned_ok)
    return main_candidate, supplemental_candidate


def parse_batch_rows(batch_dir: Path, world_root: Path) -> dict[int, dict]:
    rows: dict[int, dict] = {}
    log_paths = list_log_paths(batch_dir)
    if not log_paths:
        raise FileNotFoundError(
            f'No world_*.log files found under {batch_dir}. '
            'Pass either a single batch directory containing logs/, '
            'or an aggregate directory that recursively contains batch subdirectories.'
        )
    for world_idx, log_path in log_paths.items():
        parsed = batch_analysis.parse_log(log_path, world_root / 'path_files')
        rows[world_idx] = parsed
    return rows


def merge_rows(original_rows: dict[int, dict], tuned_rows: dict[int, dict], world_root: Path, timeout_threshold: float, margin_threshold: float) -> list[dict]:
    merged = []
    all_worlds = sorted(set(original_rows) | set(tuned_rows))
    for world_idx in all_worlds:
        geom = compute_geometry(world_root, world_idx)
        o = original_rows.get(world_idx, {})
        t = tuned_rows.get(world_idx, {})
        o_time = o.get('completion_time_s', float('nan'))
        t_time = t.get('completion_time_s', float('nan'))
        time_gain = float(o_time - t_time) if not math.isnan(o_time) and not math.isnan(t_time) else float('nan')
        row = {
            'world_idx': world_idx,
            'original_status': o.get('status', 'missing'),
            'original_completion_time_s': o_time,
            'original_behavior_label': o.get('behavior_label', 'missing'),
            'original_path_progress_ratio': o.get('path_progress_ratio', float('nan')),
            'original_recovery_mentions_total': o.get('recovery_mentions_total', 0),
            'tuned_status': t.get('status', 'missing'),
            'tuned_completion_time_s': t_time,
            'tuned_behavior_label': t.get('behavior_label', 'missing'),
            'tuned_path_progress_ratio': t.get('path_progress_ratio', float('nan')),
            'tuned_recovery_mentions_total': t.get('recovery_mentions_total', 0),
            'time_gain_s': time_gain,
            'tuned_margin_s': tuned_margin({'tuned_status': t.get('status'), 'tuned_completion_time_s': t_time}, timeout_threshold),
            'original_margin_s': original_margin({'original_status': o.get('status'), 'original_completion_time_s': o_time}, timeout_threshold),
            'obstacle_count': geom.obstacle_count,
            'bbox_area_m2': geom.bbox_area_m2,
            'obstacle_density_per_m2': geom.obstacle_density_per_m2,
            'path_length_m': geom.path_length_m,
            'path_tortuosity': geom.path_tortuosity,
            'turn_sum_deg': geom.turn_sum_deg,
            'max_turn_deg': geom.max_turn_deg,
            'min_clearance_m': geom.min_clearance_m,
            'p10_clearance_m': geom.p10_clearance_m,
            'mean_clearance_m': geom.mean_clearance_m,
            'narrow_fraction_lt_03': geom.narrow_fraction_lt_03,
            'narrow_fraction_lt_05': geom.narrow_fraction_lt_05,
            'stress_case': geom.stress_case,
        }
        main_candidate, supplemental_candidate = row_selection_flags(row, timeout_threshold, margin_threshold)
        row['main_candidate'] = main_candidate
        row['supplemental_candidate'] = supplemental_candidate
        row['selection_score'] = selection_score(row, timeout_threshold)
        merged.append(row)
    return merged


def recommend_worlds(rows: list[dict], timeout_threshold: float, target_count: int) -> list[dict]:
    by_case: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row['main_candidate']:
            by_case[row['stress_case']].append(row)
    for case_rows in by_case.values():
        case_rows.sort(key=lambda r: (-r['selection_score'], r['tuned_completion_time_s'], r['world_idx']))

    selected = []
    used = set()
    case_order = sorted(by_case.keys())
    for case in case_order:
        if by_case[case]:
            row = by_case[case][0]
            selected.append({**row, 'selection_reason': f'Best robust candidate for stress case {case}'})
            used.add(row['world_idx'])

    remaining = [r for r in rows if r['main_candidate'] and r['world_idx'] not in used]
    remaining.sort(key=lambda r: (-r['selection_score'], r['tuned_completion_time_s'], r['world_idx']))
    for row in remaining:
        if len(selected) >= target_count:
            break
        selected.append({**row, 'selection_reason': f'High-margin additional candidate in {row["stress_case"]}'})
        used.add(row['world_idx'])

    return selected[:target_count]


def make_summary(rows: list[dict], recommended: list[dict]) -> dict:
    stress_counts = defaultdict(int)
    for row in rows:
        stress_counts[row['stress_case']] += 1
    return {
        'world_count_total': len(rows),
        'main_candidate_count': sum(bool(r['main_candidate']) for r in rows),
        'supplemental_candidate_count': sum(bool(r['supplemental_candidate']) for r in rows),
        'original_success_count': sum(r['original_status'] == 'succeeded' for r in rows),
        'tuned_success_count': sum(r['tuned_status'] == 'succeeded' for r in rows),
        'tune_dependent_count': sum(r['original_status'] != 'succeeded' and r['tuned_status'] == 'succeeded' for r in rows),
        'stress_case_counts': dict(sorted(stress_counts.items())),
        'recommended_worlds': [r['world_idx'] for r in recommended],
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = build_parser().parse_args()
    original_batch_dir = args.original_batch_dir.resolve()
    tuned_batch_dir = args.tuned_batch_dir.resolve()
    world_root = args.world_root.resolve()
    if args.output_dir is None:
        output_dir = original_batch_dir.parent / f'selection_{original_batch_dir.name}__{tuned_batch_dir.name}'
    else:
        output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    original_rows = parse_batch_rows(original_batch_dir, world_root)
    tuned_rows = parse_batch_rows(tuned_batch_dir, world_root)
    merged = merge_rows(original_rows, tuned_rows, world_root, args.timeout_threshold, args.margin_threshold)
    merged.sort(key=lambda r: r['world_idx'])
    recommended = recommend_worlds(merged, args.timeout_threshold, args.target_count)
    summary = make_summary(merged, recommended)

    write_csv(output_dir / 'merged_world_metrics.csv', merged)
    write_csv(output_dir / 'recommended_worlds.csv', recommended)
    (output_dir / 'selection_summary.json').write_text(json.dumps(summary, indent=2))

    methodology = {
        'timeout_threshold_s': args.timeout_threshold,
        'margin_threshold_s': args.margin_threshold,
        'selection_logic': [
            'Main candidates require tuned success and sufficient timing margin.',
            'Geometry features derive from obstacle poses and reference path files.',
            'Stress cases are heuristic labels: open_straight, dense_clutter, narrow_gap_corridor, narrow_turning, turning_slalom, mixed_moderate.',
            'Recommended worlds are selected by taking the strongest robust candidate per stress case, then filling remaining slots by score.',
        ],
    }
    (output_dir / 'selection_methodology.json').write_text(json.dumps(methodology, indent=2))

    print(json.dumps(summary, indent=2))
    print(f'Wrote {output_dir / "merged_world_metrics.csv"}')
    print(f'Wrote {output_dir / "recommended_worlds.csv"}')
    print(f'Wrote {output_dir / "selection_summary.json"}')


if __name__ == '__main__':
    main()
