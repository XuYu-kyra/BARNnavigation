#!/usr/bin/env python3
"""Run a resumable fault campaign across fixed BARN worlds with structured outputs."""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import time
from datetime import datetime
from pathlib import Path

import analyze_fault_pipeline as fault_analysis
import evaluate_paired_fault_study as paired_eval
import run_paired_fault_study as paired

VALID_NAV_STATUSES = {'succeeded', 'timeout', 'collided'}
RUN_ATTEMPT_FIELDS = [
    'campaign_label',
    'fault_label',
    'world_idx',
    'pair_id',
    'condition',
    'attempt_idx',
    'valid',
    'validity_reason',
    'navigation_status',
    'completion_time_s',
    'returncode',
    'cleanup_ok',
    'hard_timed_out',
    'log_path',
    'resource_path',
    'meta_path',
    'started_at',
    'recorded_at',
]
WORLD_STATUS_FIELDS = [
    'world_idx',
    'complete_pairs',
    'valid_runs',
    'invalid_runs',
    'missing_runs',
    'validation_ready',
    'overall_state',
    'next_pair_id',
    'next_conditions',
]


def parse_worlds(spec: str) -> list[int]:
    spec = spec.strip()
    if ',' in spec:
        return [int(part.strip()) for part in spec.split(',') if part.strip()]
    if ':' in spec:
        parts = [int(part.strip()) for part in spec.split(':') if part.strip()]
        if len(parts) not in (2, 3):
            raise ValueError('Range spec must be start:end or start:end:step')
        start, end = parts[0], parts[1]
        step = parts[2] if len(parts) == 3 else 1
        stop = end + (1 if step > 0 else -1)
        return list(range(start, stop, step))
    return [int(spec)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-label', required=True, help='Stable label for this campaign, e.g. frontal_masking_tuned_clean')
    parser.add_argument('--fault-label', default='frontal_masking', help='Fault label recorded in manifests and ledgers')
    parser.add_argument('--campaign-dir', type=Path, default=None, help='Existing or new campaign directory; if omitted a timestamped directory is created under --campaign-root')
    parser.add_argument('--campaign-root', type=Path, default=Path(__file__).resolve().parents[1] / 'experiment_runs' / 'fault_campaigns', help='Root directory for new campaign folders')
    parser.add_argument('--worlds', required=True, help='World selection, e.g. 8,94,274 or 0:20:2')
    parser.add_argument('--setup-path', type=Path, required=True, help='setup_path passed to BARN_runner.launch.py')
    parser.add_argument('--path-root', type=Path, default=Path(__file__).resolve().parents[1] / 'jackal_helper/worlds/BARN/path_files', help='Directory containing BARN path_*.npy files')
    parser.add_argument('--out-file-prefix', default='fault_campaign', help='Prefix used for BARN result filenames')
    parser.add_argument('--target-pairs', type=int, default=6, help='Target number of valid pairs per world')
    parser.add_argument('--validation-pairs', type=int, default=1, help='Initial execution-validation pair count per world')
    parser.add_argument('--max-runs-this-session', type=int, default=None, help='Optional cap on attempted runs in this invocation')
    parser.add_argument('--timeout', type=int, default=300, help='Benchmark timeout passed to BARN runner')
    parser.add_argument('--hard-timeout-buffer', type=int, default=180, help='Extra wall-clock seconds beyond benchmark timeout')
    parser.add_argument('--nav2-log-level', default='INFO', help='Nav2 log level')
    parser.add_argument('--throttle-duration', type=int, default=5, help='Seconds between BARN_Runner pose log messages')
    parser.add_argument('--sleep-between-runs', type=float, default=8.0, help='Seconds between individual runs')
    parser.add_argument('--cleanup-timeout', type=float, default=45.0, help='Seconds budget for cleaning up launch processes after each run')
    parser.add_argument('--resource-sample-period', type=float, default=1.0, help='Seconds between process-group resource samples')
    parser.add_argument('--stop-speed-threshold', type=float, default=0.05, help='Speed below this threshold counts as a stop interval during evaluation')
    parser.add_argument('--stale-process-timeout', type=float, default=20.0, help='Seconds budget for clearing stale ROS/Gazebo processes before the study or after failures')
    parser.add_argument('--seed', type=int, default=8, help='Random seed used for per-pair condition ordering')
    parser.add_argument('--fault-type', default='scan', choices=['scan', 'odom'], help='Fault injector type used for the fault condition')
    parser.add_argument('--scan-fault-start', type=float, default=15.0, help='Fault start time in seconds')
    parser.add_argument('--scan-fault-duration', type=float, default=20.0, help='Fault duration in seconds')
    parser.add_argument('--scan-fault-persistent', action='store_true', help='Keep the scan fault active from start time until run end')
    parser.add_argument('--scan-fault-mode', default='mask', choices=['mask', 'dropout'], help='Scan fault mode: steady mask or intermittent dropout')
    parser.add_argument('--scan-fault-center-deg', type=float, default=0.0, help='Fault sector center angle in degrees')
    parser.add_argument('--scan-fault-width-deg', type=float, default=90.0, help='Fault sector width in degrees')
    parser.add_argument('--scan-fault-dropout-period', type=float, default=1.0, help='For dropout mode: cycle period in seconds')
    parser.add_argument('--scan-fault-dropout-duty', type=float, default=0.5, help='For dropout mode: fraction of cycle spent dropping returns')
    parser.add_argument('--odom-fault-start', type=float, default=20.0, help='Odometry fault start time in seconds')
    parser.add_argument('--odom-fault-duration', type=float, default=20.0, help='Odometry fault duration in seconds')
    parser.add_argument('--odom-fault-linear-scale', type=float, default=1.08, help='Scale factor applied to odometry translation increments during fault')
    parser.add_argument('--odom-fault-yaw-rate-bias-deg-s', type=float, default=1.5, help='Additional yaw-rate bias in deg/s during odometry fault')
    parser.add_argument('--recovery-enable', action='store_true', help='Enable the fault-aware recovery gate for the fault condition')
    parser.add_argument('--recovery-mode', default='scale', choices=['scale', 'masking_reorient', 'nav2_masking_recovery', 'dropout_scan_filter', 'closed_loop_selector'], help='Recovery mode used when --recovery-enable is set')
    parser.add_argument('--recovery-linear-scale', type=float, default=0.35, help='Linear cmd_vel scale used by the legacy recovery gate during fault activity')
    parser.add_argument('--recovery-angular-scale', type=float, default=0.50, help='Angular cmd_vel scale used by the legacy recovery gate during fault activity')
    parser.add_argument('--recovery-active-timeout', type=float, default=1.0, help='Seconds after the last fault-active pulse before the recovery node disengages')
    parser.add_argument('--recovery-trigger-policy', default='immediate', choices=['immediate', 'progress_stall'], help='For masking_reorient: trigger immediately on fault or after odom progress stalls')
    parser.add_argument('--recovery-trigger-delay', type=float, default=0.0, help='For masking_reorient: seconds after fault onset before immediate trigger is allowed')
    parser.add_argument('--recovery-stall-window', type=float, default=5.0, help='For masking_reorient: odom window used for progress-stall detection')
    parser.add_argument('--recovery-stall-distance', type=float, default=0.15, help='For masking_reorient: max displacement over stall window that counts as stalled')
    parser.add_argument('--recovery-rotation-deg', type=float, default=60.0, help='For masking_reorient: in-place active-perception turn angle')
    parser.add_argument('--recovery-angular-speed', type=float, default=0.45, help='For masking_reorient: in-place turn angular speed in rad/s')
    parser.add_argument('--recovery-settle-duration', type=float, default=1.0, help='For masking_reorient: zero-cmd settle time after rotation')
    parser.add_argument('--recovery-dropout-range-max-ratio-threshold', type=float, default=0.55, help='For dropout_scan_filter: frontal sector range_max ratio above which a scan phase is rejected')
    parser.add_argument('--recovery-dropout-near-range-max-fraction', type=float, default=0.98, help='For dropout_scan_filter: fraction of range_max used to classify a beam as near max range')
    return parser


def world_dir(campaign_dir: Path, world_idx: int) -> Path:
    return campaign_dir / 'worlds' / f'world_{world_idx:03d}'


def run_stem(world_idx: int, condition: str, pair_id: int) -> str:
    return f'world_{world_idx:03d}_{condition}_r{pair_id:03d}'


def ensure_world_dirs(base: Path) -> dict[str, Path]:
    paths = {
        'base': base,
        'logs': base / 'logs',
        'resource_logs': base / 'logs' / 'resource_logs',
        'meta': base / 'meta',
        'analysis': base / 'analysis',
        'archive_invalid': base / 'archive_invalid',
        'progress': base / 'progress',
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def campaign_timestamp() -> str:
    return datetime.now().strftime('%Y-%m-%d_%H-%M-%S')


def create_or_load_campaign(args: argparse.Namespace, worlds: list[int]) -> Path:
    if args.campaign_dir:
        campaign_dir = args.campaign_dir.resolve()
        campaign_dir.mkdir(parents=True, exist_ok=True)
    else:
        campaign_dir = (args.campaign_root.resolve() / f'{campaign_timestamp()}_{args.campaign_label}').resolve()
        campaign_dir.mkdir(parents=True, exist_ok=True)

    (campaign_dir / 'summaries').mkdir(parents=True, exist_ok=True)
    (campaign_dir / 'worlds').mkdir(parents=True, exist_ok=True)

    manifest_path = campaign_dir / 'manifest.json'
    manifest = {
        'campaign_label': args.campaign_label,
        'fault_label': args.fault_label,
        'worlds': worlds,
        'setup_path': str(args.setup_path.resolve()),
        'path_root': str(args.path_root.resolve()),
        'target_pairs': args.target_pairs,
        'validation_pairs': args.validation_pairs,
        'timeout': args.timeout,
        'hard_timeout_buffer': args.hard_timeout_buffer,
        'nav2_log_level': args.nav2_log_level,
        'throttle_duration': args.throttle_duration,
        'cleanup_timeout': args.cleanup_timeout,
        'resource_sample_period': args.resource_sample_period,
        'sleep_between_runs': args.sleep_between_runs,
        'stale_process_timeout': args.stale_process_timeout,
        'stop_speed_threshold': args.stop_speed_threshold,
        'seed': args.seed,
        'fault_type': args.fault_type,
        'scan_fault_start': args.scan_fault_start,
        'scan_fault_duration': args.scan_fault_duration,
        'scan_fault_persistent': args.scan_fault_persistent,
        'scan_fault_mode': args.scan_fault_mode,
        'scan_fault_center_deg': args.scan_fault_center_deg,
        'scan_fault_width_deg': args.scan_fault_width_deg,
        'scan_fault_dropout_period': args.scan_fault_dropout_period,
        'scan_fault_dropout_duty': args.scan_fault_dropout_duty,
        'odom_fault_start': args.odom_fault_start,
        'odom_fault_duration': args.odom_fault_duration,
        'odom_fault_linear_scale': args.odom_fault_linear_scale,
        'odom_fault_yaw_rate_bias_deg_s': args.odom_fault_yaw_rate_bias_deg_s,
        'recovery_enable': args.recovery_enable,
        'recovery_mode': args.recovery_mode,
        'recovery_linear_scale': args.recovery_linear_scale,
        'recovery_angular_scale': args.recovery_angular_scale,
        'recovery_active_timeout': args.recovery_active_timeout,
        'recovery_trigger_policy': args.recovery_trigger_policy,
        'recovery_trigger_delay': args.recovery_trigger_delay,
        'recovery_stall_window': args.recovery_stall_window,
        'recovery_stall_distance': args.recovery_stall_distance,
        'recovery_rotation_deg': args.recovery_rotation_deg,
        'recovery_angular_speed': args.recovery_angular_speed,
        'recovery_settle_duration': args.recovery_settle_duration,
        'recovery_dropout_range_max_ratio_threshold': args.recovery_dropout_range_max_ratio_threshold,
        'recovery_dropout_near_range_max_fraction': args.recovery_dropout_near_range_max_fraction,
        'created_at': datetime.now().isoformat(),
    }
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text())
        existing_worlds = [int(v) for v in existing.get('worlds', [])]
        if existing.get('campaign_label') != args.campaign_label or existing_worlds != worlds:
            raise SystemExit(f'Existing campaign manifest at {manifest_path} does not match requested label/world set')
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2))
    return campaign_dir


