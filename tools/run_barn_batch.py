#!/usr/bin/env python3
"""Run BARN worlds sequentially for one baseline and capture per-world logs."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path


def parse_worlds(spec: str) -> list[int]:
    spec = spec.strip()
    if spec == 'all':
        return list(range(300))
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
    parser.add_argument('--label', required=True, help='Short label for this batch, e.g. original_long or tuned_long.')
    parser.add_argument('--setup-path', type=Path, required=True, help='setup_path passed to BARN_runner.launch.py.')
    parser.add_argument('--worlds', default='all', help='World selection: all, 0:299, 0:299:2, or comma-separated list.')
    parser.add_argument('--timeout', type=int, default=300, help='Benchmark timeout passed to BARN runner.')
    parser.add_argument('--hard-timeout-buffer', type=int, default=180, help='Extra wall-clock seconds allowed beyond benchmark timeout.')
    parser.add_argument('--throttle-duration', type=int, default=5, help='Seconds between BARN_Runner pose log messages.')
    parser.add_argument('--nav2-log-level', default='INFO', help='Nav2 log level. Use INFO if you want behavior/recovery traces.')
    parser.add_argument('--sleep-between', type=float, default=8.0, help='Seconds to sleep between worlds.')
    parser.add_argument('--run-root', type=Path, default=Path(__file__).resolve().parents[1] / 'experiment_runs', help='Root folder for batch outputs.')
    parser.add_argument('--resume', action='store_true', help='Skip worlds whose log already contains a finished benchmark status line.')
    return parser


def log_contains_finish(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    text = log_path.read_text(errors='ignore')
    return 'Test finished' in text and 'Navigation ' in text


def log_contains_runner_crash(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    lines = log_path.read_text(errors='ignore').splitlines()
    return any('Traceback (most recent call last):' in line for line in lines) or any(
        'process has died' in line and 'barn_runner.py' in line
        for line in lines
    )


def main() -> int:
    args = build_parser().parse_args()
    worlds = parse_worlds(args.worlds)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    batch_dir = args.run_root.resolve() / f'{timestamp}_{args.label}'
    logs_dir = batch_dir / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)

    out_file_name = f'{timestamp}_{args.label}_results.txt'
    manifest = {
        'label': args.label,
        'setup_path': str(args.setup_path.resolve()),
        'worlds': worlds,
        'timeout': args.timeout,
        'hard_timeout_buffer': args.hard_timeout_buffer,
        'throttle_duration': args.throttle_duration,
        'nav2_log_level': args.nav2_log_level,
        'out_file_name': out_file_name,
        'created_at': timestamp,
    }
    (batch_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2))

    print(f'Batch directory: {batch_dir}')
    print('Make sure this shell has already sourced /opt/ros/jazzy/setup.bash and install/local_setup.bash.')

    failures = []
    for world_idx in worlds:
        log_path = logs_dir / f'world_{world_idx:03d}.log'
        if args.resume and log_contains_finish(log_path):
            print(f'[skip] world {world_idx:03d} already finished according to {log_path.name}')
            continue

        cmd = [
            'ros2', 'launch', 'jackal_helper', 'BARN_runner.launch.py',
            f'world_idx:={world_idx}',
            'gui:=false',
            'rviz:=false',
            f'timeout:={args.timeout}',
            f'throttle_duration:={int(args.throttle_duration)}',
            f'out_file:={out_file_name}',
            f'setup_path:={args.setup_path.resolve()}',
            f'nav2_log_level:={args.nav2_log_level}',
        ]
        hard_timeout = max(args.timeout + args.hard_timeout_buffer, args.hard_timeout_buffer)
        print(f'[run] world {world_idx:03d} -> {log_path.name}')
        print('      ' + ' '.join(cmd))
        started = time.time()
        with log_path.open('w') as log_file:
            log_file.write('COMMAND: ' + ' '.join(cmd) + '\n')
            log_file.write(f'STARTED_AT: {datetime.now().isoformat()}\n\n')
            log_file.flush()
            try:
                completed = subprocess.run(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=hard_timeout,
                    check=False,
                )
                rc = completed.returncode
            except subprocess.TimeoutExpired:
                rc = 124
                log_file.write(f'\n[batch_runner] HARD_TIMEOUT after {hard_timeout} s\n')
        elapsed_wall = time.time() - started
        finished = log_contains_finish(log_path)
        runner_crashed = log_contains_runner_crash(log_path)
        print(f'[done] world {world_idx:03d} rc={rc} wall={elapsed_wall:.1f}s finished={finished} runner_crashed={runner_crashed}')
        if rc != 0 or not finished:
            failures.append({'world_idx': world_idx, 'returncode': rc, 'finished': finished, 'runner_crashed': runner_crashed, 'log_path': str(log_path)})
        time.sleep(args.sleep_between)

    (batch_dir / 'failures.json').write_text(json.dumps(failures, indent=2))
    print(f'Finished batch with {len(failures)} non-zero return codes.')
    print(f'Per-world logs: {logs_dir}')
    print(f'Results file name inside repo res/: {out_file_name}')
    if failures:
        print('Inspect failures.json before trusting the batch summary.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
