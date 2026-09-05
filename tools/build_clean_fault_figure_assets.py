#!/usr/bin/env python3
"""Generate clean chart assets for the fault-injection data analysis.

This intentionally creates figure assets only: no slide titles, no explanatory
footer text, no background panels, and transparent output suitable for PPT or
thesis reuse.
"""

from __future__ import annotations

import csv
import math
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path("/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis")
OUT = ROOT / "clean_figure_assets_v2"
PNG_OUT = OUT / "png"

TEAL = "#148A84"
ORANGE = "#F57C16"
GREY = "#6b7280"
DARK = "#111827"
GRID = "#d1d5db"
LIGHT_GREY = "#f3f4f6"
ZERO = "#1f2937"

FAULTS = ["frontal_masking", "lidar_dropout"]
FAULT_LABEL = {"frontal_masking": "Frontal masking", "lidar_dropout": "LiDAR dropout"}
FAULT_SHORT = {"frontal_masking": "Masking", "lidar_dropout": "Dropout"}
FAULT_COLOR = {"frontal_masking": TEAL, "lidar_dropout": ORANGE}
OUTCOMES = ["succeeded", "timeout", "collided"]
OUTCOME_LABEL = {"succeeded": "success", "timeout": "timeout", "collided": "collision"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def fnum(value: object, default: float = float("nan")) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def fmt(value: float, digits: int = 2, plus: bool = False) -> str:
    if not math.isfinite(value):
        return "NA"
    sign = "+" if plus and value >= 0 else ""
    return f"{sign}{value:.{digits}f}"


def esc(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class Svg:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            "<style><![CDATA[",
            "text{font-family:Arial,Helvetica,sans-serif;fill:#111827}",
            ".axis{font-size:15px;fill:#374151}",
            ".tick{font-size:13px;fill:#6b7280}",
            ".label{font-size:16px;font-weight:700}",
            ".small{font-size:13px;fill:#4b5563}",
            ".value{font-size:14px;font-weight:700}",
            "]]></style>",
        ]

    def rect(self, x: float, y: float, w: float, h: float, fill: str, stroke: str = "none", sw: float = 1, rx: float = 0, opacity: float = 1.0) -> None:
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"/>')

    def line(self, x1: float, y1: float, x2: float, y2: float, stroke: str = GRID, sw: float = 1.5, dash: str | None = None) -> None:
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{dash_attr}/>')

    def circle(self, x: float, y: float, r: float, fill: str, stroke: str = "white", sw: float = 2, opacity: float = 1.0) -> None:
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"/>')

    def polyline(self, points: list[tuple[float, float]], stroke: str, sw: float = 3) -> None:
        p = " ".join(f"{x},{y}" for x, y in points)
        self.parts.append(f'<polyline points="{p}" fill="none" stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"/>')

    def text(self, x: float, y: float, text: object, cls: str = "", size: int | None = None, weight: int | None = None, fill: str | None = None, anchor: str = "start", rotate: float | None = None) -> None:
        style = []
        if size:
            style.append(f"font-size:{size}px")
        if weight:
            style.append(f"font-weight:{weight}")
        if fill:
            style.append(f"fill:{fill}")
        style_attr = f' style="{";".join(style)}"' if style else ""
        cls_attr = f' class="{cls}"' if cls else ""
        transform = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
        self.parts.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}"{cls_attr}{style_attr}{transform}>{esc(text)}</text>')

    def arrow(self, x1: float, y1: float, x2: float, y2: float, stroke: str = GREY) -> None:
        self.line(x1, y1, x2, y2, stroke=stroke, sw=2)
        angle = math.atan2(y2 - y1, x2 - x1)
        head = 9
        for offset in (2.55, -2.55):
            ax = x2 - head * math.cos(angle + offset)
            ay = y2 - head * math.sin(angle + offset)
            self.line(x2, y2, ax, ay, stroke=stroke, sw=2)

    def save(self, path: Path) -> None:
        self.parts.append("</svg>")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.parts) + "\n")


