#!/usr/bin/env python3
"""Build thesis-ready fault-analysis figures.

These figures are intentionally more publication-like than the 16:9 meeting
slides: less explanatory text, clearer axes, and reusable captions.
"""

from __future__ import annotations

import csv
import math
import random
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


ROOT = Path("/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis")
OUT = ROOT / "thesis_figures_v4"
PNG_OUT = OUT / "png"

FAULTS = ["frontal_masking", "lidar_dropout"]
FAULT_LABEL = {
    "frontal_masking": "Frontal LiDAR masking",
    "lidar_dropout": "Intermittent LiDAR dropout",
}
FAULT_SHORT = {
    "frontal_masking": "Masking",
    "lidar_dropout": "Dropout",
}
FAULT_COLOR = {
    "frontal_masking": "#2563eb",
    "lidar_dropout": "#f97316",
}
METRIC_ORDER = [
    ("whole_stop_ratio", "Stop ratio", "positive", 3),
    ("whole_mean_speed_mps", "Mean speed decrease", "negative", 4),
    ("controller_new_path_count", "Controller updates", "positive", 1),
    ("whole_max_stop_streak_s", "Max stop streak (s)", "positive", 1),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def fnum(value: object, default: float = float("nan")) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def fmt(value: float, digits: int = 2) -> str:
    if not math.isfinite(value):
        return "NA"
    return f"{value:.{digits}f}"


def esc(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class Svg:
    def __init__(self, width: int = 1500, height: int = 950) -> None:
        self.width = width
        self.height = height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            '<style><![CDATA['
            "text{font-family:Arial,Helvetica,sans-serif;fill:#111827}"
            ".title{font-size:34px;font-weight:700}"
            ".subtitle{font-size:19px;fill:#4b5563}"
            ".axis{font-size:16px;fill:#4b5563}"
            ".tick{font-size:14px;fill:#6b7280}"
            ".label{font-size:18px;font-weight:700}"
            ".note{font-size:16px;fill:#4b5563}"
            "]]></style>",
        ]

    def rect(self, x: float, y: float, w: float, h: float, fill: str, stroke: str = "none", sw: float = 1, rx: float = 0) -> None:
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def line(self, x1: float, y1: float, x2: float, y2: float, stroke: str = "#9ca3af", sw: float = 2, dash: str | None = None) -> None:
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def circle(self, x: float, y: float, r: float, fill: str, stroke: str = "#ffffff", sw: float = 2) -> None:
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def text(self, x: float, y: float, text: object, cls: str = "", size: int | None = None, weight: int | None = None, fill: str | None = None, anchor: str = "start") -> None:
        style = []
        if size:
            style.append(f"font-size:{size}px")
        if weight:
            style.append(f"font-weight:{weight}")
        if fill:
            style.append(f"fill:{fill}")
        style_attr = f' style="{";".join(style)}"' if style else ""
        cls_attr = f' class="{cls}"' if cls else ""
        self.parts.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}"{cls_attr}{style_attr}>{esc(text)}</text>')

    def save(self, path: Path) -> None:
        self.parts.append("</svg>")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.parts) + "\n")


def add_title(svg: Svg, title: str, subtitle: str = "") -> None:
    svg.text(70, 62, title, cls="title")
    if subtitle:
        svg.text(70, 95, subtitle, cls="subtitle")
    svg.line(70, 120, svg.width - 70, 120, stroke="#d1d5db", sw=1.5)


def percentile(values: list[float], pct: float) -> float:
    xs = sorted(values)
    if not xs:
        return float("nan")
    pos = (len(xs) - 1) * pct / 100
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return xs[lo]
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def cluster_bootstrap(rows: list[dict[str, str]], fault: str, n_boot: int = 5000) -> tuple[float, float, float, int]:
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["fault_label"] == fault and row["metric"] == "completion_time_s":
            groups[row["world_idx"]].append(fnum(row["difference_fault_minus_baseline"]))
    worlds = sorted(groups)
    observed = [value for world in worlds for value in groups[world]]
    rng = random.Random(13)
    boots: list[float] = []
    for _ in range(n_boot):
        vals: list[float] = []
        for _ in worlds:
            vals.extend(groups[rng.choice(worlds)])
        boots.append(mean(vals))
    return mean(observed), percentile(boots, 2.5), percentile(boots, 97.5), len(observed)


