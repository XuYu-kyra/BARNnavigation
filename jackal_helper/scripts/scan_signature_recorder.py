#!/usr/bin/env python3
"""Record lightweight LiDAR fault-signature features from LaserScan streams."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Iterable

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool


def normalize_angle(angle_rad: float) -> float:
    return math.atan2(math.sin(angle_rad), math.cos(angle_rad))


def stamp_to_seconds(msg: LaserScan) -> float:
    return float(msg.header.stamp.sec) + float(msg.header.stamp.nanosec) / 1e9


def safe_mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else float('nan')


def longest_true_streak(flags: list[bool]) -> int:
    best = 0
    current = 0
    for flag in flags:
        if flag:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


class ScanSignatureRecorder(Node):
    def __init__(self) -> None:
        super().__init__('scan_signature_recorder')

        self.declare_parameter('scan_topic', '/front/scan_faulted')
        self.declare_parameter('reference_topic', '/front/scan')
        self.declare_parameter('fault_active_topic', '/fault/scan_active')
        self.declare_parameter('output_csv', '/tmp/scan_signature_features.csv')
        self.declare_parameter('sector_center_deg', 0.0)
        self.declare_parameter('sector_width_deg', 90.0)
        self.declare_parameter('range_max_epsilon_m', 1e-3)
        self.declare_parameter('reference_max_age_s', 0.25)

        self._scan_topic = str(self.get_parameter('scan_topic').value)
        self._reference_topic = str(self.get_parameter('reference_topic').value)
        self._fault_active_topic = str(self.get_parameter('fault_active_topic').value)
        self._output_csv = Path(str(self.get_parameter('output_csv').value)).expanduser().resolve()
        self._sector_center_rad = math.radians(float(self.get_parameter('sector_center_deg').value))
        self._sector_half_width_rad = math.radians(float(self.get_parameter('sector_width_deg').value)) / 2.0
        self._range_max_epsilon_m = float(self.get_parameter('range_max_epsilon_m').value)
        self._reference_max_age_s = float(self.get_parameter('reference_max_age_s').value)

        self._output_csv.parent.mkdir(parents=True, exist_ok=True)
        self._csv_file = self._output_csv.open('w', newline='')
        self._writer = csv.DictWriter(
            self._csv_file,
            fieldnames=[
                'sample_index',
                'stamp_s',
                'elapsed_s',
                'fault_active',
                'scan_topic',
                'reference_topic',
                'reference_available',
                'reference_age_s',
                'angle_min',
                'angle_max',
                'angle_increment',
                'range_min',
                'range_max',
                'beam_count',
                'frontal_beam_count',
                'frontal_finite_ratio',
                'frontal_range_max_ratio',
                'frontal_largest_range_max_span_ratio',
                'frontal_mean_range_m',
                'frontal_min_range_m',
                'changed_to_range_max_ratio',
                'changed_to_range_max_span_ratio',
                'mean_abs_delta_m',
                'max_abs_delta_m',
            ],
        )
        self._writer.writeheader()

        self._sample_index = 0
        self._first_stamp_s: float | None = None
        self._latest_reference: LaserScan | None = None
        self._latest_fault_active = False

        self.create_subscription(Bool, self._fault_active_topic, self._fault_active_callback, 10)
        self.create_subscription(LaserScan, self._reference_topic, self._reference_callback, qos_profile_sensor_data)
        self.create_subscription(LaserScan, self._scan_topic, self._scan_callback, qos_profile_sensor_data)

        self.get_logger().info(
            'Scan signature recorder ready: '
            f'scan_topic={self._scan_topic}, reference_topic={self._reference_topic}, '
            f'fault_active_topic={self._fault_active_topic}, output_csv={self._output_csv}, '
            f'sector_center_deg={math.degrees(self._sector_center_rad):.1f}, '
            f'sector_width_deg={math.degrees(self._sector_half_width_rad * 2.0):.1f}'
        )

    def _fault_active_callback(self, msg: Bool) -> None:
        self._latest_fault_active = bool(msg.data)

    def _reference_callback(self, msg: LaserScan) -> None:
        self._latest_reference = msg

    def _sector_indices(self, msg: LaserScan) -> list[int]:
        indices: list[int] = []
        if msg.angle_increment == 0.0:
            return indices
        for i in range(len(msg.ranges)):
            beam_angle = msg.angle_min + i * msg.angle_increment
            if abs(normalize_angle(beam_angle - self._sector_center_rad)) <= self._sector_half_width_rad:
                indices.append(i)
        return indices

    def _near_range_max(self, value: float, range_max: float) -> bool:
        if math.isnan(value):
            return False
        if math.isinf(value):
            return value > 0.0
        return value >= range_max - self._range_max_epsilon_m

    def _scan_callback(self, msg: LaserScan) -> None:
        stamp_s = stamp_to_seconds(msg)
        if self._first_stamp_s is None:
            self._first_stamp_s = stamp_s
        elapsed_s = stamp_s - self._first_stamp_s
        sector_indices = self._sector_indices(msg)

        frontal_values = [msg.ranges[i] for i in sector_indices]
        finite_values = [v for v in frontal_values if math.isfinite(v)]
        max_flags = [self._near_range_max(v, msg.range_max) for v in frontal_values]

        reference_available = False
        reference_age_s = float('nan')
        changed_flags: list[bool] = []
        abs_deltas: list[float] = []
        ref = self._latest_reference
        if ref is not None and len(ref.ranges) == len(msg.ranges):
            reference_age_s = abs(stamp_s - stamp_to_seconds(ref))
            reference_available = reference_age_s <= self._reference_max_age_s
        if reference_available and ref is not None:
            for i in sector_indices:
                ref_value = ref.ranges[i]
                out_value = msg.ranges[i]
                ref_valid_for_replacement = math.isfinite(ref_value) and ref_value < msg.range_max - self._range_max_epsilon_m
                changed_to_max = ref_valid_for_replacement and self._near_range_max(out_value, msg.range_max)
                changed_flags.append(changed_to_max)
                if math.isfinite(ref_value) and math.isfinite(out_value):
                    abs_deltas.append(abs(out_value - ref_value))

        frontal_count = len(frontal_values)
        row = {
            'sample_index': self._sample_index,
            'stamp_s': stamp_s,
            'elapsed_s': elapsed_s,
            'fault_active': self._latest_fault_active,
            'scan_topic': self._scan_topic,
            'reference_topic': self._reference_topic,
            'reference_available': reference_available,
            'reference_age_s': reference_age_s,
            'angle_min': msg.angle_min,
            'angle_max': msg.angle_max,
            'angle_increment': msg.angle_increment,
            'range_min': msg.range_min,
            'range_max': msg.range_max,
            'beam_count': len(msg.ranges),
            'frontal_beam_count': frontal_count,
            'frontal_finite_ratio': len(finite_values) / frontal_count if frontal_count else float('nan'),
            'frontal_range_max_ratio': sum(max_flags) / frontal_count if frontal_count else float('nan'),
            'frontal_largest_range_max_span_ratio': longest_true_streak(max_flags) / frontal_count if frontal_count else float('nan'),
            'frontal_mean_range_m': safe_mean(finite_values),
            'frontal_min_range_m': min(finite_values) if finite_values else float('nan'),
            'changed_to_range_max_ratio': sum(changed_flags) / frontal_count if changed_flags and frontal_count else float('nan'),
            'changed_to_range_max_span_ratio': longest_true_streak(changed_flags) / frontal_count if changed_flags and frontal_count else float('nan'),
            'mean_abs_delta_m': safe_mean(abs_deltas),
            'max_abs_delta_m': max(abs_deltas) if abs_deltas else float('nan'),
        }
        self._writer.writerow(row)
        self._csv_file.flush()
        self._sample_index += 1

    def destroy_node(self) -> bool:
        try:
            self._csv_file.flush()
            self._csv_file.close()
        finally:
            return super().destroy_node()


def main() -> None:
    rclpy.init()
    node = ScanSignatureRecorder()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