def read_text_if_exists(path: Path) -> str:
    return path.read_text(errors='ignore') if path.exists() else ''


def assess_run(record: dict[str, object], log_path: Path, path_root: Path, stop_speed_threshold: float) -> tuple[bool, str, dict[str, object]]:
    row, _ = fault_analysis.analyze_log(log_path, path_root, stop_speed_threshold)
    status = str(row.get('status', 'unknown'))
    if int(record.get('returncode', 1)) != 0:
        return False, 'nonzero_returncode', row
    if not bool(record.get('cleanup_ok', False)):
        return False, 'cleanup_failed', row
    if status not in VALID_NAV_STATUSES:
        if bool(record.get('hard_timed_out', False)):
            return False, 'hard_timeout', row
        return False, 'missing_final_status', row
    return True, 'valid', row


def meta_path_for(world_paths: dict[str, Path], world_idx: int, condition: str, pair_id: int) -> Path:
    return world_paths['meta'] / f'{run_stem(world_idx, condition, pair_id)}.json'


def log_path_for(world_paths: dict[str, Path], world_idx: int, condition: str, pair_id: int) -> Path:
    return world_paths['logs'] / f'{run_stem(world_idx, condition, pair_id)}.log'


def resource_path_for(world_paths: dict[str, Path], world_idx: int, condition: str, pair_id: int) -> Path:
    return world_paths['resource_logs'] / f'{run_stem(world_idx, condition, pair_id)}.csv'


