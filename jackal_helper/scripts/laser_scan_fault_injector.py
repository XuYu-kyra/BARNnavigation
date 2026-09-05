#!/usr/bin/env python3
"""Inject a simple, time-windowed fault into a LaserScan stream."""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool


def normalize_angle(angle_rad: float) -> float:
    """Wrap an angle to [-pi, pi]."""
    return math.atan2(math.sin(angle_rad), math.cos(angle_rad))


class LaserScanFaultInjector(Node):
    def __init__(self) -> None:
        super().__init__('laser_scan_fault_injector')

        self.declare_parameter('input_topic', '/front/scan')
        self.declare_parameter('output_topic', '/front/scan_faulted')
        self.declare_parameter('fault_start_s', 30.0)
        self.declare_parameter('fault_duration_s', 8.0)
        self.declare_parameter('fault_persistent', False)
        self.declare_parameter('fault_mode', 'mask')
        self.declare_parameter('sector_center_deg', 0.0)
        self.declare_parameter('sector_width_deg', 70.0)
        self.declare_parameter('replacement_value', 'range_max')
        self.declare_parameter('dropout_period_s', 1.0)
        self.declare_parameter('dropout_duty_cycle', 0.5)
        self.declare_parameter('fault_active_topic', '/fault/scan_active')

        self._input_topic = self.get_parameter('input_topic').value
        self._output_topic = self.get_parameter('output_topic').value
        self._fault_start_s = float(self.get_parameter('fault_start_s').value)
        self._fault_duration_s = float(self.get_parameter('fault_duration_s').value)
        self._fault_persistent = bool(self.get_parameter('fault_persistent').value)
        self._fault_mode = str(self.get_parameter('fault_mode').value)
        self._sector_center_rad = math.radians(float(self.get_parameter('sector_center_deg').value))
        self._sector_half_width_rad = math.radians(float(self.get_parameter('sector_width_deg').value)) / 2.0
        self._replacement_value = str(self.get_parameter('replacement_value').value)
        self._dropout_period_s = max(1e-3, float(self.get_parameter('dropout_period_s').value))
        self._dropout_duty_cycle = min(1.0, max(0.0, float(self.get_parameter('dropout_duty_cycle').value)))
        self._fault_active_topic = str(self.get_parameter('fault_active_topic').value)
        self._start_time = None
        self._fault_window_logged = False

        self._publisher = self.create_publisher(
            LaserScan,
            self._output_topic,
            qos_profile_sensor_data,
        )
        self._fault_active_publisher = self.create_publisher(Bool, self._fault_active_topic, 10)
        self._subscription = self.create_subscription(
            LaserScan,
            self._input_topic,
            self._scan_callback,
            qos_profile_sensor_data,
        )

        self.get_logger().info(
            'Laser scan fault injector ready: '
            f'{self._input_topic} -> {self._output_topic}, '
            f'start={self._fault_start_s:.1f}s, '
            f'duration={"persistent" if self._fault_persistent else f"{self._fault_duration_s:.1f}s"}, '
            f'mode={self._fault_mode}, '
            f'center={math.degrees(self._sector_center_rad):.1f}deg, '
            f'width={math.degrees(self._sector_half_width_rad * 2.0):.1f}deg, '
            f'replacement={self._replacement_value}, '
            f'dropout_period_s={self._dropout_period_s:.2f}, '
            f'dropout_duty_cycle={self._dropout_duty_cycle:.2f}, '
            f'fault_active_topic={self._fault_active_topic}'
        )

    def _scan_callback(self, msg: LaserScan) -> None:
        now = self.get_clock().now()
        if self._start_time is None:
            self._start_time = now

        elapsed_s = (now - self._start_time).nanoseconds / 1e9
        if self._fault_persistent:
            fault_window_active = elapsed_s >= self._fault_start_s
        else:
            fault_window_active = self._fault_start_s <= elapsed_s < (self._fault_start_s + self._fault_duration_s)
        fault_effect_active = fault_window_active
        if self._fault_mode == 'dropout' and fault_window_active:
            phase_s = (elapsed_s - self._fault_start_s) % self._dropout_period_s
            active_width_s = self._dropout_period_s * self._dropout_duty_cycle
            fault_effect_active = phase_s < active_width_s

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

        if fault_window_active and not self._fault_window_logged:
            mode_desc = 'replacing frontal sector scan ranges continuously'
            if self._fault_mode == 'dropout':
                mode_desc = (
                    f'cycling frontal sector dropout bursts '
                    f'(period={self._dropout_period_s:.2f}s, duty={self._dropout_duty_cycle:.2f})'
                )
            window_desc = 'persistent' if self._fault_persistent else f'for {self._fault_duration_s:.2f}s'
            self.get_logger().warn(f'Fault active at t={elapsed_s:.2f}s ({window_desc}): {mode_desc}.')
            self._fault_window_logged = True
        elif not fault_window_active and self._fault_window_logged:
            self.get_logger().info(f'Fault window closed at t={elapsed_s:.2f}s.')
            self._fault_window_logged = False

        if fault_effect_active:
            replacement = msg.range_max if self._replacement_value == 'range_max' else float(self._replacement_value)
            for i, range_value in enumerate(out_msg.ranges):
                if math.isinf(range_value) or math.isnan(range_value):
                    continue
                beam_angle = msg.angle_min + i * msg.angle_increment
                angle_delta = normalize_angle(beam_angle - self._sector_center_rad)
                if abs(angle_delta) <= self._sector_half_width_rad:
                    out_msg.ranges[i] = replacement

        self._publisher.publish(out_msg)
        self._fault_active_publisher.publish(Bool(data=fault_window_active))


def main() -> None:
    rclpy.init()
    node = LaserScanFaultInjector()
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
