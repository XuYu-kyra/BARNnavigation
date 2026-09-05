# W8 Masking Recovery Layer Trace Summary

Purpose: targeted recovery tracing for one representative case, comparing the same W8 masking fault with recovery OFF vs forced Nav2 masking recovery ON.

## Mission-Level Outcome

| Condition | Outcome | Completion time (s) | Nav metric |
|---|---|---:|---:|
| Recovery OFF | succeeded | 86.0834 | 0.1250 |
| Recovery ON | succeeded | 112.2875 | 0.1250 |

Mission-level interpretation: both runs succeeded, but forced masking recovery ON was slower in this single trace. This should not be claimed as mission-level improvement.

## Recovery Action Evidence

| Condition | Monitoring started | Recovery started | Navigation goal resent | Progress failures | Goal failed |
|---|---|---|---|---:|---|
| Recovery OFF | False | False | False | 0 | False |
| Recovery ON | True | True | True | 0 | False |

## Layer-Level Observation

Unlike dropout filtering, masking recovery does not repair the scan stream. It acts at the behaviour/action layer by triggering Nav2 masking recovery, rotating/reorienting, and resending the navigation goal. The trace therefore expects scan degradation to remain visible while command/motion behaviour changes during the intervention.

Key fault-window means:

| Layer metric | OFF | ON | ON - OFF |
|---|---:|---:|---:|
| scan range-max ratio | 1.0000 | 1.0000 | 0.0000 |
| scan span ratio | 1.0000 | 1.0000 | 0.0000 |
| local occupied ratio | 0.0593 | 0.0696 | 0.0103 |
| local lethal ratio | 0.0393 | 0.0441 | 0.0047 |
| cmd linear x | 0.6111 | 0.3802 | -0.2309 |
| cmd angular z | -0.0053 | -0.0530 | -0.0477 |
| odom speed | 0.6218 | 0.3932 | -0.2287 |

Claim boundary: this is one targeted trace. It confirms behaviour/action-layer intervention for masking, but it does not show scan-layer repair or mission-level improvement.
