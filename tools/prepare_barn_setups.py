#!/usr/bin/env python3
"""Create reproducible setup directories for original and tuned BARN baselines."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


PATH_FOLLOW_ORIGINAL = """cost_weight: 5.0
        offset_from_furthest: 5
        threshold_to_consider: 1.4"""
PATH_FOLLOW_TUNED = """cost_weight: 7.0
        offset_from_furthest: 5
        threshold_to_consider: 1.4"""

TUNED_FROM_ORIGINAL = [
    ('vx_max: 0.5', 'vx_max: 1.0'),
    ('inflation_radius: 0.8', 'inflation_radius: 0.65'),
    ('cost_weight: 14.0', 'cost_weight: 10.0'),
    (PATH_FOLLOW_ORIGINAL, PATH_FOLLOW_TUNED),
]
ORIGINAL_FROM_TUNED = [(new, old) for old, new in TUNED_FROM_ORIGINAL]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--config-root',
        type=Path,
        default=Path(__file__).resolve().parents[1] / 'jackal_helper' / 'config',
        help='Path to the source jackal_helper config directory.',
    )
    parser.add_argument(
        '--out-root',
        type=Path,
        default=Path(__file__).resolve().parents[1] / 'experiment_setups',
        help='Directory where baseline setup folders will be created.',
    )
    return parser


def copy_config_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def detect_nav2_state(text: str) -> str:
    if 'vx_max: 0.5' in text and 'cost_weight: 14.0' in text:
        return 'original'
    if 'vx_max: 1.0' in text and 'cost_weight: 10.0' in text:
        return 'tuned'
    return 'unknown'


def apply_replacements(text: str, replacements: list[tuple[str, str]], label: str, nav2_path: Path) -> str:
    for old, new in replacements:
        if old not in text:
            raise ValueError(f'Missing expected pattern while building {label} from {nav2_path}: {old!r}')
        text = text.replace(old, new)
    return text


def write_variant_from_source(source_nav2: Path, target_nav2: Path, target_state: str) -> dict:
    text = source_nav2.read_text()
    source_state = detect_nav2_state(text)

    if target_state == source_state:
        target_nav2.write_text(text)
    elif source_state == 'original' and target_state == 'tuned':
        target_nav2.write_text(apply_replacements(text, TUNED_FROM_ORIGINAL, 'tuned variant', source_nav2))
    elif source_state == 'tuned' and target_state == 'original':
        target_nav2.write_text(apply_replacements(text, ORIGINAL_FROM_TUNED, 'original variant', source_nav2))
    else:
        raise ValueError(
            f'Could not infer whether {source_nav2} is original or tuned. '
            'Please inspect nav2.yaml manually and set up the two variants explicitly.'
        )

    return {
        'source_state': source_state,
        'target_state': target_state,
    }


def main() -> None:
    args = build_parser().parse_args()
    src = args.config_root.resolve()
    out_root = args.out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    original_dir = out_root / 'original_clean'
    tuned_dir = out_root / 'tuned_clean'

    copy_config_tree(src, original_dir)
    copy_config_tree(src, tuned_dir)

    source_nav2 = src / 'nav2.yaml'
    original_info = write_variant_from_source(source_nav2, original_dir / 'nav2.yaml', 'original')
    tuned_info = write_variant_from_source(source_nav2, tuned_dir / 'nav2.yaml', 'tuned')

    metadata = {
        'source_config': str(src),
        'source_state': original_info['source_state'],
        'original_setup_path': str(original_dir),
        'tuned_setup_path': str(tuned_dir),
        'tuned_changes_expected': {
            'vx_max': 1.0,
            'local_inflation_radius': 0.65,
            'global_inflation_radius': 0.65,
            'PathAlignCritic.cost_weight': 10.0,
            'PathFollowCritic.cost_weight': 7.0,
        },
        'target_states': {
            'original_clean': original_info['target_state'],
            'tuned_clean': tuned_info['target_state'],
        },
    }
    metadata_path = out_root / 'baseline_metadata.json'
    metadata_path.write_text(json.dumps(metadata, indent=2))

    print(f'Detected source nav2.yaml state: {original_info["source_state"]}')
    print(f'Created {original_dir}')
    print(f'Created {tuned_dir}')
    print(f'Wrote metadata to {metadata_path}')


if __name__ == '__main__':
    main()
