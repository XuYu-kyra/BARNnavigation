#!/usr/bin/env python3
"""Build time-aligned propagation plots from a ROS 2 bag.

The script is intentionally lightweight: it extracts proxy metrics from the
topics recorded in a direct propagation trace and writes one CSV plus one PNG.
It is meant for dissertation evidence, not online robot control.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", required=True, help="Path to rosbag2 directory")
    parser.add_argument("--output-dir", required=True, help="Directory for CSV/PNG outputs")
    parser.add_argument("--label", default="", help="Figure label, e.g. w8_masking")
    parser.add_argument("--scan-topic", default="/front/scan_faulted")
    parser.add_argument("--fault-topic", default="/fault/scan_active")
    parser.add_argument("--cmd-vel-topic", default="/cmd_vel")
    parser.add_argument("--odom-topic", default="/platform/odom/filtered")
    parser.add_argument("--local-costmap-topic", default="/local_costmap/costmap")
    parser.add_argument("--global-costmap-topic", default="/global_costmap/costmap")
    parser.add_argument("--plan-topic", default="/plan")
    parser.add_argument("--local-plan-topic", default="/local_plan")
    parser.add_argument("--sector-center-deg", type=float, default=0.0)
    parser.add_argument("--sector-width-deg", type=float, default=90.0)
    parser.add_argument("--near-range-max-fraction", type=float, default=0.98)
    parser.add_argument("--resample-dt", type=float, default=0.25)
    return parser.parse_args()


def open_reader(bag_dir: Path) -> tuple[rosbag2_py.SequentialReader, dict[str, str]]:
    storage_id = detect_storage_id(bag_dir)
    storage_options = rosbag2_py.StorageOptions(uri=str(bag_dir), storage_id=storage_id)
    converter_options = rosbag2_py.ConverterOptions(
        input_serialization_format="cdr",
        output_serialization_format="cdr",
    )
    reader = rosbag2_py.SequentialReader()
    reader.open(storage_options, converter_options)
    topic_types = {topic.name: topic.type for topic in reader.get_all_topics_and_types()}
    return reader, topic_types


def detect_storage_id(bag_dir: Path) -> str:
    metadata = bag_dir / "metadata.yaml"
    if not metadata.exists():
        return "sqlite3"
    text = metadata.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"storage_identifier:\s*([A-Za-z0-9_]+)", text)
    if match:
        return match.group(1)
    return "sqlite3"


def normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def in_sector(angle: float, center: float, half_width: float) -> bool:
    return abs(normalize_angle(angle - center)) <= half_width


def scan_metrics(msg: Any, center_deg: float, width_deg: float, near_fraction: float) -> tuple[float, float]:
    center = math.radians(center_deg)
    half_width = math.radians(width_deg / 2.0)
    ranges = np.asarray(msg.ranges, dtype=float)
    angles = msg.angle_min + np.arange(len(ranges)) * msg.angle_increment
    mask = np.array([in_sector(a, center, half_width) for a in angles], dtype=bool)
    sector = ranges[mask]
    valid = np.isfinite(sector)
    if sector.size == 0 or not np.any(valid):
        return math.nan, math.nan
    sector = sector[valid]
    near_max = sector >= (msg.range_max * near_fraction)
    range_max_ratio = float(np.mean(near_max))

    # Longest contiguous near-range-max span, normalized by frontal sector size.
    if not np.any(near_max):
        return range_max_ratio, 0.0
    best = current = 0
    for value in near_max:
        if value:
            current += 1
            best = max(best, current)
        else:
            current = 0
    span_ratio = float(best / max(len(near_max), 1))
    return range_max_ratio, span_ratio


def costmap_metrics(msg: Any) -> tuple[float, float, float]:
    data = np.asarray(msg.data, dtype=float)
    if data.size == 0:
        return math.nan, math.nan, math.nan
    known = data >= 0
    if not np.any(known):
        return math.nan, math.nan, 1.0
    known_data = data[known]
    occupied_ratio = float(np.mean(known_data >= 50))
    lethal_ratio = float(np.mean(known_data >= 90))
    unknown_ratio = float(np.mean(~known))
    return occupied_ratio, lethal_ratio, unknown_ratio


def append_sample(series: dict[str, list[tuple[float, float]]], key: str, t: float, value: float) -> None:
    if value is None:
        return
    try:
        v = float(value)
    except (TypeError, ValueError):
        return
    if math.isfinite(v):
        series[key].append((t, v))


def get_twist(msg: Any) -> Any | None:
    """Return a Twist-like object from Twist, TwistStamped, or Odometry."""
    if hasattr(msg, "linear") and hasattr(msg, "angular"):
        return msg
    if hasattr(msg, "twist"):
        twist = msg.twist
        if hasattr(twist, "linear") and hasattr(twist, "angular"):
            return twist
        if hasattr(twist, "twist"):
            return twist.twist
    return None


def get_pose_position(msg: Any) -> Any | None:
    """Return a Point-like position from Odometry or PoseStamped-like messages."""
    if hasattr(msg, "pose"):
        pose = msg.pose
        if hasattr(pose, "position"):
            return pose.position
        if hasattr(pose, "pose") and hasattr(pose.pose, "position"):
            return pose.pose.position
    return None


def read_bag(args: argparse.Namespace) -> tuple[dict[str, list[tuple[float, float]]], dict[str, int]]:
    reader, topic_types = open_reader(Path(args.bag))
    msg_types = {}
    for topic, type_name in topic_types.items():
        try:
            msg_types[topic] = get_message(type_name)
        except (AttributeError, ModuleNotFoundError, ValueError):
            pass

    target_topics = {
        args.scan_topic,
        args.fault_topic,
        args.cmd_vel_topic,
        args.odom_topic,
        args.local_costmap_topic,
        args.global_costmap_topic,
        args.plan_topic,
        args.local_plan_topic,
    }

    series: dict[str, list[tuple[float, float]]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    start_ns: int | None = None
    plan_counts = {args.plan_topic: 0, args.local_plan_topic: 0}

    while reader.has_next():
        topic, data, timestamp = reader.read_next()
        if topic not in target_topics or topic not in msg_types:
            continue
        if start_ns is None:
            start_ns = timestamp
        t = (timestamp - start_ns) / 1e9
        counts[topic] += 1
        msg = deserialize_message(data, msg_types[topic])

        if topic == args.fault_topic:
            append_sample(series, "fault_active", t, 1.0 if bool(getattr(msg, "data", False)) else 0.0)
        elif topic == args.scan_topic:
            range_ratio, span_ratio = scan_metrics(
                msg,
                args.sector_center_deg,
                args.sector_width_deg,
                args.near_range_max_fraction,
            )
            append_sample(series, "scan_range_max_ratio", t, range_ratio)
            append_sample(series, "scan_span_ratio", t, span_ratio)
        elif topic == args.cmd_vel_topic:
            twist = get_twist(msg)
            if twist is not None:
                append_sample(series, "cmd_linear_x", t, twist.linear.x)
                append_sample(series, "cmd_angular_z", t, twist.angular.z)
        elif topic == args.odom_topic:
            twist = get_twist(msg)
            if twist is not None:
                vx = twist.linear.x
                vy = twist.linear.y
                append_sample(series, "odom_speed", t, math.hypot(vx, vy))
            position = get_pose_position(msg)
            if position is not None:
                append_sample(series, "odom_x", t, position.x)
                append_sample(series, "odom_y", t, position.y)
        elif topic == args.local_costmap_topic:
            occupied, lethal, unknown = costmap_metrics(msg)
            append_sample(series, "local_costmap_occupied_ratio", t, occupied)
            append_sample(series, "local_costmap_lethal_ratio", t, lethal)
            append_sample(series, "local_costmap_unknown_ratio", t, unknown)
        elif topic == args.global_costmap_topic:
            occupied, lethal, unknown = costmap_metrics(msg)
            append_sample(series, "global_costmap_occupied_ratio", t, occupied)
            append_sample(series, "global_costmap_lethal_ratio", t, lethal)
            append_sample(series, "global_costmap_unknown_ratio", t, unknown)
        elif topic in plan_counts:
            plan_counts[topic] += 1
            key = "global_plan_update_count" if topic == args.plan_topic else "local_plan_update_count"
            append_sample(series, key, t, plan_counts[topic])

    return series, counts


def resample_series(series: dict[str, list[tuple[float, float]]], dt: float) -> list[dict[str, float]]:
    max_t = 0.0
    for samples in series.values():
        if samples:
            max_t = max(max_t, samples[-1][0])
    if max_t <= 0:
        return []

    keys = sorted(series)
    rows: list[dict[str, float]] = []
    sample_arrays = {}
    for key, samples in series.items():
        arr = np.asarray(samples, dtype=float)
        sample_arrays[key] = arr

    times = np.arange(0.0, max_t + dt, dt)
    for t in times:
        row = {"t_s": float(t)}
        for key in keys:
            arr = sample_arrays[key]
            idx = np.searchsorted(arr[:, 0], t, side="right") - 1
            row[key] = float(arr[idx, 1]) if idx >= 0 else math.nan
        rows.append(row)
    return rows


def write_csv(rows: list[dict[str, float]], out_csv: Path) -> None:
    if not rows:
        out_csv.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def plot(rows: list[dict[str, float]], out_png: Path, label: str) -> None:
    if not rows:
        raise RuntimeError("No samples available to plot")
    t = np.asarray([r["t_s"] for r in rows], dtype=float)

    def values(key: str) -> np.ndarray:
        return np.asarray([r.get(key, math.nan) for r in rows], dtype=float)

    fig, axes = plt.subplots(6, 1, figsize=(12, 10), sharex=True)
    fig.suptitle(label or out_png.stem)

    axes[0].plot(t, values("fault_active"), color="black", linewidth=1.8)
    axes[0].set_ylabel("fault")
    axes[0].set_ylim(-0.05, 1.05)

    axes[1].plot(t, values("scan_range_max_ratio"), label="range_max ratio", color="#008c8c")
    axes[1].plot(t, values("scan_span_ratio"), label="span ratio", color="#005f73", alpha=0.8)
    axes[1].set_ylabel("scan")
    axes[1].legend(loc="upper right")

    axes[2].plot(t, values("local_costmap_occupied_ratio"), label="local occupied", color="#6c757d")
    axes[2].plot(t, values("local_costmap_lethal_ratio"), label="local lethal", color="#343a40")
    axes[2].set_ylabel("costmap")
    axes[2].legend(loc="upper right")

    axes[3].plot(t, values("cmd_linear_x"), label="linear x", color="#1f77b4")
    axes[3].plot(t, values("cmd_angular_z"), label="angular z", color="#d62728")
    axes[3].axhline(0, color="black", linestyle="--", linewidth=0.8, alpha=0.5)
    axes[3].set_ylabel("cmd_vel")
    axes[3].legend(loc="upper right")

    axes[4].plot(t, values("odom_speed"), color="#2ca02c")
    axes[4].set_ylabel("odom speed")

    axes[5].plot(t, values("global_plan_update_count"), label="global plan", color="#9467bd")
    axes[5].plot(t, values("local_plan_update_count"), label="local plan", color="#ff7f0e")
    axes[5].set_ylabel("plan count")
    axes[5].set_xlabel("elapsed time in bag (s)")
    axes[5].legend(loc="upper right")

    fault = values("fault_active")
    active = np.where(fault > 0.5)[0]
    if active.size:
        start = t[active[0]]
        end = t[active[-1]]
        for ax in axes:
            ax.axvspan(start, end, color="#008c8c", alpha=0.10)

    for ax in axes:
        ax.grid(True, alpha=0.25)

    fig.tight_layout()
    fig.savefig(out_png, dpi=220)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    series, counts = read_bag(args)
    rows = resample_series(series, args.resample_dt)

    stem = args.label or Path(args.bag).name
    out_csv = out_dir / f"{stem}_trace_metrics.csv"
    out_png = out_dir / f"{stem}_timeline.png"
    out_counts = out_dir / f"{stem}_topic_counts.csv"
    write_csv(rows, out_csv)
    with out_counts.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["topic", "message_count"])
        for topic, count in sorted(counts.items()):
            writer.writerow([topic, count])
    plot(rows, out_png, args.label)
    print(f"Wrote {out_csv}")
    print(f"Wrote {out_png}")
    print(f"Wrote {out_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
