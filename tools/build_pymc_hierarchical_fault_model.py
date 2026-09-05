#!/usr/bin/env python3
"""Fit a dissertation-grade PyMC hierarchical model for BARN fault effects.

This script is the probabilistic-programming version of
build_hierarchical_bayes_fault_model.py.  It requires PyMC and ArviZ.  It keeps
the same statistical structure but uses NUTS sampling and formal diagnostics:

    y_ij ~ StudentT(nu, theta_j, sigma)
    theta_j ~ Normal(mu, tau)

The Student-t likelihood is used instead of a plain Normal likelihood because
BARN/Gazebo runs can produce occasional long-tail timing outliers.
"""

from __future__ import annotations

import argparse
import csv
import math
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


def require_pymc():
    try:
        import arviz as az  # type: ignore
        import numpy as np  # type: ignore
        import pymc as pm  # type: ignore
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing PyMC dependencies. Install them in the VM environment first, e.g.\n"
            "  python3 -m pip install pymc arviz numpy\n"
            "or keep using build_hierarchical_bayes_fault_model.py for the dependency-free version.\n"
            f"Original error: {exc}"
        ) from exc
    return pm, az, np


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair-differences-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--metric", default="completion_time_s", choices=sorted(METRIC_DIRECTIONS))
    parser.add_argument("--draws", type=int, default=2000)
    parser.add_argument("--tune", type=int, default=2000)
    parser.add_argument("--chains", type=int, default=4)
    parser.add_argument("--target-accept", type=float, default=0.9)
    parser.add_argument("--seed", type=int, default=43)
    parser.add_argument("--include-all-metrics", action="store_true")
    return parser