def load_run_meta(world_paths: dict[str, Path], world_idx: int, condition: str, pair_id: int, path_root: Path, stop_speed_threshold: float) -> dict[str, object] | None:
    meta_path = meta_path_for(world_paths, world_idx, condition, pair_id)
    if meta_path.exists():
        return json.loads(meta_path.read_text())

    log_path = log_path_for(world_paths, world_idx, condition, pair_id)
    if not log_path.exists():
        return None

    text = read_text_if_exists(log_path)
    row, _ = fault_analysis.analyze_log(log_path, path_root, stop_speed_threshold)
    status = str(row.get('status', 'unknown'))
    valid = status in VALID_NAV_STATUSES and 'HARD_TIMEOUT' not in text
    return {
        'world_idx': world_idx,
        'pair_id': pair_id,
        'condition': condition,
        'attempt_idx': 0,
        'valid': valid,
        'validity_reason': 'inferred_from_log' if valid else 'orphan_log',
        'navigation_status': status,
        'completion_time_s': row.get('completion_time_s', float('nan')),
        'log_path': str(log_path),
        'resource_path': str(resource_path_for(world_paths, world_idx, condition, pair_id)),
        'meta_path': str(meta_path),
        'record': {
            'returncode': 0 if valid else 1,
            'cleanup_ok': valid,
            'hard_timed_out': 'HARD_TIMEOUT' in text,
            'started_at': '',
        },
        'analysis': row,
        'recorded_at': datetime.now().isoformat(),
    }


