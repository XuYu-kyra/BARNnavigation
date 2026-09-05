#!/usr/bin/env python3
"""Closed-loop selector from LiDAR fault signature to recovery policy.

This node implements the frozen Stage-2B episode-level classifier used for the
final integration smoke test. It uses /fault/scan_active only as an episode
presence signal, observes the navigation-consumed faulted scan for a fixed
window, estimates MASKING / DROPOUT / UNKNOWN once, then latches the matching
policy until the fault episode ends.
"""

from __future__ import annotations

import math
from collections import deque
from statistics import median, mean

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool, String

FAULT_TYPES = {'MASKING', 'DROPOUT'}


def normalize_angle(angle_rad: float) -> float:
    return math.atan2(math.sin(angle_rad), math.cos(angle_rad))


def safe_mean(values: list[float]) -> float:
    values = [x for x in values if math.isfinite(x)]
    return mean(values) if values else float('nan')


def safe_max(values: list[float]) -> float:
    values = [x for x in values if math.isfinite(x)]
    return max(values) if values else float('nan')


def longest_streak_s(times: list[float], flags: list[bool], target: bool) -> float:
    if not times or not flags:
        return 0.0
    best = 0.0
    start: float | None = None
    last_t = times[0]
    for t, flag in zip(times, flags):
        if flag == target:
            if start is None:
                start = t
            last_t = t
        else:
            if start is not None:
                best = max(best, last_t - start)
                start = None
    if start is not None:
        best = max(best, last_t - start)
    return max(0.0, best)


def switching_rate_per_s(times: list[float], flags: list[bool]) -> float:
    if len(times) < 2 or len(flags) < 2:
        return 0.0
    switches = sum(1 for prev, cur in zip(flags, flags[1:]) if prev != cur)
    duration = max(1e-6, times[-1] - times[0])
    return switches / duration