def make_outcome_transitions(pair_rows: list[dict[str, str]]) -> None:
    svg = Svg(1500, 880)
    add_title(svg, "Task outcome transitions", "Each bar counts paired baseline/fault outcome transitions before completion-time filtering.")
    counts: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    for row in pair_rows:
        if row["metric"] == "completion_time_s":
            counts[row["fault_label"]][(row["baseline_status"], row["fault_status"])] += 1
    transitions = [
        ("succeeded", "succeeded", "success→success"),
        ("succeeded", "timeout", "success→timeout"),
        ("timeout", "succeeded", "timeout→success"),
        ("timeout", "timeout", "timeout→timeout"),
        ("collided", "succeeded", "collision→success"),
    ]
    max_count = max(max(counter.values()) for counter in counts.values())
    lefts = [130, 820]
    baseline_y = 690
    for fault, left in zip(FAULTS, lefts):
        svg.text(left + 240, 175, FAULT_LABEL[fault], size=23, weight=700, fill=FAULT_COLOR[fault], anchor="middle")
        svg.line(left + 40, baseline_y, left + 540, baseline_y, stroke="#9ca3af")
        for tick in [0, 10, 20, 30, 40, 50]:
            y = baseline_y - tick / max_count * 430
            svg.line(left + 30, y, left + 40, y, stroke="#9ca3af")
            svg.text(left + 22, y + 5, tick, cls="tick", anchor="end")
        for idx, (b, f, label) in enumerate(transitions):
            n = counts[fault][(b, f)]
            h = n / max_count * 430
            x = left + 70 + idx * 94
            svg.rect(x, baseline_y - h, 56, h, FAULT_COLOR[fault], rx=5)
            svg.text(x + 28, baseline_y - h - 10, n, size=16, weight=700, anchor="middle")
            svg.text(x + 28, baseline_y + 28, label, size=13, anchor="middle", fill="#4b5563")
        svg.text(left - 10, 450, "count", cls="axis", anchor="middle")
    svg.text(750, 812, "Note: success-success pairs are used for primary completion-time inference; mixed outcomes are retained as outcome evidence.", cls="note", anchor="middle")
    svg.save(OUT / "fig_01_task_outcome_transitions.svg")


def make_completion_effects(matched_rows: list[dict[str, str]], main_rows: list[dict[str, str]]) -> None:
    svg = Svg(1500, 820)
    add_title(svg, "Completion-time degradation estimates", "Primary estimates use matched-success pairs; all-pair/capped estimates are sensitivity analysis.")
    primary = {fault: cluster_bootstrap(matched_rows, fault) for fault in FAULTS}
    sensitivity = {}
    for row in main_rows:
        if row["metric"] == "completion_time_s":
            sensitivity[row["fault_label"]] = (
                fnum(row["paired_mean_difference"]),
                fnum(row["bootstrap_ci95_lower"]),
                fnum(row["bootstrap_ci95_upper"]),
                int(fnum(row["pair_count"], 0)),
            )
    rows = [
        ("Primary: matched-success", "frontal_masking", primary["frontal_masking"]),
        ("Primary: matched-success", "lidar_dropout", primary["lidar_dropout"]),
        ("Sensitivity: all pairs/capped", "frontal_masking", sensitivity["frontal_masking"]),
        ("Sensitivity: all pairs/capped", "lidar_dropout", sensitivity["lidar_dropout"]),
    ]
    x0, y0, scale = 430, 250, 40
    svg.line(x0, y0 + 395, x0 + 950, y0 + 395, stroke="#9ca3af")
    for tick in [0, 5, 10, 15, 20]:
        x = x0 + tick * scale
        svg.line(x, y0 + 385, x, y0 + 405, stroke="#9ca3af")
        svg.text(x, y0 + 430, f"{tick}", cls="tick", anchor="middle")
    svg.text(x0 + 400, y0 + 470, "Fault-minus-baseline completion time (s)", cls="axis", anchor="middle")
    for idx, (group, fault, values) in enumerate(rows):
        y = y0 + idx * 92
        mean_v, lo, hi, n = values
        svg.text(90, y + 7, group if idx in (0, 2) else "", size=17, weight=700, fill="#374151")
        svg.text(300, y + 7, FAULT_SHORT[fault], size=17, weight=700, fill=FAULT_COLOR[fault], anchor="end")
        svg.line(x0 + lo * scale, y, x0 + hi * scale, y, stroke="#111827", sw=3)
        svg.line(x0 + lo * scale, y - 10, x0 + lo * scale, y + 10, stroke="#111827", sw=2)
        svg.line(x0 + hi * scale, y - 10, x0 + hi * scale, y + 10, stroke="#111827", sw=2)
        svg.circle(x0 + mean_v * scale, y, 9, FAULT_COLOR[fault])
        svg.text(x0 + 575, y + 7, f"{fmt(mean_v)} [{fmt(lo)}, {fmt(hi)}], n={n}", size=16)
    svg.save(OUT / "fig_02_completion_primary_sensitivity.svg")