def safe_float(value: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return out if math.isfinite(out) else float("nan")


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


def orient_difference(metric: str, value: float) -> float:
    if METRIC_DIRECTIONS.get(metric) == "negative":
        return -value
    return value


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


def group_data(rows: list[dict[str, str]], metrics: list[str]) -> dict[tuple[str, str], dict[str, list[float]]]:
    grouped: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        metric = row.get("metric", "")
        if metric not in metrics:
            continue
        value = difference_value(row)
        if not math.isfinite(value):
            continue
        fault_label = row.get("fault_label", "")
        world_idx = row.get("world_idx", "")
        grouped[(fault_label, metric)][world_idx].append(orient_difference(metric, value))
    return grouped


def flatten_posterior(idata, var_name: str) -> list[float]:
    values = idata.posterior[var_name].values.reshape(-1)
    return [float(value) for value in values]


def flatten_world_posterior(idata, world_index: int) -> list[float]:
    values = idata.posterior["theta"].values[..., world_index].reshape(-1)
    return [float(value) for value in values]


def posterior_summary(samples: list[float]) -> dict[str, float]:
    return {
        "posterior_mean": mean(samples) if samples else float("nan"),
        "posterior_median": percentile(samples, 50),
        "credible_interval_95_lower": percentile(samples, 2.5),
        "credible_interval_95_upper": percentile(samples, 97.5),
    }


def prob_gt(samples: list[float], threshold: float) -> float:
    if not samples:
        return float("nan")
    return sum(value > threshold for value in samples) / len(samples)


def judgement(p_deg: float, p_meaningful: float) -> str:
    if p_meaningful >= 0.90:
        return "strong practically meaningful degradation"
    if p_deg >= 0.90:
        return "strong directional degradation"
    if p_deg >= 0.75:
        return "moderate degradation evidence"
    if p_deg <= 0.25:
        return "little degradation evidence"
    return "uncertain / mixed"


def fit_one_model(
    pm,
    az,
    np,
    fault_label: str,
    metric: str,
    world_values: dict[str, list[float]],
    args: argparse.Namespace,
    output_dir: Path,
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    worlds = sorted(world_values, key=lambda value: int(value) if value.isdigit() else value)
    world_lookup = {world: idx for idx, world in enumerate(worlds)}
    y_values: list[float] = []
    world_index: list[int] = []
    for world in worlds:
        for value in world_values[world]:
            y_values.append(value)
            world_index.append(world_lookup[world])

    y = np.array(y_values, dtype=float)
    world_idx = np.array(world_index, dtype=int)
    observed_scale = float(np.std(y, ddof=1)) if len(y) > 1 else max(abs(float(np.mean(y))), 1.0)
    prior_scale = max(observed_scale, abs(float(np.mean(y))), MEANINGFUL_THRESHOLDS[metric], 1e-3)

    coords = {"world": worlds, "obs_id": np.arange(len(y))}
    with pm.Model(coords=coords) as model:
        world_idx_data = pm.Data("world_idx", world_idx, dims="obs_id")
        mu = pm.Normal("mu", mu=0.0, sigma=10.0 * prior_scale)
        tau = pm.HalfNormal("tau", sigma=5.0 * prior_scale)
        sigma = pm.HalfNormal("sigma", sigma=5.0 * prior_scale)
        nu_minus_two = pm.Exponential("nu_minus_two", lam=1.0 / 30.0)
        nu = pm.Deterministic("nu", nu_minus_two + 2.0)
        theta_offset = pm.Normal("theta_offset", mu=0.0, sigma=1.0, dims="world")
        theta = pm.Deterministic("theta", mu + tau * theta_offset, dims="world")
        pm.StudentT("y", nu=nu, mu=theta[world_idx_data], sigma=sigma, observed=y, dims="obs_id")

        idata = pm.sample(
            draws=args.draws,
            tune=args.tune,
            chains=args.chains,
            target_accept=args.target_accept,
            random_seed=args.seed,
            return_inferencedata=True,
            progressbar=False,
        )
        pm.sample_posterior_predictive(idata, extend_inferencedata=True, random_seed=args.seed, progressbar=False)

    safe_fault = fault_label.replace("/", "_")
    model_name = f"{safe_fault}__{metric}"
    netcdf_path = output_dir / f"{model_name}.nc"
    netcdf_saved = True
    try:
        idata.to_netcdf(netcdf_path)
    except Exception as exc:
        netcdf_saved = False
        netcdf_path = output_dir / f"{model_name}.nc_NOT_WRITTEN_{type(exc).__name__}"

    summary = az.summary(idata, var_names=["mu", "tau", "sigma", "nu", "theta"], round_to=6)
    diag_path = output_dir / f"{model_name}_arviz_summary.csv"
    summary.to_csv(diag_path)

    mu_samples = flatten_posterior(idata, "mu")
    tau_samples = flatten_posterior(idata, "tau")
    sigma_samples = flatten_posterior(idata, "sigma")
    threshold = MEANINGFUL_THRESHOLDS[metric]
    p_deg = prob_gt(mu_samples, 0.0)
    p_meaningful = prob_gt(mu_samples, threshold)
    mu_summary = posterior_summary(mu_samples)

    fault_row = {
        "fault_label": fault_label,
        "metric": metric,
        "model": "PyMC StudentT hierarchical model",
        "effect_orientation": "positive values mean degradation",
        "meaningful_threshold": threshold,
        "n_worlds": len(worlds),
        "n_pairs": len(y_values),
        "observed_mean_degradation": float(np.mean(y)),
        "observed_sd_degradation": float(np.std(y, ddof=1)) if len(y) > 1 else 0.0,
        **mu_summary,
        "p_global_degradation": p_deg,
        "p_global_meaningful_degradation": p_meaningful,
        "posterior_tau_median": percentile(tau_samples, 50),
        "posterior_sigma_median": percentile(sigma_samples, 50),
        "rhat_mu": float(summary.loc["mu", "r_hat"]) if "mu" in summary.index else float("nan"),
        "ess_bulk_mu": float(summary.loc["mu", "ess_bulk"]) if "mu" in summary.index else float("nan"),
        "netcdf_path": str(netcdf_path),
        "netcdf_saved": netcdf_saved,
        "arviz_summary_csv": str(diag_path),
        "interpretation": judgement(p_deg, p_meaningful),
    }

    world_rows: list[dict[str, object]] = []
    for world, idx in world_lookup.items():
        samples = flatten_world_posterior(idata, idx)
        p_world = prob_gt(samples, 0.0)
        p_world_meaningful = prob_gt(samples, threshold)
        observed = world_values[world]
        world_rows.append(
            {
                "fault_label": fault_label,
                "metric": metric,
                "world_idx": world,
                "effect_orientation": "positive values mean degradation",
                "meaningful_threshold": threshold,
                "n_pairs": len(observed),
                "observed_world_mean_degradation": mean(observed),
                "observed_world_sd_degradation": stdev(observed) if len(observed) > 1 else 0.0,
                **posterior_summary(samples),
                "p_world_degradation": p_world,
                "p_world_meaningful_degradation": p_world_meaningful,
                "interpretation": judgement(p_world, p_world_meaningful),
            }
        )

    diagnostics = {
        "fault_label": fault_label,
        "metric": metric,
        "netcdf_path": str(netcdf_path),
        "netcdf_saved": netcdf_saved,
        "arviz_summary_csv": str(diag_path),
        "rhat_mu": fault_row["rhat_mu"],
        "ess_bulk_mu": fault_row["ess_bulk_mu"],
        "draws": args.draws,
        "tune": args.tune,
        "chains": args.chains,
        "target_accept": args.target_accept,
    }
    return fault_row, world_rows, diagnostics


def write_markdown(path: Path, fault_rows: list[dict[str, object]], world_rows: list[dict[str, object]], diagnostics: list[dict[str, object]]) -> None:
    lines: list[str] = []
    lines.append("# PyMC Hierarchical Bayesian Fault Model")
    lines.append("")
    lines.append("This is the probabilistic-programming version of the hierarchical analysis.")
    lines.append("It uses a Student-t likelihood to reduce sensitivity to occasional long-tail Gazebo/Nav2 timing outliers.")
    lines.append("")
    lines.append("```text")
    lines.append("y_ij ~ StudentT(nu, theta_j, sigma)")
    lines.append("theta_j ~ Normal(mu, tau)")
    lines.append("```")
    lines.append("")
    lines.append("All effects are oriented so positive values mean degradation.")
    lines.append("")
    lines.append("## Fault-Level Results")
    lines.append("")
    lines.append("| Fault | Metric | n worlds | n pairs | Median global degradation | 95% credible interval | P(degradation) | P(meaningful degradation) | tau median | sigma median | R-hat(mu) | ESS(mu) | Interpretation |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for row in fault_rows:
        lines.append(
            "| {fault_label} | {metric} | {n_worlds} | {n_pairs} | {posterior_median:.3f} | [{credible_interval_95_lower:.3f}, {credible_interval_95_upper:.3f}] | {p_global_degradation:.3f} | {p_global_meaningful_degradation:.3f} | {posterior_tau_median:.3f} | {posterior_sigma_median:.3f} | {rhat_mu:.3f} | {ess_bulk_mu:.1f} | {interpretation} |".format(
                **row
            )
        )
    lines.append("")
    lines.append("## Completion-Time World Susceptibility")
    lines.append("")
    lines.append("| Fault | World | n pairs | Median slowdown | 95% credible interval | P(slowdown) | P(slowdown > threshold) | Interpretation |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    completion_rows = [row for row in world_rows if row["metric"] == "completion_time_s"]
    completion_rows.sort(key=lambda row: (str(row["fault_label"]), -safe_float(row["p_world_meaningful_degradation"]), -safe_float(row["posterior_median"])))
    for row in completion_rows:
        lines.append(
            "| {fault_label} | {world_idx} | {n_pairs} | {posterior_median:.3f} | [{credible_interval_95_lower:.3f}, {credible_interval_95_upper:.3f}] | {p_world_degradation:.3f} | {p_world_meaningful_degradation:.3f} | {interpretation} |".format(
                **row
            )
        )
    lines.append("")
    lines.append("## Diagnostics Files")
    lines.append("")
    for row in diagnostics:
        lines.append(f"- `{row['fault_label']}` / `{row['metric']}`: `{row['arviz_summary_csv']}` and `{row['netcdf_path']}`")
    lines.append("")
    lines.append("## How This Differs From The Dependency-Free Gibbs Version")
    lines.append("")
    lines.append("- This version uses PyMC NUTS/HMC sampling rather than a hand-written conjugate Gibbs sampler.")
    lines.append("- It uses a Student-t likelihood, which is more robust to simulation outliers.")
    lines.append("- It stores full ArviZ inference data and diagnostics, so R-hat/ESS/posterior predictive checks can be inspected.")
    lines.append("- This is closer to dissertation-grade methodology, but it depends on PyMC/ArviZ and takes longer to run.")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    args = build_parser().parse_args()
    pm, az, np = require_pymc()
    rows = read_csv(args.pair_differences_csv.resolve())
    metrics = sorted(METRIC_DIRECTIONS) if args.include_all_metrics else [args.metric]
    grouped = group_data(rows, metrics)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    fault_rows: list[dict[str, object]] = []
    world_rows: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    for (fault_label, metric), world_values in sorted(grouped.items()):
        if len(world_values) < 2:
            continue
        fault_row, this_world_rows, diagnostic = fit_one_model(pm, az, np, fault_label, metric, world_values, args, output_dir)
        fault_rows.append(fault_row)
        world_rows.extend(this_world_rows)
        diagnostics.append(diagnostic)

    write_csv(output_dir / "pymc_hierarchical_fault_effects.csv", fault_rows)
    write_csv(output_dir / "pymc_hierarchical_world_effects.csv", world_rows)
    write_csv(output_dir / "pymc_hierarchical_diagnostics.csv", diagnostics)
    write_markdown(output_dir / "pymc_hierarchical_report.md", fault_rows, world_rows, diagnostics)

    print(f"Wrote {output_dir / 'pymc_hierarchical_fault_effects.csv'}")
    print(f"Wrote {output_dir / 'pymc_hierarchical_world_effects.csv'}")
    print(f"Wrote {output_dir / 'pymc_hierarchical_diagnostics.csv'}")
    print(f"Wrote {output_dir / 'pymc_hierarchical_report.md'}")


if __name__ == "__main__":
    main()