class ScanFaultPolicySelector(Node):
    def __init__(self) -> None:
        super().__init__('scan_fault_policy_selector')

        self.declare_parameter('scan_topic', '/front/scan_faulted')
        self.declare_parameter('fault_active_topic', '/fault/scan_active')
        self.declare_parameter('fault_type_topic', '/fault/type_estimated')
        self.declare_parameter('dropout_enable_topic', '/recovery/dropout_filter_enable')
        self.declare_parameter('masking_enable_topic', '/recovery/masking_monitor_enable')
        self.declare_parameter('observation_window_s', 2.0)
        self.declare_parameter('baseline_window_s', 4.5)
        self.declare_parameter('sector_center_deg', 0.0)
        self.declare_parameter('sector_width_deg', 90.0)
        self.declare_parameter('near_range_max_fraction', 0.98)
        self.declare_parameter('online_evidence_threshold', 0.25)
        self.declare_parameter('absolute_range_max_ratio_threshold', 0.55)
        self.declare_parameter('absolute_span_ratio_threshold', 0.55)
        self.declare_parameter('stage2b_min_degraded_fraction', 0.15)
        self.declare_parameter('stage2b_masking_min_degraded_fraction', 0.55)
        self.declare_parameter('stage2b_masking_max_switching_rate_per_s', 0.55)
        self.declare_parameter('stage2b_masking_min_degraded_streak_s', 0.75)
        self.declare_parameter('stage2b_dropout_min_degraded_fraction', 0.15)
        self.declare_parameter('stage2b_dropout_min_switching_rate_per_s', 0.75)
        self.declare_parameter('stage2b_dropout_min_degraded_streak_s', 0.15)
        self.declare_parameter('stage2b_dropout_min_healthy_streak_s', 0.15)
        self.declare_parameter('stage2b_dropout_override_switching_rate_per_s', 0.75)
        self.declare_parameter('min_observation_samples', 3)
        self.declare_parameter('publish_period_s', 0.25)

        self._scan_topic = str(self.get_parameter('scan_topic').value)
        self._fault_active_topic = str(self.get_parameter('fault_active_topic').value)
        self._fault_type_topic = str(self.get_parameter('fault_type_topic').value)
        self._dropout_enable_topic = str(self.get_parameter('dropout_enable_topic').value)
        self._masking_enable_topic = str(self.get_parameter('masking_enable_topic').value)
        self._observation_window_s = max(0.1, float(self.get_parameter('observation_window_s').value))
        self._baseline_window_s = max(0.1, float(self.get_parameter('baseline_window_s').value))
        self._sector_center_rad = math.radians(float(self.get_parameter('sector_center_deg').value))
        self._sector_half_width_rad = math.radians(float(self.get_parameter('sector_width_deg').value)) / 2.0
        self._near_range_max_fraction = float(self.get_parameter('near_range_max_fraction').value)
        self._online_evidence_threshold = float(self.get_parameter('online_evidence_threshold').value)
        self._absolute_range_max_ratio_threshold = float(self.get_parameter('absolute_range_max_ratio_threshold').value)
        self._absolute_span_ratio_threshold = float(self.get_parameter('absolute_span_ratio_threshold').value)
        self._stage2b_min_degraded_fraction = float(self.get_parameter('stage2b_min_degraded_fraction').value)
        self._stage2b_masking_min_degraded_fraction = float(self.get_parameter('stage2b_masking_min_degraded_fraction').value)
        self._stage2b_masking_max_switching_rate_per_s = float(self.get_parameter('stage2b_masking_max_switching_rate_per_s').value)
        self._stage2b_masking_min_degraded_streak_s = float(self.get_parameter('stage2b_masking_min_degraded_streak_s').value)
        self._stage2b_dropout_min_degraded_fraction = float(self.get_parameter('stage2b_dropout_min_degraded_fraction').value)
        self._stage2b_dropout_min_switching_rate_per_s = float(self.get_parameter('stage2b_dropout_min_switching_rate_per_s').value)
        self._stage2b_dropout_min_degraded_streak_s = float(self.get_parameter('stage2b_dropout_min_degraded_streak_s').value)
        self._stage2b_dropout_min_healthy_streak_s = float(self.get_parameter('stage2b_dropout_min_healthy_streak_s').value)
        self._stage2b_dropout_override_switching_rate_per_s = float(self.get_parameter('stage2b_dropout_override_switching_rate_per_s').value)
        self._min_observation_samples = max(1, int(self.get_parameter('min_observation_samples').value))
        publish_period_s = max(0.1, float(self.get_parameter('publish_period_s').value))

        self._fault_active = False
        self._episode_start_scan_time: float | None = None
        self._episode_decided = False
        self._latched_type = 'NONE'
        self._latched_reason = 'no_fault_episode'
        self._baseline_stats: deque[tuple[float, float, float]] = deque()
        self._baseline_range = 0.0
        self._baseline_span = 0.0
        self._observation: list[tuple[float, bool, float]] = []

        self._fault_type_pub = self.create_publisher(String, self._fault_type_topic, 10)
        self._dropout_enable_pub = self.create_publisher(Bool, self._dropout_enable_topic, 10)
        self._masking_enable_pub = self.create_publisher(Bool, self._masking_enable_topic, 10)
        self._fault_sub = self.create_subscription(Bool, self._fault_active_topic, self._fault_active_callback, 10)
        self._scan_sub = self.create_subscription(LaserScan, self._scan_topic, self._scan_callback, qos_profile_sensor_data)
        self._timer = self.create_timer(publish_period_s, self._publish_latched_outputs)

        self.get_logger().info(
            'Stage2B scan fault policy selector ready: '
            f'scan_topic={self._scan_topic}, fault_active_topic={self._fault_active_topic}, '
            f'observation_window_s={self._observation_window_s:.2f}, '
            f'absolute_range_max_ratio_threshold={self._absolute_range_max_ratio_threshold:.2f}, '
            f'absolute_span_ratio_threshold={self._absolute_span_ratio_threshold:.2f}, '
            f'output_type_topic={self._fault_type_topic}, '
            f'dropout_enable_topic={self._dropout_enable_topic}, '
            f'masking_enable_topic={self._masking_enable_topic}'
        )
        self._publish_latched_outputs()

    def _scan_time_s(self, msg: LaserScan) -> float:
        stamp = msg.header.stamp
        if stamp.sec != 0 or stamp.nanosec != 0:
            return float(stamp.sec) + float(stamp.nanosec) * 1e-9
        now = self.get_clock().now().nanoseconds
        return now * 1e-9

    def _fault_active_callback(self, msg: Bool) -> None:
        active = bool(msg.data)
        if active and not self._fault_active:
            self._start_episode()
        elif not active and self._fault_active:
            self._reset_episode('fault_episode_ended')
        self._fault_active = active

    def _start_episode(self) -> None:
        self._episode_start_scan_time = None
        self._episode_decided = False
        self._latched_type = 'OBSERVING'
        self._latched_reason = 'fault_active_observation_window_open'
        self._observation = []
        self._snapshot_baseline()
        self.get_logger().warn(
            'fault_episode_start: Stage2B observation started, '
            f'observation_window_s={self._observation_window_s:.2f}, '
            f'baseline_range_max_ratio={self._baseline_range:.3f}, '
            f'baseline_span_ratio={self._baseline_span:.3f}.'
        )
        self._publish_latched_outputs()

    def _reset_episode(self, reason: str) -> None:
        if self._latched_type not in ('NONE',):
            self.get_logger().info(f'fault_episode_reset: reason={reason}, previous_type={self._latched_type}.')
        self._episode_start_scan_time = None
        self._episode_decided = False
        self._latched_type = 'NONE'
        self._latched_reason = reason
        self._observation = []
        self._publish_latched_outputs()

    def _snapshot_baseline(self) -> None:
        values = list(self._baseline_stats)
        range_values = [row[1] for row in values if math.isfinite(row[1])]
        span_values = [row[2] for row in values if math.isfinite(row[2])]
        self._baseline_range = median(range_values) if range_values else 0.0
        self._baseline_span = median(span_values) if span_values else 0.0

    def _scan_callback(self, msg: LaserScan) -> None:
        now = self._scan_time_s(msg)
        range_max_ratio, span_ratio = self._sector_ratios(msg)

        if not self._fault_active:
            self._baseline_stats.append((now, range_max_ratio, span_ratio))
            while self._baseline_stats and now - self._baseline_stats[0][0] > self._baseline_window_s:
                self._baseline_stats.popleft()
            return

        if self._episode_decided:
            return
        if self._episode_start_scan_time is None:
            self._episode_start_scan_time = now

        elapsed = now - self._episode_start_scan_time
        range_delta = max(0.0, range_max_ratio - self._baseline_range)
        span_delta = max(0.0, span_ratio - self._baseline_span)
        delta_score = max(range_delta, span_delta)
        absolute_score = max(range_max_ratio, span_ratio)
        degraded_by_delta = math.isfinite(delta_score) and delta_score >= self._online_evidence_threshold
        degraded_by_absolute = (
            (math.isfinite(range_max_ratio) and range_max_ratio >= self._absolute_range_max_ratio_threshold)
            or (math.isfinite(span_ratio) and span_ratio >= self._absolute_span_ratio_threshold)
        )
        degraded = degraded_by_delta or degraded_by_absolute
        evidence_score = absolute_score if degraded_by_absolute else delta_score
        self._observation.append((elapsed, degraded, evidence_score))

        if elapsed >= self._observation_window_s:
            self._decide_episode(elapsed)

    def _sector_ratios(self, msg: LaserScan) -> tuple[float, float]:
        indices = self._sector_indices(msg)
        if not indices:
            return 0.0, 0.0
        near_max_count = 0
        valid_count = 0
        longest_span = 0
        current_span = 0
        near_max_value = msg.range_max * self._near_range_max_fraction
        for i in indices:
            value = msg.ranges[i]
            if math.isnan(value):
                current_span = 0
                continue
            valid_count += 1
            near_max = math.isinf(value) or value >= near_max_value
            if near_max:
                near_max_count += 1
                current_span += 1
                longest_span = max(longest_span, current_span)
            else:
                current_span = 0
        if valid_count == 0:
            return 0.0, 0.0
        return near_max_count / valid_count, longest_span / max(1, len(indices))

    def _sector_indices(self, msg: LaserScan) -> list[int]:
        indices = []
        for i in range(len(msg.ranges)):
            beam_angle = msg.angle_min + i * msg.angle_increment
            angle_delta = normalize_angle(beam_angle - self._sector_center_rad)
            if abs(angle_delta) <= self._sector_half_width_rad:
                indices.append(i)
        return indices

    def _decide_episode(self, elapsed: float) -> None:
        times = [row[0] for row in self._observation]
        flags = [row[1] for row in self._observation]
        scores = [row[2] for row in self._observation]
        if len(self._observation) < self._min_observation_samples:
            predicted, reason = 'UNKNOWN', 'insufficient_samples'
            metrics = {
                'degraded_fraction': float('nan'),
                'switching_rate_per_s': float('nan'),
                'longest_degraded_streak_s': float('nan'),
                'longest_healthy_streak_s': float('nan'),
                'evidence_mean': float('nan'),
                'evidence_max': float('nan'),
            }
        else:
            metrics = {
                'degraded_fraction': safe_mean([float(flag) for flag in flags]),
                'switching_rate_per_s': switching_rate_per_s(times, flags),
                'longest_degraded_streak_s': longest_streak_s(times, flags, True),
                'longest_healthy_streak_s': longest_streak_s(times, flags, False),
                'evidence_mean': safe_mean(scores),
                'evidence_max': safe_max(scores),
            }
            predicted, reason = self._classify(metrics)

        self._episode_decided = True
        self._latched_type = predicted
        self._latched_reason = reason
        self.get_logger().warn(
            'fault_type_estimated: '
            f'predicted_type={predicted}, reason={reason}, '
            f'classification_latency_s={elapsed:.2f}, sample_count={len(self._observation)}, '
            f'degraded_fraction={metrics["degraded_fraction"]:.3f}, '
            f'switching_rate_per_s={metrics["switching_rate_per_s"]:.3f}, '
            f'longest_degraded_streak_s={metrics["longest_degraded_streak_s"]:.3f}, '
            f'longest_healthy_streak_s={metrics["longest_healthy_streak_s"]:.3f}, '
            f'evidence_mean={metrics["evidence_mean"]:.3f}, evidence_max={metrics["evidence_max"]:.3f}.'
        )
        self._publish_latched_outputs(log_policy=True)

    def _classify(self, metrics: dict[str, float]) -> tuple[str, str]:
        degraded_fraction = metrics['degraded_fraction']
        switching_rate = metrics['switching_rate_per_s']
        bad_streak_s = metrics['longest_degraded_streak_s']
        good_streak_s = metrics['longest_healthy_streak_s']

        dropout_like = (
            degraded_fraction >= self._stage2b_dropout_min_degraded_fraction
            and switching_rate >= self._stage2b_dropout_min_switching_rate_per_s
            and bad_streak_s >= self._stage2b_dropout_min_degraded_streak_s
            and good_streak_s >= self._stage2b_dropout_min_healthy_streak_s
        )
        masking_like = (
            degraded_fraction >= self._stage2b_masking_min_degraded_fraction
            and switching_rate <= self._stage2b_masking_max_switching_rate_per_s
            and bad_streak_s >= self._stage2b_masking_min_degraded_streak_s
        )

        if dropout_like and not masking_like:
            return 'DROPOUT', 'clear_dropout_switching'
        if masking_like and not dropout_like:
            return 'MASKING', 'clear_sustained_masking'
        if dropout_like and masking_like:
            if switching_rate >= self._stage2b_dropout_override_switching_rate_per_s:
                return 'DROPOUT', 'both_patterns_switching_override'
            return 'UNKNOWN', 'ambiguous_both_patterns'
        if degraded_fraction >= self._stage2b_min_degraded_fraction:
            return 'UNKNOWN', 'degraded_but_pattern_unclear'
        return 'UNKNOWN', 'insufficient_degradation_evidence'

    def _publish_latched_outputs(self, log_policy: bool = False) -> None:
        fault_type_msg = String()
        fault_type_msg.data = self._latched_type
        dropout_enabled = self._latched_type == 'DROPOUT'
        masking_enabled = self._latched_type == 'MASKING'
        self._fault_type_pub.publish(fault_type_msg)
        self._dropout_enable_pub.publish(Bool(data=dropout_enabled))
        self._masking_enable_pub.publish(Bool(data=masking_enabled))
        if log_policy:
            if self._latched_type == 'DROPOUT':
                selected_policy = 'dropout_scan_filter'
            elif self._latched_type == 'MASKING':
                selected_policy = 'masking_nav2_recovery'
            else:
                selected_policy = 'none'
            self.get_logger().warn(
                'policy_selected: '
                f'predicted_type={self._latched_type}, selected_policy={selected_policy}, '
                f'dropout_filter_enable={dropout_enabled}, masking_monitor_enable={masking_enabled}.'
            )


def main() -> None:
    rclpy.init()
    node = ScanFaultPolicySelector()
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