def make_bayes_threshold(fault_effects: list[dict[str, str]]) -> None:
    svg = Svg(1300, 760)
    add_title(svg, "Bayesian threshold sensitivity", "Posterior probabilities from the matched-success hierarchical Student-t model.")
    probs = {
        "frontal_masking": {0: 0.9999, 3: 0.994, 5: 0.843, 7: 0.258},
        "lidar_dropout": {0: 0.998, 3: 0.883, 5: 0.342, 7: 0.033},
    }
    thresholds = [0, 3, 5, 7]
    x0, y0, cw, ch = 365, 215, 190, 95
    svg.text(110, y0 - 45, "Fault", size=18, weight=700)
    for j, t in enumerate(thresholds):
        svg.text(x0 + j * cw + cw / 2, y0 - 45, f"P(Δ > {t}s)", size=18, weight=700, anchor="middle")
    for i, fault in enumerate(FAULTS):
        y = y0 + i * ch
        svg.text(110, y + 58, FAULT_SHORT[fault], size=19, weight=700, fill=FAULT_COLOR[fault])
        for j, t in enumerate(thresholds):
            p = probs[fault][t]
            color = "#dbeafe" if fault == "frontal_masking" else "#ffedd5"
            x = x0 + j * cw
            svg.rect(x, y, cw - 18, ch - 18, color, "#ffffff", 1, rx=8)
            label = ">0.999" if p >= 0.9995 else f"{p:.3f}"
            svg.text(x + (cw - 18) / 2, y + 52, label, size=24, weight=700, anchor="middle")
    y = 505
    for row in fault_effects:
        fault = row["fault_label"]
        svg.text(
            120,
            y,
            f"{FAULT_SHORT[fault]}: median Δ={float(row['posterior_median']):.2f}s, 95% CrI [{float(row['credible_interval_95_lower']):.2f}, {float(row['credible_interval_95_upper']):.2f}]",
            size=18,
            fill="#374151",
        )
        y += 42
    svg.text(650, 695, "Δ denotes fault-minus-baseline completion time among matched-success pairs.", cls="note", anchor="middle")
    svg.save(OUT / "fig_03_bayesian_threshold_sensitivity.svg")