def archive_existing_run(world_paths: dict[str, Path], world_idx: int, condition: str, pair_id: int, attempt_idx: int) -> None:
    stem = run_stem(world_idx, condition, pair_id)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    for source in [
        log_path_for(world_paths, world_idx, condition, pair_id),
        resource_path_for(world_paths, world_idx, condition, pair_id),
        meta_path_for(world_paths, world_idx, condition, pair_id),
    ]:
        if source.exists():
            target = world_paths['archive_invalid'] / f'{stem}_attempt{attempt_idx:02d}_{stamp}{source.suffix}'
            shutil.move(str(source), str(target))


def load_attempt_entries(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def write_attempt_indexes(campaign_dir: Path, entries: list[dict[str, object]]) -> None:
    summaries = campaign_dir / 'summaries'
    jsonl_path = summaries / 'run_attempts.jsonl'
    csv_path = summaries / 'run_attempts.csv'
    with jsonl_path.open('w') as f:
        for row in entries:
            f.write(json.dumps(row) + '\n')
    with csv_path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=RUN_ATTEMPT_FIELDS)
        writer.writeheader()
        for row in entries:
            writer.writerow({field: row.get(field, '') for field in RUN_ATTEMPT_FIELDS})


def attempt_count(entries: list[dict[str, object]], world_idx: int, pair_id: int, condition: str) -> int:
    return sum(
        int(row.get('world_idx', -1)) == world_idx and int(row.get('pair_id', -1)) == pair_id and str(row.get('condition')) == condition
        for row in entries
    )


