#!/usr/bin/env python3
"""Parse per-world BARN batch logs into a CSV/JSON summary."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np


INIT = (-2.25, 3.0)
GOAL = (-2.25, 13.0)
STATUS_RE = re.compile(r'Navigation (succeeded|collided|timeout) with time ([0-9.]+)')
METRIC_RE = re.compile(r'Navigation metric: ([0-9.]+)')
POSE_RE = re.compile(r'Time: ([0-9.]+) \(s\), x: (-?[0-9.]+) \(m\), y: (-?[0-9.]+) \(m\)')
WORLD_RE = re.compile(r'world_idx:=(\d+)')
RECOVERY_KEYWORDS = {
    'spin': re.compile(r'behavior_server.*spin', re.IGNORECASE),
    'backup': re.compile(r'behavior_server.*back.?up', re.IGNORECASE),
    'drive_on_heading': re.compile(r'behavior_server.*drive_on_heading', re.IGNORECASE),
    'wait': re.compile(r'behavior_server.*wait', re.IGNORECASE),
    'assisted_teleop': re.compile(r'behavior_server.*assisted_teleop', re.IGNORECASE),
}


@dataclass
class PoseSample:
    t: float
    x: float
    y: float


def compute_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def path_coord_to_gazebo_coord(x: float, y: float) -> tuple[float, float]:
    radius = 0.075
    r_shift = -radius - (30 * radius * 2)
    c_shift = radius + 5
    gazebo_x = x * (radius * 2) + r_shift
    gazebo_y = y * (radius * 2) + c_shift
    return gazebo_x, gazebo_y


def load_world_path(path_root: Path, world_idx: int) -> tuple[np.ndarray, np.ndarray, float]:
    path_file = path_root / f'path_{world_idx}.npy'
    raw = np.load(path_file)
    converted = np.array([path_coord_to_gazebo_coord(float(p[0]), float(p[1])) for p in raw], dtype=float)
    poly = np.vstack([np.array(INIT, dtype=float), converted, np.array(GOAL, dtype=float)])
    segs = poly[1:] - poly[:-1]
    seg_lengths = np.linalg.norm(segs, axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(seg_lengths)])
    return poly, cumulative, float(cumulative[-1])


def project_progress(poly: np.ndarray, cumulative: np.ndarray, point: tuple[float, float]) -> float:
    p = np.array(point, dtype=float)
    best_dist = float('inf')
    best_progress = 0.0
    for i in range(len(poly) - 1):
        a = poly[i]
        b = poly[i + 1]
        ab = b - a
        ab_norm_sq = float(np.dot(ab, ab))
        if ab_norm_sq == 0.0:
            proj = a
            t = 0.0
        else:
            t = float(np.dot(p - a, ab) / ab_norm_sq)
            t = min(1.0, max(0.0, t))
            proj = a + t * ab
        dist = float(np.linalg.norm(p - proj))
        if dist < best_dist:
            best_dist = dist
            seg_len = float(np.linalg.norm(ab))
            best_progress = float(cumulative[i] + t * seg_len)
    return best_progress


def tail_displacement(samples: list[PoseSample], tail_seconds: float = 30.0) -> float:
    if not samples:
        return 0.0
    end_t = samples[-1].t
    tail = [s for s in samples if s.t >= end_t - tail_seconds]
    if len(tail) < 2:
        return 0.0
    ref = (tail[0].x, tail[0].y)
    return max(compute_distance(ref, (s.x, s.y)) for s in tail)


def classify_behavior(status: str, progress_ratio: float, tail_motion: float, min_goal_distance: float) -> str:
    if status == 'succeeded':
        return 'success'
    if status == 'collided':
        return 'early_collision' if progress_ratio < 0.3 else 'collision_after_progress'
    if progress_ratio < 0.1:
        return 'failed_to_start'
    if min_goal_distance < 1.5:
        return 'near_goal_timeout'
    if tail_motion < 0.25:
        return 'stuck_midway' if progress_ratio < 0.7 else 'stuck_after_partial_progress'
    return 'slow_timeout'


def parse_log(log_path: Path, path_root: Path) -> dict:
    text = log_path.read_text(errors='ignore')
    world_match = WORLD_RE.search(text)
    if not world_match:
        raise ValueError(f'Could not infer world index from {log_path}')
    world_idx = int(world_match.group(1))

    status_match = STATUS_RE.search(text)
    metric_match = METRIC_RE.search(text)
    poses = [PoseSample(float(t), float(x), float(y)) for t, x, y in POSE_RE.findall(text)]

    poly, cumulative, path_length = load_world_path(path_root, world_idx)

    final_x = poses[-1].x if poses else INIT[0]
    final_y = poses[-1].y if poses else INIT[1]
    min_goal_distance = min((compute_distance((s.x, s.y), GOAL) for s in poses), default=compute_distance(INIT, GOAL))
    max_progress = max((project_progress(poly, cumulative, (s.x, s.y)) for s in poses), default=0.0)
    progress_ratio = max_progress / path_length if path_length > 0 else 0.0
    goal_axis_progress = max((s.y - INIT[1] for s in poses), default=0.0)
    tail_motion = tail_displacement(poses)
    recovery_counts = {name: len(regex.findall(text)) for name, regex in RECOVERY_KEYWORDS.items()}
    recovery_total = sum(recovery_counts.values())

    status = status_match.group(1) if status_match else 'unknown'
    completion_time = float(status_match.group(2)) if status_match else float('nan')
    nav_metric = float(metric_match.group(1)) if metric_match else float('nan')
    behavior_label = classify_behavior(status, progress_ratio, tail_motion, min_goal_distance)
    stuck = status == 'timeout' and tail_motion < 0.25 and progress_ratio < 0.95

    return {
        'world_idx': world_idx,
        'status': status,
        'completion_time_s': completion_time,
        'nav_metric': nav_metric,
        'final_x': final_x,
        'final_y': final_y,
        'goal_axis_progress_m': goal_axis_progress,
        'goal_axis_progress_ratio': max(0.0, min(1.0, goal_axis_progress / 10.0)),
        'min_goal_distance_m': min_goal_distance,
        'path_progress_m': max_progress,
        'path_progress_ratio': progress_ratio,
        'tail_motion_last_30s_m': tail_motion,
        'stuck_flag': stuck,
        'behavior_label': behavior_label,
        'recovery_mentions_total': recovery_total,
        'recovery_spin_mentions': recovery_counts['spin'],
        'recovery_backup_mentions': recovery_counts['backup'],
        'recovery_drive_on_heading_mentions': recovery_counts['drive_on_heading'],
        'recovery_wait_mentions': recovery_counts['wait'],
        'recovery_assisted_teleop_mentions': recovery_counts['assisted_teleop'],
        'sample_count': len(poses),
        'log_path': str(log_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-dir', type=Path, required=True, help='Batch directory created by run_barn_batch.py')
    parser.add_argument('--path-root', type=Path, default=Path(__file__).resolve().parents[1] / 'jackal_helper/worlds/BARN/path_files', help='Directory containing BARN path_*.npy files.')
    return parser


def main() -> None:
    args = build_parser().parse_args()
    batch_dir = args.batch_dir.resolve()
    logs_dir = batch_dir / 'logs'
    rows = []
    for log_path in sorted(logs_dir.glob('world_*.log')):
        rows.append(parse_log(log_path, args.path_root.resolve()))

    summary_csv = batch_dir / 'summary.csv'
    if rows:
        with summary_csv.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    aggregates = {
        'world_count': len(rows),
        'succeeded_count': sum(row['status'] == 'succeeded' for row in rows),
        'collided_count': sum(row['status'] == 'collided' for row in rows),
        'timeout_count': sum(row['status'] == 'timeout' for row in rows),
        'unknown_count': sum(row['status'] == 'unknown' for row in rows),
        'mean_completion_time_s': float(np.nanmean([row['completion_time_s'] for row in rows])) if rows else float('nan'),
        'mean_path_progress_ratio': float(np.nanmean([row['path_progress_ratio'] for row in rows])) if rows else float('nan'),
        'mean_goal_axis_progress_ratio': float(np.nanmean([row['goal_axis_progress_ratio'] for row in rows])) if rows else float('nan'),
        'stuck_count': sum(bool(row['stuck_flag']) for row in rows),
        'total_recovery_mentions': sum(row['recovery_mentions_total'] for row in rows),
    }
    (batch_dir / 'aggregate.json').write_text(json.dumps(aggregates, indent=2))
    print(json.dumps(aggregates, indent=2))
    print(f'Wrote {summary_csv}')
    print(f'Wrote {batch_dir / "aggregate.json"}')


if __name__ == '__main__':
    main()