def interpolate_color(base: str, intensity: float) -> str:
    intensity = max(0.0, min(1.0, intensity))
    base = base.lstrip("#")
    r = int(base[0:2], 16)
    g = int(base[2:4], 16)
    b = int(base[4:6], 16)
    # Blend with white for a clean heatmap.
    rb = int(255 * (1 - intensity) + r * intensity)
    gb = int(255 * (1 - intensity) + g * intensity)
    bb = int(255 * (1 - intensity) + b * intensity)
    return f"#{rb:02x}{gb:02x}{bb:02x}"


def scale_linear(v: float, dmin: float, dmax: float, rmin: float, rmax: float) -> float:
    if dmax == dmin:
        return (rmin + rmax) / 2
    return rmin + (v - dmin) / (dmax - dmin) * (rmax - rmin)


def analysis_pipeline_only() -> None:
    svg = Svg(980, 430)

    def box(x: float, y: float, w: float, h: float, text: str, fill: str = "white", stroke: str = GREY) -> None:
        svg.rect(x, y, w, h, fill, stroke, 1.5, rx=10)
        lines = text.split("\n")
        for i, line in enumerate(lines):
            svg.text(x + w / 2, y + h / 2 - (len(lines) - 1) * 9 + i * 20 + 6, line, size=15, weight=700 if i == 0 else None, anchor="middle")

    box(35, 165, 120, 58, "paired\nruns", "#ffffff")
    box(205, 165, 135, 58, "pair\ndifferences", "#ffffff")
    svg.arrow(155, 194, 205, 194)
    branches = [
        (420, 60, "descriptive\nsummary", GREY),
        (420, 165, "cluster\nbootstrap", GREY),
        (420, 270, "robust hierarchical\nBayesian", GREY),
    ]
    for x, y, label, color in branches:
        svg.arrow(340, 194, x, y + 29, stroke=color)
        box(x, y, 160, 58, label, "#ffffff", color)
    box(665, 235, 120, 48, "global\neffect", "#f0fdfa", TEAL)
    box(665, 295, 120, 48, "world\neffects", "#fff7ed", ORANGE)
    box(665, 355, 120, 48, "probabilities", "#f3f4f6", GREY)
    svg.arrow(580, 299, 665, 259, TEAL)
    svg.arrow(580, 299, 665, 319, ORANGE)
    svg.arrow(580, 299, 665, 379, GREY)
    box(850, 165, 100, 58, "interpretation", "#ffffff", DARK)
    for sx, sy in [(580, 89), (580, 194), (785, 259), (785, 319), (785, 379)]:
        svg.arrow(sx, sy, 850, 194, GREY)
    svg.save(OUT / "analysis_pipeline_only.svg")


def task_outcome_transition_matrices(pair_rows: list[dict[str, str]]) -> None:
    svg = Svg(930, 390)
    counts: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    for row in pair_rows:
        if row["metric"] == "completion_time_s":
            counts[row["fault_label"]][(row["baseline_status"], row["fault_status"])] += 1
    max_count = max(max(counter.values()) for counter in counts.values())
    panel_w, cell = 365, 72
    for pidx, fault in enumerate(FAULTS):
        left = 85 + pidx * 465
        top = 78
        svg.text(left + cell * 1.5, 28, FAULT_LABEL[fault], size=18, weight=700, fill=FAULT_COLOR[fault], anchor="middle")
        svg.text(left + cell * 1.5, 56, "fault outcome", cls="axis", anchor="middle")
        svg.text(left - 62, top + cell * 1.5, "baseline outcome", cls="axis", anchor="middle", rotate=-90)
        for j, outcome in enumerate(OUTCOMES):
            svg.text(left + j * cell + cell / 2, top - 12, OUTCOME_LABEL[outcome], size=12, anchor="middle", fill="#4b5563")
        for i, base in enumerate(OUTCOMES):
            svg.text(left - 12, top + i * cell + cell / 2 + 5, OUTCOME_LABEL[base], size=12, anchor="end", fill="#4b5563")
            for j, fault_out in enumerate(OUTCOMES):
                n = counts[fault][(base, fault_out)]
                color = interpolate_color(FAULT_COLOR[fault], 0.12 + 0.88 * n / max_count)
                x, y = left + j * cell, top + i * cell
                svg.rect(x, y, cell - 4, cell - 4, color, "#ffffff", 1, rx=5)
                svg.text(x + cell / 2 - 2, y + cell / 2 + 6, n, size=20, weight=700, anchor="middle", fill=DARK if n < max_count * 0.45 else "white")
    svg.save(OUT / "task_outcome_transition_matrices.svg")



