#!/usr/bin/env python3
"""Filter intermittent LiDAR dropout bursts before they reach Nav2 costmaps."""

from __future__ import annotations

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool


def normalize_angle(angle_rad: float) -> float:
    """Wrap an angle to [-pi, pi]."""
    return math.atan2(math.sin(angle_rad), math.cos(angle_rad))


class DropoutScanRecoveryFilter(Node):
    """Reject corrupted dropout bursts while passing healthy scan phases.

    The dropout injector creates intermittent frontal-sector range_max bursts.
    This filter detects those bursts from the navigation-consumed scan stream
    and marks affected frontal beams as NaN so they are not treated as fresh,
    trustworthy free-space evidence by downstream costmaps.
    """

    def __init__(self) -> None:
        super().__init__('dropout_scan_recovery_filter')

        self.declare_parameter('input_topic', '/front/scan_faulted')
        self.declare_parameter('output_topic', '/front/scan_recovered')
        self.declare_parameter('fault_active_topic', '/fault/scan_active')
        self.declare_parameter('enable_topic', '/recovery/dropout_filter_enable')
        self.declare_parameter('filter_active_topic', '/fault/dropout_filter_active')
        self.declare_parameter('require_enable', False)
        self.declare_parameter('sector_center_deg', 0.0)
        self.declare_parameter('sector_width_deg', 90.0)
        self.declare_parameter('range_max_ratio_threshold', 0.55)
        self.declare_parameter('near_range_max_fraction', 0.98)

        self._input_topic = str(self.get_parameter('input_topic').value)
        self._output_topic = str(self.get_parameter('output_topic').value)
        self._fault_active_topic = str(self.get_parameter('fault_active_topic').value)
        self._enable_topic = str(self.get_parameter('enable_topic').value)
        self._filter_active_topic = str(self.get_parameter('filter_active_topic').value)
        self._require_enable = bool(self.get_parameter('require_enable').value)
        self._sector_center_rad = math.radians(float(self.get_parameter('sector_center_deg').value))
        self._sector_half_width_rad = math.radians(float(self.get_parameter('sector_width_deg').value)) / 2.0
        self._range_max_ratio_threshold = float(self.get_parameter('range_max_ratio_threshold').value)
        self._near_range_max_fraction = float(self.get_parameter('near_range_max_fraction').value)

        self._fault_active = False
        self._policy_enabled = not self._require_enable
        self._filtering_logged = False
        self._filtering_state = False

        self._publisher = self.create_publisher(LaserScan, self._output_topic, qos_profile_sensor_data)
        self._filter_active_publisher = self.create_publisher(Bool, self._filter_active_topic, 10)
        self._fault_subscription = self.create_subscription(
            Bool,
            self._fault_active_topic,
            self._fault_active_callback,
            10,
        )
        self._enable_subscription = self.create_subscription(
            Bool,
            self._enable_topic,
            self._enable_callback,
            10,
        )
        self._scan_subscription = self.create_subscription(
            LaserScan,
            self._input_topic,
            self._scan_callback,
            qos_profile_sensor_data,
        )

        self.get_logger().info(
            'Dropout scan recovery filter ready: '
            f'{self._input_topic} -> {self._output_topic}, '
            f'fault_active_topic={self._fault_active_topic}, '
            f'enable_topic={self._enable_topic}, require_enable={self._require_enable}, '
            f'center={math.degrees(self._sector_center_rad):.1f}deg, '
            f'width={math.degrees(self._sector_half_width_rad * 2.0):.1f}deg, '
            f'range_max_ratio_threshold={self._range_max_ratio_threshold:.2f}, '
            f'near_range_max_fraction={self._near_range_max_fraction:.2f}'
        )

    def _fault_active_callback(self, msg: Bool) -> None:
        self._fault_active = bool(msg.data)
        if not self._fault_active:
            self._filtering_logged = False
            if self._filtering_state:
                self.get_logger().info('Dropout recovery filter inactive: fault episode ended.')
            self._filtering_state = False
            self._filter_active_publisher.publish(Bool(data=False))

    def _enable_callback(self, msg: Bool) -> None:
        enabled = bool(msg.data)
        if enabled == self._policy_enabled:
            return
        self._policy_enabled = enabled
        if enabled:
            self.get_logger().warn('Dropout recovery filter enabled by selector.')
        else:
            self.get_logger().info('Dropout recovery filter disabled by selector.')
            self._filtering_logged = False
            self._filtering_state = False
            self._filter_active_publisher.publish(Bool(data=False))

    def _scan_callback(self, msg: LaserScan) -> None:
        out_msg = LaserScan()
        out_msg.header = msg.header
        out_msg.angle_min = msg.angle_min
        out_msg.angle_max = msg.angle_max
        out_msg.angle_increment = msg.angle_increment
        out_msg.time_increment = msg.time_increment
        out_msg.scan_time = msg.scan_time
        out_msg.range_min = msg.range_min
        out_msg.range_max = msg.range_max
        out_msg.ranges = list(msg.ranges)
        out_msg.intensities = list(msg.intensities)

        sector_indices = self._sector_indices(msg)
        range_max_ratio = self._range_max_ratio(msg, sector_indices)
        reject_burst = (
            self._policy_enabled
            and self._fault_active
            and range_max_ratio >= self._range_max_ratio_threshold
        )

        if reject_burst:
            for i in sector_indices:
                out_msg.ranges[i] = float('nan')
            if not self._filtering_logged:
                self.get_logger().warn(
                    'Dropout recovery filter active: rejecting frontal dropout bursts '
                    f'(range_max_ratio={range_max_ratio:.2f}, threshold={self._range_max_ratio_threshold:.2f}).'
                )
                self._filtering_logged = True
        elif self._filtering_state:
            self.get_logger().info(
                'Dropout recovery filter pass-through: healthy scan phase returned '
                f'(range_max_ratio={range_max_ratio:.2f}).'
            )

        self._filtering_state = reject_burst
        self._filter_active_publisher.publish(Bool(data=reject_burst))
        self._publisher.publish(out_msg)

    def _sector_indices(self, msg: LaserScan) -> list[int]:
        indices = []
        for i in range(len(msg.ranges)):
            beam_angle = msg.angle_min + i * msg.angle_increment
            angle_delta = normalize_angle(beam_angle - self._sector_center_rad)
            if abs(angle_delta) <= self._sector_half_width_rad:
                indices.append(i)
        return indices

    def _range_max_ratio(self, msg: LaserScan, indices: list[int]) -> float:
        if not indices:
            return 0.0
        near_max_count = 0
        valid_count = 0
        near_max_value = msg.range_max * self._near_range_max_fraction
        for i in indices:
            value = msg.ranges[i]
            if math.isnan(value):
                continue
            if math.isinf(value):
                valid_count += 1
                near_max_count += 1
                continue
            valid_count += 1
            if value >= near_max_value:
                near_max_count += 1
        if valid_count == 0:
            return 0.0
        return near_max_count / valid_count


def main() -> None:
    rclpy.init()
    node = DropoutScanRecoveryFilter()
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