def ordered_conditions(seed: int, world_idx: int, pair_id: int) -> list[str]:
    conditions = ['baseline', 'fault']
    rng = random.Random(seed + world_idx * 1000 + pair_id)
    rng.shuffle(conditions)
    return conditions


def run_meta_state(meta: dict[str, object] | None) -> str:
    if meta is None:
        return 'missing'
    return 'valid' if bool(meta.get('valid', False)) else 'invalid'


def pair_state(world_paths: dict[str, Path], world_idx: int, pair_id: int, args: argparse.Namespace) -> dict[str, object]:
    baseline_meta = load_run_meta(world_paths, world_idx, 'baseline', pair_id, args.path_root.resolve(), args.stop_speed_threshold)
    fault_meta = load_run_meta(world_paths, world_idx, 'fault', pair_id, args.path_root.resolve(), args.stop_speed_threshold)
    baseline_state = run_meta_state(baseline_meta)
    fault_state = run_meta_state(fault_meta)
    if baseline_state == 'valid' and fault_state == 'valid':
        state = 'complete'
    elif baseline_state == 'missing' and fault_state == 'missing':
        state = 'missing'
    elif 'invalid' in (baseline_state, fault_state):
        state = 'retry_needed'
    else:
        state = 'partial'
    return {
        'state': state,
        'baseline_meta': baseline_meta,
        'fault_meta': fault_meta,
        'baseline_state': baseline_state,
        'fault_state': fault_state,
    }


def next_conditions_for_pair(world_paths: dict[str, Path], world_idx: int, pair_id: int, args: argparse.Namespace) -> list[str]:
    state = pair_state(world_paths, world_idx, pair_id, args)
    if state['state'] == 'complete':
        return []
    ordered = ordered_conditions(args.seed, world_idx, pair_id)
    missing_or_invalid = []
    for condition in ordered:
        key = f'{condition}_state'
        if state[key] != 'valid':
            missing_or_invalid.append(condition)
    return missing_or_invalid