def completion_time_primary_and_sensitivity() -> None:
    svg = Svg(920, 285)
    x0, y0, scale = 170, 70, 50
    primary = [
        ("Masking", TEAL, 5.97, 3.36, 8.46, 47),
        ("Dropout", ORANGE, 4.77, 2.11, 7.03, 40),
    ]
    sensitivity = [
        ("Masking", 9.21, -0.2, 23.9),
        ("Dropout", 6.43, -2.5, 19.5),
    ]

    # Primary forest plot: visually dominant, 0-10s axis.
    svg.text(18, 32, "Matched-success primary", size=16, weight=700)
    svg.line(x0, 188, x0 + 500, 188, stroke=GRID)
    svg.line(x0, 42, x0, 200, stroke=ZERO, sw=1.7, dash="5 5")
    for tick in [0, 2, 4, 6, 8, 10]:
        x = x0 + tick * scale
        svg.line(x, 181, x, 195, stroke=GRID)
        svg.text(x, 216, tick, cls="tick", anchor="middle")
    for i, (label, color, m, lo, hi, n) in enumerate(primary):
        y = y0 + i * 58
        svg.text(98, y + 5, label, size=15, weight=700, fill=color, anchor="end")
        svg.line(x0 + lo * scale, y, x0 + hi * scale, y, stroke=DARK, sw=2.8)
        svg.line(x0 + lo * scale, y - 10, x0 + lo * scale, y + 10, stroke=DARK, sw=2)
        svg.line(x0 + hi * scale, y - 10, x0 + hi * scale, y + 10, stroke=DARK, sw=2)
        svg.circle(x0 + m * scale, y, 7.5, color)
        svg.text(x0 + 525, y + 5, f"{fmt(m, 2, True)} s [{fmt(lo)}, {fmt(hi)}], n={n}", size=14)
    svg.text(x0 + 250, 250, "fault-minus-baseline completion time (s)", cls="axis", anchor="middle")

    # Compact grey sensitivity table, deliberately not on the main axis.
    bx, by, bw, bh = 690, 45, 210, 120
    svg.rect(bx, by, bw, bh, "#f9fafb", GRID, 1.2, rx=8)
    svg.text(bx + 15, by + 27, "All-pair sensitivity", size=14, weight=700, fill=GREY)
    for i, (label, m, lo, hi) in enumerate(sensitivity):
        y = by + 62 + i * 36
        svg.text(bx + 15, y, label, size=13, weight=700, fill=GREY)
        svg.text(bx + 82, y, f"{fmt(m, 2, True)} s", size=13, fill=GREY)
        svg.text(bx + 145, y, f"[{fmt(lo, 1)}, {fmt(hi, 1)}]", size=13, fill=GREY)
    svg.save(OUT / "completion_time_primary_and_sensitivity.svg")

def global_bayesian_posterior_forest() -> None:
    svg = Svg(780, 210)
    rows = [
        ("Masking", TEAL, 6.25, 3.73, 8.83),
        ("Dropout", ORANGE, 4.54, 1.63, 7.27),
    ]
    x0, y0, scale = 180, 60, 45
    svg.line(x0, 155, x0 + 560, 155, stroke=GRID)
    svg.line(x0, 30, x0, 170, stroke=ZERO, sw=1.6, dash="5 5")
    for tick in [0, 3, 5, 7, 10]:
        x = x0 + tick * scale
        svg.line(x, 148, x, 162, stroke=GRID)
        svg.text(x, 185, tick, cls="tick", anchor="middle")
    for i, (label, color, med, lo, hi) in enumerate(rows):
        y = y0 + i * 55
        svg.text(115, y + 5, label, size=15, weight=700, fill=color, anchor="end")
        svg.line(x0 + lo * scale, y, x0 + hi * scale, y, stroke=DARK, sw=2.5)
        svg.circle(x0 + med * scale, y, 7, color)
        svg.text(x0 + 390, y + 5, f"{fmt(med)} [{fmt(lo)}, {fmt(hi)}]", size=14)
    svg.text(x0 + 250, 205, "posterior completion-time slowdown (s)", cls="axis", anchor="middle")
    svg.save(OUT / "global_bayesian_posterior_forest.svg")



