#!/usr/bin/env python3
"""Action-level Nav2 recovery supervisor for frontal LiDAR masking.

This is the v2 masking recovery pilot: instead of overriding cmd_vel directly,
it coordinates with Nav2's action/service layer:

  fault/progress trigger -> cancel NavigateToPose -> clear costmap -> Spin -> resend goal

The goal is to test whether task-level recovery requires explicit Nav2 action
coordination, after the cmd_vel-level reorientation pilot failed.
"""

from __future__ import annotations

import math
import time
from collections import deque

import rclpy
from action_msgs.msg import GoalInfo
from action_msgs.srv import CancelGoal
from builtin_interfaces.msg import Duration
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose, Spin
from nav2_msgs.srv import ClearEntireCostmap
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Bool


class MaskingNav2RecoverySupervisor(Node):
    def __init__(self) -> None:
        super().__init__('masking_nav2_recovery_supervisor')

        self.declare_parameter('fault_active_topic', '/fault/scan_active')
        self.declare_parameter('enable_topic', '/recovery/masking_monitor_enable')
        self.declare_parameter('require_enable', False)
        self.declare_parameter('odom_topic', '/platform/odom/filtered')
        self.declare_parameter('navigate_action_name', '/navigate_to_pose')
        self.declare_parameter('spin_action_name', '/spin')
        self.declare_parameter('local_clear_service', '/local_costmap/clear_entirely_local_costmap')
        self.declare_parameter('global_clear_service', '/global_costmap/clear_entirely_global_costmap')
        self.declare_parameter('clear_global_costmap', False)
        self.declare_parameter('trigger_policy', 'progress_stall')
        self.declare_parameter('trigger_delay_s', 0.0)
        self.declare_parameter('stall_window_s', 5.0)
        self.declare_parameter('stall_distance_m', 0.05)
        self.declare_parameter('spin_angle_deg', 60.0)
        self.declare_parameter('spin_time_allowance_s', 20.0)
        self.declare_parameter('settle_duration_s', 1.0)
        self.declare_parameter('goal_frame_id', 'odom')
        self.declare_parameter('goal_x', 10.0)
        self.declare_parameter('goal_y', 0.0)
        self.declare_parameter('goal_yaw_deg', 0.0)
        self.declare_parameter('max_recoveries', 1)
        self.declare_parameter('fault_active_timeout_s', 1.0)
        self.declare_parameter('cancel_timeout_s', 2.0)
        self.declare_parameter('service_timeout_s', 3.0)
        self.declare_parameter('spin_goal_response_timeout_s', 5.0)
        self.declare_parameter('spin_result_timeout_s', 25.0)
        self.declare_parameter('nav_goal_response_timeout_s', 5.0)

        self._fault_active_topic = str(self.get_parameter('fault_active_topic').value)
        self._enable_topic = str(self.get_parameter('enable_topic').value)
        self._require_enable = bool(self.get_parameter('require_enable').value)
        self._odom_topic = str(self.get_parameter('odom_topic').value)
        self._navigate_action_name = str(self.get_parameter('navigate_action_name').value)
        self._spin_action_name = str(self.get_parameter('spin_action_name').value)
        self._local_clear_service = str(self.get_parameter('local_clear_service').value)
        self._global_clear_service = str(self.get_parameter('global_clear_service').value)
        self._clear_global_costmap = bool(self.get_parameter('clear_global_costmap').value)
        self._trigger_policy = str(self.get_parameter('trigger_policy').value)
        self._trigger_delay_s = max(0.0, float(self.get_parameter('trigger_delay_s').value))
        self._stall_window_s = max(0.5, float(self.get_parameter('stall_window_s').value))
        self._stall_distance_m = max(0.0, float(self.get_parameter('stall_distance_m').value))
        self._spin_angle_rad = math.radians(float(self.get_parameter('spin_angle_deg').value))
        self._spin_time_allowance_s = max(1.0, float(self.get_parameter('spin_time_allowance_s').value))
        self._settle_duration_s = max(0.0, float(self.get_parameter('settle_duration_s').value))
        self._goal_frame_id = str(self.get_parameter('goal_frame_id').value)
        self._goal_x = float(self.get_parameter('goal_x').value)
        self._goal_y = float(self.get_parameter('goal_y').value)
        self._goal_yaw_deg = float(self.get_parameter('goal_yaw_deg').value)
        self._max_recoveries = max(0, int(self.get_parameter('max_recoveries').value))
        self._fault_active_timeout_s = max(0.1, float(self.get_parameter('fault_active_timeout_s').value))
        self._cancel_timeout_s = max(0.1, float(self.get_parameter('cancel_timeout_s').value))
        self._service_timeout_s = max(0.1, float(self.get_parameter('service_timeout_s').value))
        self._spin_goal_response_timeout_s = max(0.1, float(self.get_parameter('spin_goal_response_timeout_s').value))
        self._spin_result_timeout_s = max(1.0, float(self.get_parameter('spin_result_timeout_s').value))
        self._nav_goal_response_timeout_s = max(0.1, float(self.get_parameter('nav_goal_response_timeout_s').value))

        if self._trigger_policy not in ('immediate', 'progress_stall'):
            raise ValueError("trigger_policy must be 'immediate' or 'progress_stall'")

        self._navigate_client = ActionClient(self, NavigateToPose, self._navigate_action_name)
        self._spin_client = ActionClient(self, Spin, self._spin_action_name)
        self._cancel_client = self.create_client(CancelGoal, f'{self._navigate_action_name}/_action/cancel_goal')
        self._local_clear_client = self.create_client(ClearEntireCostmap, self._local_clear_service)
        self._global_clear_client = self.create_client(ClearEntireCostmap, self._global_clear_service)

        self._raw_fault_active = False
        self._policy_enabled = not self._require_enable
        self._fault_active = False
        self._fault_active_since: float | None = None
        self._last_fault_signal_monotonic_s: float | None = None
        self._recovery_count = 0
        self._state = 'IDLE'
        self._state_started_s = time.monotonic()
        self._odom_history: deque[tuple[float, float, float]] = deque()
        self._pending_future = None
        self._settle_until_s: float | None = None

        self._fault_sub = self.create_subscription(Bool, self._fault_active_topic, self._fault_callback, 10)
        self._enable_sub = self.create_subscription(Bool, self._enable_topic, self._enable_callback, 10)
        self._odom_sub = self.create_subscription(Odometry, self._odom_topic, self._odom_callback, 10)
        self._timer = self.create_timer(0.1, self._timer_callback)

        self.get_logger().info(
            'Masking Nav2 recovery supervisor ready: '
            f'fault_active_topic={self._fault_active_topic}, enable_topic={self._enable_topic}, '
            f'require_enable={self._require_enable}, odom_topic={self._odom_topic}, '
            f'navigate_action={self._navigate_action_name}, spin_action={self._spin_action_name}, '
            f'trigger_policy={self._trigger_policy}, spin_angle_deg={math.degrees(self._spin_angle_rad):.1f}, '
            f'goal=({self._goal_x:.2f}, {self._goal_y:.2f}) in {self._goal_frame_id}'
        )

    def _now(self) -> float:
        return time.monotonic()

    def _fault_signal_is_fresh(self) -> bool:
        if not self._fault_active or self._last_fault_signal_monotonic_s is None:
            return False
        return self._now() - self._last_fault_signal_monotonic_s <= self._fault_active_timeout_s

    def _state_elapsed_s(self) -> float:
        return self._now() - self._state_started_s

    def _finish_failed(self, reason: str) -> None:
        self.get_logger().error(f'nav2_masking_recovery_failed: reason={reason}')
        self._pending_future = None
        self._state = 'FAILED'
        self._state_started_s = self._now()

    def _set_effective_fault_active(self, active: bool, now: float) -> None:
        if active and not self._fault_active:
            self._fault_active_since = now
            if self._state == 'IDLE' and self._recovery_count < self._max_recoveries:
                self._state = 'MONITORING'
                self._state_started_s = now
                self.get_logger().warn(
                    'Nav2 masking recovery monitoring started: fault active and masking policy enabled, '
                    f'trigger_policy={self._trigger_policy}.'
                )
        elif not active and self._fault_active:
            self._fault_active_since = None
            if self._state == 'MONITORING':
                self._state = 'IDLE'
                self._state_started_s = now
                self.get_logger().info('Nav2 masking recovery monitoring stopped: fault inactive or masking policy disabled before recovery.')
        self._fault_active = active

    def _fault_callback(self, msg: Bool) -> None:
        now = self._now()
        self._last_fault_signal_monotonic_s = now
        self._raw_fault_active = bool(msg.data)
        self._set_effective_fault_active(self._raw_fault_active and self._policy_enabled, now)

    def _enable_callback(self, msg: Bool) -> None:
        now = self._now()
        enabled = bool(msg.data)
        if enabled == self._policy_enabled:
            return
        self._policy_enabled = enabled
        if enabled:
            self.get_logger().warn('Nav2 masking recovery policy enabled by selector.')
        else:
            self.get_logger().info('Nav2 masking recovery policy disabled by selector.')
        self._last_fault_signal_monotonic_s = now
        self._set_effective_fault_active(self._raw_fault_active and self._policy_enabled, now)

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

    def _duration_msg(self, seconds: float) -> Duration:
        sec = int(seconds)
        nanosec = int((seconds - sec) * 1e9)
        return Duration(sec=sec, nanosec=nanosec)

    def _make_goal_pose(self) -> PoseStamped:
        pose = PoseStamped()
        pose.header.frame_id = self._goal_frame_id
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = self._goal_x
        pose.pose.position.y = self._goal_y
        pose.pose.position.z = 0.0
        yaw = math.radians(self._goal_yaw_deg)
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        return pose

    def _cancel_current_navigation(self) -> None:
        if not self._cancel_client.service_is_ready():
            self.get_logger().warn(
                'old_nav_cancel_unavailable_proceeding: cancel service is not ready; continuing to costmap clear.'
            )
            self._clear_local_costmap()
            return
        self.get_logger().warn('old_nav_cancel_requested: canceling current NavigateToPose goals.')
        req = CancelGoal.Request()
        req.goal_info = GoalInfo()
        # Zero UUID + zero stamp requests cancellation of all goals on the action server.
        req.goal_info.goal_id.uuid = [0] * 16
        req.goal_info.stamp.sec = 0
        req.goal_info.stamp.nanosec = 0
        self._pending_future = self._cancel_client.call_async(req)
        self._state = 'CANCELING_NAV'
        self._state_started_s = self._now()

    def _clear_local_costmap(self) -> None:
        if not self._local_clear_client.service_is_ready():
            self.get_logger().warn(
                'local_costmap_clear_unavailable_proceeding: service is not ready; continuing to next recovery step.'
            )
            if self._clear_global_costmap:
                self._clear_global_costmap()
            else:
                self._send_spin_goal()
            return
        self.get_logger().warn('local_costmap_clear_start: requesting local costmap clear.')
        self._pending_future = self._local_clear_client.call_async(ClearEntireCostmap.Request())
        self._state = 'CLEARING_LOCAL'
        self._state_started_s = self._now()

    def _clear_global_costmap(self) -> None:
        if not self._global_clear_client.service_is_ready():
            self.get_logger().warn(
                'global_costmap_clear_unavailable_proceeding: service is not ready; continuing to spin.'
            )
            self._send_spin_goal()
            return
        self.get_logger().warn('global_costmap_clear_start: requesting global costmap clear.')
        self._pending_future = self._global_clear_client.call_async(ClearEntireCostmap.Request())
        self._state = 'CLEARING_GLOBAL'
        self._state_started_s = self._now()

    def _send_spin_goal(self) -> None:
        if not self._spin_client.server_is_ready():
            self._finish_failed('spin_action_server_unavailable')
            return
        self.get_logger().warn(
            'spin_goal_sent: requesting Nav2 Spin action, '
            f'target_yaw_deg={math.degrees(self._spin_angle_rad):.1f}.'
        )
        goal = Spin.Goal()
        goal.target_yaw = self._spin_angle_rad
        goal.time_allowance = self._duration_msg(self._spin_time_allowance_s)
        self._pending_future = self._spin_client.send_goal_async(goal)
        self._state = 'SENDING_SPIN'
        self._state_started_s = self._now()

    def _resend_navigation_goal(self) -> None:
        if not self._navigate_client.server_is_ready():
            self._finish_failed('navigate_action_server_unavailable_for_resend')
            return
        self.get_logger().warn(
            'navigation_goal_resent: sending same NavigateToPose goal, '
            f'goal=({self._goal_x:.2f}, {self._goal_y:.2f}) frame={self._goal_frame_id}.'
        )
        goal = NavigateToPose.Goal()
        goal.pose = self._make_goal_pose()
        self._pending_future = self._navigate_client.send_goal_async(goal)
        self._state = 'SENDING_NAV'
        self._state_started_s = self._now()

    def _service_future_done_ok(self, label: str) -> bool:
        if self._pending_future is None or not self._pending_future.done():
            return False
        try:
            result = self._pending_future.result()
            self.get_logger().warn(f'{label}: service/action request completed, result={result}.')
        except Exception as exc:  # noqa: BLE001 - log and stop supervisor sequence.
            self.get_logger().error(f'{label}: request failed: {exc}')
            self._state = 'FAILED'
            return False
        finally:
            self._pending_future = None
        return True

    def _action_goal_response_done(self, accepted_label: str, rejected_label: str) -> bool:
        if self._pending_future is None or not self._pending_future.done():
            return False
        try:
            goal_handle = self._pending_future.result()
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f'{rejected_label}: goal request failed: {exc}')
            self._state = 'FAILED'
            self._pending_future = None
            return False
        self._pending_future = None
        if not goal_handle.accepted:
            self.get_logger().error(f'{rejected_label}: goal rejected.')
            self._state = 'FAILED'
            return False
        self.get_logger().warn(f'{accepted_label}: goal accepted.')
        self._pending_future = goal_handle.get_result_async()
        return True

    def _action_result_done(self, label: str) -> bool:
        if self._pending_future is None or not self._pending_future.done():
            return False
        try:
            result = self._pending_future.result()
            self.get_logger().warn(f'{label}: result_code={result.status}, result={result.result}.')
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f'{label}: action result failed: {exc}')
            self._state = 'FAILED'
            self._pending_future = None
            return False
        self._pending_future = None
        return True

    def _start_recovery_if_needed(self) -> None:
        if not self._fault_signal_is_fresh():
            self._state = 'IDLE'
            self.get_logger().info('Nav2 masking recovery monitoring stopped: fault signal timed out.')
            return
        if self._recovery_count >= self._max_recoveries:
            return
        elapsed_since_fault = 0.0 if self._fault_active_since is None else self._now() - self._fault_active_since
        if elapsed_since_fault < self._trigger_delay_s:
            return
        reason = None
        if self._trigger_policy == 'immediate':
            reason = 'immediate_fault_trigger'
        else:
            distance = self._distance_over_stall_window()
            if distance is not None and distance <= self._stall_distance_m:
                reason = f'progress_stall_{distance:.3f}m_over_{self._stall_window_s:.1f}s'
        if reason is None:
            return
        self._recovery_count += 1
        self.get_logger().warn(
            'Nav2 masking recovery started: '
            f'reason={reason}, recovery_count={self._recovery_count}.'
        )
        self._cancel_current_navigation()

    def _timer_callback(self) -> None:
        if self._state == 'MONITORING':
            self._start_recovery_if_needed()
            return

        if self._state == 'CANCELING_NAV':
            if self._service_future_done_ok('old_nav_cancel_confirmed'):
                self._clear_local_costmap()
            elif self._state_elapsed_s() >= self._cancel_timeout_s:
                self.get_logger().warn(
                    f'old_nav_cancel_timeout_proceeding: no cancel response after {self._cancel_timeout_s:.1f}s.'
                )
                self._pending_future = None
                self._clear_local_costmap()
            return

        if self._state == 'CLEARING_LOCAL':
            if self._service_future_done_ok('local_costmap_clear_end'):
                if self._clear_global_costmap:
                    self._clear_global_costmap()
                else:
                    self._send_spin_goal()
            elif self._state_elapsed_s() >= self._service_timeout_s:
                self.get_logger().warn(
                    f'local_costmap_clear_timeout_proceeding: no response after {self._service_timeout_s:.1f}s.'
                )
                self._pending_future = None
                if self._clear_global_costmap:
                    self._clear_global_costmap()
                else:
                    self._send_spin_goal()
            return

        if self._state == 'CLEARING_GLOBAL':
            if self._service_future_done_ok('global_costmap_clear_end'):
                self._send_spin_goal()
            elif self._state_elapsed_s() >= self._service_timeout_s:
                self.get_logger().warn(
                    f'global_costmap_clear_timeout_proceeding: no response after {self._service_timeout_s:.1f}s.'
                )
                self._pending_future = None
                self._send_spin_goal()
            return

        if self._state == 'SENDING_SPIN':
            if self._action_goal_response_done('spin_goal_accepted', 'spin_goal_rejected'):
                self._state = 'WAITING_SPIN_RESULT'
                self._state_started_s = self._now()
            elif self._state_elapsed_s() >= self._spin_goal_response_timeout_s:
                self._finish_failed(f'spin_goal_response_timeout_{self._spin_goal_response_timeout_s:.1f}s')
            return

        if self._state == 'WAITING_SPIN_RESULT':
            if self._action_result_done('spin_result'):
                self._settle_until_s = self._now() + self._settle_duration_s
                self._state = 'SETTLING'
                self._state_started_s = self._now()
                self.get_logger().warn(f'settle_start: waiting {self._settle_duration_s:.2f}s for fresh scans/costmap updates.')
            elif self._state_elapsed_s() >= self._spin_result_timeout_s:
                self._finish_failed(f'spin_result_timeout_{self._spin_result_timeout_s:.1f}s')
            return

        if self._state == 'SETTLING':
            if self._settle_until_s is not None and self._now() >= self._settle_until_s:
                self.get_logger().warn('settle_end: resending navigation goal.')
                self._resend_navigation_goal()
            return

        if self._state == 'SENDING_NAV':
            if self._action_goal_response_done('navigation_goal_accepted', 'navigation_goal_rejected'):
                self._state = 'WAITING_NAV_RESULT'
                self._state_started_s = self._now()
            elif self._state_elapsed_s() >= self._nav_goal_response_timeout_s:
                self._finish_failed(f'navigation_goal_response_timeout_{self._nav_goal_response_timeout_s:.1f}s')
            return

        if self._state == 'WAITING_NAV_RESULT':
            if self._action_result_done('resent_navigation_result'):
                self._state = 'DONE'
                self.get_logger().warn('Nav2 masking recovery sequence complete: resent navigation action finished.')
            return


def main() -> None:
    rclpy.init()
    node = MaskingNav2RecoverySupervisor()
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