def world_status_row(world_paths: dict[str, Path], world_idx: int, args: argparse.Namespace) -> dict[str, object]:
    complete_pairs = 0
    valid_runs = 0
    invalid_runs = 0
    missing_runs = 0
    frontier_pair = args.target_pairs
    frontier_conditions: list[str] = []
    first_incomplete_pair = None

    for pair_id in range(1, args.target_pairs + 1):
        state = pair_state(world_paths, world_idx, pair_id, args)
        if state['baseline_state'] == 'valid':
            valid_runs += 1
        elif state['baseline_state'] == 'invalid':
            invalid_runs += 1
        else:
            missing_runs += 1
        if state['fault_state'] == 'valid':
            valid_runs += 1
        elif state['fault_state'] == 'invalid':
            invalid_runs += 1
        else:
            missing_runs += 1

        if state['state'] == 'complete':
            complete_pairs += 1
            continue

        if first_incomplete_pair is None:
            first_incomplete_pair = pair_id
            frontier_pair = pair_id
            frontier_conditions = next_conditions_for_pair(world_paths, world_idx, pair_id, args)

    if complete_pairs >= args.target_pairs:
        overall_state = 'completed'
    elif first_incomplete_pair is None:
        overall_state = 'completed'
    else:
        frontier_state = pair_state(world_paths, world_idx, frontier_pair, args)['state']
        if frontier_state == 'retry_needed':
            overall_state = 'retry_needed'
        elif complete_pairs < args.validation_pairs:
            overall_state = 'pending_validation'
        else:
            overall_state = 'in_progress'

    return {
        'world_idx': world_idx,
        'complete_pairs': complete_pairs,
        'valid_runs': valid_runs,
        'invalid_runs': invalid_runs,
        'missing_runs': missing_runs,
        'validation_ready': complete_pairs >= args.validation_pairs,
        'overall_state': overall_state,
        'next_pair_id': frontier_pair if complete_pairs < args.target_pairs else '',
        'next_conditions': ','.join(frontier_conditions),
    }


def write_world_analysis(world_paths: dict[str, Path], args: argparse.Namespace) -> None:
    log_dir = world_paths['logs']
    if not any(log_dir.glob('*.log')):
        return
    run_rows = paired_eval.build_run_rows(log_dir, args.path_root.resolve(), args.stop_speed_threshold)
    pair_rows = paired_eval.build_pair_rows(run_rows, 'completion_time_s')
    pair_summary = paired_eval.build_pair_summary(pair_rows, 5.0, 0.25)
    drift_rows = paired_eval.build_condition_drift(run_rows)
    resource_rows = paired_eval.build_resource_summary(log_dir)
    summary = {
        'log_dir': str(log_dir),
        'metric': 'completion_time_s',
        'run_count': len(run_rows),
        'pair_summary': pair_summary,
        'condition_drift': drift_rows,
        'resource_summary_available': bool(resource_rows),
    }
    paired_eval.write_csv(world_paths['analysis'] / 'run_summary.csv', run_rows)
    paired_eval.write_csv(world_paths['analysis'] / 'pair_differences.csv', pair_rows)
    paired_eval.write_csv(world_paths['analysis'] / 'condition_drift.csv', drift_rows)
    paired_eval.write_csv(world_paths['analysis'] / 'resource_summary.csv', resource_rows)
    (world_paths['analysis'] / 'summary.json').write_text(json.dumps(summary, indent=2))