def posterior_probability_threshold_curve() -> None:
    svg = Svg(780, 430)
    data = {
        "frontal_masking": [(0, 0.9995, ">0.999"), (3, 0.994, "0.994"), (5, 0.843, "0.843"), (7, 0.258, "0.258")],
        "lidar_dropout": [(0, 0.998, "0.998"), (3, 0.883, "0.883"), (5, 0.342, "0.342"), (7, 0.033, "0.033")],
    }
    left, top, w, h = 90, 35, 610, 310
    svg.line(left, top + h, left + w, top + h, stroke=DARK)
    svg.line(left, top, left, top + h, stroke=DARK)
    for yv in [0, 0.25, 0.5, 0.75, 1.0]:
        y = top + h - yv * h
        svg.line(left, y, left + w, y, stroke=GRID, sw=1)
        svg.text(left - 12, y + 5, f"{yv:.2f}", cls="tick", anchor="end")
    for xv in [0, 3, 5, 7]:
        x = left + xv / 7 * w
        svg.line(x, top + h, x, top + h + 7, stroke=DARK)
        svg.text(x, top + h + 28, xv, cls="tick", anchor="middle")

    label_offsets = {
        ("frontal_masking", 0): (10, -18),
        ("lidar_dropout", 0): (10, 22),
        ("frontal_masking", 3): (8, -15),
        ("lidar_dropout", 3): (8, 20),
        ("frontal_masking", 5): (8, -14),
        ("lidar_dropout", 5): (8, 19),
        ("frontal_masking", 7): (-10, -13),
        ("lidar_dropout", 7): (-10, 21),
    }
    for fault in FAULTS:
        pts = [(left + x / 7 * w, top + h - y * h) for x, y, _ in data[fault]]
        svg.polyline(pts, FAULT_COLOR[fault], sw=3)
        for (xv, yv, label), (x, y) in zip(data[fault], pts):
            svg.circle(x, y, 6.5, FAULT_COLOR[fault])
            dx, dy = label_offsets[(fault, xv)]
            anchor = "end" if dx < 0 else "start"
            svg.text(x + dx, y + dy, label, size=12, fill=FAULT_COLOR[fault], anchor=anchor)
    svg.text(left + w / 2, 410, "Slowdown threshold (s)", cls="axis", anchor="middle")
    svg.text(16, top + h / 2, "Posterior probability", cls="axis", anchor="middle", rotate=-90)
    svg.circle(495, 35, 6, TEAL)
    svg.text(510, 40, "Frontal masking", size=13)
    svg.circle(625, 35, 6, ORANGE)
    svg.text(640, 40, "LiDAR dropout", size=13)
    svg.save(OUT / "posterior_probability_threshold_curve.svg")


def posterior_world_effect_forest(world_rows: list[dict[str, str]]) -> None:
    svg = Svg(1060, 560)
    # Shared x-axis scale across panels to avoid visual heterogeneity artefacts.
    x_min, x_max = -5, 15
    for col, fault in enumerate(FAULTS):
        left = 75 + col * 515
        top = 45
        rows = [r for r in world_rows if r["fault_label"] == fault and r["metric"] == "completion_time_s"]
        rows.sort(key=lambda r: fnum(r["posterior_median"]), reverse=True)
        svg.text(left + 235, 18, FAULT_LABEL[fault], size=16, weight=700, fill=FAULT_COLOR[fault], anchor="middle")
        x0, axis_w = left + 112, 390
        svg.line(x0, top + 440, x0 + axis_w, top + 440, stroke=GRID)
        zero_x = scale_linear(0, x_min, x_max, x0, x0 + axis_w)
        svg.line(zero_x, top + 12, zero_x, top + 455, stroke=ZERO, sw=1.5, dash="5 5")
        for tick in [-5, 0, 5, 10, 15]:
            x = scale_linear(tick, x_min, x_max, x0, x0 + axis_w)
            svg.line(x, top + 433, x, top + 447, stroke=GRID)
            svg.text(x, top + 472, tick, cls="tick", anchor="middle")
        for i, row in enumerate(rows):
            y = top + 35 + i * 43
            lo = fnum(row["credible_interval_95_lower"])
            hi = fnum(row["credible_interval_95_upper"])
            med = fnum(row["posterior_median"])
            svg.text(left + 3, y + 5, f"W{int(row['world_idx']):03d}", size=12, anchor="start")
            svg.text(left + 58, y + 5, f"n={row['n_pairs']}", size=11, fill=GREY)
            svg.line(scale_linear(lo, x_min, x_max, x0, x0 + axis_w), y, scale_linear(hi, x_min, x_max, x0, x0 + axis_w), y, stroke=DARK, sw=2)
            svg.circle(scale_linear(med, x_min, x_max, x0, x0 + axis_w), y, 5.8, FAULT_COLOR[fault])
    svg.text(530, 548, "posterior world-level slowdown (s)", cls="axis", anchor="middle")
    svg.save(OUT / "posterior_world_effect_forest.svg")

