#!/usr/bin/env python3
"""Build critique-aware PPT figures for the BARN fault analysis update.

The figures intentionally avoid external Python plotting dependencies so they
can run in the same minimal environment used for the ROS/Gazebo analysis.
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
OUT = ROOT / "ppt_figures_v4"
PNG_OUT = OUT / "png"

FAULT_DISPLAY = {
    "frontal_masking": "Frontal masking",
    "lidar_dropout": "LiDAR dropout",
}

FAULT_COLORS = {
    "frontal_masking": "#2563eb",
    "lidar_dropout": "#f97316",
}

METRIC_ORDER = [
    ("whole_stop_ratio", "Stop ratio", "positive"),
    ("whole_mean_speed_mps", "Mean speed decrease", "negative"),
    ("controller_new_path_count", "Controller path updates", "positive"),
    ("whole_max_stop_streak_s", "Max stop streak", "positive"),
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


def escape(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class Svg:
    def __init__(self, width: int = 1600, height: int = 900) -> None:
        self.width = width
        self.height = height
        self.parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#f8fafc"/>',
            '<style><![CDATA['
            "text{font-family:Arial,Helvetica,sans-serif;fill:#0f172a}"
            ".title{font-size:42px;font-weight:700}"
            ".subtitle{font-size:22px;fill:#475569}"
            ".small{font-size:17px;fill:#475569}"
            ".tiny{font-size:14px;fill:#64748b}"
            ".label{font-size:20px;font-weight:700}"
            ".metric{font-size:18px;fill:#334155}"
            ".note{font-size:18px;fill:#475569}"
            "]]></style>",
        ]

    def rect(self, x: float, y: float, w: float, h: float, fill: str, stroke: str = "none", sw: float = 1, rx: float = 18) -> None:
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def line(self, x1: float, y1: float, x2: float, y2: float, stroke: str = "#94a3b8", sw: float = 3, dash: str | None = None) -> None:
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{dash_attr}/>')

    def circle(self, x: float, y: float, r: float, fill: str, stroke: str = "none", sw: float = 1) -> None:
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
        self.parts.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}"{cls_attr}{style_attr}>{escape(text)}</text>')

    def multiline(self, x: float, y: float, lines: list[str], cls: str = "note", line_h: int = 28, size: int | None = None, fill: str | None = None) -> None:
        for idx, line in enumerate(lines):
            self.text(x, y + idx * line_h, line, cls=cls, size=size, fill=fill)

    def arrow(self, x1: float, y1: float, x2: float, y2: float, stroke: str = "#64748b") -> None:
        self.line(x1, y1, x2, y2, stroke=stroke, sw=4)
        angle = math.atan2(y2 - y1, x2 - x1)
        head = 14
        for offset in (2.55, -2.55):
            ax = x2 - head * math.cos(angle + offset)
            ay = y2 - head * math.sin(angle + offset)
            self.line(x2, y2, ax, ay, stroke=stroke, sw=4)

    def save(self, path: Path) -> None:
        self.parts.append("</svg>")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.parts) + "\n")


def add_header(svg: Svg, title: str, subtitle: str) -> None:
    svg.text(70, 78, title, cls="title")
    svg.text(72, 116, subtitle, cls="subtitle")
    svg.line(70, 138, 1530, 138, stroke="#cbd5e1", sw=2)


def percentiles(values: list[float], lo: float = 2.5, hi: float = 97.5) -> tuple[float, float]:
    xs = sorted(values)
    if not xs:
        return float("nan"), float("nan")

    def pct(p: float) -> float:
        pos = (len(xs) - 1) * p / 100
        low = math.floor(pos)
        high = math.ceil(pos)
        if low == high:
            return xs[low]
        frac = pos - low
        return xs[low] * (1 - frac) + xs[high] * frac

    return pct(lo), pct(hi)


def cluster_bootstrap_by_world(rows: list[dict[str, str]], fault: str, n_boot: int = 5000) -> tuple[float, float, float, int]:
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["fault_label"] == fault and row["metric"] == "completion_time_s":
            groups[row["world_idx"]].append(fnum(row["difference_fault_minus_baseline"]))
    worlds = sorted(groups)
    observed = [value for world in worlds for value in groups[world]]
    rng = random.Random(7)
    boots = []
    for _ in range(n_boot):
        values: list[float] = []
        for _ in worlds:
            world = rng.choice(worlds)
            values.extend(groups[world])
        boots.append(mean(values))
    lo, hi = percentiles(boots)
    return mean(observed), lo, hi, len(observed)


def outcome_counts(rows: list[dict[str, str]]) -> dict[str, Counter[tuple[str, str]]]:
    counts: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    for row in rows:
        if row["metric"] == "completion_time_s":
            counts[row["fault_label"]][(row["baseline_status"], row["fault_status"])] += 1
    return counts


def load_arviz_summary(path: Path) -> dict[str, dict[str, float]]:
    rows = read_csv(path)
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        name = row.get("", "")
        out[name] = {key: fnum(value) for key, value in row.items() if key}
    return out


def figure_01_design() -> None:
    svg = Svg()
    add_header(svg, "Data Analysis Design", "Separate mission outcome from continuous performance before modelling slowdown.")
    steps = [
        ("1", "Outcome transitions", "success / timeout / collision\nanalysed as task outcome"),
        ("2", "Primary estimand", "completion time only for\nmatched-success pairs"),
        ("3", "Uncertainty", "cluster bootstrap by world\n+ hierarchical Bayesian model"),
        ("4", "Mechanism proxy", "stop ratio, speed, controller updates,\nmax stop streak"),
    ]
    x0, y0, w, h, gap = 90, 220, 315, 210, 40
    for idx, (num, title, body) in enumerate(steps):
        x = x0 + idx * (w + gap)
        svg.rect(x, y0, w, h, "#ffffff", "#cbd5e1", 2)
        svg.circle(x + 42, y0 + 52, 26, "#dbeafe")
        svg.text(x + 42, y0 + 61, num, size=24, weight=700, fill="#1d4ed8", anchor="middle")
        svg.text(x + 82, y0 + 58, title, size=24, weight=700)
        svg.multiline(x + 36, y0 + 110, body.split("\n"), cls="note", line_h=31)
        if idx < len(steps) - 1:
            svg.arrow(x + w + 7, y0 + h / 2, x + w + gap - 7, y0 + h / 2)

    svg.rect(155, 535, 1290, 210, "#eff6ff", "#93c5fd", 2)
    svg.text(190, 585, "Why this ordering?", size=28, weight=700, fill="#1d4ed8")
    svg.multiline(
        190,
        635,
        [
            "Not every pair has two successful missions, so mission outcome is not treated as ordinary completion time.",
            "Matched-success pairs form the primary completion-time analysis; all-pair/capped results are sensitivity evidence.",
            "This avoids getting a cleaner-looking result by silently mixing success, timeout and collision semantics.",
        ],
        line_h=34,
    )
    svg.save(OUT / "01_final_analysis_design.svg")


def figure_02_outcomes(pair_rows: list[dict[str, str]]) -> None:
    svg = Svg()
    add_header(svg, "Task Outcome Transitions", "Outcome is analysed before completion time; mixed outcomes justify matched-success as primary.")
    counts = outcome_counts(pair_rows)
    transitions = [
        ("succeeded", "succeeded", "success → success"),
        ("succeeded", "timeout", "success → timeout"),
        ("timeout", "succeeded", "timeout → success"),
        ("timeout", "timeout", "timeout → timeout"),
        ("collided", "succeeded", "collision → success"),
    ]
    x_start, y_base, bar_w, gap = 230, 650, 88, 48
    max_count = max(max(counter.values()) for counter in counts.values())
    for fi, fault in enumerate(["frontal_masking", "lidar_dropout"]):
        x_offset = x_start + fi * 600
        svg.text(x_offset + 190, 205, FAULT_DISPLAY[fault], size=28, weight=700, fill=FAULT_COLORS[fault], anchor="middle")
        for idx, (b, f, label) in enumerate(transitions):
            count = counts[fault][(b, f)]
            h = 360 * count / max_count
            x = x_offset + idx * (bar_w + gap)
            svg.rect(x, y_base - h, bar_w, h, FAULT_COLORS[fault], rx=10)
            svg.text(x + bar_w / 2, y_base - h - 16, count, size=22, weight=700, anchor="middle")
            svg.text(x + bar_w / 2, y_base + 42, label, size=15, anchor="middle", fill="#334155")
    svg.line(160, y_base, 1445, y_base, stroke="#94a3b8", sw=2)
    svg.rect(110, 735, 1380, 85, "#fff7ed", "#fed7aa", 2)
    svg.text(135, 778, "Key point:", size=22, weight=700, fill="#c2410c")
    svg.text(
        260,
        778,
        "No simple systematic shift to failure; many failures are world difficulty. Completion-time inference therefore uses success-success pairs.",
        size=21,
        fill="#334155",
    )
    svg.save(OUT / "02_task_outcome_transitions.svg")


def figure_03_completion(pair_rows: list[dict[str, str]], matched_rows: list[dict[str, str]], main_rows: list[dict[str, str]]) -> None:
    svg = Svg()
    add_header(svg, "Completion-Time Degradation: Primary vs Sensitivity", "Primary = matched-success pairs; all-pair/capped completion is reported only as sensitivity.")
    primary = {fault: cluster_bootstrap_by_world(matched_rows, fault) for fault in FAULT_DISPLAY}
    sensitivity = {}
    for row in main_rows:
        if row["metric"] == "completion_time_s":
            sensitivity[row["fault_label"]] = (
                fnum(row["paired_mean_difference"]),
                fnum(row["bootstrap_ci95_lower"]),
                fnum(row["bootstrap_ci95_upper"]),
                int(fnum(row["pair_count"], 0)),
            )
    panels = [("Primary: matched-success", primary, 220), ("Sensitivity: all pairs / capped", sensitivity, 555)]
    for title, values, y in panels:
        svg.text(145, y - 35, title, size=27, weight=700)
        svg.line(490, y + 145, 1390, y + 145, stroke="#94a3b8", sw=2)
        for tick in [0, 5, 10, 15, 20]:
            x = 490 + tick * 45
            svg.line(x, y + 135, x, y + 155, stroke="#94a3b8", sw=2)
            svg.text(x, y + 180, f"{tick}s", size=15, anchor="middle", fill="#64748b")
        for idx, fault in enumerate(["frontal_masking", "lidar_dropout"]):
            mean_v, lo, hi, n = values[fault]
            cy = y + idx * 78 + 35
            svg.text(165, cy + 8, FAULT_DISPLAY[fault], size=22, weight=700, fill=FAULT_COLORS[fault])
            x0 = 490
            x_mean = x0 + mean_v * 45
            x_lo = x0 + lo * 45
            x_hi = x0 + hi * 45
            svg.line(x_lo, cy, x_hi, cy, stroke="#0f172a", sw=4)
            svg.line(x_lo, cy - 13, x_lo, cy + 13, stroke="#0f172a", sw=3)
            svg.line(x_hi, cy - 13, x_hi, cy + 13, stroke="#0f172a", sw=3)
            svg.circle(x_mean, cy, 13, FAULT_COLORS[fault], "#ffffff", 3)
            svg.text(1120, cy + 8, f"+{fmt(mean_v)}s  CI [{fmt(lo)}, {fmt(hi)}], n={n}", size=20, fill="#334155")
    svg.rect(110, 770, 1380, 70, "#ecfdf5", "#86efac", 2)
    svg.text(135, 813, "Interpretation:", size=21, weight=700, fill="#15803d")
    svg.text(290, 813, "Including non-success/capped outcomes increases estimates but also uncertainty; this supports, not weakens, the primary design.", size=20)
    svg.save(OUT / "03_completion_primary_vs_sensitivity.svg")


def figure_04_model(fault_effects: list[dict[str, str]]) -> None:
    svg = Svg()
    add_header(svg, "Robust Hierarchical Bayesian Model", "Student-t likelihood, pairs nested within worlds, and partial pooling for world susceptibility.")
    svg.rect(95, 185, 690, 310, "#ffffff", "#cbd5e1", 2)
    svg.text(135, 235, "Model specification", size=28, weight=700)
    svg.text(145, 300, "dᵢⱼ ~ Student-t(ν, θⱼ, σ)", size=32, weight=700, fill="#1e3a8a")
    svg.text(145, 355, "θⱼ ~ Normal(μ, τ)", size=32, weight=700, fill="#1e3a8a")
    svg.multiline(
        145,
        415,
        ["i = paired repetition", "j = world", "positive d means performance degradation"],
        line_h=28,
    )
    svg.rect(815, 185, 685, 310, "#ffffff", "#cbd5e1", 2)
    svg.text(855, 235, "Actual priors used", size=28, weight=700)
    svg.multiline(
        865,
        292,
        [
            "μ ~ Normal(0, 10 × prior_scale)",
            "τ, σ ~ HalfNormal(5 × prior_scale)",
            "ν - 2 ~ Exponential(1/30)",
            "θ uses non-centred parameterisation",
        ],
        line_h=36,
    )
    svg.rect(95, 540, 1405, 250, "#f8fafc", "#cbd5e1", 2)
    svg.text(135, 590, "Meeting-level diagnostics for global effect μ", size=27, weight=700)
    x = 155
    for row in fault_effects:
        fault = row["fault_label"]
        svg.rect(x, 630, 585, 95, "#ffffff", "#e2e8f0", 2)
        svg.text(x + 25, 670, FAULT_DISPLAY[fault], size=22, weight=700, fill=FAULT_COLORS[fault])
        svg.text(x + 25, 707, f"R-hat(μ)={float(row['rhat_mu']):.3f}; ESS_bulk(μ)={float(row['ess_bulk_mu']):.0f}; τ median={float(row['posterior_tau_median']):.2f}", size=20)
        x += 635
    svg.text(
        135,
        765,
        "For dissertation: also report all key-parameter R-hat/ESS, divergences and posterior predictive checks.",
        size=20,
        fill="#475569",
    )
    svg.save(OUT / "04_model_specification_diagnostics.svg")


def figure_05_threshold(fault_effects: list[dict[str, str]]) -> None:
    svg = Svg()
    add_header(svg, "Bayesian Threshold Sensitivity", "Thresholds are exploratory practical-effect cutoffs; they should not be over-interpreted as hard pass/fail tests.")
    probs = {
        "frontal_masking": {0: 0.9999, 3: 0.994, 5: 0.843, 7: 0.258},
        "lidar_dropout": {0: 0.998, 3: 0.883, 5: 0.342, 7: 0.033},
    }
    thresholds = [0, 3, 5, 7]
    x0, y0, cell_w, cell_h = 330, 250, 230, 95
    svg.text(115, y0 - 55, "Fault", size=24, weight=700)
    for j, th in enumerate(thresholds):
        svg.text(x0 + j * cell_w + cell_w / 2, y0 - 55, f"P(slowdown > {th}s)", size=22, weight=700, anchor="middle")
    for i, fault in enumerate(["frontal_masking", "lidar_dropout"]):
        y = y0 + i * cell_h
        svg.text(115, y + 58, FAULT_DISPLAY[fault], size=23, weight=700, fill=FAULT_COLORS[fault])
        for j, th in enumerate(thresholds):
            p = probs[fault][th]
            x = x0 + j * cell_w
            fill = "#dbeafe" if fault == "frontal_masking" else "#ffedd5"
            svg.rect(x, y, cell_w - 16, cell_h - 16, fill, "#ffffff", 2, rx=12)
            label = ">0.999" if p >= 0.9995 else f"{p:.3f}"
            svg.text(x + (cell_w - 16) / 2, y + 55, label, size=29, weight=700, anchor="middle", fill="#0f172a")
    svg.rect(115, 515, 1365, 210, "#ffffff", "#cbd5e1", 2)
    svg.text(150, 565, "How to say it", size=28, weight=700)
    svg.multiline(
        150,
        615,
        [
            "Both faults probably slow successful navigation: P(slowdown > 0) is very high under the fitted model.",
            "Evidence for exceeding the exploratory 5s threshold is much stronger for frontal masking.",
            "Dropout is not 'no effect'; it is a smaller / less threshold-stable estimated slowdown.",
        ],
        line_h=34,
    )
    svg.save(OUT / "05_bayesian_threshold_sensitivity_matched_success.svg")


def figure_06_world_forest(world_rows: list[dict[str, str]], arviz: dict[str, dict[str, dict[str, float]]]) -> None:
    svg = Svg()
    add_header(svg, "Posterior World Effects", "Partial pooling separates global fault effect from uncertain world-level susceptibility.")
    faults = ["frontal_masking", "lidar_dropout"]
    for col, fault in enumerate(faults):
        x0 = 170 + col * 725
        y0 = 220
        svg.text(x0 + 250, y0 - 40, FAULT_DISPLAY[fault], size=27, weight=700, fill=FAULT_COLORS[fault], anchor="middle")
        rows = [r for r in world_rows if r["fault_label"] == fault and r["metric"] == "completion_time_s"]
        rows.sort(key=lambda r: int(r["world_idx"]))
        svg.line(x0 + 145, y0 + 25, x0 + 555, y0 + 25, stroke="#94a3b8", sw=2)
        for tick in [-5, 0, 5, 10, 15]:
            x = x0 + 145 + (tick + 5) * 20.5
            svg.line(x, y0 + 15, x, y0 + 35, stroke="#94a3b8", sw=2)
            svg.text(x, y0 + 58, str(tick), size=14, anchor="middle", fill="#64748b")
        svg.text(x0 + 350, y0 + 86, "slowdown seconds", size=15, anchor="middle", fill="#64748b")
        for idx, row in enumerate(rows):
            y = y0 + 120 + idx * 48
            lo = fnum(row["credible_interval_95_lower"])
            hi = fnum(row["credible_interval_95_upper"])
            med = fnum(row["posterior_median"])
            x_lo = x0 + 145 + (lo + 5) * 20.5
            x_hi = x0 + 145 + (hi + 5) * 20.5
            x_med = x0 + 145 + (med + 5) * 20.5
            svg.text(x0 + 15, y + 6, f"W{int(row['world_idx']):03d} (n={row['n_pairs']})", size=16, fill="#334155")
            svg.line(x_lo, y, x_hi, y, stroke="#334155", sw=3)
            svg.circle(x_med, y, 8, FAULT_COLORS[fault], "#ffffff", 2)
    tau_mask = arviz["frontal_masking"].get("tau", {})
    tau_drop = arviz["lidar_dropout"].get("tau", {})
    svg.rect(105, 765, 1390, 78, "#f1f5f9", "#cbd5e1", 2)
    svg.text(135, 810, "Heterogeneity wording:", size=21, weight=700)
    svg.text(
        355,
        810,
        f"τ 89% interval masking=[{tau_mask.get('eti89_lb', float('nan')):.2f}, {tau_mask.get('eti89_ub', float('nan')):.2f}]; dropout=[{tau_drop.get('eti89_lb', float('nan')):.2f}, {tau_drop.get('eti89_ub', float('nan')):.2f}]. Effects appear more variable for dropout, but keep the claim cautious.",
        size=19,
    )
    svg.save(OUT / "06_posterior_world_effect_forest_matched_success.svg")


def figure_07_pipeline(matched_rows: list[dict[str, str]]) -> None:
    svg = Svg()
    add_header(svg, "Pipeline-Level Proxy Evidence", "Descriptive process metrics in matched-success runs; positive values are oriented as degradation.")
    values: dict[str, dict[str, float]] = defaultdict(dict)
    for fault in FAULT_DISPLAY:
        for metric, _, direction in METRIC_ORDER:
            vals = []
            for row in matched_rows:
                if row["fault_label"] == fault and row["metric"] == metric:
                    diff = fnum(row["difference_fault_minus_baseline"])
                    vals.append(-diff if direction == "negative" else diff)
            values[fault][metric] = mean(vals) if vals else float("nan")
    # Normalize per metric for a compact descriptive view.
    x0, y0, group_w = 210, 265, 300
    for idx, (metric, label, _) in enumerate(METRIC_ORDER):
        x = x0 + idx * group_w
        svg.text(x + 95, y0 - 55, label, size=19, weight=700, anchor="middle")
        vals = [values[f][metric] for f in FAULT_DISPLAY]
        max_abs = max(abs(v) for v in vals if math.isfinite(v)) or 1
        for j, fault in enumerate(["frontal_masking", "lidar_dropout"]):
            v = values[fault][metric]
            h = 280 * abs(v) / max_abs
            bx = x + 45 + j * 85
            by = y0 + 310 - h
            svg.rect(bx, by, 58, h, FAULT_COLORS[fault], rx=10)
            svg.text(bx + 29, by - 15, fmt(v, 3 if abs(v) < 1 else 1), size=17, anchor="middle")
        svg.line(x + 20, y0 + 310, x + 210, y0 + 310, stroke="#94a3b8", sw=2)
    svg.rect(195, 630, 1180, 42, "#ffffff", "#e2e8f0", 2)
    svg.circle(235, 651, 10, FAULT_COLORS["frontal_masking"])
    svg.text(255, 657, "Frontal masking", size=18)
    svg.circle(440, 651, 10, FAULT_COLORS["lidar_dropout"])
    svg.text(460, 657, "LiDAR dropout", size=18)
    svg.rect(115, 735, 1370, 80, "#fff7ed", "#fed7aa", 2)
    svg.text(145, 780, "Interpretation:", size=21, weight=700, fill="#c2410c")
    svg.text(300, 780, "Mechanism-consistent proxy evidence only; final proof needs time-aligned scan/costmap/controller/cmd_vel traces.", size=20)
    svg.save(OUT / "07_pipeline_proxy_bars_positive_worse.svg")


def figure_08_cases(world_heterogeneity: list[dict[str, str]]) -> None:
    svg = Svg()
    add_header(svg, "Case Selection for Follow-Up Propagation Evidence", "Use clean typical cases for layer-by-layer evidence; treat extreme cases separately.")
    cases = [
        ("Typical", "frontal_masking", 8, "6/6 matched success; moderate slowdown; controller response observable"),
        ("Typical", "lidar_dropout", 240, "6/6 matched success; moderate slowdown; controller response observable"),
        ("Extreme", "frontal_masking", 173, "largest raw slowdown; high variability; exploratory follow-up"),
        ("Extreme", "lidar_dropout", 76, "largest raw slowdown; high variability; exploratory follow-up"),
    ]
    lookup = {(r["fault_label"], int(r["world_idx"])): r for r in world_heterogeneity}
    x0, y0, w, h = 115, 220, 660, 180
    for idx, (kind, fault, world, reason) in enumerate(cases):
        x = x0 + (idx % 2) * 720
        y = y0 + (idx // 2) * 220
        row = lookup.get((fault, world), {})
        svg.rect(x, y, w, h, "#ffffff", "#cbd5e1", 2)
        svg.text(x + 28, y + 48, f"{kind}: W{world:03d} / {FAULT_DISPLAY[fault]}", size=25, weight=700, fill=FAULT_COLORS[fault])
        if row:
            svg.text(x + 28, y + 90, f"raw slowdown mean: {fmt(fnum(row['completion_slowdown_mean_s']))}s; success counts B/F: {row['baseline_success_count']}/{row['fault_success_count']}", size=19)
            svg.text(x + 28, y + 124, f"controller update delta: {fmt(fnum(row['controller_new_path_delta_mean']), 1)}", size=19)
        svg.text(x + 28, y + 158, reason, size=17, fill="#475569")
    svg.rect(120, 740, 1360, 70, "#ecfdf5", "#86efac", 2)
    svg.text(150, 782, "Typical-case rule:", size=21, weight=700, fill="#15803d")
    svg.text(340, 782, "clean 6/6 matched success + measurable non-extreme slowdown + observable controller response.", size=20)
    svg.save(OUT / "08_case_selection_typical_extreme.svg")


def figure_09_questions() -> None:
    svg = Svg()
    add_header(svg, "Analysis Questions and Current Evidence", "The current analysis supports effect estimation; full cross-layer propagation is the next evidence target.")
    rows = [
        ("Q1", "Do faults slow successful navigation?", "Supported", "Matched-success bootstrap + Bayesian estimates show positive slowdown."),
        ("Q2", "How does intermittent dropout differ from continuous masking?", "Directional support", "Dropout appears smaller / less threshold-stable than masking."),
        ("Q3", "Does susceptibility vary across environments?", "Supported, nuanced", "World effects differ, but claims about stronger dropout heterogeneity need τ/PPC support."),
        ("Q4", "Can we explain the effect through the Nav2 pipeline?", "Partial", "Proxy metrics are mechanism-consistent; time-aligned propagation evidence remains next step."),
    ]
    y = 205
    colors = {"Supported": "#dcfce7", "Directional support": "#fef9c3", "Supported, nuanced": "#e0f2fe", "Partial": "#ffedd5"}
    for q, question, status, evidence in rows:
        svg.rect(105, y, 1390, 115, "#ffffff", "#cbd5e1", 2)
        svg.circle(155, y + 58, 32, "#e2e8f0")
        svg.text(155, y + 68, q, size=24, weight=700, anchor="middle")
        svg.text(210, y + 46, question, size=24, weight=700)
        svg.rect(990, y + 25, 270, 42, colors[status], "#ffffff", 1, rx=20)
        svg.text(1125, y + 54, status, size=18, weight=700, anchor="middle")
        svg.text(210, y + 88, evidence, size=19, fill="#475569")
        y += 135
    svg.rect(135, 765, 1330, 62, "#f1f5f9", "#cbd5e1", 2)
    svg.text(165, 804, "Next highest-value work:", size=21, weight=700)
    svg.text(405, 804, "W8 masking + W240 dropout time-aligned scan → costmap → controller → cmd_vel → motion evidence.", size=20)
    svg.save(OUT / "09_analysis_questions_current_evidence.svg")


def write_notes(fault_effects: list[dict[str, str]]) -> None:
    notes = OUT / "ppt_v4_speaker_notes.md"
    lines = [
        "# PPT v4 Speaker Notes",
        "",
        "## Key wording changes from v3",
        "",
        "- Put task outcome transitions before completion-time inference.",
        "- Primary completion-time estimand is matched-success only.",
        "- All-pair/capped completion-time analysis is sensitivity evidence, not the primary estimate.",
        "- Pipeline metrics are mechanism-consistent proxy evidence, not formal proof of propagation.",
        "- Do not claim dropout has greater heterogeneity unless tau posterior intervals are explicitly compared.",
        "- Use 'smaller / less threshold-stable estimated effect' for dropout rather than 'not meaningful'.",
        "",
        "## Actual Bayesian model details",
        "",
        "```text",
        "d_ij ~ StudentT(nu, theta_j, sigma)",
        "theta_j = mu + tau * theta_offset_j",
        "theta_offset_j ~ Normal(0, 1)",
        "mu ~ Normal(0, 10 * prior_scale)",
        "tau ~ HalfNormal(5 * prior_scale)",
        "sigma ~ HalfNormal(5 * prior_scale)",
        "nu_minus_two ~ Exponential(1/30)",
        "nu = nu_minus_two + 2",
        "```",
        "",
        "The model uses a Student-t likelihood to reduce sensitivity to long-tail Gazebo/Nav2 timing outliers.",
        "",
        "## Primary matched-success Bayesian results",
        "",
    ]
    for row in fault_effects:
        lines.append(
            f"- {FAULT_DISPLAY[row['fault_label']]}: n={row['n_pairs']}, posterior median "
            f"{float(row['posterior_median']):.2f}s, 95% CrI "
            f"[{float(row['credible_interval_95_lower']):.2f}, {float(row['credible_interval_95_upper']):.2f}], "
            f"P(>0)={('>0.999' if float(row['p_global_degradation']) >= 0.9995 else f'{float(row['p_global_degradation']):.3f}')}, "
            f"P(>5s)={float(row['p_global_meaningful_degradation']):.3f}."
        )
    lines.extend(
        [
            "",
            "## Safe one-sentence conclusion",
            "",
            "Both faults probably slow successful navigation under the fitted model, but evidence for a larger slowdown above the exploratory 5s threshold is much stronger for frontal masking.",
        ]
    )
    notes.write_text("\n".join(lines) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PNG_OUT.mkdir(parents=True, exist_ok=True)

    pair_rows = read_csv(ROOT / "thesis_pair_level_metric_differences.csv")
    matched_rows = read_csv(ROOT / "thesis_pair_level_metric_differences_matched_success.csv")
    main_rows = read_csv(ROOT / "thesis_main_paired_effects.csv")
    fault_effects = read_csv(ROOT / "pymc_hierarchical_matched_success_completion/pymc_hierarchical_fault_effects.csv")
    world_effects = read_csv(ROOT / "pymc_hierarchical_matched_success_completion/pymc_hierarchical_world_effects.csv")
    world_heterogeneity = read_csv(ROOT / "thesis_world_heterogeneity.csv")
    arviz = {
        "frontal_masking": load_arviz_summary(ROOT / "pymc_hierarchical_matched_success_completion/frontal_masking__completion_time_s_arviz_summary.csv"),
        "lidar_dropout": load_arviz_summary(ROOT / "pymc_hierarchical_matched_success_completion/lidar_dropout__completion_time_s_arviz_summary.csv"),
    }

    figure_01_design()
    figure_02_outcomes(pair_rows)
    figure_03_completion(pair_rows, matched_rows, main_rows)
    figure_04_model(fault_effects)
    figure_05_threshold(fault_effects)
    figure_06_world_forest(world_effects, arviz)
    figure_07_pipeline(matched_rows)
    figure_08_cases(world_heterogeneity)
    figure_09_questions()
    write_notes(fault_effects)

    for svg in sorted(OUT.glob("*.svg")):
        png = PNG_OUT / f"{svg.stem}.png"
        subprocess.run(["convert", "-density", "180", str(svg), str(png)], check=True)
        print(png)

    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
