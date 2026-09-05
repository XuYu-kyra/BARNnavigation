#!/usr/bin/env python3
"""Conservatively scale cmd_vel while a fault window is active."""

from __future__ import annotations

import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool


class FaultAwareCmdVelGate(Node):
    def __init__(self) -> None:
        super().__init__('fault_aware_cmdvel_gate')

        self.declare_parameter('input_topic', '/cmd_vel_recovery_in')
        self.declare_parameter('output_topic', '/cmd_vel')
        self.declare_parameter('fault_active_topic', '/fault/scan_active')
        self.declare_parameter('linear_scale', 0.35)
        self.declare_parameter('angular_scale', 0.50)
        self.declare_parameter('active_timeout_s', 1.0)

        self._input_topic = str(self.get_parameter('input_topic').value)
        self._output_topic = str(self.get_parameter('output_topic').value)
        self._fault_active_topic = str(self.get_parameter('fault_active_topic').value)
        self._linear_scale = float(self.get_parameter('linear_scale').value)
        self._angular_scale = float(self.get_parameter('angular_scale').value)
        self._active_timeout_s = max(0.1, float(self.get_parameter('active_timeout_s').value))

        self._fault_active = False
        self._last_fault_signal_monotonic_s: float | None = None
        self._gate_engaged_logged = False

        self._publisher = self.create_publisher(Twist, self._output_topic, 10)
        self._cmd_sub = self.create_subscription(Twist, self._input_topic, self._cmd_callback, 10)
        self._fault_sub = self.create_subscription(Bool, self._fault_active_topic, self._fault_callback, 10)

        self.get_logger().info(
            'Fault-aware cmd_vel gate ready: '
            f'{self._input_topic} -> {self._output_topic}, '
            f'fault_active_topic={self._fault_active_topic}, '
            f'linear_scale={self._linear_scale:.3f}, '
            f'angular_scale={self._angular_scale:.3f}, '
            f'active_timeout_s={self._active_timeout_s:.2f}'
        )

    def _fault_callback(self, msg: Bool) -> None:
        self._fault_active = bool(msg.data)
        self._last_fault_signal_monotonic_s = time.monotonic()
        if self._fault_active and not self._gate_engaged_logged:
            self.get_logger().warn('Recovery gate active: scaling cmd_vel conservatively during fault window.')
            self._gate_engaged_logged = True
        elif not self._fault_active and self._gate_engaged_logged:
            self.get_logger().info('Recovery gate inactive: restoring nominal cmd_vel output.')
            self._gate_engaged_logged = False

    def _gate_should_engage(self) -> bool:
        if not self._fault_active:
            return False
        if self._last_fault_signal_monotonic_s is None:
            return False
        return (time.monotonic() - self._last_fault_signal_monotonic_s) <= self._active_timeout_s

    def _cmd_callback(self, msg: Twist) -> None:
        out = Twist()
        out.linear.x = msg.linear.x
        out.linear.y = msg.linear.y
        out.linear.z = msg.linear.z
        out.angular.x = msg.angular.x
        out.angular.y = msg.angular.y
        out.angular.z = msg.angular.z

        if self._gate_should_engage():
            out.linear.x *= self._linear_scale
            out.linear.y *= self._linear_scale
            out.linear.z *= self._linear_scale
            out.angular.x *= self._angular_scale
            out.angular.y *= self._angular_scale
            out.angular.z *= self._angular_scale

        self._publisher.publish(out)


def main() -> None:
    rclpy.init()
    node = FaultAwareCmdVelGate()
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
