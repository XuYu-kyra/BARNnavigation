#!/usr/bin/env python3
"""Build a lightweight Bayesian paired-effect report for BARN fault campaigns.

This is deliberately small and dependency-free.  It uses the paired
baseline-vs-fault differences produced by build_fault_thesis_analysis.py and
fits a one-sample Bayesian model per metric:

    d_i ~ Normal(mu, sigma)

with the standard weak Jeffreys prior p(mu, sigma) proportional to 1 / sigma.
The resulting posterior for mu is equivalent to a Student-t distribution.  We
sample from that posterior using only Python's standard library so the script
can run on the VM without installing PyMC/Stan/SciPy.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev


METRIC_DIRECTIONS = {
    "completion_time_s": "positive",
    "actual_path_length_m": "positive",
    "whole_stop_ratio": "positive",
    "whole_mean_speed_mps": "negative",
    "controller_new_path_count": "positive",
    "whole_max_stop_streak_s": "positive",
}


MEANINGFUL_THRESHOLDS = {
    "completion_time_s": 5.0,
    "actual_path_length_m": 0.10,
    "whole_stop_ratio": 0.05,
    "whole_mean_speed_mps": 0.005,
    "controller_new_path_count": 5.0,
    "whole_max_stop_streak_s": 5.0,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pair-differences-csv",
        type=Path,
        required=True,
        help="thesis_pair_level_metric_differences.csv from build_fault_thesis_analysis.py.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=17)
    return parser


def safe_float(value: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return out if math.isfinite(out) else float("nan")


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    xs = sorted(values)
    pos = (len(xs) - 1) * pct / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return xs[int(pos)]
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def difference_value(row: dict[str, str]) -> float:
    """Read paired difference from either old or thesis-analysis column names."""
    value = row.get("difference", "")
    if value == "":
        value = row.get("difference_fault_minus_baseline", "")
    return safe_float(value)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def posterior_mu_samples(values: list[float], sample_count: int, rng: random.Random) -> list[float]:
    """Sample posterior means for d_i ~ Normal(mu, sigma), p(mu,sigma) ∝ 1/sigma."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        # One observation cannot identify variance. Use a deliberately wide
        # weak scale so the report communicates uncertainty instead of fake precision.
        return [rng.gauss(values[0], max(abs(values[0]), 10.0)) for _ in range(sample_count)]

    xbar = mean(values)
    s = stdev(values)
    if s == 0:
        return [xbar for _ in range(sample_count)]

    df = n - 1
    ss = df * s * s
    out: list[float] = []
    for _ in range(sample_count):
        chi2 = rng.gammavariate(df / 2.0, 2.0)
        sigma = math.sqrt(ss / chi2)
        out.append(rng.gauss(xbar, sigma / math.sqrt(n)))
    return out


def probability_degradation(samples: list[float], metric: str) -> float:
    direction = METRIC_DIRECTIONS.get(metric, "positive")
    if not samples:
        return float("nan")
    if direction == "negative":
        return sum(value < 0.0 for value in samples) / len(samples)
    return sum(value > 0.0 for value in samples) / len(samples)


def probability_meaningful(samples: list[float], metric: str) -> float:
    direction = METRIC_DIRECTIONS.get(metric, "positive")
    threshold = MEANINGFUL_THRESHOLDS.get(metric, 0.0)
    if not samples:
        return float("nan")
    if direction == "negative":
        return sum(value < -threshold for value in samples) / len(samples)
    return sum(value > threshold for value in samples) / len(samples)


def summarize_group(
    fault_label: str,
    metric: str,
    values: list[float],
    samples: int,
    rng: random.Random,
    world_idx: str | None = None,
) -> dict[str, object]:
    posterior = posterior_mu_samples(values, samples, rng)
    direction = METRIC_DIRECTIONS.get(metric, "positive")
    threshold = MEANINGFUL_THRESHOLDS.get(metric, 0.0)
    row: dict[str, object] = {
        "fault_label": fault_label,
        "metric": metric,
        "direction_interpreted_as_degradation": direction,
        "meaningful_threshold": threshold,
        "n_pairs": len(values),
        "observed_mean_difference": mean(values) if values else float("nan"),
        "observed_sd_difference": stdev(values) if len(values) > 1 else 0.0,
        "posterior_mean_effect": mean(posterior) if posterior else float("nan"),
        "posterior_median_effect": percentile(posterior, 50),
        "credible_interval_95_lower": percentile(posterior, 2.5),
        "credible_interval_95_upper": percentile(posterior, 97.5),
        "p_degradation": probability_degradation(posterior, metric),
        "p_meaningful_degradation": probability_meaningful(posterior, metric),
    }
    if world_idx is not None:
        row = {"world_idx": world_idx, **row}
    return row


