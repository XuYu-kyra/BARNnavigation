#!/usr/bin/env python3
"""Analyze BARN fault-injection logs into process-level summaries and trace tables."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Iterable

import numpy as np

import analyze_barn_batch as batch_analysis

STATUS_RE = re.compile(r'Navigation (succeeded|collided|timeout) with time ([0-9.]+)')
METRIC_RE = re.compile(r'Navigation metric: ([0-9.]+)')
POSE_RE = re.compile(r'Time: ([0-9.]+) \(s\), x: (-?[0-9.]+) \(m\), y: (-?[0-9.]+) \(m\)')
WORLD_RE = re.compile(r'world(?:_idx:=|_)(\d+)')
READY_RE = re.compile(
    r'(?:Laser scan|Odometry) fault injector ready: .* start=([0-9.]+)s, duration=([0-9.]+)s(?:, (.*))?'
)
SCAN_READY_DETAILS_RE = re.compile(r'mode=([a-z_]+), center=([-0-9.]+)deg, width=([0-9.]+)deg, replacement=([^,\s]+), dropout_period_s=([0-9.]+), dropout_duty_cycle=([0-9.]+)')
ODOM_READY_DETAILS_RE = re.compile(r'linear_scale=([0-9.]+), yaw_rate_bias_deg_s=([-0-9.]+)')
ACTIVE_RE = re.compile(r'Fault active at t=([0-9.]+)s')
CLOSED_RE = re.compile(r'Fault window closed at t=([0-9.]+)s')
RECOVERY_GATE_READY_RE = re.compile(
    r'Fault-aware cmd_vel gate ready: .* linear_scale=([0-9.]+), angular_scale=([0-9.]+), active_timeout_s=([0-9.]+)'
)
RECOVERY_GATE_ACTIVE_RE = re.compile(r'Recovery gate active:', re.IGNORECASE)
RECOVERY_GATE_INACTIVE_RE = re.compile(r'Recovery gate inactive:', re.IGNORECASE)
MASKING_RECOVERY_READY_RE = re.compile(r'Masking reorientation recovery ready:', re.IGNORECASE)
MASKING_RECOVERY_STARTED_RE = re.compile(r'Masking reorientation recovery started:', re.IGNORECASE)
MASKING_RECOVERY_ROTATION_COMPLETE_RE = re.compile(r'Masking reorientation rotation complete:', re.IGNORECASE)
MASKING_RECOVERY_COMPLETE_RE = re.compile(r'Masking reorientation recovery complete:', re.IGNORECASE)
NAV2_MASKING_RECOVERY_READY_RE = re.compile(r'Masking Nav2 recovery supervisor ready:', re.IGNORECASE)
NAV2_MASKING_RECOVERY_STARTED_RE = re.compile(r'Nav2 masking recovery started:', re.IGNORECASE)
NAV2_CANCEL_REQUESTED_RE = re.compile(r'old_nav_cancel_requested:', re.IGNORECASE)
NAV2_CANCEL_CONFIRMED_RE = re.compile(r'old_nav_cancel_confirmed:', re.IGNORECASE)
NAV2_LOCAL_CLEAR_START_RE = re.compile(r'local_costmap_clear_start:', re.IGNORECASE)
NAV2_LOCAL_CLEAR_END_RE = re.compile(r'local_costmap_clear_end:', re.IGNORECASE)
NAV2_SPIN_SENT_RE = re.compile(r'spin_goal_sent:', re.IGNORECASE)
NAV2_SPIN_ACCEPTED_RE = re.compile(r'spin_goal_accepted:', re.IGNORECASE)
NAV2_SPIN_RESULT_RE = re.compile(r'spin_result:', re.IGNORECASE)
NAV2_GOAL_RESENT_RE = re.compile(r'navigation_goal_resent:', re.IGNORECASE)
NAV2_GOAL_ACCEPTED_RE = re.compile(r'navigation_goal_accepted:', re.IGNORECASE)
NAV2_RESENT_RESULT_RE = re.compile(r'resent_navigation_result:', re.IGNORECASE)
NAV2_CANCEL_TIMEOUT_RE = re.compile(r'old_nav_cancel_timeout_proceeding:', re.IGNORECASE)
NAV2_CANCEL_UNAVAILABLE_RE = re.compile(r'old_nav_cancel_unavailable_proceeding:', re.IGNORECASE)
NAV2_LOCAL_CLEAR_TIMEOUT_RE = re.compile(r'local_costmap_clear_timeout_proceeding:', re.IGNORECASE)
NAV2_LOCAL_CLEAR_UNAVAILABLE_RE = re.compile(r'local_costmap_clear_unavailable_proceeding:', re.IGNORECASE)
NAV2_RECOVERY_FAILED_RE = re.compile(r'nav2_masking_recovery_failed:', re.IGNORECASE)
DROPOUT_FILTER_READY_RE = re.compile(r'Dropout scan recovery filter ready:', re.IGNORECASE)
DROPOUT_FILTER_ACTIVE_RE = re.compile(r'Dropout recovery filter active:', re.IGNORECASE)
DROPOUT_FILTER_PASS_THROUGH_RE = re.compile(r'Dropout recovery filter pass-through:', re.IGNORECASE)
DROPOUT_FILTER_INACTIVE_RE = re.compile(r'Dropout recovery filter inactive:', re.IGNORECASE)
DROPOUT_FILTER_ENABLED_RE = re.compile(r'Dropout recovery filter enabled by selector\.', re.IGNORECASE)
DROPOUT_FILTER_DISABLED_RE = re.compile(r'Dropout recovery filter disabled by selector\.', re.IGNORECASE)
STAGE2B_SELECTOR_READY_RE = re.compile(r'Stage2B scan fault policy selector ready:', re.IGNORECASE)
STAGE2B_TYPE_RE = re.compile(r'fault_type_estimated: predicted_type=([A-Z]+), reason=([^,]+), classification_latency_s=([0-9.]+)', re.IGNORECASE)
STAGE2B_POLICY_RE = re.compile(r'policy_selected: predicted_type=([A-Z]+), selected_policy=([^,]+), dropout_filter_enable=(True|False), masking_monitor_enable=(True|False)', re.IGNORECASE)
MASKING_POLICY_ENABLED_RE = re.compile(r'Nav2 masking recovery policy enabled by selector\.', re.IGNORECASE)
MASKING_POLICY_DISABLED_RE = re.compile(r'Nav2 masking recovery policy disabled by selector\.', re.IGNORECASE)
RUN_RE = re.compile(r'_r(\d+)\.log$')
CONDITION_RE = re.compile(r'_(baseline|fault)(?:_|\.log)')
WARN_PATTERNS = {
    'local_costmap_warn_count': re.compile(r'\[WARN\] \[local_costmap(?:\.local_costmap)?\]'),
    'global_costmap_warn_count': re.compile(r'\[WARN\] \[global_costmap(?:\.global_costmap)?\]'),
    'controller_warn_count': re.compile(r'\[WARN\] \[controller_server\]'),
    'planner_warn_count': re.compile(r'\[WARN\] \[planner_server\]'),
    'behavior_warn_count': re.compile(r'\[WARN\] \[behavior_server\]'),
    'bt_warn_count': re.compile(r'\[WARN\] \[bt_navigator\]'),
}
EVENT_PATTERNS = {
    'controller_new_path_count': re.compile(r'Passing new path to controller', re.IGNORECASE),
    'robot_out_of_bounds_count': re.compile(r'Robot is out of bounds of the costmap', re.IGNORECASE),
    'raytrace_oob_count': re.compile(r'costmap cannot raytrace', re.IGNORECASE),
}
RECOVERY_PATTERNS = {
    'recovery_spin_mentions': re.compile(r'behavior_server.*spin', re.IGNORECASE),
    'recovery_backup_mentions': re.compile(r'behavior_server.*back.?up', re.IGNORECASE),
    'recovery_drive_on_heading_mentions': re.compile(r'behavior_server.*drive_on_heading', re.IGNORECASE),
    'recovery_wait_mentions': re.compile(r'behavior_server.*wait', re.IGNORECASE),
    'recovery_assisted_teleop_mentions': re.compile(r'behavior_server.*assisted_teleop', re.IGNORECASE),
}


@dataclass
class PoseSample:
    t: float
    x: float
    y: float


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log-dir', type=Path, required=True, help='Directory containing manual fault run logs')
    parser.add_argument('--path-root', type=Path, default=Path(__file__).resolve().parents[1] / 'jackal_helper/worlds/BARN/path_files', help='Directory containing BARN path_*.npy files')
    parser.add_argument('--output-dir', type=Path, default=None, help='Output directory; defaults to <log-dir>/analysis')
    parser.add_argument('--stop-speed-threshold', type=float, default=0.05, help='Speed below this threshold counts as a stop interval')
    return parser


def infer_world_idx(log_path: Path, text: str) -> int:
    for candidate in (log_path.name, text):
        match = WORLD_RE.search(candidate)
        if match:
            return int(match.group(1))
    raise ValueError(f'Could not infer world index from {log_path}')


def infer_condition(log_path: Path) -> str:
    match = CONDITION_RE.search(log_path.name)
    return match.group(1) if match else 'unknown'


def infer_run_id(log_path: Path) -> int:
    match = RUN_RE.search(log_path.name)
    return int(match.group(1)) if match else 1


def safe_mean(values: Iterable[float]) -> float:
    vals = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    return mean(vals) if vals else float('nan')


def safe_std(values: Iterable[float]) -> float:
    vals = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    return pstdev(vals) if len(vals) >= 2 else 0.0 if vals else float('nan')


def compute_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def pose_at_or_before(samples: list[PoseSample], t: float) -> PoseSample | None:
    chosen = None
    for sample in samples:
        if sample.t <= t:
            chosen = sample
        else:
            break
    return chosen


def segment_stats(samples: list[PoseSample], t_start: float, t_end: float, stop_speed_threshold: float) -> dict[str, float]:
    if not samples or t_end <= t_start:
        return {
            'duration_s': max(0.0, t_end - t_start),
            'path_length_m': 0.0,
            'mean_speed_mps': 0.0,
            'stop_ratio': 0.0,
            'max_stop_streak_s': 0.0,
        }

    segment = [s for s in samples if t_start <= s.t <= t_end]
    if len(segment) < 2:
        return {
            'duration_s': max(0.0, t_end - t_start),
            'path_length_m': 0.0,
            'mean_speed_mps': 0.0,
            'stop_ratio': 0.0,
            'max_stop_streak_s': 0.0,
        }

    total_dt = 0.0
    stopped_dt = 0.0
    max_stop_streak = 0.0
    current_stop_streak = 0.0
    path_length = 0.0
    for prev, curr in zip(segment[:-1], segment[1:]):
        dt = max(1e-9, curr.t - prev.t)
        dist = compute_distance((prev.x, prev.y), (curr.x, curr.y))
        speed = dist / dt
        total_dt += dt
        path_length += dist
        if speed < stop_speed_threshold:
            stopped_dt += dt
            current_stop_streak += dt
            max_stop_streak = max(max_stop_streak, current_stop_streak)
        else:
            current_stop_streak = 0.0
    return {
        'duration_s': max(0.0, t_end - t_start),
        'path_length_m': path_length,
        'mean_speed_mps': path_length / total_dt if total_dt > 0 else 0.0,
        'stop_ratio': stopped_dt / total_dt if total_dt > 0 else 0.0,
        'max_stop_streak_s': max_stop_streak,
    }


def classify_phase(t: float, fault_active_t: float | None, fault_end_t: float | None) -> str:
    if fault_active_t is None:
        return 'baseline'
    if t < fault_active_t:
        return 'pre_fault'
    if fault_end_t is None or t <= fault_end_t:
        return 'during_fault'
    return 'post_fault'


def analyze_log(log_path: Path, path_root: Path, stop_speed_threshold: float) -> tuple[dict[str, object], list[dict[str, object]]]:
    text = log_path.read_text(errors='ignore')
    world_idx = infer_world_idx(log_path, text)
    condition = infer_condition(log_path)
    run_id = infer_run_id(log_path)

    status_match = STATUS_RE.search(text)
    metric_match = METRIC_RE.search(text)
    ready_match = READY_RE.search(text)
    active_match = ACTIVE_RE.search(text)
    closed_match = CLOSED_RE.search(text)
    samples = [PoseSample(float(t), float(x), float(y)) for t, x, y in POSE_RE.findall(text)]

    poly, cumulative, nominal_path_length = batch_analysis.load_world_path(path_root, world_idx)
    goal = batch_analysis.GOAL
    init = batch_analysis.INIT

    status = status_match.group(1) if status_match else 'unknown'
    completion_time = float(status_match.group(2)) if status_match else float('nan')
    nav_metric = float(metric_match.group(1)) if metric_match else float('nan')

    fault_config_start = float(ready_match.group(1)) if ready_match else float('nan')
    fault_config_duration = float(ready_match.group(2)) if ready_match else float('nan')
    ready_details = ready_match.group(3) if ready_match and ready_match.lastindex and ready_match.lastindex >= 3 else ''
    scan_ready_match = SCAN_READY_DETAILS_RE.search(ready_details or '') if ready_details else None
    odom_ready_match = ODOM_READY_DETAILS_RE.search(ready_details or '') if ready_details else None
    recovery_ready_match = RECOVERY_GATE_READY_RE.search(text)
    stage2b_type_matches = STAGE2B_TYPE_RE.findall(text)
    stage2b_policy_matches = STAGE2B_POLICY_RE.findall(text)
    stage2b_type_match = stage2b_type_matches[-1] if stage2b_type_matches else None
    stage2b_policy_match = stage2b_policy_matches[-1] if stage2b_policy_matches else None
    scan_fault_mode = scan_ready_match.group(1) if scan_ready_match else ''
    fault_center_deg = float(scan_ready_match.group(2)) if scan_ready_match else float('nan')
    fault_width_deg = float(scan_ready_match.group(3)) if scan_ready_match else float('nan')
    fault_replacement = scan_ready_match.group(4) if scan_ready_match else (ready_details or '')
    scan_dropout_period_s = float(scan_ready_match.group(5)) if scan_ready_match else float('nan')
    scan_dropout_duty_cycle = float(scan_ready_match.group(6)) if scan_ready_match else float('nan')
    odom_linear_scale = float(odom_ready_match.group(1)) if odom_ready_match else float('nan')
    odom_yaw_rate_bias_deg_s = float(odom_ready_match.group(2)) if odom_ready_match else float('nan')
    recovery_gate_linear_scale = float(recovery_ready_match.group(1)) if recovery_ready_match else float('nan')
    recovery_gate_angular_scale = float(recovery_ready_match.group(2)) if recovery_ready_match else float('nan')
    recovery_gate_active_timeout_s = float(recovery_ready_match.group(3)) if recovery_ready_match else float('nan')
    fault_active_t = float(active_match.group(1)) if active_match else None
    fault_timing_source = 'logged'
    if fault_active_t is None and math.isfinite(fault_config_start):
        fault_active_t = fault_config_start
        fault_timing_source = 'inferred_from_config'
    fault_end_t = float(closed_match.group(1)) if closed_match else (
        (fault_active_t + fault_config_duration) if (fault_active_t is not None and math.isfinite(fault_config_duration)) else None
    )

    trace_rows: list[dict[str, object]] = []
    progress_values = []
    goal_distances = []
    actual_path_length = 0.0
    if samples:
        prev_x, prev_y = init
        for sample in samples:
            progress_m = batch_analysis.project_progress(poly, cumulative, (sample.x, sample.y))
            goal_distance_m = compute_distance((sample.x, sample.y), goal)
            phase = classify_phase(sample.t, fault_active_t, fault_end_t)
            step_distance = compute_distance((prev_x, prev_y), (sample.x, sample.y))
            actual_path_length += step_distance
            progress_values.append(progress_m)
            goal_distances.append(goal_distance_m)
            trace_rows.append({
                'world_idx': world_idx,
                'condition': condition,
                'run_id': run_id,
                't_s': sample.t,
                'x_m': sample.x,
                'y_m': sample.y,
                'step_distance_m': step_distance,
                'ref_progress_m': progress_m,
                'ref_progress_ratio': progress_m / nominal_path_length if nominal_path_length > 0 else 0.0,
                'goal_distance_m': goal_distance_m,
                'phase': phase,
            })
            prev_x, prev_y = sample.x, sample.y

    max_progress = max(progress_values) if progress_values else 0.0
    min_goal_distance = min(goal_distances) if goal_distances else compute_distance(init, goal)
    final_goal_distance = goal_distances[-1] if goal_distances else compute_distance(init, goal)
    path_efficiency = max_progress / actual_path_length if actual_path_length > 0 else 0.0
    net_displacement = compute_distance(init, (samples[-1].x, samples[-1].y)) if samples else 0.0

    pre_end = fault_active_t if fault_active_t is not None else completion_time
    during_end = fault_end_t if fault_end_t is not None else completion_time
    pre_stats = segment_stats(samples, 0.0, pre_end if math.isfinite(pre_end) else 0.0, stop_speed_threshold)
    during_stats = segment_stats(samples, fault_active_t or 0.0, during_end if during_end is not None else (completion_time if math.isfinite(completion_time) else 0.0), stop_speed_threshold) if fault_active_t is not None else segment_stats([], 0.0, 0.0, stop_speed_threshold)
    post_stats = segment_stats(samples, during_end if during_end is not None else 0.0, completion_time if math.isfinite(completion_time) else 0.0, stop_speed_threshold) if fault_active_t is not None else segment_stats([], 0.0, 0.0, stop_speed_threshold)
    whole_stats = segment_stats(samples, 0.0, completion_time if math.isfinite(completion_time) else (samples[-1].t if samples else 0.0), stop_speed_threshold)

    progress_at_fault_start = batch_analysis.project_progress(poly, cumulative, (pose_at_or_before(samples, fault_active_t).x, pose_at_or_before(samples, fault_active_t).y)) if (samples and fault_active_t is not None and pose_at_or_before(samples, fault_active_t) is not None) else float('nan')
    progress_at_fault_end = batch_analysis.project_progress(poly, cumulative, (pose_at_or_before(samples, fault_end_t).x, pose_at_or_before(samples, fault_end_t).y)) if (samples and fault_end_t is not None and pose_at_or_before(samples, fault_end_t) is not None) else float('nan')

    row: dict[str, object] = {
        'world_idx': world_idx,
        'condition': condition,
        'run_id': run_id,
        'status': status,
        'completion_time_s': completion_time,
        'nav_metric': nav_metric,
        'sample_count': len(samples),
        'nominal_path_length_m': nominal_path_length,
        'actual_path_length_m': actual_path_length,
        'net_displacement_m': net_displacement,
        'path_efficiency_ratio': path_efficiency,
        'max_ref_progress_m': max_progress,
        'max_ref_progress_ratio': max_progress / nominal_path_length if nominal_path_length > 0 else 0.0,
        'min_goal_distance_m': min_goal_distance,
        'final_goal_distance_m': final_goal_distance,
        'fault_config_start_s': fault_config_start,
        'fault_config_duration_s': fault_config_duration,
        'scan_fault_mode': scan_fault_mode,
        'fault_center_deg': fault_center_deg,
        'fault_width_deg': fault_width_deg,
        'fault_replacement': fault_replacement,
        'scan_dropout_period_s': scan_dropout_period_s,
        'scan_dropout_duty_cycle': scan_dropout_duty_cycle,
        'odom_linear_scale': odom_linear_scale,
        'odom_yaw_rate_bias_deg_s': odom_yaw_rate_bias_deg_s,
        'recovery_gate_linear_scale': recovery_gate_linear_scale,
        'recovery_gate_angular_scale': recovery_gate_angular_scale,
        'recovery_gate_active_timeout_s': recovery_gate_active_timeout_s,
        'recovery_gate_active_count': len(RECOVERY_GATE_ACTIVE_RE.findall(text)),
        'recovery_gate_inactive_count': len(RECOVERY_GATE_INACTIVE_RE.findall(text)),
        'masking_recovery_ready_count': len(MASKING_RECOVERY_READY_RE.findall(text)),
        'masking_recovery_started_count': len(MASKING_RECOVERY_STARTED_RE.findall(text)),
        'masking_recovery_rotation_complete_count': len(MASKING_RECOVERY_ROTATION_COMPLETE_RE.findall(text)),
        'masking_recovery_complete_count': len(MASKING_RECOVERY_COMPLETE_RE.findall(text)),
        'nav2_masking_recovery_ready_count': len(NAV2_MASKING_RECOVERY_READY_RE.findall(text)),
        'nav2_masking_recovery_started_count': len(NAV2_MASKING_RECOVERY_STARTED_RE.findall(text)),
        'nav2_cancel_requested_count': len(NAV2_CANCEL_REQUESTED_RE.findall(text)),
        'nav2_cancel_confirmed_count': len(NAV2_CANCEL_CONFIRMED_RE.findall(text)),
        'nav2_cancel_timeout_count': len(NAV2_CANCEL_TIMEOUT_RE.findall(text)),
        'nav2_cancel_unavailable_count': len(NAV2_CANCEL_UNAVAILABLE_RE.findall(text)),
        'nav2_local_clear_start_count': len(NAV2_LOCAL_CLEAR_START_RE.findall(text)),
        'nav2_local_clear_end_count': len(NAV2_LOCAL_CLEAR_END_RE.findall(text)),
        'nav2_local_clear_timeout_count': len(NAV2_LOCAL_CLEAR_TIMEOUT_RE.findall(text)),
        'nav2_local_clear_unavailable_count': len(NAV2_LOCAL_CLEAR_UNAVAILABLE_RE.findall(text)),
        'nav2_spin_sent_count': len(NAV2_SPIN_SENT_RE.findall(text)),
        'nav2_spin_accepted_count': len(NAV2_SPIN_ACCEPTED_RE.findall(text)),
        'nav2_spin_result_count': len(NAV2_SPIN_RESULT_RE.findall(text)),
        'nav2_goal_resent_count': len(NAV2_GOAL_RESENT_RE.findall(text)),
        'nav2_goal_accepted_count': len(NAV2_GOAL_ACCEPTED_RE.findall(text)),
        'nav2_resent_result_count': len(NAV2_RESENT_RESULT_RE.findall(text)),
        'nav2_recovery_failed_count': len(NAV2_RECOVERY_FAILED_RE.findall(text)),
        'dropout_filter_ready_count': len(DROPOUT_FILTER_READY_RE.findall(text)),
        'dropout_filter_active_count': len(DROPOUT_FILTER_ACTIVE_RE.findall(text)),
        'dropout_filter_pass_through_count': len(DROPOUT_FILTER_PASS_THROUGH_RE.findall(text)),
        'dropout_filter_inactive_count': len(DROPOUT_FILTER_INACTIVE_RE.findall(text)),
        'dropout_filter_enabled_by_selector_count': len(DROPOUT_FILTER_ENABLED_RE.findall(text)),
        'dropout_filter_disabled_by_selector_count': len(DROPOUT_FILTER_DISABLED_RE.findall(text)),
        'stage2b_selector_ready_count': len(STAGE2B_SELECTOR_READY_RE.findall(text)),
        'stage2b_fault_type_estimated_count': len(stage2b_type_matches),
        'stage2b_predicted_type': stage2b_type_match[0] if stage2b_type_match else '',
        'stage2b_decision_reason': stage2b_type_match[1] if stage2b_type_match else '',
        'stage2b_classification_latency_s': float(stage2b_type_match[2]) if stage2b_type_match else float('nan'),
        'stage2b_policy_selected_count': len(stage2b_policy_matches),
        'stage2b_selected_policy': stage2b_policy_match[1] if stage2b_policy_match else '',
        'stage2b_dropout_filter_enable': stage2b_policy_match[2] if stage2b_policy_match else '',
        'stage2b_masking_monitor_enable': stage2b_policy_match[3] if stage2b_policy_match else '',
        'masking_policy_enabled_by_selector_count': len(MASKING_POLICY_ENABLED_RE.findall(text)),
        'masking_policy_disabled_by_selector_count': len(MASKING_POLICY_DISABLED_RE.findall(text)),
        'fault_active_t_s': fault_active_t if fault_active_t is not None else float('nan'),
        'fault_end_t_s': fault_end_t if fault_end_t is not None else float('nan'),
        'fault_timing_source': fault_timing_source if ready_match else '',
        'progress_at_fault_start_m': progress_at_fault_start,
        'progress_at_fault_end_m': progress_at_fault_end,
        'progress_delta_during_fault_m': (progress_at_fault_end - progress_at_fault_start) if (math.isfinite(progress_at_fault_start) and math.isfinite(progress_at_fault_end)) else float('nan'),
        'whole_path_length_m': whole_stats['path_length_m'],
        'whole_mean_speed_mps': whole_stats['mean_speed_mps'],
        'whole_stop_ratio': whole_stats['stop_ratio'],
        'whole_max_stop_streak_s': whole_stats['max_stop_streak_s'],
        'pre_fault_mean_speed_mps': pre_stats['mean_speed_mps'],
        'pre_fault_stop_ratio': pre_stats['stop_ratio'],
        'during_fault_mean_speed_mps': during_stats['mean_speed_mps'],
        'during_fault_stop_ratio': during_stats['stop_ratio'],
        'during_fault_path_length_m': during_stats['path_length_m'],
        'during_fault_max_stop_streak_s': during_stats['max_stop_streak_s'],
        'post_fault_mean_speed_mps': post_stats['mean_speed_mps'],
        'post_fault_stop_ratio': post_stats['stop_ratio'],
        'post_fault_path_length_m': post_stats['path_length_m'],
        'post_fault_max_stop_streak_s': post_stats['max_stop_streak_s'],
    }

    for key, pattern in WARN_PATTERNS.items():
        row[key] = len(pattern.findall(text))
    for key, pattern in EVENT_PATTERNS.items():
        row[key] = len(pattern.findall(text))
    for key, pattern in RECOVERY_PATTERNS.items():
        row[key] = len(pattern.findall(text))
    row['recovery_mentions_total'] = sum(row[key] for key in RECOVERY_PATTERNS)

    return row, trace_rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_condition_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    numeric_fields = [
        'completion_time_s', 'actual_path_length_m', 'whole_stop_ratio', 'whole_mean_speed_mps',
        'during_fault_mean_speed_mps', 'during_fault_stop_ratio', 'progress_delta_during_fault_m',
        'controller_new_path_count', 'robot_out_of_bounds_count', 'raytrace_oob_count',
        'recovery_mentions_total', 'masking_recovery_started_count', 'masking_recovery_complete_count',
        'nav2_masking_recovery_started_count', 'nav2_spin_result_count', 'nav2_goal_resent_count',
        'dropout_filter_ready_count', 'dropout_filter_active_count',
        'dropout_filter_pass_through_count', 'dropout_filter_inactive_count',
        'dropout_filter_enabled_by_selector_count', 'dropout_filter_disabled_by_selector_count',
        'stage2b_selector_ready_count', 'stage2b_fault_type_estimated_count',
        'stage2b_policy_selected_count', 'stage2b_classification_latency_s',
        'masking_policy_enabled_by_selector_count', 'masking_policy_disabled_by_selector_count',
        'local_costmap_warn_count', 'global_costmap_warn_count',
    ]
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row['condition']), []).append(row)

    out: list[dict[str, object]] = []
    for condition, condition_rows in sorted(grouped.items()):
        summary: dict[str, object] = {
            'condition': condition,
            'run_count': len(condition_rows),
            'success_count': sum(row['status'] == 'succeeded' for row in condition_rows),
            'timeout_count': sum(row['status'] == 'timeout' for row in condition_rows),
            'collision_count': sum(row['status'] == 'collided' for row in condition_rows),
        }
        for field in numeric_fields:
            values = [float(row[field]) for row in condition_rows if isinstance(row.get(field), (int, float)) and math.isfinite(float(row[field]))]
            summary[f'{field}_mean'] = safe_mean(values)
            summary[f'{field}_std'] = safe_std(values)
        out.append(summary)
    return out


def build_comparison(condition_summary: list[dict[str, object]]) -> dict[str, object]:
    by_condition = {str(row['condition']): row for row in condition_summary}
    baseline = by_condition.get('baseline')
    fault = by_condition.get('fault')
    if not baseline or not fault:
        return {}

    def delta(field: str) -> float:
        b = baseline.get(f'{field}_mean')
        f = fault.get(f'{field}_mean')
        if not isinstance(b, (int, float)) or not isinstance(f, (int, float)) or not math.isfinite(float(b)) or not math.isfinite(float(f)):
            return float('nan')
        return float(f) - float(b)

    slowdown = delta('completion_time_s')
    baseline_time = float(baseline['completion_time_s_mean']) if math.isfinite(float(baseline['completion_time_s_mean'])) else float('nan')
    return {
        'mean_completion_slowdown_s': slowdown,
        'mean_completion_slowdown_ratio': (slowdown / baseline_time) if math.isfinite(slowdown) and math.isfinite(baseline_time) and baseline_time > 0 else float('nan'),
        'mean_actual_path_length_delta_m': delta('actual_path_length_m'),
        'mean_stop_ratio_delta': delta('whole_stop_ratio'),
        'mean_speed_delta_mps': delta('whole_mean_speed_mps'),
        'mean_during_fault_speed_delta_mps': delta('during_fault_mean_speed_mps'),
        'mean_during_fault_stop_ratio_delta': delta('during_fault_stop_ratio'),
        'mean_controller_new_path_delta': delta('controller_new_path_count'),
        'mean_robot_out_of_bounds_delta': delta('robot_out_of_bounds_count'),
        'mean_recovery_mentions_delta': delta('recovery_mentions_total'),
    }


def main() -> None:
    args = build_parser().parse_args()
    log_dir = args.log_dir.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else (log_dir / 'analysis')
    output_dir.mkdir(parents=True, exist_ok=True)

    log_paths = sorted(log_dir.glob('*.log'))
    if not log_paths:
        raise SystemExit(f'No .log files found in {log_dir}')

    run_rows: list[dict[str, object]] = []
    trace_rows: list[dict[str, object]] = []
    for log_path in log_paths:
        row, traces = analyze_log(log_path, args.path_root.resolve(), args.stop_speed_threshold)
        run_rows.append(row)
        trace_rows.extend(traces)

    run_rows.sort(key=lambda row: (row['world_idx'], row['condition'], row['run_id']))
    trace_rows.sort(key=lambda row: (row['world_idx'], row['condition'], row['run_id'], row['t_s']))

    condition_summary = build_condition_summary(run_rows)
    comparison = build_comparison(condition_summary)
    json_summary = {
        'log_dir': str(log_dir),
        'run_count': len(run_rows),
        'world_ids': sorted({int(row['world_idx']) for row in run_rows}),
        'condition_summary': condition_summary,
        'comparison': comparison,
    }

    write_csv(output_dir / 'run_summary.csv', run_rows)
    write_csv(output_dir / 'trace_samples.csv', trace_rows)
    write_csv(output_dir / 'condition_summary.csv', condition_summary)
    (output_dir / 'summary.json').write_text(json.dumps(json_summary, indent=2))

    print(json.dumps(json_summary, indent=2))
    print(f'Wrote {output_dir / "run_summary.csv"}')
    print(f'Wrote {output_dir / "trace_samples.csv"}')
    print(f'Wrote {output_dir / "condition_summary.csv"}')
    print(f'Wrote {output_dir / "summary.json"}')


if __name__ == '__main__':
    main()