def write_campaign_status(campaign_dir: Path, worlds: list[int], args: argparse.Namespace) -> None:
    status_rows = []
    for world_idx in worlds:
        wpaths = ensure_world_dirs(world_dir(campaign_dir, world_idx))
        write_world_analysis(wpaths, args)
        status_rows.append(world_status_row(wpaths, world_idx, args))
    summaries = campaign_dir / 'summaries'
    with (summaries / 'world_status.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=WORLD_STATUS_FIELDS)
        writer.writeheader()
        for row in status_rows:
            writer.writerow(row)
    progress = {
        'campaign_label': args.campaign_label,
        'fault_label': args.fault_label,
        'generated_at': datetime.now().isoformat(),
        'worlds_total': len(worlds),
        'worlds_completed': sum(row['overall_state'] == 'completed' for row in status_rows),
        'worlds_retry_needed': sum(row['overall_state'] == 'retry_needed' for row in status_rows),
        'worlds_pending_validation': sum(row['overall_state'] == 'pending_validation' for row in status_rows),
        'worlds_in_progress': sum(row['overall_state'] == 'in_progress' for row in status_rows),
        'status_rows': status_rows,
    }
    (summaries / 'campaign_status.json').write_text(json.dumps(progress, indent=2))


def write_run_meta(meta_path: Path, meta: dict[str, object]) -> None:
    meta_path.write_text(json.dumps(meta, indent=2))


def maybe_stop(max_runs_this_session: int | None, attempted_runs: int) -> bool:
    return max_runs_this_session is not None and attempted_runs >= max_runs_this_session


def run_condition_once(args: argparse.Namespace, campaign_dir: Path, world_idx: int, pair_id: int, condition: str, attempt_idx: int, attempt_entries: list[dict[str, object]]) -> dict[str, object]:
    wpaths = ensure_world_dirs(world_dir(campaign_dir, world_idx))
    canonical_meta = meta_path_for(wpaths, world_idx, condition, pair_id)
    canonical_log = log_path_for(wpaths, world_idx, condition, pair_id)
    canonical_resource = resource_path_for(wpaths, world_idx, condition, pair_id)
    if canonical_log.exists() or canonical_meta.exists() or canonical_resource.exists():
        archive_existing_run(wpaths, world_idx, condition, pair_id, attempt_idx)

    stale_ok, stale_before = paired.terminate_stale_processes(args.stale_process_timeout)
    if stale_before:
        print(f'[cleanup] world {world_idx:03d} found {len(stale_before)} stale process(es) before run')
    if not stale_ok:
        meta = {
            'world_idx': world_idx,
            'pair_id': pair_id,
            'condition': condition,
            'attempt_idx': attempt_idx,
            'valid': False,
            'validity_reason': 'pre_run_stale_cleanup_failed',
            'navigation_status': 'unknown',
            'completion_time_s': float('nan'),
            'log_path': str(canonical_log),
            'resource_path': str(canonical_resource),
            'meta_path': str(canonical_meta),
            'record': {
                'returncode': 1,
                'cleanup_ok': False,
                'hard_timed_out': False,
                'started_at': '',
            },
            'analysis': {},
            'recorded_at': datetime.now().isoformat(),
        }
        write_run_meta(canonical_meta, meta)
        attempt_entries.append({
            'campaign_label': args.campaign_label,
            'fault_label': args.fault_label,
            'world_idx': world_idx,
            'pair_id': pair_id,
            'condition': condition,
            'attempt_idx': attempt_idx,
            'valid': False,
            'validity_reason': 'pre_run_stale_cleanup_failed',
            'navigation_status': 'unknown',
            'completion_time_s': '',
            'returncode': 1,
            'cleanup_ok': False,
            'hard_timed_out': False,
            'log_path': str(canonical_log),
            'resource_path': str(canonical_resource),
            'meta_path': str(canonical_meta),
            'started_at': '',
            'recorded_at': datetime.now().isoformat(),
        })
        write_attempt_indexes(campaign_dir, attempt_entries)
        return meta

    print(f'[run] world={world_idx:03d} pair={pair_id:03d} condition={condition} attempt={attempt_idx:02d}')
    run_args = argparse.Namespace(**vars(args), world_idx=world_idx)
    record = paired.run_one_condition(run_args, condition, pair_id, wpaths['logs'], wpaths['resource_logs'])
    print(
        f'[done] world={world_idx:03d} pair={pair_id:03d} condition={condition} '
        f'rc={record["returncode"]} wall={record["wall_time_s"]:.1f}s cleanup_ok={record["cleanup_ok"]}'
    )
    valid, validity_reason, analysis = assess_run(record, Path(record['log_path']), args.path_root.resolve(), args.stop_speed_threshold)
    meta = {
        'world_idx': world_idx,
        'pair_id': pair_id,
        'condition': condition,
        'attempt_idx': attempt_idx,
        'valid': valid,
        'validity_reason': validity_reason,
        'navigation_status': analysis.get('status', 'unknown'),
        'completion_time_s': analysis.get('completion_time_s', float('nan')),
        'log_path': record['log_path'],
        'resource_path': record['resource_path'],
        'meta_path': str(canonical_meta),
        'record': record,
        'analysis': analysis,
        'recorded_at': datetime.now().isoformat(),
    }
    write_run_meta(canonical_meta, meta)
    attempt_entries.append({
        'campaign_label': args.campaign_label,
        'fault_label': args.fault_label,
        'world_idx': world_idx,
        'pair_id': pair_id,
        'condition': condition,
        'attempt_idx': attempt_idx,
        'valid': valid,
        'validity_reason': validity_reason,
        'navigation_status': analysis.get('status', 'unknown'),
        'completion_time_s': analysis.get('completion_time_s', ''),
        'returncode': record['returncode'],
        'cleanup_ok': record['cleanup_ok'],
        'hard_timed_out': record['hard_timed_out'],
        'log_path': record['log_path'],
        'resource_path': record['resource_path'],
        'meta_path': str(canonical_meta),
        'started_at': record.get('started_at', ''),
        'recorded_at': datetime.now().isoformat(),
    })
    write_attempt_indexes(campaign_dir, attempt_entries)
    return meta


def world_ready_for_pair(campaign_dir: Path, world_idx: int, pair_id: int, args: argparse.Namespace) -> bool:
    if pair_id <= 1:
        return True
    wpaths = ensure_world_dirs(world_dir(campaign_dir, world_idx))
    prev_status = pair_state(wpaths, world_idx, pair_id - 1, args)
    return prev_status['state'] == 'complete'


def process_pair_for_world(args: argparse.Namespace, campaign_dir: Path, world_idx: int, pair_id: int, attempt_entries: list[dict[str, object]]) -> int:
    if not world_ready_for_pair(campaign_dir, world_idx, pair_id, args):
        return 0
    wpaths = ensure_world_dirs(world_dir(campaign_dir, world_idx))
    conditions = next_conditions_for_pair(wpaths, world_idx, pair_id, args)
    attempted = 0
    for condition in conditions:
        attempt_idx = attempt_count(attempt_entries, world_idx, pair_id, condition) + 1
        meta = run_condition_once(args, campaign_dir, world_idx, pair_id, condition, attempt_idx, attempt_entries)
        attempted += 1
        if not bool(meta.get('valid', False)):
            break
        time.sleep(args.sleep_between_runs)
    return attempted


def main() -> int:
    args = build_parser().parse_args()
    worlds = parse_worlds(args.worlds)
    campaign_dir = create_or_load_campaign(args, worlds)
    attempt_entries = load_attempt_entries(campaign_dir / 'summaries' / 'run_attempts.jsonl')

    for world_idx in worlds:
        ensure_world_dirs(world_dir(campaign_dir, world_idx))

    attempted_runs = 0
    phases = [
        ('validation', range(1, args.validation_pairs + 1)),
        ('bulk', range(args.validation_pairs + 1, args.target_pairs + 1)),
    ]

    for phase_name, pair_ids in phases:
        print(f'[phase] {phase_name}')
        for pair_id in pair_ids:
            print(f'[pair-target] {pair_id:03d}')
            for world_idx in worlds:
                if maybe_stop(args.max_runs_this_session, attempted_runs):
                    write_campaign_status(campaign_dir, worlds, args)
                    print(f'[stop] reached max runs this session: {attempted_runs}')
                    return 0
                attempted = process_pair_for_world(args, campaign_dir, world_idx, pair_id, attempt_entries)
                attempted_runs += attempted
                write_campaign_status(campaign_dir, worlds, args)

    write_campaign_status(campaign_dir, worlds, args)
    print(f'Campaign directory: {campaign_dir}')
    print(f'Attempted runs this session: {attempted_runs}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