def build_effect_rows(rows: list[dict[str, str]], samples: int, seed: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    grouped_world: dict[tuple[str, str], list[float]] = defaultdict(list)

    for row in rows:
        metric = row.get("metric", "")
        if metric not in METRIC_DIRECTIONS:
            continue
        value = difference_value(row)
        if not math.isfinite(value):
            continue
        fault_label = row.get("fault_label", "")
        world_idx = row.get("world_idx", "")
        grouped[(fault_label, metric)].append(value)
        if metric == "completion_time_s":
            grouped_world[(fault_label, world_idx)].append(value)

    rng = random.Random(seed)
    effect_rows = [
        summarize_group(fault, metric, values, samples, rng)
        for (fault, metric), values in sorted(grouped.items())
    ]
    world_rows = [
        summarize_group(fault, "completion_time_s", values, samples, rng, world_idx=world_idx)
        for (fault, world_idx), values in sorted(grouped_world.items(), key=lambda item: (item[0][0], int(item[0][1])))
    ]
    world_rows.sort(key=lambda row: (str(row["fault_label"]), -safe_float(row["p_meaningful_degradation"]), -safe_float(row["posterior_mean_effect"])))
    return effect_rows, world_rows


def judgement(row: dict[str, object]) -> str:
    p_deg = safe_float(row.get("p_degradation"))
    p_meaningful = safe_float(row.get("p_meaningful_degradation"))
    if p_meaningful >= 0.90:
        return "strong evidence of practically meaningful degradation"
    if p_deg >= 0.90:
        return "strong evidence of directional degradation, magnitude may be modest"
    if p_deg >= 0.75:
        return "moderate evidence of degradation"
    if p_deg <= 0.25:
        return "little evidence of degradation"
    return "uncertain / mixed effect"


def write_markdown(path: Path, effect_rows: list[dict[str, object]], world_rows: list[dict[str, object]]) -> None:
    lines: list[str] = []
    lines.append("# Lightweight Bayesian Fault Analysis")
    lines.append("")
    lines.append("Model: paired differences were analysed as `d_i = fault_i - baseline_i` using a normal likelihood with unknown mean and variance.")
    lines.append("A weak Jeffreys prior `p(mu, sigma) proportional to 1/sigma` was used, giving a Student-t posterior for the mean effect.")
    lines.append("")
    lines.append("Interpretation: `p_degradation` is the posterior probability that the fault worsens the metric in the expected direction. `p_meaningful_degradation` additionally requires the effect to exceed a pre-defined practical threshold.")
    lines.append("")
    lines.append("## Main Fault-Level Results")
    lines.append("")
    lines.append("| Fault | Metric | n pairs | Posterior median | 95% credible interval | P(degradation) | P(meaningful degradation) | Interpretation |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for row in effect_rows:
        lines.append(
            "| {fault_label} | {metric} | {n_pairs} | {posterior_median_effect:.3f} | [{credible_interval_95_lower:.3f}, {credible_interval_95_upper:.3f}] | {p_degradation:.3f} | {p_meaningful_degradation:.3f} | {judge} |".format(
                **row,
                judge=judgement(row),
            )
        )
    lines.append("")
    lines.append("## World-Level Completion-Time Susceptibility")
    lines.append("")
    lines.append("| Fault | World | n pairs | Posterior median slowdown (s) | 95% credible interval | P(slowdown) | P(slowdown > 5s) | Interpretation |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for row in world_rows:
        lines.append(
            "| {fault_label} | {world_idx} | {n_pairs} | {posterior_median_effect:.3f} | [{credible_interval_95_lower:.3f}, {credible_interval_95_upper:.3f}] | {p_degradation:.3f} | {p_meaningful_degradation:.3f} | {judge} |".format(
                **row,
                judge=judgement(row),
            )
        )
    lines.append("")
    lines.append("## How to Present This")
    lines.append("")
    lines.append("- This is not a full hierarchical Bayesian model; it is a lightweight Bayesian paired-effect analysis.")
    lines.append("- It is appropriate as a supervisor-facing robustness check because it answers: how probable is degradation, not just whether a p-value crosses 0.05.")
    lines.append("- A future dissertation extension can replace this with a hierarchical model that shares information across worlds and fault types.")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    args = build_parser().parse_args()
    rows = read_rows(args.pair_differences_csv.resolve())
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    effect_rows, world_rows = build_effect_rows(rows, args.samples, args.seed)
    write_csv(output_dir / "bayesian_fault_effects.csv", effect_rows)
    write_csv(output_dir / "bayesian_world_completion_effects.csv", world_rows)
    write_markdown(output_dir / "bayesian_fault_report.md", effect_rows, world_rows)

    print(f"Wrote {output_dir / 'bayesian_fault_effects.csv'}")
    print(f"Wrote {output_dir / 'bayesian_world_completion_effects.csv'}")
    print(f"Wrote {output_dir / 'bayesian_fault_report.md'}")


if __name__ == "__main__":
    main()