def pipeline_proxy_small_multiples(matched_rows: list[dict[str, str]]) -> None:
    svg = Svg(860, 430)
    # Values are the final rounded thesis-analysis values, all oriented so positive=worse.
    metrics = [
        ("Stop ratio increase", 0.05, 0.03, 3),
        ("Speed decrease", 0.0013, 0.0010, 4),
        ("Controller update increase", 5.91, 4.83, 2),
        ("Max stop streak increase", 10.77, 14.29, 2),
    ]
    panel_w, panel_h = 360, 145
    positions = [(30, 25), (470, 25), (30, 220), (470, 220)]
    for (label, masking, dropout, digits), (left, top) in zip(metrics, positions):
        svg.text(left, top, label, size=15, weight=700)
        local_max = max(masking, dropout) * 1.18
        bar_x, bar_y = left + 115, top + 35
        bar_max_w = 185
        for i, (name, val, color) in enumerate([("Masking", masking, TEAL), ("Dropout", dropout, ORANGE)]):
            y = bar_y + i * 42
            w = val / local_max * bar_max_w if local_max else 0
            svg.text(left + 100, y + 15, name, size=12, fill="#374151", anchor="end")
            svg.rect(bar_x, y, w, 18, color, rx=4)
            svg.text(bar_x + w + 8, y + 15, fmt(val, digits), size=12, weight=700, fill=DARK)
    svg.circle(355, 410, 6, TEAL)
    svg.text(370, 415, "Frontal masking", size=12)
    svg.circle(505, 410, 6, ORANGE)
    svg.text(520, 415, "LiDAR dropout", size=12)
    svg.save(OUT / "pipeline_proxy_small_multiples.svg")


