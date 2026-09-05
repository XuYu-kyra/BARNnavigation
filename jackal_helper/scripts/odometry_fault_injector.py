#!/usr/bin/env python3
"""Inject a time-windowed drift/bias fault into an Odometry stream."""

from __future__ import annotations

import math
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data


def normalize_angle(angle_rad: float) -> float:
    return math.atan2(math.sin(angle_rad), math.cos(angle_rad))


def yaw_from_quaternion(msg) -> float:
    siny_cosp = 2.0 * (msg.w * msg.z + msg.x * msg.y)
    cosy_cosp = 1.0 - 2.0 * (msg.y * msg.y + msg.z * msg.z)
    return math.atan2(siny_cosp, cosy_cosp)


def quaternion_from_yaw(yaw: float) -> tuple[float, float, float, float]:
    half = yaw * 0.5
    return (0.0, 0.0, math.sin(half), math.cos(half))


class OdometryFaultInjector(Node):
    def __init__(self) -> None:
        super().__init__('odometry_fault_injector')

        self.declare_parameter('input_topic', '/platform/odom/filtered')
        self.declare_parameter('output_topic', '/platform/odom/filtered_faulted')
        self.declare_parameter('fault_start_s', 20.0)
        self.declare_parameter('fault_duration_s', 20.0)
        self.declare_parameter('linear_scale', 1.08)
        self.declare_parameter('yaw_rate_bias_deg_s', 1.5)

        self._input_topic = str(self.get_parameter('input_topic').value)
        self._output_topic = str(self.get_parameter('output_topic').value)
        self._fault_start_s = float(self.get_parameter('fault_start_s').value)
        self._fault_duration_s = float(self.get_parameter('fault_duration_s').value)
        self._linear_scale = float(self.get_parameter('linear_scale').value)
        self._yaw_rate_bias_rad_s = math.radians(float(self.get_parameter('yaw_rate_bias_deg_s').value))

        self._start_monotonic_s = None
        self._logged_fault_active = False
        self._prev_x = None
        self._prev_y = None
        self._prev_yaw = None
        self._prev_elapsed_s = None
        self._bias_x = 0.0
        self._bias_y = 0.0
        self._bias_yaw = 0.0

        self._publisher = self.create_publisher(
            Odometry,
            self._output_topic,
            qos_profile_sensor_data,
        )
        self._subscription = self.create_subscription(
            Odometry,
            self._input_topic,
            self._odom_callback,
            qos_profile_sensor_data,
        )

        self.get_logger().info(
            'Odometry fault injector ready: '
            f'{self._input_topic} -> {self._output_topic}, '
            f'start={self._fault_start_s:.1f}s, '
            f'duration={self._fault_duration_s:.1f}s, '
            f'linear_scale={self._linear_scale:.3f}, '
            f'yaw_rate_bias_deg_s={math.degrees(self._yaw_rate_bias_rad_s):.3f}'
        )

    def _odom_callback(self, msg: Odometry) -> None:
        now_monotonic_s = time.monotonic()
        if self._start_monotonic_s is None:
            self._start_monotonic_s = now_monotonic_s

        elapsed_s = now_monotonic_s - self._start_monotonic_s
        fault_active = self._fault_start_s <= elapsed_s < (self._fault_start_s + self._fault_duration_s)

        x = float(msg.pose.pose.position.x)
        y = float(msg.pose.pose.position.y)
        yaw = yaw_from_quaternion(msg.pose.pose.orientation)

        if self._prev_x is not None and self._prev_y is not None and self._prev_yaw is not None and self._prev_elapsed_s is not None:
            delta_x = x - self._prev_x
            delta_y = y - self._prev_y
            delta_yaw = normalize_angle(yaw - self._prev_yaw)
            delta_t = max(1e-9, elapsed_s - self._prev_elapsed_s)

            if fault_active:
                extra_scale = self._linear_scale - 1.0
                self._bias_x += extra_scale * delta_x
                self._bias_y += extra_scale * delta_y
                self._bias_yaw = normalize_angle(self._bias_yaw + self._yaw_rate_bias_rad_s * delta_t)

        out_msg = Odometry()
        out_msg.header = msg.header
        out_msg.child_frame_id = msg.child_frame_id
        out_msg.pose = msg.pose
        out_msg.twist = msg.twist

        out_msg.pose.pose.position.x = x + self._bias_x
        out_msg.pose.pose.position.y = y + self._bias_y
        qx, qy, qz, qw = quaternion_from_yaw(normalize_angle(yaw + self._bias_yaw))
        out_msg.pose.pose.orientation.x = qx
        out_msg.pose.pose.orientation.y = qy
        out_msg.pose.pose.orientation.z = qz
        out_msg.pose.pose.orientation.w = qw

        if fault_active:
            out_msg.twist.twist.linear.x = float(msg.twist.twist.linear.x) * self._linear_scale
            out_msg.twist.twist.linear.y = float(msg.twist.twist.linear.y) * self._linear_scale
            out_msg.twist.twist.angular.z = float(msg.twist.twist.angular.z) + self._yaw_rate_bias_rad_s
            if not self._logged_fault_active:
                self.get_logger().warn(
                    f'Fault active at t={elapsed_s:.2f}s: accumulating odometry scale and yaw bias.'
                )
                self._logged_fault_active = True
        elif self._logged_fault_active:
            self.get_logger().info(f'Fault window closed at t={elapsed_s:.2f}s.')
            self._logged_fault_active = False

        self._publisher.publish(out_msg)
        self._prev_x = x
        self._prev_y = y
        self._prev_yaw = yaw
        self._prev_elapsed_s = elapsed_s


def main() -> None:
    rclpy.init()
    node = OdometryFaultInjector()
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
