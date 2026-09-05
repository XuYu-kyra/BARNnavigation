#!/usr/bin/env python3
"""Replot direct-propagation trace CSVs with dissertation-ready labels.

The original trace extractor stores time as rosbag elapsed time. This plotting
helper realigns each trace so that the observed fault-active transition maps to
the configured experiment fault onset, e.g. 15 s. This makes the figure match
the experiment definition while preserving the raw extracted signal values.
It has a pure-SVG fallback so it can run even without matplotlib.
"""

from __future__ import annotations

import argparse
import csv
import math
import subprocess
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Trace metrics CSV")
    parser.add_argument("--output", required=True, help="Output PNG/SVG path")
    parser.add_argument("--label", required=True, help="Figure title label")
    parser.add_argument("--fault-start-s", type=float, default=15.0)
    parser.add_argument("--fault-duration-s", type=float, default=20.0)
    parser.add_argument("--xmax-s", type=float, default=300.0)
    parser.add_argument("--dpi", type=int, default=300)
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            row: dict[str, float] = {}
            for key, value in raw.items():
                try:
                    row[key] = float(value)
                except (TypeError, ValueError):
                    row[key] = math.nan
            rows.append(row)
    if not rows:
        raise RuntimeError(f"No rows found in {path}")
    return rows


def arr(rows: list[dict[str, float]], key: str) -> np.ndarray:
    return np.asarray([r.get(key, math.nan) for r in rows], dtype=float)


def experiment_time(rows: list[dict[str, float]], fault_start_s: float) -> tuple[np.ndarray, float | None]:
    raw_t = arr(rows, "t_s")
    fault = arr(rows, "fault_active")
    active = np.where(fault > 0.5)[0]
    if active.size == 0:
        return raw_t, None
    raw_fault_start = float(raw_t[active[0]])
    return raw_t - raw_fault_start + fault_start_s, raw_fault_start


def plot_matplotlib(args: argparse.Namespace) -> bool:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ModuleNotFoundError:
        return False

    rows = read_rows(Path(args.csv))
    t, raw_fault_start = experiment_time(rows, args.fault_start_s)
    fault_end = args.fault_start_s + args.fault_duration_s

    fig, axes = plt.subplots(6, 1, figsize=(12.5, 10.2), sharex=True)
    fig.suptitle(args.label, fontsize=13, fontweight="bold")

    panels = [
        ("Fault state\n(binary)", [(arr(rows, "fault_active"), "fault active", "black", 1.8)], (-0.05, 1.05)),
        (
            "Frontal LiDAR sector\nreturn ratios (0-1)",
            [
                (arr(rows, "scan_range_max_ratio"), "max-range return ratio", "#008c8c", 1.4),
                (arr(rows, "scan_span_ratio"), "longest max-range span ratio", "#005f73", 1.2),
            ],
            (-0.03, 1.05),
        ),
        (
            "Local costmap\ncell ratios (0-1)",
            [
                (arr(rows, "local_costmap_occupied_ratio"), "occupied cell ratio", "#6c757d", 1.4),
                (arr(rows, "local_costmap_lethal_ratio"), "lethal cell ratio", "#343a40", 1.4),
            ],
            None,
        ),
        (
            "Commanded velocity\nm/s and rad/s",
            [
                (arr(rows, "cmd_linear_x"), "linear x command (m/s)", "#1f77b4", 1.2),
                (arr(rows, "cmd_angular_z"), "angular z command (rad/s)", "#d62728", 1.2),
            ],
            None,
        ),
        ("Robot speed from odometry\nm/s", [(arr(rows, "odom_speed"), "robot speed magnitude (m/s)", "#2ca02c", 1.5)], (0.0, None)),
        (
            "Plan update count\ncumulative",
            [
                (arr(rows, "global_plan_update_count"), "global plan updates", "#9467bd", 1.4),
                (arr(rows, "local_plan_update_count"), "local plan updates", "#ff7f0e", 1.4),
            ],
            None,
        ),
    ]

    for ax, (ylabel, lines, ylim) in zip(axes, panels):
        ax.axvspan(args.fault_start_s, fault_end, color="#008c8c", alpha=0.10)
        ax.axvline(args.fault_start_s, color="#008c8c", linestyle="--", linewidth=0.9)
        ax.axvline(fault_end, color="#008c8c", linestyle="--", linewidth=0.9)
        for values, legend, color, linewidth in lines:
            ax.plot(t, values, label=legend, color=color, linewidth=linewidth)
        ax.set_ylabel(ylabel)
        if ylim is not None:
            ax.set_ylim(bottom=ylim[0], top=ylim[1])
        ax.grid(True, alpha=0.22)
        ax.legend(loc="upper right", fontsize=8, frameon=True)

    axes[3].axhline(0.0, color="black", linestyle=":", linewidth=0.8, alpha=0.65)
    axes[-1].set_xlim(0.0, args.xmax_s)
    axes[-1].set_xlabel("Experiment-aligned simulation time (s)")

    note = "configured fault window: 15-35 s"
    if raw_fault_start is not None:
        note += "; trace realigned to configured experiment timing"
    fig.text(0.5, 0.006, note, ha="center", va="bottom", fontsize=8)

    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=args.dpi)
    fig.savefig(out.with_suffix(".svg"))
    plt.close(fig)
    print(f"Wrote {out}")
    print(f"Wrote {out.with_suffix('.svg')}")
    return True