def make_world_forest(world_rows: list[dict[str, str]]) -> None:
    svg = Svg(1500, 930)
    add_title(svg, "Posterior world-level completion-time effects", "Partial pooling shrinks uncertain world estimates towards the global fault effect.")
    for col, fault in enumerate(FAULTS):
        left = 110 + col * 715
        y0 = 205
        rows = [r for r in world_rows if r["fault_label"] == fault and r["metric"] == "completion_time_s"]
        rows.sort(key=lambda r: int(r["world_idx"]))
        svg.text(left + 330, 165, FAULT_LABEL[fault], size=21, weight=700, fill=FAULT_COLOR[fault], anchor="middle")
        x_axis = left + 135
        svg.line(x_axis, y0 + 35, x_axis + 460, y0 + 35, stroke="#9ca3af")
        for tick in [-5, 0, 5, 10, 15]:
            x = x_axis + (tick + 5) * 23
            svg.line(x, y0 + 25, x, y0 + 45, stroke="#9ca3af")
            svg.text(x, y0 + 68, tick, cls="tick", anchor="middle")
        for idx, row in enumerate(rows):
            y = y0 + 105 + idx * 56
            lo = fnum(row["credible_interval_95_lower"])
            hi = fnum(row["credible_interval_95_upper"])
            med = fnum(row["posterior_median"])
            svg.text(left + 15, y + 5, f"W{int(row['world_idx']):03d} (n={row['n_pairs']})", size=15)
            svg.line(x_axis + (lo + 5) * 23, y, x_axis + (hi + 5) * 23, y, stroke="#374151", sw=2.5)
            svg.circle(x_axis + (med + 5) * 23, y, 7, FAULT_COLOR[fault])
        svg.text(left + 365, 840, "slowdown seconds", cls="axis", anchor="middle")
    svg.text(750, 900, "Interpret cautiously: apparent world dependence is shown, but stronger heterogeneity claims require explicit tau/PPC reporting.", cls="note", anchor="middle")
    svg.save(OUT / "fig_04_posterior_world_effects.svg")


def make_pipeline_metrics(matched_rows: list[dict[str, str]]) -> None:
    svg = Svg(1500, 850)
    add_title(svg, "Pipeline-level proxy metrics", "Matched-success descriptive effects; all metrics are oriented so positive values indicate degradation.")
    vals: dict[str, dict[str, float]] = defaultdict(dict)
    for fault in FAULTS:
        for metric, _, direction, _ in METRIC_ORDER:
            diffs = []
            for row in matched_rows:
                if row["fault_label"] == fault and row["metric"] == metric:
                    d = fnum(row["difference_fault_minus_baseline"])
                    diffs.append(-d if direction == "negative" else d)
            vals[fault][metric] = mean(diffs) if diffs else float("nan")
    left, y_axis = 145, 660
    group_w = 310
    for i, (metric, label, _, digits) in enumerate(METRIC_ORDER):
        x = left + i * group_w
        local = [vals[f][metric] for f in FAULTS]
        max_abs = max(abs(v) for v in local if math.isfinite(v)) or 1.0
        svg.text(x + 100, 185, label, size=17, weight=700, anchor="middle")
        svg.line(x + 25, y_axis, x + 205, y_axis, stroke="#9ca3af")
        for j, fault in enumerate(FAULTS):
            v = vals[fault][metric]
            h = 400 * abs(v) / max_abs
            bx = x + 60 + j * 78
            svg.rect(bx, y_axis - h, 52, h, FAULT_COLOR[fault], rx=5)
            svg.text(bx + 26, y_axis - h - 12, fmt(v, digits), size=14, anchor="middle")
    svg.circle(560, 745, 8, FAULT_COLOR["frontal_masking"])
    svg.text(580, 751, "Frontal masking", size=15)
    svg.circle(760, 745, 8, FAULT_COLOR["lidar_dropout"])
    svg.text(780, 751, "LiDAR dropout", size=15)
    svg.text(750, 815, "These are mechanism-consistent proxy metrics, not formal causal mediation evidence.", cls="note", anchor="middle")
    svg.save(OUT / "fig_05_pipeline_proxy_metrics.svg")


