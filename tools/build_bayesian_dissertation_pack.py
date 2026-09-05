#!/usr/bin/env python3
"""Build dissertation-level Bayesian diagnostics from saved PyMC InferenceData.

This does not refit the model. It reads the existing matched-success PyMC .nc
files and produces convergence diagnostics, posterior predictive checks,
heterogeneity interpretation, and a write-up suitable for the dissertation.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from statistics import mean


def require_libs():
    try:
        import arviz as az  # type: ignore
        import numpy as np  # type: ignore
        import pandas as pd  # type: ignore
    except ModuleNotFoundError as exc:
        raise SystemExit(f"Missing dependency: {exc}") from exc
    return az, np, pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_matched_success_completion"),
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--metric", default="completion_time_s")
    parser.add_argument("--meaningful-threshold", type=float, default=5.0)
    parser.add_argument("--rhat-threshold", type=float, default=1.01)
    parser.add_argument("--ess-threshold", type=float, default=400.0)
    parser.add_argument("--min-bfmi-threshold", type=float, default=0.30)
    return parser.parse_args()


def percentile(np, values, q):
    return float(np.percentile(np.asarray(values, dtype=float), q))


def flatten(np, data_array):
    return np.asarray(data_array.values, dtype=float).reshape(-1)


def safe_float(value) -> float:
    try:
        out = float(value)
    except Exception:
        return float("nan")
    return out if math.isfinite(out) else float("nan")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def svg_hist(np, observed, yrep, title: str, out_path: Path) -> None:
    """Small dependency-free PPC SVG: observed histogram vs PPC mean histogram."""
    observed = np.asarray(observed, dtype=float)
    yrep = np.asarray(yrep, dtype=float)
    ppc_flat = yrep.reshape(-1)
    lo = float(np.nanpercentile(np.concatenate([observed, ppc_flat]), 1))
    hi = float(np.nanpercentile(np.concatenate([observed, ppc_flat]), 99))
    if not math.isfinite(lo) or not math.isfinite(hi) or lo == hi:
        lo, hi = -1.0, 1.0
    bins = np.linspace(lo, hi, 24)
    obs_counts, _ = np.histogram(observed, bins=bins)
    # Average posterior predictive histogram across a capped number of draws.
    draws = yrep[: min(800, yrep.shape[0])]
    pred_counts = []
    for row in draws:
        pred_counts.append(np.histogram(row, bins=bins)[0])
    pred_mean = np.mean(np.asarray(pred_counts), axis=0)
    max_count = max(float(np.max(obs_counts)), float(np.max(pred_mean)), 1.0)

    width, height = 760, 360
    left, right, top, bottom = 70, 20, 40, 55
    plot_w = width - left - right
    plot_h = height - top - bottom
    bar_w = plot_w / len(obs_counts)

    def x_at(value):
        return left + (value - lo) / (hi - lo) * plot_w

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="24" font-family="Arial" font-size="16" font-weight="700">{title}</text>',
        f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#222"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#222"/>',
    ]
    for i, count in enumerate(pred_mean):
        h = float(count) / max_count * plot_h
        x = left + i * bar_w
        y = top + plot_h - h
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w*0.92:.1f}" height="{h:.1f}" fill="#94a3b8" opacity="0.45"/>')
    for i, count in enumerate(obs_counts):
        h = float(count) / max_count * plot_h
        x = left + i * bar_w + bar_w * 0.18
        y = top + plot_h - h
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w*0.56:.1f}" height="{h:.1f}" fill="#0f766e" opacity="0.85"/>')
    for val in [0, 5]:
        if lo <= val <= hi:
            x = x_at(val)
            parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+plot_h}" stroke="#111" stroke-dasharray="5 4"/>')
            parts.append(f'<text x="{x+4:.1f}" y="{top+14}" font-family="Arial" font-size="11">{val}s</text>')
    parts += [
        f'<text x="{left}" y="{height-20}" font-family="Arial" font-size="12">paired slowdown (fault - baseline), seconds</text>',
        f'<rect x="{width-220}" y="18" width="12" height="12" fill="#0f766e"/><text x="{width-202}" y="29" font-family="Arial" font-size="12">observed</text>',
        f'<rect x="{width-130}" y="18" width="12" height="12" fill="#94a3b8" opacity="0.45"/><text x="{width-112}" y="29" font-family="Arial" font-size="12">posterior predictive</text>',
        '</svg>',
    ]
    out_path.write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    args = parse_args()
    az, np, pd = require_libs()
    model_dir = args.model_dir.resolve()
    output_dir = (args.output_dir or (model_dir / "dissertation_bayesian_diagnostics")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    nc_files = sorted(model_dir.glob(f"*__{args.metric}.nc"))
    if not nc_files:
        raise SystemExit(f"No *__{args.metric}.nc files found in {model_dir}")

    convergence_rows: list[dict[str, object]] = []
    sampling_rows: list[dict[str, object]] = []
    ppc_rows: list[dict[str, object]] = []
    tau_rows: list[dict[str, object]] = []

    for nc_path in nc_files:
        fault_label = nc_path.name.split(f"__{args.metric}.nc")[0]
        idata = az.from_netcdf(nc_path)
        summary = az.summary(idata, var_names=["mu", "tau", "sigma", "nu", "theta"], ci_prob=0.95, round_to=6)
        summary_path = output_dir / f"{fault_label}__{args.metric}_full_arviz_summary_95.csv"
        summary.to_csv(summary_path)

        for var_name, row in summary.iterrows():
            rhat = safe_float(row.get("r_hat"))
            ess_bulk = safe_float(row.get("ess_bulk"))
            ess_tail = safe_float(row.get("ess_tail"))
            convergence_rows.append({
                "fault_label": fault_label,
                "metric": args.metric,
                "parameter": var_name,
                "mean": safe_float(row.get("mean")),
                "sd": safe_float(row.get("sd")),
                "ci_lower": safe_float(row.get("hdi_2.5%", row.get("eti95_lb", row.get("eti89_lb")))),
                "ci_upper": safe_float(row.get("hdi_97.5%", row.get("eti95_ub", row.get("eti89_ub")))),
                "ess_bulk": ess_bulk,
                "ess_tail": ess_tail,
                "r_hat": rhat,
                "rhat_ok": rhat <= args.rhat_threshold if math.isfinite(rhat) else False,
                "ess_bulk_ok": ess_bulk >= args.ess_threshold if math.isfinite(ess_bulk) else False,
                "ess_tail_ok": ess_tail >= args.ess_threshold if math.isfinite(ess_tail) else False,
            })

        ss = idata.sample_stats
        divergences = int(np.asarray(ss["diverging"].values).sum()) if "diverging" in ss else int(np.asarray(ss["divergences"].values).sum()) if "divergences" in ss else 0
        max_tree = int(np.asarray(ss["reached_max_treedepth"].values).sum()) if "reached_max_treedepth" in ss else 0
        accept = np.asarray(ss["acceptance_rate"].values, dtype=float) if "acceptance_rate" in ss else np.asarray([], dtype=float)
        bfmi_data = az.bfmi(idata)
        try:
            bfmi_values = np.asarray(bfmi_data["energy"].values, dtype=float)
        except Exception:
            try:
                bfmi_values = np.asarray(bfmi_data.sample_stats["energy"].values, dtype=float)
            except Exception:
                bfmi_values = np.asarray([], dtype=float)
        sampling_rows.append({
            "fault_label": fault_label,
            "metric": args.metric,
            "chains": int(idata.posterior.sizes.get("chain", 0)),
            "draws_per_chain": int(idata.posterior.sizes.get("draw", 0)),
            "total_posterior_draws": int(idata.posterior.sizes.get("chain", 0) * idata.posterior.sizes.get("draw", 0)),
            "divergences": divergences,
            "reached_max_treedepth": max_tree,
            "mean_acceptance_rate": float(np.nanmean(accept)) if accept.size else float("nan"),
            "min_bfmi": float(np.nanmin(bfmi_values)) if bfmi_values.size else float("nan"),
            "bfmi_ok": bool(float(np.nanmin(bfmi_values)) >= args.min_bfmi_threshold) if bfmi_values.size else False,
            "sampling_ok": divergences == 0 and max_tree == 0 and (float(np.nanmin(bfmi_values)) >= args.min_bfmi_threshold if bfmi_values.size else False),
        })

        y_obs = np.asarray(idata.observed_data["y"].values, dtype=float)
        y_rep = np.asarray(idata.posterior_predictive["y"].values, dtype=float).reshape(-1, y_obs.shape[0])
        obs_stats = {
            "mean": float(np.mean(y_obs)),
            "sd": float(np.std(y_obs, ddof=1)) if y_obs.size > 1 else 0.0,
            "median": float(np.median(y_obs)),
            "min": float(np.min(y_obs)),
            "max": float(np.max(y_obs)),
            "p_gt_0": float(np.mean(y_obs > 0)),
            "p_gt_threshold": float(np.mean(y_obs > args.meaningful_threshold)),
        }
        rep_stats = {
            "mean": np.mean(y_rep, axis=1),
            "sd": np.std(y_rep, axis=1, ddof=1),
            "median": np.median(y_rep, axis=1),
            "min": np.min(y_rep, axis=1),
            "max": np.max(y_rep, axis=1),
            "p_gt_0": np.mean(y_rep > 0, axis=1),
            "p_gt_threshold": np.mean(y_rep > args.meaningful_threshold, axis=1),
        }
        lower = np.percentile(y_rep, 2.5, axis=0)
        upper = np.percentile(y_rep, 97.5, axis=0)
        ppc_rows.append({
            "fault_label": fault_label,
            "metric": args.metric,
            "n_observations": int(y_obs.size),
            "observed_mean": obs_stats["mean"],
            "ppc_mean_median": percentile(np, rep_stats["mean"], 50),
            "ppc_mean_95_lower": percentile(np, rep_stats["mean"], 2.5),
            "ppc_mean_95_upper": percentile(np, rep_stats["mean"], 97.5),
            "ppc_p_mean_ge_observed": float(np.mean(rep_stats["mean"] >= obs_stats["mean"])),
            "observed_sd": obs_stats["sd"],
            "ppc_sd_median": percentile(np, rep_stats["sd"], 50),
            "ppc_sd_95_lower": percentile(np, rep_stats["sd"], 2.5),
            "ppc_sd_95_upper": percentile(np, rep_stats["sd"], 97.5),
            "ppc_p_sd_ge_observed": float(np.mean(rep_stats["sd"] >= obs_stats["sd"])),
            "observed_max": obs_stats["max"],
            "ppc_max_median": percentile(np, rep_stats["max"], 50),
            "ppc_max_95_lower": percentile(np, rep_stats["max"], 2.5),
            "ppc_max_95_upper": percentile(np, rep_stats["max"], 97.5),
            "ppc_p_max_ge_observed": float(np.mean(rep_stats["max"] >= obs_stats["max"])),
            "observed_fraction_gt_0": obs_stats["p_gt_0"],
            "ppc_fraction_gt_0_median": percentile(np, rep_stats["p_gt_0"], 50),
            "observed_fraction_gt_threshold": obs_stats["p_gt_threshold"],
            "ppc_fraction_gt_threshold_median": percentile(np, rep_stats["p_gt_threshold"], 50),
            "pointwise_95ppc_coverage": float(np.mean((y_obs >= lower) & (y_obs <= upper))),
        })
        svg_hist(np, y_obs, y_rep, f"{fault_label}: posterior predictive check", output_dir / f"{fault_label}__{args.metric}_ppc_hist.svg")

        tau_samples = np.asarray(idata.posterior["tau"].values, dtype=float).reshape(-1)
        tau_rows.append({
            "fault_label": fault_label,
            "metric": args.metric,
            "tau_median_s": percentile(np, tau_samples, 50),
            "tau_95_lower_s": percentile(np, tau_samples, 2.5),
            "tau_95_upper_s": percentile(np, tau_samples, 97.5),
            "p_tau_gt_1s": float(np.mean(tau_samples > 1.0)),
            "p_tau_gt_2s": float(np.mean(tau_samples > 2.0)),
            "p_tau_gt_5s": float(np.mean(tau_samples > 5.0)),
            "tau_as_fraction_of_5s_threshold_median": percentile(np, tau_samples / args.meaningful_threshold, 50),
            "interpretation": "between-world heterogeneity scale; larger values mean stronger environment-to-environment variation",
        })

    write_csv(output_dir / "convergence_diagnostics_full.csv", convergence_rows)
    write_csv(output_dir / "sampling_diagnostics.csv", sampling_rows)
    write_csv(output_dir / "posterior_predictive_checks.csv", ppc_rows)
    write_csv(output_dir / "tau_heterogeneity_interpretation.csv", tau_rows)

    # Report-level summaries.
    conv_failures = [r for r in convergence_rows if not (r["rhat_ok"] and r["ess_bulk_ok"] and r["ess_tail_ok"])]
    sampling_failures = [r for r in sampling_rows if not r["sampling_ok"]]

    lines = []
    lines.append("# Dissertation Bayesian Diagnostics Pack")
    lines.append("")
    lines.append(f"Model directory: `{model_dir}`")
    lines.append(f"Output directory: `{output_dir}`")
    lines.append("")
    lines.append("## Model Specification")
    lines.append("")
    lines.append("Primary model for completion-time slowdown uses matched-success paired differences only:")
    lines.append("")
    lines.append("```text")
    lines.append("y_ij ~ StudentT(nu, theta_j, sigma)")
    lines.append("theta_j = mu + tau * theta_offset_j")
    lines.append("theta_offset_j ~ Normal(0, 1)")
    lines.append("mu ~ Normal(0, 10 * prior_scale)")
    lines.append("tau ~ HalfNormal(5 * prior_scale)")
    lines.append("sigma ~ HalfNormal(5 * prior_scale)")
    lines.append("nu_minus_two ~ Exponential(1 / 30)")
    lines.append("nu = nu_minus_two + 2")
    lines.append("```")
    lines.append("")
    lines.append("Positive effects are oriented as degradation. For completion time, positive means the fault run was slower than its paired baseline run.")
    lines.append("")
    lines.append("The Student-t likelihood was used because Gazebo/Nav2 experiments can produce occasional long-tail timing outliers; this reduces sensitivity compared with a Normal likelihood.")
    lines.append("")
    lines.append("## Prior Specification")
    lines.append("")
    lines.append("The model uses weakly regularising scale priors. `prior_scale` is chosen from the observed paired-difference scale and the practical threshold, so priors remain broad relative to the observed data while keeping sampling stable. The practical threshold for completion time is 5s, matching the pre-registered repeat-count stopping rule and the smallest slowdown treated as operationally meaningful in this analysis.")
    lines.append("")
    lines.append("## Convergence Diagnostics")
    lines.append("")
    lines.append(f"R-hat threshold: <= {args.rhat_threshold}; ESS threshold: >= {args.ess_threshold}.")
    lines.append("")
    if conv_failures:
        lines.append(f"Convergence warning: {len(conv_failures)} parameter rows failed at least one R-hat/ESS criterion. Inspect `convergence_diagnostics_full.csv` before final write-up.")
    else:
        lines.append("All reported key parameters passed the R-hat and ESS thresholds.")
    if sampling_failures:
        lines.append(f"Sampling warning: {len(sampling_failures)} model(s) had divergences, max treedepth hits, or low BFMI. Inspect `sampling_diagnostics.csv`.")
    else:
        lines.append("Sampling diagnostics showed no divergences, no max-treedepth saturation, and acceptable BFMI for all primary models.")
    lines.append("")
    lines.append("## Posterior Predictive Checks")
    lines.append("")
    lines.append("Posterior predictive checks compare observed paired slowdowns with simulated replicated datasets from the fitted model. The generated table reports predictive intervals for mean, standard deviation, maximum slowdown, pointwise 95% coverage, and threshold exceedance fractions.")
    lines.append("")
    for row in ppc_rows:
        lines.append(
            f"- `{row['fault_label']}`: observed mean {row['observed_mean']:.2f}s; "
            f"PPC mean median {row['ppc_mean_median']:.2f}s "
            f"[{row['ppc_mean_95_lower']:.2f}, {row['ppc_mean_95_upper']:.2f}]; "
            f"pointwise 95% PPC coverage {row['pointwise_95ppc_coverage']:.2f}."
        )
    lines.append("")
    lines.append("## Tau / World Heterogeneity")
    lines.append("")
    lines.append("`tau` is the posterior scale of world-level effects. It quantifies how much slowdown varies between worlds after accounting for within-world run noise. A non-zero tau supports the thesis claim that environment susceptibility is heterogeneous rather than uniform.")
    lines.append("")
    for row in tau_rows:
        lines.append(
            f"- `{row['fault_label']}`: tau median {row['tau_median_s']:.2f}s "
            f"[{row['tau_95_lower_s']:.2f}, {row['tau_95_upper_s']:.2f}], "
            f"P(tau>2s)={row['p_tau_gt_2s']:.3f}."
        )
    lines.append("")
    lines.append("## Robustness / Sensitivity Statement")
    lines.append("")
    lines.append("The Bayesian model is used as a probabilistic summary of the primary matched-success completion-time outcome. It should be reported together with the non-parametric paired/bootstrap results and the all-pair/capped sensitivity analysis. Agreement in direction between these analyses supports robustness; differences in practical-threshold probability should be interpreted as uncertainty about effect magnitude rather than a contradiction of directional degradation.")
    lines.append("")
    lines.append("## Files Generated")
    lines.append("")
    for name in ["convergence_diagnostics_full.csv", "sampling_diagnostics.csv", "posterior_predictive_checks.csv", "tau_heterogeneity_interpretation.csv"]:
        lines.append(f"- `{name}`")
    lines.append("- `*_ppc_hist.svg`")
    lines.append("")

    (output_dir / "bayesian_dissertation_diagnostics_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
