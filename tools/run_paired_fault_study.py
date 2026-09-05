#!/usr/bin/env python3
"""Run paired baseline-vs-fault studies with random ordering and stopping checks."""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import evaluate_paired_fault_study as paired_eval


STALE_PROCESS_PATTERNS = [
    'BARN_runner.launch.py',
    'gz sim',
    'planner_server',
    'controller_server',
    'behavior_server',
    'bt_navigator',
    'amcl',
    'laser_scan_fault_injector',
    'masking_reorientation_recovery',
    'masking_nav2_recovery_supervisor',
    'dropout_scan_recovery_filter',
    'odometry_fault_injector',
    'lifecycle_manager_navigation',
    'lifecycle_manager_localization',
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world-idx', type=int, required=True, help='BARN world index to study')
    parser.add_argument('--setup-path', type=Path, required=True, help='setup_path passed to BARN_runner.launch.py')
    parser.add_argument('--log-dir', type=Path, required=True, help='Directory for paired study outputs')
    parser.add_argument('--path-root', type=Path, default=Path(__file__).resolve().parents[1] / 'jackal_helper/worlds/BARN/path_files', help='Directory containing BARN path_*.npy files')
    parser.add_argument('--out-file-prefix', default='paired_fault_study', help='Prefix used for BARN result filenames')
    parser.add_argument('--timeout', type=int, default=300, help='Benchmark timeout passed to BARN runner')
    parser.add_argument('--hard-timeout-buffer', type=int, default=180, help='Extra wall-clock seconds beyond benchmark timeout')
    parser.add_argument('--nav2-log-level', default='INFO', help='Nav2 log level')
    parser.add_argument('--throttle-duration', type=int, default=5, help='Seconds between BARN_Runner pose log messages')
    parser.add_argument('--sleep-between-runs', type=float, default=8.0, help='Seconds between individual runs')
    parser.add_argument('--cleanup-timeout', type=float, default=25.0, help='Seconds budget for cleaning up launch processes after each run')
    parser.add_argument('--resource-sample-period', type=float, default=1.0, help='Seconds between process-group resource samples')
    parser.add_argument('--stop-speed-threshold', type=float, default=0.05, help='Speed below this threshold counts as a stop interval during evaluation')
    parser.add_argument('--stale-process-timeout', type=float, default=20.0, help='Seconds budget for clearing stale ROS/Gazebo processes before the study or after failures')
    parser.add_argument('--seed', type=int, default=8, help='Random seed used for per-pair condition ordering')
    parser.add_argument('--initial-pairs', type=int, default=6, help='Minimum number of pairs before evaluating stopping rules')
    parser.add_argument('--pair-step', type=int, default=2, help='Evaluate stopping rules every N additional pairs after the initial block')
    parser.add_argument('--max-pairs', type=int, default=14, help='Hard cap on number of pairs')
    parser.add_argument('--ci-halfwidth-abs-threshold', type=float, default=5.0, help='Absolute stopping target for 95%% CI half-width')
    parser.add_argument('--ci-halfwidth-rel-threshold', type=float, default=0.25, help='Relative stopping target for 95%% CI half-width as a fraction of |mean difference|')
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


def build_launch_cmd(args: argparse.Namespace, out_file_name: str, condition: str) -> list[str]:
    cmd = [
        'ros2', 'launch', 'jackal_helper', 'BARN_runner.launch.py',
        f'world_idx:={args.world_idx}',
        'gui:=false',
        'rviz:=false',
        f'timeout:={args.timeout}',
        f'throttle_duration:={args.throttle_duration}',
        f'out_file:={out_file_name}',
        f'setup_path:={args.setup_path.resolve()}',
        f'nav2_log_level:={args.nav2_log_level}',
    ]
    if condition == 'fault':
        if args.fault_type == 'scan':
            cmd.extend([
                'scan_fault_enable:=true',
                f'scan_fault_start:={args.scan_fault_start}',
                f'scan_fault_duration:={args.scan_fault_duration}',
                f'scan_fault_persistent:={str(args.scan_fault_persistent).lower()}',
                f'scan_fault_mode:={args.scan_fault_mode}',
                f'scan_fault_center_deg:={args.scan_fault_center_deg}',
                f'scan_fault_width_deg:={args.scan_fault_width_deg}',
                f'scan_fault_dropout_period:={args.scan_fault_dropout_period}',
                f'scan_fault_dropout_duty:={args.scan_fault_dropout_duty}',
            ])
        elif args.fault_type == 'odom':
            cmd.extend([
                'odom_fault_enable:=true',
                f'odom_fault_start:={args.odom_fault_start}',
                f'odom_fault_duration:={args.odom_fault_duration}',
                f'odom_fault_linear_scale:={args.odom_fault_linear_scale}',
                f'odom_fault_yaw_rate_bias_deg_s:={args.odom_fault_yaw_rate_bias_deg_s}',
            ])
        if args.recovery_enable:
            cmd.extend([
                'recovery_enable:=true',
                f'recovery_mode:={args.recovery_mode}',
                f'recovery_linear_scale:={args.recovery_linear_scale}',
                f'recovery_angular_scale:={args.recovery_angular_scale}',
                f'recovery_active_timeout:={args.recovery_active_timeout}',
                f'recovery_trigger_policy:={args.recovery_trigger_policy}',
                f'recovery_trigger_delay:={args.recovery_trigger_delay}',
                f'recovery_stall_window:={args.recovery_stall_window}',
                f'recovery_stall_distance:={args.recovery_stall_distance}',
                f'recovery_rotation_deg:={args.recovery_rotation_deg}',
                f'recovery_angular_speed:={args.recovery_angular_speed}',
                f'recovery_settle_duration:={args.recovery_settle_duration}',
                f'recovery_dropout_range_max_ratio_threshold:={args.recovery_dropout_range_max_ratio_threshold}',
                f'recovery_dropout_near_range_max_fraction:={args.recovery_dropout_near_range_max_fraction}',
            ])
    return cmd


def collect_process_group_stats(pgid: int) -> dict[str, float]:
    proc = subprocess.run(
        ['ps', '-eo', 'pid=,pgid=,pcpu=,rss=,comm='],
        capture_output=True,
        text=True,
        check=False,
    )
    process_count = 0
    total_cpu = 0.0
    total_rss_mb = 0.0
    for line in proc.stdout.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        _, line_pgid, cpu_percent, rss_kb, _ = parts
        if int(line_pgid) != pgid:
            continue
        process_count += 1
        total_cpu += float(cpu_percent)
        total_rss_mb += float(rss_kb) / 1024.0
    load1, load5, load15 = os.getloadavg()
    mem_available_mb = float('nan')
    with open('/proc/meminfo', 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('MemAvailable:'):
                mem_available_mb = float(line.split()[1]) / 1024.0
                break
    return {
        'load1': load1,
        'load5': load5,
        'load15': load15,
        'mem_available_mb': mem_available_mb,
        'pg_process_count': process_count,
        'pg_cpu_percent': total_cpu,
        'pg_rss_mb': total_rss_mb,
    }


def resource_monitor(pgid: int, csv_path: Path, stop_event: threading.Event, sample_period: float) -> None:
    with csv_path.open('w', newline='') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                't_rel_s', 'load1', 'load5', 'load15', 'mem_available_mb',
                'pg_process_count', 'pg_cpu_percent', 'pg_rss_mb',
            ],
        )
        writer.writeheader()
        start = time.time()
        while not stop_event.is_set():
            stats = collect_process_group_stats(pgid)
            row = {'t_rel_s': time.time() - start}
            row.update(stats)
            writer.writerow(row)
            f.flush()
            stop_event.wait(sample_period)


