#!/usr/bin/env python3
"""Create dissertation-ready direct propagation trace figures from ROS 2 MCAP bags.

This script intentionally avoids plotting /fault/scan_active as a state signal.
In these experiments that topic behaved as an episode trigger and did not reset
cleanly after the transient window. The scan panel therefore uses a direct
raw-vs-faulted frontal-sector difference ratio, computed from /front/scan and
/front/scan_faulted in the bag.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rosbags.highlevel import AnyReader


@dataclass
class Series:
    t: list[float]
    y: list[float]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--bag", required=True, help="ROS 2 bag directory")
    p.add_argument("--output", required=True, help="Output PNG path")
    p.add_argument("--label", required=True, help="Figure title")
    p.add_argument("--fault-start-s", type=float, default=15.0, help="Displayed/campaign-aligned fault start")
    p.add_argument("--fault-duration-s", type=float, default=20.0)
    p.add_argument("--trace-original-start-s", type=float, default=5.0, help="Fallback original trace onset if no trigger topic is available")
    p.add_argument("--sector-center-deg", type=float, default=0.0)
    p.add_argument("--sector-width-deg", type=float, default=90.0)
    p.add_argument("--xmax-s", type=float, default=120.0, help="Shown x-axis max after campaign alignment")
    p.add_argument("--transparent", action="store_true")
    p.add_argument("--no-title", action="store_true", help="Do not draw title/subtitle inside the figure")
    return p.parse_args()


def sector_indices(msg, center_deg: float, width_deg: float) -> np.ndarray:
    center = math.radians(center_deg)
    half = math.radians(width_deg / 2.0)
    idx: list[int] = []
    for i in range(len(msg.ranges)):
        a = float(msg.angle_min) + i * float(msg.angle_increment)
        d = math.atan2(math.sin(a - center), math.cos(a - center))
        if abs(d) <= half:
            idx.append(i)
    return np.asarray(idx, dtype=int)


def changed_ratio(a: np.ndarray, b: np.ndarray) -> float:
    changed = 0
    total = 0
    for x_raw, x_faulted in zip(a, b):
        x = float(x_raw)
        y = float(x_faulted)
        total += 1
        if math.isnan(x) and math.isnan(y):
            continue
        if math.isinf(x) and math.isinf(y):
            continue
        if math.isfinite(x) and math.isfinite(y) and abs(x - y) < 1e-4:
            continue
        changed += 1
    return changed / total if total else math.nan


def interpolate_step(series: Series, t: float) -> float:
    if not series.t:
        return math.nan
    arr_t = np.asarray(series.t)
    i = int(np.searchsorted(arr_t, t, side="right") - 1)
    if i < 0:
        return math.nan
    return series.y[i]


def read_bag(args: argparse.Namespace) -> dict[str, Series]:
    bag = Path(args.bag)
    data: dict[str, Series] = {
        "scan_diff": Series([], []),
        "scan_faulted_max": Series([], []),
        "local_occ": Series([], []),
        "local_lethal": Series([], []),
        "global_occ": Series([], []),
        "global_lethal": Series([], []),
        "cmd_linear_x": Series([], []),
        "cmd_angular_z": Series([], []),
        "odom_speed": Series([], []),
        "plan_updates": Series([], []),
    }

    plan_count = 0
    start_ns: int | None = None
    records: list[tuple[str, float, object]] = []
    trigger_times: list[float] = []

    with AnyReader([bag]) as reader:
        connections = [c for c in reader.connections if c.topic in {
            "/front/scan", "/front/scan_faulted", "/local_costmap/costmap", "/global_costmap/costmap",
            "/cmd_vel", "/platform/odom/filtered", "/plan", "/fault/scan_active"
        }]
        for conn, ts, raw in reader.messages(connections=connections):
            if start_ns is None:
                start_ns = ts
            bag_t = (ts - start_ns) / 1e9
            msg = reader.deserialize(raw, conn.msgtype)
            records.append((conn.topic, bag_t, msg))
            if conn.topic == "/fault/scan_active" and bool(msg.data):
                trigger_times.append(bag_t)

    if trigger_times:
        align_offset = min(trigger_times) - args.fault_start_s
    else:
        align_offset = args.trace_original_start_s - args.fault_start_s

    raw_scans: list[tuple[float, object]] = []
    faulted_scans: list[tuple[float, object]] = []

    for topic, bag_t, msg in records:
        t = bag_t - align_offset

        if topic == "/front/scan":
            raw_scans.append((t, msg))
        elif topic == "/front/scan_faulted":
            faulted_scans.append((t, msg))
            idx = sector_indices(msg, args.sector_center_deg, args.sector_width_deg)
            rf = np.asarray(msg.ranges, dtype=float)[idx]
            max_ratio = float(np.mean(np.isinf(rf) | (rf >= 0.98 * float(msg.range_max))))
            data["scan_faulted_max"].t.append(t)
            data["scan_faulted_max"].y.append(max_ratio)
        elif topic == "/local_costmap/costmap":
            arr = np.asarray(msg.data, dtype=float)
            known = arr >= 0
            denom = max(1, int(np.sum(known)))
            data["local_occ"].t.append(t)
            data["local_occ"].y.append(float(np.sum(arr[known] > 0) / denom))
            data["local_lethal"].t.append(t)
            data["local_lethal"].y.append(float(np.sum(arr[known] >= 100) / denom))
        elif topic == "/global_costmap/costmap":
            arr = np.asarray(msg.data, dtype=float)
            known = arr >= 0
            denom = max(1, int(np.sum(known)))
            data["global_occ"].t.append(t)
            data["global_occ"].y.append(float(np.sum(arr[known] > 0) / denom))
            data["global_lethal"].t.append(t)
            data["global_lethal"].y.append(float(np.sum(arr[known] >= 100) / denom))
        elif topic == "/cmd_vel":
            data["cmd_linear_x"].t.append(t)
            data["cmd_linear_x"].y.append(float(msg.twist.linear.x))
            data["cmd_angular_z"].t.append(t)
            data["cmd_angular_z"].y.append(float(msg.twist.angular.z))
        elif topic == "/platform/odom/filtered":
            vx = float(msg.twist.twist.linear.x)
            vy = float(msg.twist.twist.linear.y)
            vz = float(msg.twist.twist.linear.z)
            data["odom_speed"].t.append(t)
            data["odom_speed"].y.append(math.sqrt(vx * vx + vy * vy + vz * vz))
        elif topic == "/plan":
            plan_count += 1
            data["plan_updates"].t.append(t)
            data["plan_updates"].y.append(float(plan_count))

    raw_t = np.asarray([x[0] for x in raw_scans])
    if raw_t.size and faulted_scans:
        for tf, msgf in faulted_scans:
            j = int(np.argmin(np.abs(raw_t - tf)))
            if abs(raw_t[j] - tf) > 0.25:
                continue
            msgr = raw_scans[j][1]
            idx = sector_indices(msgf, args.sector_center_deg, args.sector_width_deg)
            rf = np.asarray(msgr.ranges, dtype=float)[idx]
            ff = np.asarray(msgf.ranges, dtype=float)[idx]
            data["scan_diff"].t.append(tf)
            data["scan_diff"].y.append(changed_ratio(rf, ff))

    return data


def finite_limits(series_list: list[Series], fixed: tuple[float | None, float | None] | None = None) -> tuple[float, float]:
    vals: list[float] = []
    for s in series_list:
        vals.extend([v for v in s.y if math.isfinite(v)])
    if vals:
        lo = min(vals)
        hi = max(vals)
    else:
        lo, hi = 0.0, 1.0
    if fixed:
        if fixed[0] is not None:
            lo = fixed[0]
        if fixed[1] is not None:
            hi = fixed[1]
    if hi <= lo:
        hi = lo + 1.0
    pad = 0.08 * (hi - lo)
    if not fixed or fixed[0] is None:
        lo -= pad
    if not fixed or fixed[1] is None:
        hi += pad
    return lo, hi


def polyline(series: Series, x0: float, y0: float, w: float, h: float, xmin: float, xmax: float, ymin: float, ymax: float) -> str:
    pts: list[str] = []
    for tx, yy in zip(series.t, series.y):
        if not (math.isfinite(tx) and math.isfinite(yy)):
            continue
        if tx < xmin or tx > xmax:
            continue
        px = x0 + ((tx - xmin) / (xmax - xmin)) * w
        py = y0 + h - ((yy - ymin) / (ymax - ymin)) * h
        pts.append(f"{px:.1f},{py:.1f}")
    return " ".join(pts)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def draw_svg(args: argparse.Namespace, data: dict[str, Series], out_svg: Path) -> None:
    W, H = 1600, 1180
    left, right, top, bottom = 285, 70, (35 if args.no_title else 85), 80
    panels = [
        ("Scan modification ratio\nraw vs faulted, frontal sector", [("scan_diff", "raw-vs-faulted difference ratio", "#008c8c", 3.0)], (0.0, 1.0)),
        ("Faulted scan max-range\nreturn ratio (0-1)", [("scan_faulted_max", "faulted scan max-range return ratio", "#5f7f8f", 2.0)], (0.0, 1.0)),
        ("Local costmap\ncell ratios (0-1)", [("local_occ", "occupied cell ratio", "#6c757d", 2.2), ("local_lethal", "lethal cell ratio", "#343a40", 2.2)], (0.0, None)),
        ("Commanded velocity\nlinear m/s, angular rad/s", [("cmd_linear_x", "linear x command (m/s)", "#1f77b4", 2.0), ("cmd_angular_z", "angular z command (rad/s)", "#d62728", 2.0)], None),
        ("Robot speed from odometry\n(m/s)", [("odom_speed", "speed magnitude (m/s)", "#2ca02c", 2.4)], (0.0, None)),
        ("Global plan updates\ncount", [("plan_updates", "cumulative global plan updates", "#9467bd", 2.2)], (0.0, None)),
    ]
    gap = 22
    ph = (H - top - bottom - gap * (len(panels) - 1)) / len(panels)
    pw = W - left - right
    xmin, xmax = 0.0, float(args.xmax_s)
    fault_end = args.fault_start_s + args.fault_duration_s
    bg = "none" if args.transparent else "white"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        f'<rect width="100%" height="100%" fill="{bg}"/>',
    ]
    if not args.no_title:
        parts.extend([
            f'<text x="{W/2:.1f}" y="34" text-anchor="middle" font-family="Arial, sans-serif" font-size="24" font-weight="700" fill="#1b2831">{esc(args.label)}</text>',
            f'<text x="{W/2:.1f}" y="61" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#52616b">Campaign-aligned simulation time; shaded window shows the 20 s transient fault interval at 15-35 s.</text>',
        ])

    xticks = np.arange(0, xmax + 0.1, 10 if xmax <= 120 else 50)
    for i, (ylabel, lines, fixed) in enumerate(panels):
        y0 = top + i * (ph + gap)
        sers = [data[k] for k, *_ in lines]
        ymin, ymax = finite_limits(sers, fixed)
        parts.append(f'<rect x="{left}" y="{y0:.1f}" width="{pw}" height="{ph:.1f}" fill="white" stroke="#cfd6dc" stroke-width="1"/>')
        fsx = left + ((args.fault_start_s - xmin) / (xmax - xmin)) * pw
        fex = left + ((fault_end - xmin) / (xmax - xmin)) * pw
        parts.append(f'<rect x="{fsx:.1f}" y="{y0:.1f}" width="{max(0,fex-fsx):.1f}" height="{ph:.1f}" fill="#008c8c" opacity="0.12"/>')
        for x in xticks:
            px = left + ((x - xmin) / (xmax - xmin)) * pw
            parts.append(f'<line x1="{px:.1f}" x2="{px:.1f}" y1="{y0:.1f}" y2="{y0+ph:.1f}" stroke="#e5e9ec" stroke-width="1"/>')
        for frac in [0.0, 0.5, 1.0]:
            yy = y0 + ph - frac * ph
            val = ymin + frac * (ymax - ymin)
            parts.append(f'<line x1="{left}" x2="{left+pw}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#edf0f2" stroke-width="1"/>')
            parts.append(f'<text x="{left-12}" y="{yy+4:.1f}" text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#52616b">{val:.2g}</text>')
        parts.append(f'<line x1="{fsx:.1f}" x2="{fsx:.1f}" y1="{y0:.1f}" y2="{y0+ph:.1f}" stroke="#008c8c" stroke-width="1.5" stroke-dasharray="5 4"/>')
        parts.append(f'<line x1="{fex:.1f}" x2="{fex:.1f}" y1="{y0:.1f}" y2="{y0+ph:.1f}" stroke="#008c8c" stroke-width="1.5" stroke-dasharray="5 4"/>')
        for key, legend, color, lw in lines:
            pts = polyline(data[key], left, y0, pw, ph, xmin, xmax, ymin, ymax)
            if pts:
                parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{lw}" stroke-linejoin="round" stroke-linecap="round"/>')
        # y-axis label, split on newline
        label_lines = ylabel.split('\n')
        for j, text in enumerate(label_lines):
            parts.append(f'<text x="28" y="{y0+ph/2-8+16*j:.1f}" font-family="Arial, sans-serif" font-size="14" font-weight="600" fill="#1b2831">{esc(text)}</text>')
        # compact legend
        lx = left + pw - 455
        ly = y0 + 18
        for j, (_, legend, color, _) in enumerate(lines):
            parts.append(f'<line x1="{lx}" x2="{lx+28}" y1="{ly+18*j}" y2="{ly+18*j}" stroke="{color}" stroke-width="3"/>')
            parts.append(f'<text x="{lx+36}" y="{ly+4+18*j}" font-family="Arial, sans-serif" font-size="12" fill="#1b2831">{esc(legend)}</text>')

    # X-axis ticks on final panel
    y_axis = top + len(panels) * ph + (len(panels)-1)*gap
    for x in xticks:
        px = left + ((x - xmin) / (xmax - xmin)) * pw
        parts.append(f'<text x="{px:.1f}" y="{H-45}" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#52616b">{int(x)}</text>')
    parts.append(f'<text x="{left+pw/2:.1f}" y="{H-18}" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="600" fill="#1b2831">Campaign-aligned simulation time (s)</text>')
    parts.append('</svg>')
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.write_text('\n'.join(parts), encoding='utf-8')


def convert_svg_to_png(svg: Path, png: Path) -> None:
    convert = shutil.which('convert') or shutil.which('magick')
    if not convert:
        print(f"Wrote {svg}; no ImageMagick convert found for PNG")
        return
    cmd = [convert, '-density', '220', str(svg), '-quality', '95', str(png)]
    subprocess.run(cmd, check=True)


def main() -> int:
    args = parse_args()
    data = read_bag(args)
    png = Path(args.output)
    svg = png.with_suffix('.svg')
    draw_svg(args, data, svg)
    convert_svg_to_png(svg, png)
    print(f"Wrote {svg}")
    print(f"Wrote {png}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
