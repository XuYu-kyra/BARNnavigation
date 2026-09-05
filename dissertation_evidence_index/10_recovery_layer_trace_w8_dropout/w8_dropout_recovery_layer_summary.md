# W8 Dropout Recovery Layer Trace Summary

Purpose: targeted recovery tracing for one representative case, comparing the same W8 dropout fault with recovery OFF vs recovery ON.

## Mission-Level Outcome

| Condition | Outcome | Completion time (s) | Nav metric |
|---|---|---:|---:|
| Recovery OFF | succeeded | 84.9901 | 0.1250 |
| Recovery ON | succeeded | 93.0634 | 0.1250 |

Mission-level interpretation: both runs succeeded, but recovery ON was not faster in this single trace. This should not be claimed as mission-level improvement.

## Layer-Level Observation

The useful evidence is process-level: the ON log confirms that the dropout scan recovery filter was ready, became active during dropout bursts, and passed through healthy phases. The comparison CSV reports fault-window means for scan, costmap, command, and odometry layers.

Key fault-window means:

| Layer metric | OFF | ON | ON - OFF |
|---|---:|---:|---:|
| scan range-max ratio | 0.8320 | 0.4593 | -0.3727 |
| scan span ratio | 0.8139 | 0.4302 | -0.3838 |
| local occupied ratio | 0.2081 | 0.2044 | -0.0037 |
| local lethal ratio | 0.1408 | 0.1379 | -0.0028 |
| cmd linear x | 0.6720 | 0.6720 | -0.0000 |
| odom speed | 0.6750 | 0.6756 | 0.0007 |

Claim boundary: this is one targeted trace. It supports process-level evidence that the filter changes the scan layer, while mission-level benefit remains unproven.
