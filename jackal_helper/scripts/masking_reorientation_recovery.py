#!/usr/bin/env python3
"""Fault-aware active-perception recovery for frontal LiDAR masking.

The node sits between Nav2's command output and the robot command topic.  When a
scan fault is reported, it can execute one controlled in-place turn, then release
control back to Nav2.  The intent is to change the robot-frame observation
geometry so the previously frontal scene is observed by healthy LiDAR sectors.
"""

from __future__ import annotations

import math
import time
from collections import deque

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import Bool


class MaskingReorientationRecovery(Node):
    def __init__(self) -> None:
        super().__init__('masking_reorientation_recovery')

        self.declare_parameter('input_topic', '/cmd_vel_recovery_in')
        self.declare_parameter('output_topic', '/cmd_vel')
        self.declare_parameter('fault_active_topic', '/fault/scan_active')
        self.declare_parameter('odom_topic', '/platform/odom/filtered')
        self.declare_parameter('trigger_policy', 'immediate')
        self.declare_parameter('trigger_delay_s', 0.0)
        self.declare_parameter('stall_window_s', 5.0)
        self.declare_parameter('stall_distance_m', 0.15)
        self.declare_parameter('rotation_angle_deg', 60.0)
        self.declare_parameter('angular_speed_rad_s', 0.45)
        self.declare_parameter('settle_duration_s', 1.0)
        self.declare_parameter('max_recoveries', 1)
        self.declare_parameter('fault_active_timeout_s', 1.0)

        self._input_topic = str(self.get_parameter('input_topic').value)
        self._output_topic = str(self.get_parameter('output_topic').value)
        self._fault_active_topic = str(self.get_parameter('fault_active_topic').value)
        self._odom_topic = str(self.get_parameter('odom_topic').value)
        self._trigger_policy = str(self.get_parameter('trigger_policy').value)
        self._trigger_delay_s = max(0.0, float(self.get_parameter('trigger_delay_s').value))
        self._stall_window_s = max(0.5, float(self.get_parameter('stall_window_s').value))
        self._stall_distance_m = max(0.0, float(self.get_parameter('stall_distance_m').value))
        self._rotation_angle_rad = math.radians(abs(float(self.get_parameter('rotation_angle_deg').value)))
        self._angular_speed_rad_s = max(0.05, abs(float(self.get_parameter('angular_speed_rad_s').value)))
        self._settle_duration_s = max(0.0, float(self.get_parameter('settle_duration_s').value))
        self._max_recoveries = max(0, int(self.get_parameter('max_recoveries').value))
        self._fault_active_timeout_s = max(0.1, float(self.get_parameter('fault_active_timeout_s').value))

        if self._trigger_policy not in ('immediate', 'progress_stall'):
            raise ValueError("trigger_policy must be 'immediate' or 'progress_stall'")

        self._state = 'PASS_THROUGH'
        self._fault_active = False
        self._fault_active_since: float | None = None
        self._last_fault_signal_monotonic_s: float | None = None
        self._recovery_count = 0
        self._state_started_s = time.monotonic()
        self._odom_history: deque[tuple[float, float, float]] = deque()

        self._publisher = self.create_publisher(Twist, self._output_topic, 10)
        self._cmd_sub = self.create_subscription(Twist, self._input_topic, self._cmd_callback, 10)
        self._fault_sub = self.create_subscription(Bool, self._fault_active_topic, self._fault_callback, 10)
        self._odom_sub = self.create_subscription(Odometry, self._odom_topic, self._odom_callback, 10)
        self._timer = self.create_timer(0.05, self._timer_callback)

        self.get_logger().info(
            'Masking reorientation recovery ready: '
            f'{self._input_topic} -> {self._output_topic}, '
            f'fault_active_topic={self._fault_active_topic}, '
            f'odom_topic={self._odom_topic}, '
            f'trigger_policy={self._trigger_policy}, '
            f'rotation_angle_deg={math.degrees(self._rotation_angle_rad):.1f}, '
            f'angular_speed_rad_s={self._angular_speed_rad_s:.3f}, '
            f'settle_duration_s={self._settle_duration_s:.2f}'
        )

    def _now(self) -> float:
        return time.monotonic()

    def _fault_signal_is_fresh(self) -> bool:
        if not self._fault_active:
            return False
        if self._last_fault_signal_monotonic_s is None:
            return False
        return (self._now() - self._last_fault_signal_monotonic_s) <= self._fault_active_timeout_s

    def _fault_callback(self, msg: Bool) -> None:
        now = self._now()
        active = bool(msg.data)
        self._last_fault_signal_monotonic_s = now

        if active and not self._fault_active:
            self._fault_active_since = now
            if self._state == 'PASS_THROUGH':
                self._state = 'MONITORING'
                self._state_started_s = now
                self.get_logger().warn(
                    'Masking recovery monitoring started: fault active, '
                    f'trigger_policy={self._trigger_policy}.'
                )
        elif not active and self._fault_active:
            self._fault_active_since = None
            if self._state == 'MONITORING':
                self._state = 'PASS_THROUGH'
                self._state_started_s = now
                self.get_logger().info('Masking recovery monitoring stopped: fault inactive before recovery.')

        self._fault_active = active

    def _odom_callback(self, msg: Odometry) -> None:
        now = self._now()
        pos = msg.pose.pose.position
        self._odom_history.append((now, float(pos.x), float(pos.y)))
        while self._odom_history and now - self._odom_history[0][0] > self._stall_window_s + 1.0:
            self._odom_history.popleft()

    def _distance_over_stall_window(self) -> float | None:
        if len(self._odom_history) < 2:
            return None
        now = self._now()
        latest = self._odom_history[-1]
        earliest = None
        for sample in self._odom_history:
            if now - sample[0] <= self._stall_window_s:
                earliest = sample
                break
        if earliest is None:
            return None
        return math.hypot(latest[1] - earliest[1], latest[2] - earliest[2])

    def _start_recovery(self, reason: str) -> None:
        self._recovery_count += 1
        self._state = 'ROTATING'
        self._state_started_s = self._now()
        duration_s = self._rotation_angle_rad / self._angular_speed_rad_s
        self.get_logger().warn(
            'Masking reorientation recovery started: '
            f'reason={reason}, recovery_count={self._recovery_count}, '
            f'target_rotation_deg={math.degrees(self._rotation_angle_rad):.1f}, '
            f'expected_rotation_duration_s={duration_s:.2f}.'
        )

    def _zero_twist(self) -> Twist:
        return Twist()

    def _rotation_twist(self) -> Twist:
        msg = Twist()
        msg.angular.z = self._angular_speed_rad_s
        return msg

    def _timer_callback(self) -> None:
        now = self._now()

        if self._state == 'MONITORING':
            if not self._fault_signal_is_fresh():
                self._state = 'PASS_THROUGH'
                self._state_started_s = now
                self.get_logger().info('Masking recovery monitoring stopped: fault signal timed out.')
                return
            if self._recovery_count >= self._max_recoveries:
                return
            elapsed_since_fault = 0.0 if self._fault_active_since is None else now - self._fault_active_since
            if elapsed_since_fault < self._trigger_delay_s:
                return
            if self._trigger_policy == 'immediate':
                self._start_recovery('immediate_fault_trigger')
                return
            distance = self._distance_over_stall_window()
            if distance is not None and distance <= self._stall_distance_m:
                self._start_recovery(
                    f'progress_stall_{distance:.3f}m_over_{self._stall_window_s:.1f}s'
                )
                return

        if self._state == 'ROTATING':
            rotation_duration_s = self._rotation_angle_rad / self._angular_speed_rad_s
            if now - self._state_started_s < rotation_duration_s:
                self._publisher.publish(self._rotation_twist())
                return
            self._state = 'SETTLING'
            self._state_started_s = now
            self.get_logger().info('Masking reorientation rotation complete: settling before Nav2 release.')
            self._publisher.publish(self._zero_twist())
            return

        if self._state == 'SETTLING':
            if now - self._state_started_s < self._settle_duration_s:
                self._publisher.publish(self._zero_twist())
                return
            self._state = 'DONE'
            self._state_started_s = now
            self.get_logger().warn('Masking reorientation recovery complete: releasing cmd_vel back to Nav2.')
            return

    def _cmd_callback(self, msg: Twist) -> None:
        if self._state in ('ROTATING', 'SETTLING'):
            return
        self._publisher.publish(msg)


def main() -> None:
    rclpy.init()
    node = MaskingReorientationRecovery()
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
