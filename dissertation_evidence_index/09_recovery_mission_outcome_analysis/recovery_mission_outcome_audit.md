# Recovery Mission-Level Outcome Audit

This audit parses copied recovery/closed-loop logs and reports final task outcomes only. It does not claim recovery improvement unless matched no-recovery baselines exist for the same world/fault/timing setup.

Parsed logs: 30

## Outcome Counts By Recovery Type

| Recovery type | succeeded | timeout | collided | goal_failed | no_final_outcome |
|---|---:|---:|---:|---:|---:|
| dropout_scan_filter_enabled | 2 | 0 | 0 | 0 | 1 |
| masking_cmdvel_reorientation_action_started | 0 | 0 | 0 | 3 | 0 |
| masking_nav2_supervisor_action_started | 2 | 0 | 0 | 0 | 0 |
| masking_nav2_supervisor_policy_enabled | 1 | 0 | 2 | 0 | 0 |
| no_recovery_policy_enabled | 16 | 0 | 0 | 0 | 0 |
| none_fault_only | 2 | 0 | 0 | 0 | 1 |

## Outcome Counts By Fault And Recovery Type

| Fault | Recovery type | succeeded | timeout | collided | goal_failed | no_final_outcome |
|---|---|---:|---:|---:|---:|---:|
| dropout | dropout_scan_filter_enabled | 2 | 0 | 0 | 0 | 1 |
| dropout | no_recovery_policy_enabled | 7 | 0 | 0 | 0 | 0 |
| dropout | none_fault_only | 1 | 0 | 0 | 0 | 1 |
| masking | masking_cmdvel_reorientation_action_started | 0 | 0 | 0 | 3 | 0 |
| masking | masking_nav2_supervisor_action_started | 2 | 0 | 0 | 0 | 0 |
| masking | masking_nav2_supervisor_policy_enabled | 1 | 0 | 2 | 0 | 0 |
| masking | no_recovery_policy_enabled | 3 | 0 | 0 | 0 | 0 |
| masking | none_fault_only | 1 | 0 | 0 | 0 | 0 |
| unknown | no_recovery_policy_enabled | 6 | 0 | 0 | 0 | 0 |

## Interpretation Boundary

- Mission-level outcome can be checked directly from `Navigation succeeded/timeout/collided`, completion time, and navigation metric.
- A run with `policy_selected` or `filter enabled` plus successful navigation proves the recovery branch was operational, not that it improved performance.
- To prove mission-level improvement, compare matched conditions: same world, same fault mode, same timing, same timeout, with recovery disabled vs enabled, ideally with paired repeats.
- Existing logs support a mission-level audit and functional branch evidence; they do not yet form a rigorous recovery-effectiveness campaign.