def make_case_selection(world_rows: list[dict[str, str]]) -> None:
    svg = Svg(1450, 780)
    add_title(svg, "Representative cases for follow-up propagation analysis", "Typical cases are selected for clean layer-by-layer evidence; extreme cases are exploratory.")
    lookup = {(r["fault_label"], int(r["world_idx"])): r for r in world_rows}
    cases = [
        ("Typical", "frontal_masking", 8),
        ("Typical", "lidar_dropout", 240),
        ("Extreme", "frontal_masking", 173),
        ("Extreme", "lidar_dropout", 76),
    ]
    x0, y0, w, h = 95, 190, 610, 145
    for i, (kind, fault, world) in enumerate(cases):
        x = x0 + (i % 2) * 675
        y = y0 + (i // 2) * 185
        row = lookup[(fault, world)]
        svg.rect(x, y, w, h, "#f9fafb", "#d1d5db", 1.5, rx=8)
        svg.text(x + 25, y + 38, f"{kind}: W{world:03d} / {FAULT_SHORT[fault]}", size=20, weight=700, fill=FAULT_COLOR[fault])
        svg.text(x + 25, y + 78, f"mean slowdown={fmt(fnum(row['completion_slowdown_mean_s']))}s; matched success B/F={row['baseline_success_count']}/{row['fault_success_count']}", size=16)
        svg.text(x + 25, y + 112, f"controller update delta={fmt(fnum(row['controller_new_path_delta_mean']), 1)}", size=16)
    svg.text(725, 670, "Typical-case rule: 6/6 matched success + measurable non-extreme slowdown + observable controller response.", cls="note", anchor="middle")
    svg.save(OUT / "fig_06_case_selection.svg")


def write_captions() -> None:
    captions = {
        "fig_01_task_outcome_transitions": "Task outcome transitions for paired baseline/fault runs. The figure separates mission outcome from continuous completion-time analysis and motivates using matched-success pairs as the primary estimand.",
        "fig_02_completion_primary_sensitivity": "Fault-minus-baseline completion-time degradation. Primary estimates use matched-success pairs with world-cluster bootstrap intervals; all-pair/capped estimates are shown as sensitivity analysis.",
        "fig_03_bayesian_threshold_sensitivity": "Matched-success hierarchical Bayesian posterior probabilities that fault-induced slowdown exceeds exploratory practical thresholds.",
        "fig_04_posterior_world_effects": "Posterior world-level completion-time effects under the hierarchical Student-t model. Partial pooling reduces over-interpretation of noisy world-specific averages.",
        "fig_05_pipeline_proxy_metrics": "Matched-success pipeline-level proxy metrics, oriented so positive values indicate degradation. These metrics provide mechanism-consistent evidence but are not a substitute for time-aligned propagation traces.",
        "fig_06_case_selection": "Representative cases selected for follow-up propagation analysis. Typical cases are chosen for clean layer-by-layer evidence, while extreme cases are retained for exploratory sensitivity discussion.",
    }
    lines = ["# Thesis Figure Captions", ""]
    for name, caption in captions.items():
        lines.append(f"## {name}")
        lines.append(caption)
        lines.append("")
    (OUT / "figure_captions.md").write_text("\n".join(lines))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PNG_OUT.mkdir(parents=True, exist_ok=True)
    pair_rows = read_csv(ROOT / "thesis_pair_level_metric_differences.csv")
    matched_rows = read_csv(ROOT / "thesis_pair_level_metric_differences_matched_success.csv")
    main_rows = read_csv(ROOT / "thesis_main_paired_effects.csv")
    fault_effects = read_csv(ROOT / "pymc_hierarchical_matched_success_completion/pymc_hierarchical_fault_effects.csv")
    world_effects = read_csv(ROOT / "pymc_hierarchical_matched_success_completion/pymc_hierarchical_world_effects.csv")
    world_heterogeneity = read_csv(ROOT / "thesis_world_heterogeneity.csv")

    make_outcome_transitions(pair_rows)
    make_completion_effects(matched_rows, main_rows)
    make_bayes_threshold(fault_effects)
    make_world_forest(world_effects)
    make_pipeline_metrics(matched_rows)
    make_case_selection(world_heterogeneity)
    write_captions()

    for svg in sorted(OUT.glob("fig_*.svg")):
        png = PNG_OUT / f"{svg.stem}.png"
        subprocess.run(["convert", "-density", "220", str(svg), str(png)], check=True)
        print(png)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
