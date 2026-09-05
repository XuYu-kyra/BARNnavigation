#!/usr/bin/env python3
"""Build thesis-facing analysis tables for completed BARN fault campaigns.

This script is intentionally pragmatic: it turns completed campaign logs into
tables/figures that are suitable for a supervisor update before deeper modelling.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median, stdev
from typing import Iterable

import analyze_fault_pipeline as fault_analysis


METRICS = [
    ("completion_time_s", "Completion time (s)", "positive"),
    ("actual_path_length_m", "Actual path length (m)", "positive"),
    ("whole_stop_ratio", "Whole-run stop ratio", "positive"),
    ("whole_mean_speed_mps", "Whole-run mean speed (m/s)", "negative"),
    ("controller_new_path_count", "Controller new-path count", "positive"),
    ("whole_max_stop_streak_s", "Max stop streak (s)", "positive"),
]

DEFAULT_WORLD_CLASSES = {
    240: "class1_stable_success",
    274: "class1_stable_success",
    94: "class1_stable_success",
    8: "class1_stable_success",
    86: "class2_tune_dependent_recovered",
    173: "class2_tune_dependent_recovered",
    76: "class2_tune_dependent_recovered",
    239: "class2_tune_dependent_recovered",
    250: "class3_marginal_success",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--masking-campaign-dir", type=Path, required=True)
    parser.add_argument("--dropout-campaign-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--path-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "jackal_helper/worlds/BARN/path_files",
    )
    parser.add_argument("--stop-speed-threshold", type=float, default=0.05)
    parser.add_argument("--bootstrap-samples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=7)
    return parser


def safe_float(value: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return out if math.isfinite(out) else float("nan")


def finite(values: Iterable[object]) -> list[float]:
    return [v for v in (safe_float(value) for value in values) if math.isfinite(v)]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    xs = sorted(values)
    pos = (len(xs) - 1) * pct / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return xs[int(pos)]
    return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def iqr(values: list[float]) -> float:
    return percentile(values, 75) - percentile(values, 25) if values else float("nan")


def bootstrap_ci(values: list[float], samples: int, seed: int) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    if len(values) == 1:
        return values[0], values[0]
    # Small deterministic LCG avoids adding numpy dependency to this report script.
    state = seed & 0x7FFFFFFF
    means: list[float] = []
    n = len(values)
    for _ in range(samples):
        total = 0.0
        for _ in range(n):
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            total += values[state % n]
        means.append(total / n)
    return percentile(means, 2.5), percentile(means, 97.5)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return list(csv.DictReader(path.open()))


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text()) if path.exists() else {}


def ensure_campaign_analysis(campaign_dir: Path, path_root: Path, stop_speed_threshold: float) -> Path:
    output_dir = campaign_dir / "summaries" / "campaign_analysis"
    required = [
        output_dir / "world_fault_summary.csv",
        output_dir / "campaign_run_summary.csv",
        output_dir / "campaign_pair_differences.csv",
        output_dir / "overview.json",
    ]
    if all(path.exists() for path in required):
        return output_dir
    script = Path(__file__).resolve().with_name("summarize_fault_campaign.py")
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--campaign-dir",
            str(campaign_dir),
            "--path-root",
            str(path_root),
            "--stop-speed-threshold",
            str(stop_speed_threshold),
        ],
        check=True,
    )
    return output_dir


def group_runs(run_rows: list[dict[str, str]]) -> dict[tuple[int, int], dict[str, dict[str, str]]]:
    grouped: dict[tuple[int, int], dict[str, dict[str, str]]] = {}
    for row in run_rows:
        key = (int(row["world_idx"]), int(row["run_id"]))
        grouped.setdefault(key, {})[row["condition"]] = row
    return grouped


def paired_metric_rows(
    fault_label: str,
    run_rows: list[dict[str, str]],
    bootstrap_samples: int,
    seed: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    grouped = group_runs(run_rows)
    pair_detail_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    status_rows: list[dict[str, object]] = []

    transitions = Counter()
    for (world_idx, run_id), by_condition in grouped.items():
        baseline = by_condition.get("baseline")
        fault = by_condition.get("fault")
        if not baseline or not fault:
            continue
        transitions[(baseline.get("status", ""), fault.get("status", ""))] += 1
        for metric, label, degradation_direction in METRICS:
            baseline_value = safe_float(baseline.get(metric))
            fault_value = safe_float(fault.get(metric))
            diff = fault_value - baseline_value if math.isfinite(baseline_value) and math.isfinite(fault_value) else float("nan")
            pair_detail_rows.append(
                {
                    "fault_label": fault_label,
                    "world_idx": world_idx,
                    "world_class": DEFAULT_WORLD_CLASSES.get(world_idx, "unknown"),
                    "pair_id": run_id,
                    "metric": metric,
                    "metric_label": label,
                    "baseline_status": baseline.get("status", ""),
                    "fault_status": fault.get("status", ""),
                    "baseline_value": baseline_value,
                    "fault_value": fault_value,
                    "difference_fault_minus_baseline": diff,
                }
            )

    for metric, label, degradation_direction in METRICS:
        rows = [row for row in pair_detail_rows if row["metric"] == metric]
        diffs = finite(row["difference_fault_minus_baseline"] for row in rows)
        baseline_values = finite(row["baseline_value"] for row in rows)
        fault_values = finite(row["fault_value"] for row in rows)
        ci_low, ci_high = bootstrap_ci(diffs, bootstrap_samples, seed + len(summary_rows) * 97)
        if degradation_direction == "negative":
            degraded_count = sum(diff < 0 for diff in diffs)
        else:
            degraded_count = sum(diff > 0 for diff in diffs)
        sd = stdev(diffs) if len(diffs) >= 2 else 0.0 if diffs else float("nan")
        dz = (mean(diffs) / sd) if diffs and sd > 0 else float("nan")
        summary_rows.append(
            {
                "fault_label": fault_label,
                "metric": metric,
                "metric_label": label,
                "pair_count": len(diffs),
                "baseline_mean": mean(baseline_values) if baseline_values else float("nan"),
                "fault_mean": mean(fault_values) if fault_values else float("nan"),
                "paired_mean_difference": mean(diffs) if diffs else float("nan"),
                "paired_median_difference": median(diffs) if diffs else float("nan"),
                "paired_iqr_difference": iqr(diffs),
                "bootstrap_ci95_lower": ci_low,
                "bootstrap_ci95_upper": ci_high,
                "paired_cohens_dz": dz,
                "degradation_pair_count": degraded_count,
                "degradation_pair_fraction": degraded_count / len(diffs) if diffs else float("nan"),
            }
        )

    for (baseline_status, fault_status), count in sorted(transitions.items()):
        status_rows.append(
            {
                "fault_label": fault_label,
                "baseline_status": baseline_status,
                "fault_status": fault_status,
                "pair_count": count,
            }
        )
    return summary_rows, pair_detail_rows, status_rows


def world_heterogeneity_rows(fault_label: str, world_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in world_rows:
        world_idx = int(row["world_idx"])
        out.append(
            {
                "fault_label": fault_label,
                "world_idx": world_idx,
                "world_class": DEFAULT_WORLD_CLASSES.get(world_idx, "unknown"),
                "pair_count": int(safe_float(row.get("pair_count"))),
                "baseline_success_count": int(safe_float(row.get("baseline_success_count"))),
                "fault_success_count": int(safe_float(row.get("fault_success_count"))),
                "completion_slowdown_mean_s": safe_float(row.get("completion_slowdown_mean_s")),
                "completion_slowdown_ratio": safe_float(row.get("completion_slowdown_ratio")),
                "stop_ratio_delta_mean": safe_float(row.get("stop_ratio_delta_mean")),
                "controller_new_path_delta_mean": safe_float(row.get("controller_new_path_delta_mean")),
                "path_length_delta_mean_m": safe_float(row.get("path_length_delta_mean_m")),
                "pair_ci95_halfwidth_s": safe_float(row.get("pair_ci95_halfwidth_s")),
            }
        )
    return out


def log_paths_for_campaign(campaign_dir: Path) -> list[Path]:
    return sorted((campaign_dir / "worlds").glob("world_*/logs/*.log"))


def matched_window_rows(
    fault_label: str,
    campaign_dir: Path,
    path_root: Path,
    stop_speed_threshold: float,
    manifest: dict[str, object],
) -> list[dict[str, object]]:
    start = safe_float(manifest.get("scan_fault_start"))
    duration = safe_float(manifest.get("scan_fault_duration"))
    if not math.isfinite(start) or not math.isfinite(duration):
        start = safe_float(manifest.get("odom_fault_start"))
        duration = safe_float(manifest.get("odom_fault_duration"))
    if not math.isfinite(start) or not math.isfinite(duration):
        return []
    end = start + duration

    rows: list[dict[str, object]] = []
    for log_path in log_paths_for_campaign(campaign_dir):
        row, trace_rows = fault_analysis.analyze_log(log_path, path_root, stop_speed_threshold)
        samples = [
            fault_analysis.PoseSample(safe_float(trace["t_s"]), safe_float(trace["x_m"]), safe_float(trace["y_m"]))
            for trace in trace_rows
            if math.isfinite(safe_float(trace["t_s"]))
        ]
        stats = fault_analysis.segment_stats(samples, start, end, stop_speed_threshold)
        rows.append(
            {
                "fault_label": fault_label,
                "world_idx": int(row["world_idx"]),
                "world_class": DEFAULT_WORLD_CLASSES.get(int(row["world_idx"]), "unknown"),
                "pair_id": int(row["run_id"]),
                "condition": row["condition"],
                "status": row["status"],
                "matched_window_start_s": start,
                "matched_window_end_s": end,
                "matched_window_duration_s": stats["duration_s"],
                "matched_window_path_length_m": stats["path_length_m"],
                "matched_window_mean_speed_mps": stats["mean_speed_mps"],
                "matched_window_stop_ratio": stats["stop_ratio"],
                "matched_window_max_stop_streak_s": stats["max_stop_streak_s"],
            }
        )
    return rows


def matched_window_pair_rows(window_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int, int], dict[str, dict[str, object]]] = {}
    for row in window_rows:
        key = (str(row["fault_label"]), int(row["world_idx"]), int(row["pair_id"]))
        grouped.setdefault(key, {})[str(row["condition"])] = row

    out: list[dict[str, object]] = []
    for (fault_label, world_idx, pair_id), by_condition in sorted(grouped.items()):
        baseline = by_condition.get("baseline")
        fault = by_condition.get("fault")
        if not baseline or not fault:
            continue
        out.append(
            {
                "fault_label": fault_label,
                "world_idx": world_idx,
                "world_class": DEFAULT_WORLD_CLASSES.get(world_idx, "unknown"),
                "pair_id": pair_id,
                "baseline_window_stop_ratio": baseline["matched_window_stop_ratio"],
                "fault_window_stop_ratio": fault["matched_window_stop_ratio"],
                "window_stop_ratio_delta": safe_float(fault["matched_window_stop_ratio"]) - safe_float(baseline["matched_window_stop_ratio"]),
                "baseline_window_mean_speed_mps": baseline["matched_window_mean_speed_mps"],
                "fault_window_mean_speed_mps": fault["matched_window_mean_speed_mps"],
                "window_mean_speed_delta_mps": safe_float(fault["matched_window_mean_speed_mps"]) - safe_float(baseline["matched_window_mean_speed_mps"]),
                "baseline_window_path_length_m": baseline["matched_window_path_length_m"],
                "fault_window_path_length_m": fault["matched_window_path_length_m"],
                "window_path_length_delta_m": safe_float(fault["matched_window_path_length_m"]) - safe_float(baseline["matched_window_path_length_m"]),
            }
        )
    return out


def representative_case_rows(heterogeneity: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = [row for row in heterogeneity if math.isfinite(safe_float(row.get("completion_slowdown_mean_s")))]
    out: list[dict[str, object]] = []
    for fault_label in sorted({str(row["fault_label"]) for row in rows}):
        fault_rows = [row for row in rows if row["fault_label"] == fault_label]
        if not fault_rows:
            continue
        slowdowns = [safe_float(row["completion_slowdown_mean_s"]) for row in fault_rows]
        med = median(slowdowns)
        typical = min(fault_rows, key=lambda row: abs(safe_float(row["completion_slowdown_mean_s"]) - med))
        high = max(fault_rows, key=lambda row: safe_float(row["completion_slowdown_mean_s"]))
        boundary = next((row for row in fault_rows if int(row["world_idx"]) == 250), None)
        choices = [
            ("typical_case", typical, "Closest to median completion slowdown; useful as a non-extreme propagation example."),
            ("high_susceptibility_case", high, "Largest completion slowdown; useful for explaining environment-dependent susceptibility."),
        ]
        if boundary:
            choices.append(("boundary_case", boundary, "Marginal-success world retained to show boundary-case behaviour."))
        seen: set[tuple[str, int]] = set()
        for role, row, reason in choices:
            key = (str(row["fault_label"]), int(row["world_idx"]))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "fault_label": row["fault_label"],
                    "role": role,
                    "world_idx": row["world_idx"],
                    "world_class": row["world_class"],
                    "completion_slowdown_mean_s": row["completion_slowdown_mean_s"],
                    "stop_ratio_delta_mean": row["stop_ratio_delta_mean"],
                    "controller_new_path_delta_mean": row["controller_new_path_delta_mean"],
                    "selection_reason": reason,
                    "evidence_to_collect": "trajectory; scan/faulted scan; costmap snapshot; cmd_vel timeline; controller path-update events",
                }
            )
    return out


def write_markdown_report(
    path: Path,
    main_rows: list[dict[str, object]],
    heterogeneity_rows_all: list[dict[str, object]],
    representative_rows: list[dict[str, object]],
    status_rows: list[dict[str, object]],
) -> None:
    def fmt(value: object, ndigits: int = 3) -> str:
        v = safe_float(value)
        return f"{v:.{ndigits}f}" if math.isfinite(v) else str(value)

    lines = [
        "# Tonight Fault Analysis Summary",
        "",
        "## Main Paired Effects",
        "",
        "| Fault | Metric | n pairs | Mean diff | Median diff | Bootstrap 95% CI | Degradation pairs |",
        "|---|---|---:|---:|---:|---|---:|",
    ]
    key_metrics = {"completion_time_s", "actual_path_length_m", "whole_stop_ratio", "controller_new_path_count"}
    for row in main_rows:
        if row["metric"] not in key_metrics:
            continue
        lines.append(
            "| {fault_label} | {metric_label} | {pair_count} | {mean} | {median} | [{lo}, {hi}] | {count}/{n} |".format(
                fault_label=row["fault_label"],
                metric_label=row["metric_label"],
                pair_count=row["pair_count"],
                mean=fmt(row["paired_mean_difference"]),
                median=fmt(row["paired_median_difference"]),
                lo=fmt(row["bootstrap_ci95_lower"]),
                hi=fmt(row["bootstrap_ci95_upper"]),
                count=row["degradation_pair_count"],
                n=row["pair_count"],
            )
        )

    lines += [
        "",
        "## World Susceptibility: strongest completion slowdown",
        "",
        "| Fault | World | Class | Completion slowdown (s) | Stop-ratio delta | Controller path delta |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for fault_label in sorted({str(row["fault_label"]) for row in heterogeneity_rows_all}):
        fault_rows = [row for row in heterogeneity_rows_all if row["fault_label"] == fault_label]
        fault_rows.sort(key=lambda row: safe_float(row["completion_slowdown_mean_s"]), reverse=True)
        for row in fault_rows[:5]:
            lines.append(
                f"| {fault_label} | {row['world_idx']} | {row['world_class']} | "
                f"{fmt(row['completion_slowdown_mean_s'])} | {fmt(row['stop_ratio_delta_mean'])} | "
                f"{fmt(row['controller_new_path_delta_mean'])} |"
            )

    lines += [
        "",
        "## Mission Reliability Transitions",
        "",
        "| Fault | Baseline status | Fault status | Pair count |",
        "|---|---|---|---:|",
    ]
    for row in status_rows:
        lines.append(f"| {row['fault_label']} | {row['baseline_status']} | {row['fault_status']} | {row['pair_count']} |")

    lines += [
        "",
        "## Representative Propagation Cases",
        "",
        "| Fault | Role | World | Class | Why this case | Evidence to collect next |",
        "|---|---|---:|---|---|---|",
    ]
    for row in representative_rows:
        lines.append(
            f"| {row['fault_label']} | {row['role']} | {row['world_idx']} | {row['world_class']} | "
            f"{row['selection_reason']} | {row['evidence_to_collect']} |"
        )

    lines += [
        "",
        "## Interpretation Draft",
        "",
        "- Use paired effects as the primary comparison, because each fault run is matched with a baseline run in the same world/pair.",
        "- Treat world-level differences as environment-dependent susceptibility, not as a strong class-level statistical claim yet.",
        "- Use matched 15-35s window outputs to discuss fault-window behaviour; use whole-run metrics for mission-level outcome.",
        "- Keep Bayesian hierarchical modelling as an enhancement after the audit, paired summaries, and propagation evidence are stable.",
    ]
    path.write_text("\n".join(lines) + "\n")


def maybe_write_plots(output_dir: Path, main_rows: list[dict[str, object]], heterogeneity: list[dict[str, object]]) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    key = "completion_time_s"
    fig, ax = plt.subplots(figsize=(7, 4))
    rows = [row for row in main_rows if row["metric"] == key]
    labels = [str(row["fault_label"]) for row in rows]
    values = [safe_float(row["paired_mean_difference"]) for row in rows]
    ax.bar(labels, values)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Paired mean completion slowdown (s)")
    ax.set_title("Fault effect on completion time")
    fig.tight_layout()
    fig.savefig(output_dir / "main_completion_slowdown.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    labels = []
    values = []
    colors = []
    for row in sorted(heterogeneity, key=lambda r: (str(r["fault_label"]), int(r["world_idx"]))):
        labels.append(f"{row['fault_label']} W{int(row['world_idx']):03d}")
        values.append(safe_float(row["completion_slowdown_mean_s"]))
        colors.append("#4c78a8" if "mask" in str(row["fault_label"]).lower() else "#f58518")
    ax.barh(labels, values, color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Mean completion slowdown (s)")
    ax.set_title("World-level susceptibility")
    fig.tight_layout()
    fig.savefig(output_dir / "world_completion_slowdown_ranking.png", dpi=160)
    plt.close(fig)


def process_campaign(
    fault_label: str,
    campaign_dir: Path,
    args: argparse.Namespace,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    analysis_dir = ensure_campaign_analysis(campaign_dir, args.path_root.resolve(), args.stop_speed_threshold)
    run_rows = read_csv(analysis_dir / "campaign_run_summary.csv")
    world_rows = read_csv(analysis_dir / "world_fault_summary.csv")
    manifest = load_json(campaign_dir / "manifest.json")

    main_rows, pair_detail_rows, status_rows = paired_metric_rows(fault_label, run_rows, args.bootstrap_samples, args.seed)
    heterogeneity = world_heterogeneity_rows(fault_label, world_rows)
    window_rows = matched_window_rows(fault_label, campaign_dir, args.path_root.resolve(), args.stop_speed_threshold, manifest)
    window_pair_rows = matched_window_pair_rows(window_rows)
    return main_rows, pair_detail_rows, status_rows, heterogeneity, window_pair_rows


def main() -> None:
    args = build_parser().parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    campaigns = [
        ("frontal_masking", args.masking_campaign_dir.resolve()),
        ("lidar_dropout", args.dropout_campaign_dir.resolve()),
    ]

    all_main: list[dict[str, object]] = []
    all_pair_details: list[dict[str, object]] = []
    all_status: list[dict[str, object]] = []
    all_heterogeneity: list[dict[str, object]] = []
    all_window_pairs: list[dict[str, object]] = []

    for fault_label, campaign_dir in campaigns:
        main_rows, pair_detail_rows, status_rows, heterogeneity, window_pair_rows = process_campaign(fault_label, campaign_dir, args)
        all_main.extend(main_rows)
        all_pair_details.extend(pair_detail_rows)
        all_status.extend(status_rows)
        all_heterogeneity.extend(heterogeneity)
        all_window_pairs.extend(window_pair_rows)

    all_heterogeneity.sort(key=lambda row: (str(row["fault_label"]), -safe_float(row["completion_slowdown_mean_s"])))
    representatives = representative_case_rows(all_heterogeneity)

    write_csv(output_dir / "thesis_main_paired_effects.csv", all_main)
    write_csv(output_dir / "thesis_pair_level_metric_differences.csv", all_pair_details)
    write_csv(output_dir / "thesis_world_heterogeneity.csv", all_heterogeneity)
    write_csv(output_dir / "thesis_status_transitions.csv", all_status)
    write_csv(output_dir / "thesis_matched_fault_window_pairs.csv", all_window_pairs)
    write_csv(output_dir / "thesis_representative_cases.csv", representatives)
    write_markdown_report(output_dir / "tonight_fault_analysis_summary.md", all_main, all_heterogeneity, representatives, all_status)
    maybe_write_plots(output_dir, all_main, all_heterogeneity)

    print(f"Wrote thesis analysis package to {output_dir}")
    print(f"Main effects: {output_dir / 'thesis_main_paired_effects.csv'}")
    print(f"World heterogeneity: {output_dir / 'thesis_world_heterogeneity.csv'}")
    print(f"Matched fault window: {output_dir / 'thesis_matched_fault_window_pairs.csv'}")
    print(f"Summary: {output_dir / 'tonight_fault_analysis_summary.md'}")


if __name__ == "__main__":
    main()