def process_group_alive(pgid: int) -> bool:
    proc = subprocess.run(['ps', '-eo', 'pgid='], capture_output=True, text=True, check=False)
    for line in proc.stdout.splitlines():
        if line.strip() and int(line.strip()) == pgid:
            return True
    return False


def wait_for_process_group_exit(pgid: int, timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not process_group_alive(pgid):
            return True
        time.sleep(0.5)
    return not process_group_alive(pgid)


def signal_process_group(pgid: int, sig: signal.Signals) -> bool:
    try:
        os.killpg(pgid, sig)
        return True
    except ProcessLookupError:
        return False


def cleanup_process_group(pgid: int, cleanup_timeout: float, log_file) -> tuple[bool, list[str]]:
    actions: list[str] = []
    if not process_group_alive(pgid):
        return True, actions

    stages = [
        (signal.SIGINT, min(8.0, cleanup_timeout * 0.35), 'SIGINT'),
        (signal.SIGTERM, min(8.0, cleanup_timeout * 0.35), 'SIGTERM'),
        (signal.SIGKILL, max(3.0, cleanup_timeout * 0.30), 'SIGKILL'),
    ]
    remaining = cleanup_timeout
    for sig, suggested_wait, label in stages:
        if not process_group_alive(pgid):
            return True, actions
        wait_s = min(suggested_wait, max(1.0, remaining))
        sent = signal_process_group(pgid, sig)
        actions.append(f'{label}:sent={sent},wait={wait_s:.1f}s')
        if log_file is not None:
            log_file.write(f'[paired_fault_study] cleanup stage {label} for pgid={pgid}, wait={wait_s:.1f}s\n')
            log_file.flush()
        if wait_for_process_group_exit(pgid, wait_s):
            return True, actions
        remaining = max(0.0, remaining - wait_s)

    return not process_group_alive(pgid), actions


def find_stale_processes() -> list[dict[str, object]]:
    proc = subprocess.run(['ps', '-eo', 'pid=,comm=,args='], capture_output=True, text=True, check=False)
    out: list[dict[str, object]] = []
    current_pid = os.getpid()
    parent_pid = os.getppid()
    for line in proc.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid = int(parts[0])
        if pid in (current_pid, parent_pid):
            continue
        comm = parts[1]
        args = parts[2]
        matched = next((pattern for pattern in STALE_PROCESS_PATTERNS if pattern in args or pattern == comm), None)
        if matched:
            out.append({'pid': pid, 'comm': comm, 'args': args, 'pattern': matched})
    return out


def terminate_stale_processes(timeout_s: float) -> tuple[bool, list[dict[str, object]]]:
    stale = find_stale_processes()
    if not stale:
        return True, []

    pid_list = [int(row['pid']) for row in stale]
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        for pid in pid_list:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        deadline = time.time() + max(1.0, timeout_s / 3.0)
        while time.time() < deadline:
            remaining = {int(row['pid']) for row in find_stale_processes() if int(row['pid']) in pid_list}
            if not remaining:
                return True, stale
            time.sleep(0.5)

    remaining = {int(row['pid']) for row in find_stale_processes() if int(row['pid']) in pid_list}
    return not remaining, stale


def run_one_condition(args: argparse.Namespace, condition: str, run_id: int, log_dir: Path, resource_dir: Path) -> dict[str, object]:
    out_file_name = f'{args.out_file_prefix}_world{args.world_idx:03d}_{condition}_r{run_id:03d}.txt'
    log_path = log_dir / f'world_{args.world_idx:03d}_{condition}_r{run_id:03d}.log'
    resource_path = resource_dir / f'world_{args.world_idx:03d}_{condition}_r{run_id:03d}.csv'
    cmd = build_launch_cmd(args, out_file_name, condition)
    hard_timeout = max(args.timeout + args.hard_timeout_buffer, args.hard_timeout_buffer)
    started_at = datetime.now().isoformat()
    start_wall = time.time()
    cleanup_ok = True
    cleanup_actions: list[str] = []

    with log_path.open('w') as log_file:
        log_file.write('COMMAND: ' + ' '.join(cmd) + '\n')
        log_file.write(f'STARTED_AT: {started_at}\n\n')
        log_file.flush()

        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        pgid = process.pid
        stop_event = threading.Event()
        monitor_thread = threading.Thread(
            target=resource_monitor,
            args=(pgid, resource_path, stop_event, args.resource_sample_period),
            daemon=True,
        )
        monitor_thread.start()

        try:
            returncode = process.wait(timeout=hard_timeout)
            hard_timed_out = False
        except subprocess.TimeoutExpired:
            returncode = 124
            hard_timed_out = True
            log_file.write(f'\n[paired_fault_study] HARD_TIMEOUT after {hard_timeout} s\n')
            log_file.flush()
            cleanup_ok, cleanup_actions = cleanup_process_group(pgid, args.cleanup_timeout, log_file)
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass
        finally:
            stop_event.set()
            monitor_thread.join(timeout=max(1.0, args.resource_sample_period * 2.0))

    if not hard_timed_out:
        cleanup_ok, cleanup_actions = cleanup_process_group(pgid, args.cleanup_timeout, None)

    return {
        'condition': condition,
        'run_id': run_id,
        'log_path': str(log_path),
        'resource_path': str(resource_path),
        'out_file_name': out_file_name,
        'returncode': returncode,
        'hard_timed_out': hard_timed_out,
        'cleanup_ok': cleanup_ok,
        'cleanup_actions': cleanup_actions,
        'wall_time_s': time.time() - start_wall,
        'started_at': started_at,
    }


def should_evaluate(pair_count: int, initial_pairs: int, pair_step: int) -> bool:
    if pair_count < initial_pairs:
        return False
    return (pair_count - initial_pairs) % pair_step == 0


def evaluate_progress(args: argparse.Namespace, log_dir: Path) -> dict[str, object]:
    run_rows = paired_eval.build_run_rows(log_dir, args.path_root.resolve(), args.stop_speed_threshold)
    pair_rows = paired_eval.build_pair_rows(run_rows, 'completion_time_s')
    pair_summary = paired_eval.build_pair_summary(
        pair_rows,
        args.ci_halfwidth_abs_threshold,
        args.ci_halfwidth_rel_threshold,
    )
    drift_rows = paired_eval.build_condition_drift(run_rows)
    return {
        'pair_summary': pair_summary,
        'condition_drift': drift_rows,
    }


def main() -> int:
    args = build_parser().parse_args()
    log_dir = args.log_dir.resolve()
    resource_dir = log_dir / 'resource_logs'
    progress_dir = log_dir / 'progress'
    log_dir.mkdir(parents=True, exist_ok=True)
    resource_dir.mkdir(parents=True, exist_ok=True)
    progress_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        'world_idx': args.world_idx,
        'setup_path': str(args.setup_path.resolve()),
        'path_root': str(args.path_root.resolve()),
        'timeout': args.timeout,
        'hard_timeout_buffer': args.hard_timeout_buffer,
        'nav2_log_level': args.nav2_log_level,
        'throttle_duration': args.throttle_duration,
        'stop_speed_threshold': args.stop_speed_threshold,
        'stale_process_timeout': args.stale_process_timeout,
        'seed': args.seed,
        'fault_type': args.fault_type,
        'initial_pairs': args.initial_pairs,
        'pair_step': args.pair_step,
        'max_pairs': args.max_pairs,
        'ci_halfwidth_abs_threshold': args.ci_halfwidth_abs_threshold,
        'ci_halfwidth_rel_threshold': args.ci_halfwidth_rel_threshold,
        'scan_fault_start': args.scan_fault_start,
        'scan_fault_duration': args.scan_fault_duration,
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
    (log_dir / 'study_manifest.json').write_text(json.dumps(manifest, indent=2))

    rng = random.Random(args.seed)
    run_records: list[dict[str, object]] = []
    pair_evaluations: list[dict[str, object]] = []
    cleanup_failures: list[dict[str, object]] = []

    stale_ok, stale_before = terminate_stale_processes(args.stale_process_timeout)
    if stale_before:
        print(f'[cleanup] found {len(stale_before)} stale process(es) before study')
    if not stale_ok:
        print('[abort] could not clear stale processes before study start')
        cleanup_failures.append({
            'phase': 'pre_study',
            'stale_processes': stale_before,
        })
        (log_dir / 'cleanup_failures.json').write_text(json.dumps(cleanup_failures, indent=2))
        return 1

    for pair_id in range(1, args.max_pairs + 1):
        conditions = ['baseline', 'fault']
        rng.shuffle(conditions)
        print(f'[pair {pair_id:03d}] order={conditions}')

        for condition in conditions:
            print(f'[run] pair={pair_id:03d} condition={condition}')
            record = run_one_condition(args, condition, pair_id, log_dir, resource_dir)
            run_records.append(record)
            print(
                f'[done] pair={pair_id:03d} condition={condition} rc={record["returncode"]} '
                f'wall={record["wall_time_s"]:.1f}s cleanup_ok={record["cleanup_ok"]}'
            )
            if not record['cleanup_ok']:
                failure = {
                    'phase': 'post_run',
                    'pair_id': pair_id,
                    'condition': condition,
                    'record': record,
                    'stale_processes': find_stale_processes(),
                }
                cleanup_failures.append(failure)
                print(f'[abort] cleanup failed after pair={pair_id:03d} condition={condition}; stopping study to avoid contamination')
                (log_dir / 'run_records.json').write_text(json.dumps(run_records, indent=2))
                (log_dir / 'pair_evaluations.json').write_text(json.dumps(pair_evaluations, indent=2))
                (log_dir / 'cleanup_failures.json').write_text(json.dumps(cleanup_failures, indent=2))
                return 1
            time.sleep(args.sleep_between_runs)

        if should_evaluate(pair_id, args.initial_pairs, args.pair_step):
            evaluation = evaluate_progress(args, log_dir)
            evaluation['evaluated_after_pair'] = pair_id
            pair_evaluations.append(evaluation)
            (progress_dir / f'pair_{pair_id:03d}_evaluation.json').write_text(json.dumps(evaluation, indent=2))
            summary = evaluation['pair_summary']
            print(
                f'[eval] pairs={summary["pair_count"]} mean_d={summary["mean_difference"]:.3f}s '
                f'ci95_halfwidth={summary["ci95_halfwidth"]:.3f}s stop={summary["recommended_stop"]}'
            )
            if summary['recommended_stop']:
                print(f'[stop] stopping rule reached after {pair_id} pairs')
                break

    (log_dir / 'run_records.json').write_text(json.dumps(run_records, indent=2))
    (log_dir / 'pair_evaluations.json').write_text(json.dumps(pair_evaluations, indent=2))
    (log_dir / 'cleanup_failures.json').write_text(json.dumps(cleanup_failures, indent=2))
    print(f'Wrote {log_dir / "run_records.json"}')
    print(f'Wrote {log_dir / "pair_evaluations.json"}')
    print(f'Wrote {log_dir / "cleanup_failures.json"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
