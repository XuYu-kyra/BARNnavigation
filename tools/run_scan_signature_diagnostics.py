#!/usr/bin/env python3
"""Run Stage-1 LiDAR scan-signature diagnostic experiments."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
import run_paired_fault_study as paired  # noqa: E402


def parse_worlds(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return out


def parse_conditions(spec: str) -> list[str]:
    allowed = {'normal', 'masking', 'dropout'}
    conditions = [part.strip() for part in spec.split(',') if part.strip()]
    bad = [part for part in conditions if part not in allowed]
    if bad:
        raise ValueError(f'Unknown condition(s): {bad}. Allowed: {sorted(allowed)}')
    return conditions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='stage1_scan_signature', help='Diagnostic run label')
    parser.add_argument('--output-dir', type=Path, required=True, help='Directory for Stage-1 diagnostic outputs')
    parser.add_argument('--setup-path', type=Path, required=True, help='setup_path passed to BARN_runner.launch.py')
    parser.add_argument('--worlds', default='8,240,94', help='Comma-separated world indices')
    parser.add_argument('--conditions', default='normal,masking,dropout', help='Comma-separated: normal,masking,dropout')
    parser.add_argument('--timeout', type=int, default=90, help='BARN benchmark timeout for each diagnostic run')
    parser.add_argument('--hard-timeout-buffer', type=int, default=180, help='Extra wall-clock seconds beyond timeout')
    parser.add_argument('--cleanup-timeout', type=float, default=45.0, help='Seconds allowed for cleanup')
    parser.add_argument('--stale-process-timeout', type=float, default=20.0, help='Seconds allowed for stale process cleanup')
    parser.add_argument('--sleep-between-runs', type=float, default=8.0, help='Seconds between runs')
    parser.add_argument('--nav2-log-level', default='WARN', help='Nav2 log level')
    parser.add_argument('--throttle-duration', type=int, default=5, help='BARN runner pose log throttle')
    parser.add_argument('--scan-fault-start', type=float, default=15.0, help='Fault start time in sim seconds')
    parser.add_argument('--scan-fault-duration', type=float, default=20.0, help='Fault duration in sim seconds')
    parser.add_argument('--scan-fault-center-deg', type=float, default=0.0, help='Fault sector center angle')
    parser.add_argument('--scan-fault-width-deg', type=float, default=90.0, help='Fault sector width')
    parser.add_argument('--scan-fault-dropout-period', type=float, default=1.0, help='Dropout cycle period')
    parser.add_argument('--scan-fault-dropout-duty', type=float, default=0.5, help='Dropout duty cycle')
    parser.add_argument('--range-max-epsilon-m', type=float, default=1e-3, help='Tolerance for range_max feature extraction')
    parser.add_argument('--reference-max-age-s', type=float, default=0.25, help='Max age for raw reference scan pairing')
    parser.add_argument('--resume', action='store_true', help='Skip diagnostic runs that already produced feature samples')
    return parser


def build_launch_cmd(args: argparse.Namespace, world_idx: int, condition: str, out_file_name: str) -> list[str]:
    cmd = [
        'ros2', 'launch', 'jackal_helper', 'BARN_runner.launch.py',
        f'world_idx:={world_idx}',
        'gui:=false',
        'rviz:=false',
        f'timeout:={args.timeout}',
        f'throttle_duration:={args.throttle_duration}',
        f'out_file:={out_file_name}',
        f'setup_path:={args.setup_path.resolve()}',
        f'nav2_log_level:={args.nav2_log_level}',
    ]
    if condition in ('masking', 'dropout'):
        cmd.extend([
            'scan_fault_enable:=true',
            f'scan_fault_start:={args.scan_fault_start:.3f}',
            f'scan_fault_duration:={args.scan_fault_duration:.3f}',
            'scan_fault_persistent:=false',
            f'scan_fault_mode:={"mask" if condition == "masking" else "dropout"}',
            f'scan_fault_center_deg:={args.scan_fault_center_deg:.3f}',
            f'scan_fault_width_deg:={args.scan_fault_width_deg:.3f}',
            f'scan_fault_dropout_period:={args.scan_fault_dropout_period:.3f}',
            f'scan_fault_dropout_duty:={args.scan_fault_dropout_duty:.3f}',
        ])
    return cmd


def build_recorder_cmd(args: argparse.Namespace, condition: str, output_csv: Path) -> list[str]:
    scan_topic = '/front/scan_faulted' if condition in ('masking', 'dropout') else '/front/scan'
    return [
        'ros2', 'run', 'jackal_helper', 'scan_signature_recorder.py',
        '--ros-args',
        '-p', f'scan_topic:={scan_topic}',
        '-p', 'reference_topic:=/front/scan',
        '-p', 'fault_active_topic:=/fault/scan_active',
        '-p', f'output_csv:={output_csv}',
        '-p', f'sector_center_deg:={args.scan_fault_center_deg:.3f}',
        '-p', f'sector_width_deg:={args.scan_fault_width_deg:.3f}',
        '-p', f'range_max_epsilon_m:={args.range_max_epsilon_m}',
        '-p', f'reference_max_age_s:={args.reference_max_age_s}',
    ]


def cleanup_popen(proc: subprocess.Popen, cleanup_timeout: float, log_file) -> bool:
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return True
    ok, _ = paired.cleanup_process_group(pgid, cleanup_timeout, log_file)
    return ok


def count_feature_samples(feature_csv: Path) -> int:
    if not feature_csv.exists():
        return 0
    with feature_csv.open('r', encoding='utf-8') as f:
        return max(0, sum(1 for _ in f) - 1)


def run_one(args: argparse.Namespace, output_dir: Path, world_idx: int, condition: str) -> dict[str, object]:
    run_dir = output_dir / 'runs' / f'world_{world_idx:03d}' / condition
    logs_dir = run_dir / 'logs'
    features_dir = run_dir / 'features'
    logs_dir.mkdir(parents=True, exist_ok=True)
    features_dir.mkdir(parents=True, exist_ok=True)

    feature_csv = features_dir / 'scan_signature_features.csv'
    if args.resume and (run_dir / 'metadata.json').exists() and count_feature_samples(feature_csv) > 0:
        sample_count = count_feature_samples(feature_csv)
        print(f'[skip] world={world_idx:03d} condition={condition} samples={sample_count}')
        return {
            'world_idx': world_idx,
            'condition': condition,
            'returncode': 0,
            'timed_out': False,
            'wall_s': 0.0,
            'feature_csv': str(feature_csv),
            'sample_count': sample_count,
            'launch_cleanup_ok': True,
            'recorder_cleanup_ok': True,
            'run_dir': str(run_dir),
            'skipped_existing': True,
        }
    launch_log_path = logs_dir / 'launch.log'
    recorder_log_path = logs_dir / 'recorder.log'
    out_file_name = f'{args.label}_world{world_idx:03d}_{condition}.txt'
    launch_cmd = build_launch_cmd(args, world_idx, condition, out_file_name)
    recorder_cmd = build_recorder_cmd(args, condition, feature_csv)

    metadata = {
        'label': args.label,
        'world_idx': world_idx,
        'condition': condition,
        'scan_topic_recorded': '/front/scan_faulted' if condition in ('masking', 'dropout') else '/front/scan',
        'reference_topic': '/front/scan',
        'fault_active_topic': '/fault/scan_active',
        'fault_type': 'none' if condition == 'normal' else 'scan',
        'fault_mode': 'none' if condition == 'normal' else ('mask' if condition == 'masking' else 'dropout'),
        'fault_start_s': None if condition == 'normal' else args.scan_fault_start,
        'fault_duration_s': None if condition == 'normal' else args.scan_fault_duration,
        'fault_persistent': False,
        'fault_center_deg': None if condition == 'normal' else args.scan_fault_center_deg,
        'fault_width_deg': None if condition == 'normal' else args.scan_fault_width_deg,
        'dropout_period_s': None if condition != 'dropout' else args.scan_fault_dropout_period,
        'dropout_duty_cycle': None if condition != 'dropout' else args.scan_fault_dropout_duty,
        'feature_csv': str(feature_csv),
        'launch_log': str(launch_log_path),
        'recorder_log': str(recorder_log_path),
        'launch_cmd': launch_cmd,
        'recorder_cmd': recorder_cmd,
        'started_at': datetime.now().isoformat(),
    }
    (run_dir / 'metadata.json').write_text(json.dumps(metadata, indent=2))

    print(f'[run] world={world_idx:03d} condition={condition}')
    with recorder_log_path.open('w') as recorder_log, launch_log_path.open('w') as launch_log:
        recorder_proc = subprocess.Popen(
            recorder_cmd,
            stdout=recorder_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        time.sleep(2.0)
        started = time.time()
        launch_proc = subprocess.Popen(
            launch_cmd,
            stdout=launch_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        hard_timeout = max(args.timeout + args.hard_timeout_buffer, args.hard_timeout_buffer)
        rc = None
        timed_out = False
        try:
            rc = launch_proc.wait(timeout=hard_timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            launch_log.write(f'\n[scan_signature_diagnostics] HARD_TIMEOUT after {hard_timeout} s\n')
            launch_log.flush()
            cleanup_popen(launch_proc, args.cleanup_timeout, launch_log)
            rc = 124
        finally:
            cleanup_popen(recorder_proc, args.cleanup_timeout, recorder_log)

        elapsed_wall = time.time() - started
        launch_cleanup_ok = cleanup_popen(launch_proc, args.cleanup_timeout, launch_log)
        recorder_cleanup_ok = cleanup_popen(recorder_proc, args.cleanup_timeout, recorder_log)

    sample_count = count_feature_samples(feature_csv)

    record = {
        'world_idx': world_idx,
        'condition': condition,
        'returncode': rc,
        'timed_out': timed_out,
        'wall_s': elapsed_wall,
        'feature_csv': str(feature_csv),
        'sample_count': sample_count,
        'launch_cleanup_ok': launch_cleanup_ok,
        'recorder_cleanup_ok': recorder_cleanup_ok,
        'run_dir': str(run_dir),
    }
    print(
        f'[done] world={world_idx:03d} condition={condition} rc={rc} '
        f'wall={elapsed_wall:.1f}s samples={sample_count} cleanup={launch_cleanup_ok and recorder_cleanup_ok}'
    )
    return record


def main() -> int:
    args = build_parser().parse_args()
    worlds = parse_worlds(args.worlds)
    conditions = parse_conditions(args.conditions)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        'label': args.label,
        'worlds': worlds,
        'conditions': conditions,
        'setup_path': str(args.setup_path.resolve()),
        'created_at': datetime.now().isoformat(),
        'fault_parameters': {
            'scan_fault_start': args.scan_fault_start,
            'scan_fault_duration': args.scan_fault_duration,
            'scan_fault_center_deg': args.scan_fault_center_deg,
            'scan_fault_width_deg': args.scan_fault_width_deg,
            'scan_fault_dropout_period': args.scan_fault_dropout_period,
            'scan_fault_dropout_duty': args.scan_fault_dropout_duty,
        },
    }
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2))

    stale_ok, stale = paired.terminate_stale_processes(args.stale_process_timeout)
    if not stale_ok:
        print('[warn] stale process cleanup did not fully complete before diagnostics')
    if stale:
        (output_dir / 'stale_processes_before.json').write_text(json.dumps(stale, indent=2))

    records = []
    for world_idx in worlds:
        for condition in conditions:
            records.append(run_one(args, output_dir, world_idx, condition))
            time.sleep(args.sleep_between_runs)

    (output_dir / 'run_records.json').write_text(json.dumps(records, indent=2))
    print(f'Diagnostic directory: {output_dir}')
    print('Next: run tools/analyze_scan_signature_diagnostics.py on this directory.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