def nice_float(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def finite_minmax(values: np.ndarray, default: tuple[float, float]) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return default
    lo = float(np.min(finite))
    hi = float(np.max(finite))
    if lo == hi:
        pad = 0.1 if hi == 0 else abs(hi) * 0.1
        return lo - pad, hi + pad
    pad = (hi - lo) * 0.12
    return lo - pad, hi + pad


def points_to_polyline(t: np.ndarray, y: np.ndarray, x0: float, y0: float, width: float, height: float, xmax: float, ymin: float, ymax: float) -> str:
    pts: list[str] = []
    for tx, yy in zip(t, y):
        if not (math.isfinite(tx) and math.isfinite(yy)):
            continue
        if tx < 0 or tx > xmax:
            continue
        px = x0 + (tx / xmax) * width
        py = y0 + height - ((yy - ymin) / (ymax - ymin)) * height
        pts.append(f"{px:.1f},{py:.1f}")
    return " ".join(pts)


def svg_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def plot_svg_fallback(args: argparse.Namespace) -> None:
    rows = read_rows(Path(args.csv))
    t, raw_fault_start = experiment_time(rows, args.fault_start_s)
    fault_end = args.fault_start_s + args.fault_duration_s

    panels = [
        ("Fault state (binary)", [("fault_active", "fault active", "#111111")], (0.0, 1.0)),
        ("Frontal LiDAR sector return ratios (0-1)", [("scan_range_max_ratio", "max-range return ratio", "#008c8c"), ("scan_span_ratio", "longest max-range span ratio", "#005f73")], (0.0, 1.0)),
        ("Local costmap cell ratios (0-1)", [("local_costmap_occupied_ratio", "occupied cell ratio", "#6c757d"), ("local_costmap_lethal_ratio", "lethal cell ratio", "#343a40")], None),
        ("Commanded velocity (m/s and rad/s)", [("cmd_linear_x", "linear x command (m/s)", "#1f77b4"), ("cmd_angular_z", "angular z command (rad/s)", "#d62728")], None),
        ("Robot speed from odometry (m/s)", [("odom_speed", "robot speed magnitude (m/s)", "#2ca02c")], (0.0, None)),
        ("Plan update count (cumulative)", [("global_plan_update_count", "global plan updates", "#9467bd"), ("local_plan_update_count", "local plan updates", "#ff7f0e")], None),
    ]

    svg_w, svg_h = 1500, 1160
    left, right, top, bottom = 250, 55, 78, 72
    gap = 22
    plot_w = svg_w - left - right
    panel_h = (svg_h - top - bottom - gap * (len(panels) - 1)) / len(panels)
    xmax = args.xmax_s
    xticks = np.arange(0.0, xmax + 0.1, 50.0 if xmax >= 250 else 20.0)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{svg_w/2:.1f}" y="34" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" font-weight="700">{svg_escape(args.label)}</text>',
    ]

    for idx, (ylabel, lines, fixed_ylim) in enumerate(panels):
        py = top + idx * (panel_h + gap)
        if fixed_ylim is None:
            all_values = np.concatenate([arr(rows, key) for key, _, _ in lines])
            ymin, ymax = finite_minmax(all_values, (0.0, 1.0))
        else:
            ymin = fixed_ylim[0]
            ymax = fixed_ylim[1] if fixed_ylim[1] is not None else finite_minmax(arr(rows, lines[0][0]), (0.0, 1.0))[1]
            if ymax <= ymin:
                ymax = ymin + 1.0

        parts.append(f'<rect x="{left}" y="{py:.1f}" width="{plot_w}" height="{panel_h:.1f}" fill="#ffffff" stroke="#222" stroke-width="1"/>')
        fx = left + (args.fault_start_s / xmax) * plot_w
        fw = (args.fault_duration_s / xmax) * plot_w
        parts.append(f'<rect x="{fx:.1f}" y="{py:.1f}" width="{fw:.1f}" height="{panel_h:.1f}" fill="#008c8c" opacity="0.10"/>')
        for tx in (args.fault_start_s, fault_end):
            x = left + (tx / xmax) * plot_w
            parts.append(f'<line x1="{x:.1f}" y1="{py:.1f}" x2="{x:.1f}" y2="{py+panel_h:.1f}" stroke="#008c8c" stroke-width="1.2" stroke-dasharray="6,5"/>')
        for tx in xticks:
            x = left + (tx / xmax) * plot_w
            parts.append(f'<line x1="{x:.1f}" y1="{py:.1f}" x2="{x:.1f}" y2="{py+panel_h:.1f}" stroke="#dddddd" stroke-width="1"/>')
            if idx == len(panels) - 1:
                parts.append(f'<text x="{x:.1f}" y="{py+panel_h+28:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="15">{nice_float(tx)}</text>')
        for frac in (0.0, 0.5, 1.0):
            y = py + panel_h - frac * panel_h
            value = ymin + frac * (ymax - ymin)
            parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+plot_w}" y2="{y:.1f}" stroke="#eeeeee" stroke-width="1"/>')
            parts.append(f'<text x="{left-12}" y="{y+5:.1f}" text-anchor="end" font-family="Arial, sans-serif" font-size="14">{nice_float(value)}</text>')
        if "Commanded velocity" in ylabel and ymin < 0 < ymax:
            zero_y = py + panel_h - ((0 - ymin) / (ymax - ymin)) * panel_h
            parts.append(f'<line x1="{left}" y1="{zero_y:.1f}" x2="{left+plot_w}" y2="{zero_y:.1f}" stroke="#333" stroke-width="1" stroke-dasharray="4,4"/>')

        parts.append(f'<text x="18" y="{py+panel_h/2-2:.1f}" font-family="Arial, sans-serif" font-size="16" font-weight="700">{svg_escape(ylabel)}</text>')
        lx = left + plot_w - 365
        ly = py + 22
        for line_idx, (key, legend, color) in enumerate(lines):
            poly = points_to_polyline(t, arr(rows, key), left, py, plot_w, panel_h, xmax, ymin, ymax)
            if poly:
                parts.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
            legend_y = ly + line_idx * 22
            parts.append(f'<line x1="{lx}" y1="{legend_y}" x2="{lx+30}" y2="{legend_y}" stroke="{color}" stroke-width="3"/>')
            parts.append(f'<text x="{lx+38}" y="{legend_y+5}" font-family="Arial, sans-serif" font-size="14">{svg_escape(legend)}</text>')

    parts.append(f'<text x="{left+plot_w/2:.1f}" y="{svg_h-28}" text-anchor="middle" font-family="Arial, sans-serif" font-size="18">Experiment-aligned simulation time (s)</text>')
    note = "Configured fault window shown as 15-35 s."
    if raw_fault_start is not None:
        note += " Trace realigned to configured experiment timing."
    parts.append(f'<text x="{left+plot_w/2:.1f}" y="{svg_h-8}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#555">{svg_escape(note)}</text>')
    parts.append("</svg>")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    svg_path = out.with_suffix(".svg")
    svg_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {svg_path}")
    if out.suffix.lower() != ".svg":
        try:
            subprocess.run(["convert", str(svg_path), str(out)], check=True)
            print(f"Wrote {out}")
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            print(f"Could not convert SVG to {out.suffix}: {exc}")


def main() -> int:
    args = parse_args()
    if not plot_matplotlib(args):
        plot_svg_fallback(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
