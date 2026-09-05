#!/usr/bin/env python3
"""Fit a small hierarchical Bayesian model to BARN paired fault results.

Input is the pair-level difference table produced by build_fault_thesis_analysis.py.
For each fault and metric, the model is:

    y_ij ~ Normal(theta_j, sigma)
    theta_j ~ Normal(mu, tau)

where y_ij is the paired degradation effect for pair i in world j.  Metrics are
oriented so that positive values always mean degradation.  The model is sampled
with a conjugate Gibbs sampler implemented with only the Python standard
library, which keeps the VM setup simple while still producing a genuine
hierarchical Bayesian analysis.
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


METRIC_UNITS = {
    "completion_time_s": "s",
    "actual_path_length_m": "m",
    "whole_stop_ratio": "ratio",
    "whole_mean_speed_mps": "m/s decrease",
    "controller_new_path_count": "count",
    "whole_max_stop_streak_s": "s",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair-differences-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=8000)
    parser.add_argument("--burn-in", type=int, default=2000)
    parser.add_argument("--thin", type=int, default=3)
    parser.add_argument("--chains", type=int, default=4)
    parser.add_argument("--seed", type=int, default=29)
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


def read_csv(path: Path) -> list[dict[str, str]]:
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
    if not rows:
        path.write_text("")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def inv_gamma(rng: random.Random, shape: float, scale: float) -> float:
    scale = max(scale, 1e-12)
    return 1.0 / rng.gammavariate(shape, 1.0 / scale)


def variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return sum((value - m) ** 2 for value in values) / (len(values) - 1)


def rhat(chains: list[list[float]]) -> float:
    usable = [chain for chain in chains if len(chain) >= 2]
    if len(usable) < 2:
        return float("nan")
    n = min(len(chain) for chain in usable)
    trimmed = [chain[:n] for chain in usable]
    chain_means = [mean(chain) for chain in trimmed]
    chain_vars = [variance(chain) for chain in trimmed]
    w = mean(chain_vars)
    if w <= 0:
        return 1.0
    b = n * variance(chain_means)
    var_hat = ((n - 1) / n) * w + b / n
    return math.sqrt(max(var_hat / w, 0.0))


def orient_difference(metric: str, difference: float) -> float:
    if METRIC_DIRECTIONS.get(metric) == "negative":
        return -difference
    return difference


def group_pair_differences(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, list[float]]]:
    grouped: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        metric = row.get("metric", "")
        if metric not in METRIC_DIRECTIONS:
            continue
        raw = difference_value(row)
        if not math.isfinite(raw):
            continue
        fault_label = row.get("fault_label", "")
        world_idx = row.get("world_idx", "")
        grouped[(fault_label, metric)][world_idx].append(orient_difference(metric, raw))
    return grouped


def sample_chain(
    world_values: dict[str, list[float]],
    iterations: int,
    burn_in: int,
    thin: int,
    seed: int,
    meaningful_threshold: float,
) -> dict[str, list[float] | dict[str, list[float]]]:
    rng = random.Random(seed)
    worlds = sorted(world_values, key=lambda value: int(value) if value.isdigit() else value)
    all_values = [value for values in world_values.values() for value in values]
    n_total = len(all_values)
    j_total = len(worlds)

    obs_mean = mean(all_values)
    obs_sd = stdev(all_values) if len(all_values) > 1 else max(abs(obs_mean), meaningful_threshold, 1.0)
    scale = max(obs_sd, abs(obs_mean), meaningful_threshold, 1e-3)

    mu0 = 0.0
    mu0_var = (10.0 * scale) ** 2
    a_sigma = 2.0
    b_sigma = scale**2
    a_tau = 2.0
    b_tau = scale**2

    theta = {
        world: mean(values) if values else obs_mean
        for world, values in world_values.items()
    }
    mu = obs_mean
    sigma2 = max(variance(all_values), scale**2)
    theta_values = list(theta.values())
    tau2 = max(variance(theta_values), scale**2)

    mu_samples: list[float] = []
    sigma_samples: list[float] = []
    tau_samples: list[float] = []
    theta_samples: dict[str, list[float]] = {world: [] for world in worlds}

    for iteration in range(iterations):
        sigma2 = max(sigma2, 1e-12)
        tau2 = max(tau2, 1e-12)

        for world in worlds:
            values = world_values[world]
            n_j = len(values)
            sum_j = sum(values)
            post_var = 1.0 / (n_j / sigma2 + 1.0 / tau2)
            post_mean = post_var * (sum_j / sigma2 + mu / tau2)
            theta[world] = rng.gauss(post_mean, math.sqrt(post_var))

        post_mu_var = 1.0 / (j_total / tau2 + 1.0 / mu0_var)
        post_mu_mean = post_mu_var * (sum(theta.values()) / tau2 + mu0 / mu0_var)
        mu = rng.gauss(post_mu_mean, math.sqrt(post_mu_var))

        resid_ss = 0.0
        for world, values in world_values.items():
            resid_ss += sum((value - theta[world]) ** 2 for value in values)
        sigma2 = inv_gamma(rng, a_sigma + n_total / 2.0, b_sigma + 0.5 * resid_ss)

        theta_ss = sum((theta[world] - mu) ** 2 for world in worlds)
        tau2 = inv_gamma(rng, a_tau + j_total / 2.0, b_tau + 0.5 * theta_ss)

        if iteration >= burn_in and (iteration - burn_in) % thin == 0:
            mu_samples.append(mu)
            sigma_samples.append(math.sqrt(max(sigma2, 0.0)))
            tau_samples.append(math.sqrt(max(tau2, 0.0)))
            for world in worlds:
                theta_samples[world].append(theta[world])

    return {
        "mu": mu_samples,
        "sigma": sigma_samples,
        "tau": tau_samples,
        "theta": theta_samples,
    }


def flatten(chains: list[dict[str, object]], key: str) -> list[float]:
    out: list[float] = []
    for chain in chains:
        out.extend(chain[key])  # type: ignore[arg-type]
    return out


def probability_gt(samples: list[float], threshold: float) -> float:
    if not samples:
        return float("nan")
    return sum(value > threshold for value in samples) / len(samples)


def summarise_samples(samples: list[float]) -> dict[str, float]:
    return {
        "posterior_mean": mean(samples) if samples else float("nan"),
        "posterior_median": percentile(samples, 50),
        "credible_interval_95_lower": percentile(samples, 2.5),
        "credible_interval_95_upper": percentile(samples, 97.5),
    }


def judgement(p_degradation: float, p_meaningful: float) -> str:
    if p_meaningful >= 0.90:
        return "strong evidence of practically meaningful degradation"
    if p_degradation >= 0.90:
        return "strong evidence of directional degradation"
    if p_degradation >= 0.75:
        return "moderate evidence of degradation"
    if p_degradation <= 0.25:
        return "little evidence of degradation"
    return "uncertain / mixed effect"


def fit_all(
    grouped: dict[tuple[str, str], dict[str, list[float]]],
    iterations: int,
    burn_in: int,
    thin: int,
    chains_n: int,
    seed: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    fault_rows: list[dict[str, object]] = []
    world_rows: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []

    for model_index, ((fault_label, metric), world_values) in enumerate(sorted(grouped.items())):
        if len(world_values) < 2:
            continue
        threshold = MEANINGFUL_THRESHOLDS[metric]
        all_values = [value for values in world_values.values() for value in values]
        chains = [
            sample_chain(
                world_values,
                iterations=iterations,
                burn_in=burn_in,
                thin=thin,
                seed=seed + model_index * 1000 + chain_idx * 97,
                meaningful_threshold=threshold,
            )
            for chain_idx in range(chains_n)
        ]

        mu_chain_values = [chain["mu"] for chain in chains]  # type: ignore[list-item]
        mu_samples = flatten(chains, "mu")
        sigma_samples = flatten(chains, "sigma")
        tau_samples = flatten(chains, "tau")
        mu_summary = summarise_samples(mu_samples)
        p_degradation = probability_gt(mu_samples, 0.0)
        p_meaningful = probability_gt(mu_samples, threshold)

        fault_rows.append(
            {
                "fault_label": fault_label,
                "metric": metric,
                "effect_orientation": "positive values mean degradation",
                "unit": METRIC_UNITS.get(metric, ""),
                "meaningful_threshold": threshold,
                "n_worlds": len(world_values),
                "n_pairs": len(all_values),
                "observed_mean_degradation": mean(all_values),
                "observed_sd_degradation": stdev(all_values) if len(all_values) > 1 else 0.0,
                **mu_summary,
                "p_global_degradation": p_degradation,
                "p_global_meaningful_degradation": p_meaningful,
                "posterior_tau_world_heterogeneity_median": percentile(tau_samples, 50),
                "posterior_sigma_pair_noise_median": percentile(sigma_samples, 50),
                "rhat_mu": rhat(mu_chain_values),  # type: ignore[arg-type]
                "interpretation": judgement(p_degradation, p_meaningful),
            }
        )

        diagnostics.append(
            {
                "fault_label": fault_label,
                "metric": metric,
                "chains": chains_n,
                "iterations": iterations,
                "burn_in": burn_in,
                "thin": thin,
                "posterior_samples_per_chain": len(mu_chain_values[0]) if mu_chain_values else 0,
                "rhat_mu": rhat(mu_chain_values),  # type: ignore[arg-type]
                "note": "R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis.",
            }
        )

        for world in sorted(world_values, key=lambda value: int(value) if value.isdigit() else value):
            theta_samples: list[float] = []
            for chain in chains:
                theta_by_world = chain["theta"]  # type: ignore[assignment]
                theta_samples.extend(theta_by_world[world])  # type: ignore[index]
            observed = world_values[world]
            theta_summary = summarise_samples(theta_samples)
            p_world = probability_gt(theta_samples, 0.0)
            p_world_meaningful = probability_gt(theta_samples, threshold)
            world_rows.append(
                {
                    "fault_label": fault_label,
                    "metric": metric,
                    "world_idx": world,
                    "effect_orientation": "positive values mean degradation",
                    "unit": METRIC_UNITS.get(metric, ""),
                    "meaningful_threshold": threshold,
                    "n_pairs": len(observed),
                    "observed_world_mean_degradation": mean(observed),
                    "observed_world_sd_degradation": stdev(observed) if len(observed) > 1 else 0.0,
                    **theta_summary,
                    "p_world_degradation": p_world,
                    "p_world_meaningful_degradation": p_world_meaningful,
                    "shrinkage_from_observed_mean": theta_summary["posterior_median"] - mean(observed),
                    "interpretation": judgement(p_world, p_world_meaningful),
                }
            )

    world_rows.sort(
        key=lambda row: (
            str(row["fault_label"]),
            str(row["metric"]),
            -safe_float(row["p_world_meaningful_degradation"]),
            -safe_float(row["posterior_median"]),
        )
    )
    return fault_rows, world_rows, diagnostics


def write_markdown(path: Path, fault_rows: list[dict[str, object]], world_rows: list[dict[str, object]], diagnostics: list[dict[str, object]]) -> None:
    lines: list[str] = []
    lines.append("# Hierarchical Bayesian Fault Model")
    lines.append("")
    lines.append("This report fits a hierarchical normal model to paired baseline-vs-fault differences.")
    lines.append("Each pair difference is assigned to a world; each world has its own latent fault effect; those world effects are drawn from a fault-level distribution.")
    lines.append("")
    lines.append("Model:")
    lines.append("")
    lines.append("```text")
    lines.append("y_ij ~ Normal(theta_j, sigma)")
    lines.append("theta_j ~ Normal(mu, tau)")
    lines.append("```")
    lines.append("")
    lines.append("All metrics are oriented so positive values mean degradation. For example, lower mean speed under fault is converted into a positive speed-degradation effect.")
    lines.append("")
    lines.append("## Fault-Level Effects")
    lines.append("")
    lines.append("| Fault | Metric | n worlds | n pairs | Median global degradation | 95% credible interval | P(global degradation) | P(meaningful degradation) | World heterogeneity tau | R-hat | Interpretation |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for row in fault_rows:
        lines.append(
            "| {fault_label} | {metric} | {n_worlds} | {n_pairs} | {posterior_median:.3f} | [{credible_interval_95_lower:.3f}, {credible_interval_95_upper:.3f}] | {p_global_degradation:.3f} | {p_global_meaningful_degradation:.3f} | {posterior_tau_world_heterogeneity_median:.3f} | {rhat_mu:.3f} | {interpretation} |".format(
                **row
            )
        )
    lines.append("")
    lines.append("## Most Susceptible Worlds by Completion-Time Effect")
    lines.append("")
    lines.append("| Fault | World | n pairs | Median slowdown (s) | 95% credible interval | P(slowdown > 0) | P(slowdown > 5s) | Interpretation |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    completion_rows = [row for row in world_rows if row["metric"] == "completion_time_s"]
    for row in completion_rows[:18]:
        lines.append(
            "| {fault_label} | {world_idx} | {n_pairs} | {posterior_median:.3f} | [{credible_interval_95_lower:.3f}, {credible_interval_95_upper:.3f}] | {p_world_degradation:.3f} | {p_world_meaningful_degradation:.3f} | {interpretation} |".format(
                **row
            )
        )
    lines.append("")
    lines.append("## Diagnostics")
    lines.append("")
    lines.append("| Fault | Metric | Chains | Posterior samples / chain | R-hat(mu) | Note |")
    lines.append("|---|---|---:|---:|---:|---|")
    for row in diagnostics:
        lines.append(
            "| {fault_label} | {metric} | {chains} | {posterior_samples_per_chain} | {rhat_mu:.3f} | {note} |".format(
                **row
            )
        )
    lines.append("")
    lines.append("## Suggested Wording")
    lines.append("")
    lines.append("This should be presented as an initial hierarchical Bayesian analysis, not as the final statistical model.")
    lines.append("It strengthens the meeting evidence because it separates global fault effect, world-level susceptibility, and pair-level run noise.")
    lines.append("If needed, the dissertation version can later be extended with class-level effects or fitted in PyMC/Stan for more formal diagnostics.")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    args = build_parser().parse_args()
    if args.burn_in >= args.iterations:
        raise SystemExit("--burn-in must be smaller than --iterations")
    if args.thin < 1:
        raise SystemExit("--thin must be at least 1")
    if args.chains < 2:
        raise SystemExit("--chains must be at least 2 for R-hat diagnostics")

    rows = read_csv(args.pair_differences_csv.resolve())
    grouped = group_pair_differences(rows)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    fault_rows, world_rows, diagnostics = fit_all(
        grouped,
        iterations=args.iterations,
        burn_in=args.burn_in,
        thin=args.thin,
        chains_n=args.chains,
        seed=args.seed,
    )

    write_csv(output_dir / "hierarchical_bayes_fault_effects.csv", fault_rows)
    write_csv(output_dir / "hierarchical_bayes_world_effects.csv", world_rows)
    write_csv(output_dir / "hierarchical_bayes_diagnostics.csv", diagnostics)
    write_markdown(output_dir / "hierarchical_bayes_report.md", fault_rows, world_rows, diagnostics)

    print(f"Wrote {output_dir / 'hierarchical_bayes_fault_effects.csv'}")
    print(f"Wrote {output_dir / 'hierarchical_bayes_world_effects.csv'}")
    print(f"Wrote {output_dir / 'hierarchical_bayes_diagnostics.csv'}")
    print(f"Wrote {output_dir / 'hierarchical_bayes_report.md'}")


if __name__ == "__main__":
    main()
