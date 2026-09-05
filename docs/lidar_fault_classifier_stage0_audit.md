# Stage 0: LiDAR Fault Classifier Injector Semantics Audit

## Purpose

This audit freezes the observable semantics of the two LiDAR fault models used in the dissertation before implementing a classifier. The classifier scope is limited to identifying the two investigated LiDAR fault models, not general LiDAR fault diagnosis.

Online classifier input must be the LiDAR stream consumed by the navigation stack. Injector labels, fault active flags, and raw-vs-faulted scan differences may be used only for offline evaluation and signature auditing.

## Runtime Topic Path

| Item | Finding | Evidence |
|---|---|---|
| Gazebo/bridge scan topic | `/sensors/lidar2d_0/scan` is remapped to `/front/scan` during robot spawn. | `BARN_runner.launch.py`, `spawn_jackal()` |
| Injector input | `/front/scan` | `laser_scan_fault_injector.py`, default `input_topic` |
| Injector output | `/front/scan_faulted` | `laser_scan_fault_injector.py`, default `output_topic` |
| Nav2 scan stream without scan fault | `/front/scan` | `BARN_runner.launch.py`, `launch_navigation_stack()` |
| Nav2 scan stream with scan fault | `/front/scan_faulted` | `BARN_runner.launch.py`, `launch_navigation_stack()` |
| Nav2 parameter rewrite | `nav2_bringup.launch.py` rewrites `scan.topic` parameters to the launch-provided `scan_topic`. | `nav2_bringup.launch.py`, `RewrittenYaml(param_rewrites={'topic': eval_scan_topic})` |

Classifier implementation target: subscribe to the navigation-consumed LiDAR stream. In the current fault-injection experiments, this is `/front/scan_faulted` when `scan_fault_enable:=true`.

## LiDAR Sensor Configuration

| Item | Finding | Evidence |
|---|---|---|
| LiDAR model | `hokuyo_ust`, `lidar2d_0` | `robot.urdf.xacro` |
| Field of view | `[-pi, +pi]`, i.e. 360 deg | `robot.yaml`, `robot.urdf.xacro` |
| Angular resolution | `0.5 deg` | `robot.urdf.xacro`, `ang_res="0.5"` |
| Range limits | `min_range=0.05`, `max_range=25.0` | `robot.urdf.xacro` |
| Nominal update rate | `40 Hz` | `robot.urdf.xacro`, diagnostic updater expected topic rate |
| QoS used by injector | `qos_profile_sensor_data` for input and output LaserScan | `laser_scan_fault_injector.py` |

Classifier QoS should match sensor-data QoS to avoid monitor-side QoS incompatibility being mistaken for LiDAR dropout.

## Fault Injector Semantics

### Frontal Masking

| Item | Finding |
|---|---|
| Activation | Fault becomes active after `fault_start_s`; if `fault_persistent=True`, it remains active until run end. |
| Sector | Fixed angular sector centered at `sector_center_deg`; dissertation campaign uses `0 deg` center and `90 deg` width. |
| Beam selection | For each finite, non-NaN beam, compute `beam_angle = angle_min + i * angle_increment`; replace beam if its wrapped angular distance to sector center is within half-width. |
| Replacement value | `range_max`, passed by launch as `replacement_value='range_max'`. |
| Message publication | Injector continues publishing `LaserScan` messages on `/front/scan_faulted`; it does not suppress whole messages. |
| Header/timestamp | Output message copies `msg.header` from input. |
| Outside sector | Outside-sector ranges and intensities are copied unchanged. |
| Already invalid beams | Existing `inf` or `nan` beams are skipped and left unchanged. |

Observable classifier implication: masking is not message loss. In the current implementation, it is a persistent frontal-sector content degradation where finite ranges in the affected sector become `range_max`.

### Intermittent Dropout

| Item | Finding |
|---|---|
| Activation | Dropout fault window begins after `fault_start_s`; if persistent, the window remains active until run end. |
| Temporal pattern | Within the active window, the effect cycles with `dropout_period_s`; dissertation campaign uses `1.0 s`. |
| Duty cycle | Fault effect is active for `dropout_period_s * dropout_duty_cycle`; dissertation campaign uses `0.5`, so the sector is faulted for roughly 0.5 s per 1.0 s cycle. |
| Spatial pattern | Same fixed frontal sector logic as masking. |
| Replacement value | Same `range_max` replacement as masking during active dropout phases. |
| Message publication | This is not message-level dropout. The injector continues publishing scan messages even during dropout phases. |
| Fault active flag | `/fault/scan_active` is true for the whole dropout window, not only active dropout sub-phases. This flag is ground truth/control metadata, not classifier input. |

Observable classifier implication: current dropout should be treated as periodic frontal-sector completeness/content degradation, not missed LaserScan messages. A timing watchdog remains useful as a general confounder check, but it is not the primary discriminator for this injected dropout model.

## Signature Audit Table

| Fault | Injector Semantics | Online Observable | Expected Signature | Normal Confounder | Candidate Evidence |
|---|---|---|---|---|---|
| Normal | No injection; Nav2 consumes normal scan stream. | Geometry-dependent LaserScan data at approximately 40 Hz. | Scan timing remains regular; frontal ranges vary with environment and robot pose. | Open space, wall following, turns, normal max-range readings. | Baseline scan timing distribution; normal frontal usable-ratio range; normal temporal switching range. |
| Masking | Finite beams in fixed frontal sector are continuously replaced by `range_max` during fault effect. | Sustained frontal sector range pattern consistent with max-range replacement. | Fixed angular region; low temporal switching; long abnormal streak; scan messages continue. | Open space can naturally produce many max-range beams; turning can change frontal geometry. | Affected angular span; sustained high replacement-like fraction in frontal sector; low switching rate; stable sector location. |
| Dropout | Same sector replacement as masking, but switched on/off periodically during the active window. | Intermittent frontal sector degradation while scan messages continue. | Repeated abnormal/healthy switching; period near configured dropout cycle; scan messages continue. | ROS/Gazebo timing jitter, occasional delayed scans, normal environmental changes. | Switching rate; longest abnormal/healthy streaks; periodicity of affected sector; scan inter-arrival timing as confounder check. |

## Design Consequences For Stage 1

1. Do not implement classifier rules from `invalid_beam_ratio` alone.
2. Treat `range_max`-like frontal-sector replacement as the main content-level abnormality for the current injected faults.
3. Use temporal evidence to separate masking from dropout:
   - masking: persistent abnormal sector, low switching;
   - dropout: repeated abnormal/healthy switching in the same sector.
4. Keep `fault_type` separate from `fault_state`:
   - fault type: `NORMAL`, `MASKING`, `DROPOUT`, `UNKNOWN`;
   - state: `NEW`, `ACTIVE`, `PROLONGED`, `CLEARED`.
5. Use injector configuration and `/fault/scan_active` only as offline ground truth, not online classifier input.

## Open Checks Before Stage 1

These should be measured from a small diagnostic dataset before fixing thresholds:

| Check | Purpose |
|---|---|
| Normal scan inter-arrival time distribution | Quantify nominal 40 Hz timing and VM jitter. |
| Normal frontal max-range fraction across selected worlds | Estimate environment-driven confounding. |
| Masking frontal replacement fraction and affected angular span | Confirm detector evidence under injected masking. |
| Dropout switching frequency and streak lengths | Confirm temporal separability from masking. |
| Header stamp behaviour | Confirm output scan header time remains suitable for timing analysis. |