def world_case_selection_scatter(world_rows: list[dict[str, str]]) -> None:
    svg = Svg(1060, 470)
    selected = {
        ("frontal_masking", 8): "typical",
        ("frontal_masking", 173): "extreme",
        ("lidar_dropout", 240): "typical",
        ("lidar_dropout", 76): "extreme",
    }
    label_offsets = {
        ("frontal_masking", 8): (14, -15),
        ("frontal_masking", 173): (-20, -20),
        ("lidar_dropout", 240): (14, 22),
        ("lidar_dropout", 76): (-18, -20),
    }
    for pidx, fault in enumerate(FAULTS):
        left, top, w, h = 75 + pidx * 505, 45, 395, 320
        rows = [r for r in world_rows if r["fault_label"] == fault]
        xs = [fnum(r["controller_new_path_delta_mean"]) for r in rows]
        ys = [fnum(r["completion_slowdown_mean_s"]) for r in rows]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        xpad = max((xmax - xmin) * 0.14, 1)
        ypad = max((ymax - ymin) * 0.14, 1)
        xmin, xmax = xmin - xpad, xmax + xpad
        ymin, ymax = ymin - ypad, ymax + ypad
        svg.text(left + w / 2, 20, FAULT_LABEL[fault], size=16, weight=700, fill=FAULT_COLOR[fault], anchor="middle")
        svg.line(left, top + h, left + w, top + h, stroke=DARK)
        svg.line(left, top, left, top + h, stroke=DARK)
        zero_y = scale_linear(0, ymin, ymax, top + h, top)
        zero_x = scale_linear(0, xmin, xmax, left, left + w)
        if top <= zero_y <= top + h:
            svg.line(left, zero_y, left + w, zero_y, stroke=ZERO, sw=1.3, dash="5 5")
        if left <= zero_x <= left + w:
            svg.line(zero_x, top, zero_x, top + h, stroke=ZERO, sw=1.3, dash="5 5")
        for tick in [xmin, (xmin + xmax) / 2, xmax]:
            x = scale_linear(tick, xmin, xmax, left, left + w)
            svg.line(x, top + h, x, top + h + 6, stroke=DARK)
            svg.text(x, top + h + 24, fmt(tick, 0), cls="tick", anchor="middle")
        for tick in [ymin, (ymin + ymax) / 2, ymax]:
            y = scale_linear(tick, ymin, ymax, top + h, top)
            svg.line(left - 6, y, left, y, stroke=DARK)
            svg.text(left - 10, y + 5, fmt(tick, 0), cls="tick", anchor="end")
        # Draw ordinary worlds first without large labels.
        for r in rows:
            world = int(r["world_idx"])
            if (fault, world) in selected:
                continue
            x = scale_linear(fnum(r["controller_new_path_delta_mean"]), xmin, xmax, left, left + w)
            y = scale_linear(fnum(r["completion_slowdown_mean_s"]), ymin, ymax, top + h, top)
            svg.circle(x, y, 5.5, FAULT_COLOR[fault], "white", 1.4, opacity=0.42)
            svg.text(x + 6, y - 5, f"W{world}", size=9, fill="#9ca3af")
        # Draw selected worlds with strong outlines and labels.
        for r in rows:
            world = int(r["world_idx"])
            kind = selected.get((fault, world))
            if not kind:
                continue
            x = scale_linear(fnum(r["controller_new_path_delta_mean"]), xmin, xmax, left, left + w)
            y = scale_linear(fnum(r["completion_slowdown_mean_s"]), ymin, ymax, top + h, top)
            stroke = "white" if kind == "typical" else "#991b1b"
            svg.circle(x, y, 10.5, FAULT_COLOR[fault], stroke, 3.2, opacity=0.95)
            dx, dy = label_offsets[(fault, world)]
            anchor = "end" if dx < 0 else "start"
            svg.text(x + dx, y + dy, f"W{world} — {kind}", size=12, weight=700, fill=DARK, anchor=anchor)
    svg.text(520, 454, "world-level controller-update delta", cls="axis", anchor="middle")
    svg.text(18, 235, "raw completion-time slowdown (s)", cls="axis", anchor="middle", rotate=-90)
    svg.circle(760, 427, 8, "#ffffff", "white", 3)
    svg.circle(760, 427, 5, GREY, "white", 1)
    svg.text(775, 432, "other worlds", size=12)
    svg.circle(870, 427, 8, TEAL, "white", 3)
    svg.text(885, 432, "typical", size=12)
    svg.circle(950, 427, 8, TEAL, "#991b1b", 3)
    svg.text(965, 432, "extreme", size=12)
    svg.save(OUT / "world_case_selection_scatter.svg")

def convert_pngs() -> None:
    PNG_OUT.mkdir(parents=True, exist_ok=True)
    for svg in sorted(OUT.glob("*.svg")):
        png = PNG_OUT / f"{svg.stem}.png"
        subprocess.run(
            ["convert", "-background", "none", "-density", "320", str(svg), str(png)],
            check=True,
        )
        print(png)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pair_rows = read_csv(ROOT / "thesis_pair_level_metric_differences.csv")
    matched_rows = read_csv(ROOT / "thesis_pair_level_metric_differences_matched_success.csv")
    world_effect_rows = read_csv(ROOT / "pymc_hierarchical_matched_success_completion/pymc_hierarchical_world_effects.csv")
    world_rows = read_csv(ROOT / "thesis_world_heterogeneity.csv")

    analysis_pipeline_only()
    task_outcome_transition_matrices(pair_rows)
    completion_time_primary_and_sensitivity()
    global_bayesian_posterior_forest()
    posterior_probability_threshold_curve()
    posterior_world_effect_forest(world_effect_rows)
    pipeline_proxy_small_multiples(matched_rows)
    world_case_selection_scatter(world_rows)
    convert_pngs()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
