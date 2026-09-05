# Appendix A — Project Outline

This appendix reproduces the submitted project outline. The outline reflects the initial project plan; the final dissertation scope was refined during implementation to focus on two formal LiDAR sensing faults, conditional fault-type identification, and exploratory recovery.

## A.1 Background and Motivation

Autonomous mobile robots are expected to navigate reliably to target locations and complete assigned tasks with limited human intervention. Reliable robot navigation is therefore essential for mobile robot autonomy.

Sensing and localisation faults can strongly impact navigation performance, especially when the robot depends on sensor data and localisation estimates to build costmaps, path plans and execute motion commands. These faults are important to study because their effects may propagate through the navigation stack. For example, LiDAR degradation may distort costmaps, affect the planner or controller, trigger recovery behaviours, and eventually lead to collision, timeout or mission failure. This means that evaluating only the final success or failure outcome is not sufficient.

A cross-layer evaluation can provide more useful information about where and how the system starts to fail. By recording logs from sensing, costmap, planning, control and recovery components, the project can explain the relationship between the original fault and the final navigation outcome, supporting deeper analysis of fault-tolerant navigation behaviour in Nav2.

## A.2 Initial Aim and Objectives

The initial aim was to evaluate how selected sensing and localisation faults propagate through the ROS 2 Nav2 navigation stack, and to investigate whether health-aware recovery selection can improve recovery decisions under degraded navigation conditions.

Initial objectives:

- Review recent and relevant literature and define the Nav2-specific research gap.
- Build a repeatable ROS 2/Nav2 simulation and logging pipeline.
- Implement controlled fault injection for at least one LiDAR-based sensing fault and collect cross-layer data using a consistent logging format.
- Compare recovery configurations under the same robot, environment, fault settings and metrics.
- Analyse fault propagation, recovery performance and limitations.

## A.3 Initial Scope and Project Plan

The project was simulation-first. Real-robot validation was not included in the final scope. The preferred environment was BARN ROS 2 because it provides standardised navigation worlds and repeatable 2D LiDAR-based navigation tasks.

Initial stages:

- Stage 1: Test feasibility of BARN ROS 2.
- Stage 2: Inject initial LiDAR faults and collect cross-layer logs.
- Stage 3: Compare recovery configurations.
- Stage 4: Analyse data and draw conclusions; localisation faults were optional if time allowed.

Final implementation note: the final formal experiments retained two LiDAR sensing faults. Odometry drift was explored but not retained as a formal campaign fault because its effect was less repeatable under the controlled setup.

# Appendix B — Risk Assessment

This appendix summarises the submitted risk assessment document for computer-based simulation research.

| Item | Details |
|---|---|
| Assessment title | General Risk Assessment |
| Date | 25/06/2026 |
| Assessed by | Yu Xu |
| Location | University workspace / home |
| Task | Computer-based research and simulation only |
| Review date | One year from issue or if significant changes occur |

## B.1 Main Risks and Controls

| Activity / source | Hazard | People affected | Possible consequence | Existing control measures | Residual risk |
|---|---|---|---|---|---|
| Working on campus | COVID or respiratory illness through close contact or contaminated surfaces | Staff, students, visitors | Infection or illness | University COVID guidance, face coverings and hand sanitisers available, current campus guidance followed | Medium |
| Working on campus | Building fire | Staff, students, visitors | Burns, smoke inhalation, evacuation risk | Fire action notices, alarm testing, evacuation practice, fire awareness induction, clear exits, trained marshals where available | Medium |
| Working on campus | Injury or ill health | Staff, students, visitors | Need for first aid or emergency help | First aid notices, first aiders, campus security first aid support, AED availability | Medium |
| Maintaining building security | Suspicious people or activities | Staff, students, visitors | Difficulty contacting help or maintaining personal safety | Do not tailgate, contact campus security, avoid unauthorised/lone/out-of-hours areas | Medium |
| Moving around buildings | Building defects and poor housekeeping | Staff, students, visitors | Slips, trips and falls | Report defects, maintain housekeeping, keep floors and exits clear, manage trailing cables, adequate lighting | Low |
| Computer-based work | Workstation use and electrical equipment | Student | Discomfort, fatigue, electrical risk | Use appropriate furniture, follow standard DSE/workstation practice, use maintained equipment | Low |

The project involved simulation and data analysis only. No physical robot testing, hazardous materials, electrical modification, or workshop activity was included in the final dissertation work.

# Appendix C — Experimental Configuration and Environment Selection

## C.1 Software and Simulation Platform

| Item | Configuration used |
|---|---|
| ROS version | ROS 2 Jazzy |
| Navigation stack | Nav2 |
| Robot platform | Simulated Clearpath Jackal |
| Simulator | Gazebo |
| Benchmark environments | BARN navigation benchmark, 300 pre-generated worlds |
| Formal navigation setup | `tuned_clean` |
| Original comparison setup | `original_clean` |
| Global planner | `nav2_navfn_planner::NavfnPlanner` |
| Local controller | `nav2_mppi_controller::MPPIController` |
| Global frame | `odom` |
| Robot base frame | `base_link` |
| Odometry topic | `platform/odom/filtered` |
| Formal run timeout | 300 s |

Source files:

- `experiment_setups/original_clean/nav2.yaml`
- `experiment_setups/tuned_clean/nav2.yaml`

Only `nav2.yaml` differed between `original_clean` and `tuned_clean` in the local configuration diff.

## C.2 Purpose of `tuned_clean`

The `tuned_clean` configuration was used as an experimental control rather than as a navigation-optimisation contribution. Its purpose was to reduce nominal navigation instability before fault injection, so that baseline-vs-fault comparisons were less likely to be confounded by failures already present in the original setup. All formal fault campaigns used the same `tuned_clean` configuration for both nominal and fault-injected runs.

## C.3 Original to `tuned_clean` Nav2 Parameter Changes

| Nav2 component | Parameter | Original value | Tuned value | Intended role |
|---|---:|---:|---:|---|
| MPPI controller | `FollowPath.vx_max` | 0.5 | 1.0 | Increased allowed forward velocity to reduce overly slow nominal navigation. |
| MPPI `PathAlignCritic` | `cost_weight` | 14.0 | 10.0 | Reduced strict path-alignment pressure, allowing more flexible local control. |
| MPPI `PathFollowCritic` | `cost_weight` | 5.0 | 7.0 | Increased path-following incentive. |
| Local costmap inflation layer | `inflation_radius` | 0.8 | 0.65 | Reduced local obstacle-inflation conservatism. |
| Global costmap inflation layer | `inflation_radius` | 0.8 | 0.65 | Reduced global obstacle-inflation conservatism. |

## C.4 Key `tuned_clean` Planner and Controller Parameters

| Component | Parameter | Value |
|---|---:|---:|
| Controller server | `controller_frequency` | 20.0 Hz |
| Controller plugin | `FollowPath` | `nav2_mppi_controller::MPPIController` |
| MPPI | `time_steps` | 56 |
| MPPI | `model_dt` | 0.05 |
| MPPI | `batch_size` | 2000 |
| MPPI | `vx_max` | 1.0 |
| MPPI | `vx_min` | -0.35 |
| MPPI | `vy_max` | 0.5 |
| MPPI | `wz_max` | 1.9 |
| MPPI | `iteration_count` | 1 |
| MPPI | `motion_model` | `DiffDrive` |
| Progress checker | `required_movement_radius` | 0.5 |
| Progress checker | `movement_time_allowance` | 10.0 s |
| Goal checker | `xy_goal_tolerance` | 0.25 |
| Goal checker | `yaw_goal_tolerance` | 0.25 |
| Planner plugin | `GridBased` | `nav2_navfn_planner::NavfnPlanner` |
| Planner tolerance | `tolerance` | 0.5 |
| Planner | `use_astar` | false |
| Planner | `allow_unknown` | true |

## C.5 Key Costmap Parameters

| Component | Parameter | Value |
|---|---:|---:|
| Local costmap | `update_frequency` | 5.0 Hz |
| Local costmap | `publish_frequency` | 2.0 Hz |
| Local costmap | `width`, `height` | 5 m, 5 m |
| Local costmap | `resolution` | 0.06 m |
| Local costmap | `rolling_window` | true |
| Local costmap | plugins | `voxel_layer`, `inflation_layer` |
| Local inflation | `cost_scaling_factor` | 4.0 |
| Local inflation | `inflation_radius` | 0.65 |
| Global costmap | `update_frequency` | 1.0 Hz |
| Global costmap | `publish_frequency` | 1.0 Hz |
| Global costmap | `width`, `height` | 40 m, 40 m |
| Global costmap | `resolution` | 0.06 m |
| Global costmap | `rolling_window` | false |
| Global costmap | plugins | `obstacle_layer`, `inflation_layer` |
| Global inflation | `cost_scaling_factor` | 4.0 |
| Global inflation | `inflation_radius` | 0.65 |
| LaserScan obstacle max range | `obstacle_max_range` | 2.5 m |
| LaserScan raytrace max range | `raytrace_max_range` | 3.0 m |

## C.6 Baseline Characterisation Runs

| Quantity | Value |
|---|---:|
| Total BARN worlds | 300 |
| Configurations tested | `original_clean`, `tuned_clean` |
| Total baseline-characterisation runs | 600 |
| Original configuration successes | 126 |
| Tuned configuration successes | 210 |
| Tune-dependent recovered worlds | 96 |

## C.7 Four-Category Environment Classification

Worlds were classified using navigation outcome and a 60 s completion-time margin relative to the 300 s timeout.

| Category | Operational definition | Count |
|---|---|---:|
| Class 1: stable success | Original and tuned configurations both succeeded, with sufficient tuned margin. | 102 |
| Class 2: tune-dependent recovered | Original configuration failed, but tuned configuration succeeded. | 96 |
| Class 3: marginal success | Tuned configuration succeeded but with less than 60 s margin to timeout. | 12 |
| Class 4: persistent hard | Tuned configuration did not succeed. | 90 |
| Total | All BARN worlds | 300 |

## C.8 Selected Formal Experiment Worlds

| Category | Selected worlds | Count |
|---|---|---:|
| Stable success | 240, 274, 94, 8 | 4 |
| Tune-dependent recovered | 86, 173, 76, 239 | 4 |
| Marginal success | 250 | 1 |
| Persistent hard | excluded | 0 |

## C.9 4:4:1 Allocation Calculation

Persistent-hard worlds were excluded, leaving 210 retained worlds.

| Category | Count | Proportion among retained worlds | Expected count in 9-world subset |
|---|---:|---:|---:|
| Stable success | 102 | 48.6% | 4.37 |
| Tune-dependent recovered | 96 | 45.7% | 4.11 |
| Marginal success | 12 | 5.7% | 0.51 |

This was converted into a practical allocation of 4 stable, 4 tune-dependent and 1 marginal world. The marginal category was retained rather than rounded to zero so that near-timeout successful navigation remained represented.

# Appendix D — Fault Screening and Fault Realism

## D.1 Scoring Rubric

Candidate faults were screened using two first-level criteria. The scores were qualitative engineering judgements used for selection, not probabilistic estimates of real-world fault frequency.

| Criterion | Meaning |
|---|---|
| Practical plausibility | Whether the fault has a defensible real-world manifestation in mobile robot operation. |
| Experimental suitability | Whether the fault can be implemented, repeated, observed and compared in the simulation campaign. |

Experimental suitability considered:

- Repeatability: the same fault can be applied consistently across worlds and repetitions.
- Controllability: fault start, duration, spatial extent or intensity can be set explicitly.
- Observability: effects can be measured through logged Nav2 and robot signals.
- Comparability: baseline and fault runs can be paired under the same world and navigation setup.
- Automation: the fault can be run repeatedly without manual intervention.
- Avoiding trivial catastrophic failure: the fault should not simply crash the system or make all runs fail immediately.

## D.2 Full Candidate Fault Ranking

| Priority | Fault candidate | Practical plausibility | Experimental suitability | Decision | Example real-world manifestation | Self-recovery likelihood |
|---:|---|---:|---:|---|---|---|
| 1 | Frontal LiDAR sector masking | 5 | 5 | Formal campaign | Dirt, water droplets, mud, tape, or foreign material obscuring part of the LiDAR cover. | Low if persistent contamination remains; medium if transient splash clears. |
| 2 | Intermittent LiDAR dropout | 4 | 5 | Formal campaign | Unstable sensor connection, communication interruptions, driver instability, or periodic packet loss. | Medium to high if communication recovers intermittently; low if hardware fault persists. |
| 3 | Odometry drift / encoder bias | 5 | 4 | Exploratory branch only | Wheel slip, encoder bias, poor wheel-ground contact, calibration error. | Medium if localisation feedback corrects drift; low under persistent slip/bias. |
| 4 | LiDAR range bias / inflation | 4 | 4 | Not implemented | Systematic measurement distortion, calibration issue, reflective or adverse sensing condition. | Low without recalibration or sensor adaptation. |
| 5 | Localisation jump / pose offset | 3 | 4 | Not implemented | Relocalisation error, map mismatch, pose-estimation discontinuity. | Medium if localisation re-converges; otherwise low. |
| 6 | Actuation degradation | 3 | 4 | Moved to recovery/reconfiguration discussion | Reduced drive response, wheel traction loss, conservative velocity scaling. | Medium if behaviour/controller adaptation can compensate. |
| 7 | TF interruption | 2 | 3 | Not implemented | Software timing or transform publication problem. | Medium if transient; low if transform chain remains broken. |
| 8 | Planner server stall / action timeout | 2 | 2 | Not implemented | Navigation software service stall or action timeout. | Medium if lifecycle recovery restarts component; otherwise low. |
| 9 | Random Nav2 node crash | 1 | 2 | Stress case only | Catastrophic software failure. | Low without process supervision/restart. |

## D.3 Selected-Fault Physical Interpretation

| Formal fault | Physical interpretation | Implemented experimental abstraction |
|---|---|---|
| Frontal LiDAR masking | Spatially localised sensor-cover contamination or occlusion, such as water, dirt, mud or a foreign object covering part of the sensor. | A continuous frontal 90° sector centred at 0° is replaced with non-informative maximum-range returns during the active fault window. |
| Intermittent LiDAR dropout | Temporal loss of LiDAR information due to unstable connection, communication interruption, sensor-driver instability or intermittent packet loss. | The same frontal 90° sector alternates between degraded and pass-through phases with a 1.0 s period and 50% duty cycle. |

The 90° sector width, 20 s fault duration and 50% dropout duty cycle are controlled experimental severity settings. They are not claimed to estimate real-world fault distributions. The literature motivation is that structured dropout, field-of-view reduction, and occlusion/masking are recognised LiDAR degradation forms; sensor-cover contamination such as dirt, dew, water and oil can affect LiDAR outputs; and LiDAR fault detection/recovery can be treated within broader FDIIR taxonomies.

# Appendix E — Fault Injection and Replication Details

## E.1 Topic Wiring

The formal scan fault injector operated at the LiDAR scan interface.

| Element | Topic / setting |
|---|---|
| Input scan | `/front/scan` |
| Faulted scan output | `/front/scan_faulted` |
| Fault-active signal | `/fault/scan_active` |
| Fault injector script | `jackal_helper/scripts/laser_scan_fault_injector.py` |
| Launch integration | `jackal_helper/launch/BARN_runner.launch.py` |

In fault-injected runs, the injector received `/front/scan`, modified the affected sector according to the configured fault model, and published `/front/scan_faulted` for downstream Nav2 consumption.

## E.2 Exact Fault Injector Parameters

| Parameter | Frontal masking | Intermittent dropout |
|---|---|---|
| `fault_mode` | `mask` | `dropout` |
| `fault_start_s` | 15.0 | 15.0 |
| `fault_duration_s` | 20.0 | 20.0 |
| `fault_center_deg` | 0.0 | 0.0 |
| `fault_width_deg` | 90.0 | 90.0 |
| `replacement_value` | `range_max` | `range_max` during degraded burst |
| `dropout_period_s` | not applicable | 1.0 |
| `dropout_duty_cycle` | not applicable | 0.5 |
| `fault_active_topic` | `/fault/scan_active` | `/fault/scan_active` |

Implementation detail: the injector sets affected beam ranges to `msg.range_max` when `replacement_value='range_max'`. During dropout, this replacement is applied only during the active part of each dropout cycle; outside that part of the cycle, scans pass through.

## E.3 Formal Campaign Replication

| Fault campaign | Worlds | Pairs per world | Conditions per pair | Runs per fault |
|---|---:|---:|---:|---:|
| Frontal LiDAR masking | 9 | 6 | baseline + fault | 108 |
| Intermittent LiDAR dropout | 9 | 6 | baseline + fault | 108 |
| Total | 9 | 6 | 2 faults × 2 conditions | 216 |

Each pair consisted of one nominal run and one fault-injected run in the same world. Condition order within a pair was randomised or balanced by the campaign script to reduce ordering effects.

## E.4 Sequential Pilot Stopping Criterion

The number of repetitions was selected using a pilot sequential paired design. For each pair, the completion-time difference was calculated as:

`d_i = T_fault,i - T_baseline,i`

After each replication stage, the 95% confidence interval half-width `h` for the paired differences was evaluated. The stopping rule was:

- stop if `h < 5 s`, or
- stop if `h < 0.25 × |mean(d)|`.

The 5 s threshold was treated as a practical precision target: it is 1.67% of the 300 s timeout and small relative to typical successful run times of approximately 150-250 s. The relative 25% rule prevented excessive repetition when the observed effect was larger.

Pilot repeat studies showed that six pairs provided an acceptable balance between paired-effect stability and computational cost. Six pairs per world were therefore fixed for both formal campaigns to keep the design consistent across faults and environments.

# Appendix F — Statistical Diagnostics

## F.1 Primary and Sensitivity Analysis

Primary completion-time analysis used matched-success pairs. All-pair/capped analysis used the 300 s campaign cap for non-successful runs and was treated as sensitivity analysis.

| Fault | Analysis | n pairs | Mean paired difference | 95% interval | Interpretation |
|---|---|---:|---:|---|---|
| Frontal masking | matched-success primary | 47 | +5.97 s | [3.36, 8.46] s | Positive slowdown. |
| LiDAR dropout | matched-success primary | 40 | +4.77 s | [2.11, 7.03] s | Positive slowdown. |
| Frontal masking | all-pair capped sensitivity | 54 | +9.21 s | [1.27, 20.14] s | Positive direction with wider uncertainty. |
| LiDAR dropout | all-pair capped sensitivity | 54 | +6.43 s | [-0.58, 15.72] s | Positive direction but interval includes zero. |

## F.2 Bootstrap Implementation

Uncertainty for descriptive paired effects was estimated using cluster bootstrap resampling. Resampling respected world-level grouping so that repeated pairs from the same world were not treated as fully independent observations from unrelated environments.

## F.3 Bayesian Model Specification

A robust hierarchical Student-t model was fitted to matched-success paired completion-time differences. Effects were oriented so that positive values mean fault-induced degradation.

Simplified model:

`d_ij ~ StudentT(nu, mu_i, sigma)`

`mu_i = mu + u_i`

where `mu` is the global fault effect and `u_i` is the world-specific deviation. The Student-t likelihood was used to reduce sensitivity to unusually large pair effects. The practical threshold for meaningful degradation was 5 s.

## F.4 Sampling Diagnostics

| Fault | Chains | Draws per chain | Posterior draws | Divergences | Max treedepth hits | Mean acceptance rate | Min BFMI | Sampling OK |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Frontal masking | 4 | 1000 | 4000 | 0 | 0 | 0.950 | 0.728 | True |
| LiDAR dropout | 4 | 1000 | 4000 | 0 | 0 | 0.947 | 0.584 | True |

## F.5 Global Bayesian Effects

| Fault | n worlds | n pairs | Posterior median | 95% CrI | P(effect > 0) | P(effect > 5 s) | tau median | sigma median | R-hat(mu) | ESS(mu) |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| Frontal masking | 9 | 47 | 6.25 s | [3.73, 8.83] s | 1.000 | 0.843 | 1.30 | 6.58 | 1.000 | 2601 |
| LiDAR dropout | 9 | 40 | 4.54 s | [1.63, 7.27] s | 0.998 | 0.342 | 2.10 | 5.17 | 1.002 | 1498 |

## F.6 Posterior Predictive Checks

| Fault | Observed mean | PPC mean median | PPC mean 95% interval | Pointwise 95% PPC coverage |
|---|---:|---:|---|---:|
| Frontal masking | 5.97 s | 6.21 s | [3.26, 9.05] s | 0.957 |
| LiDAR dropout | 4.77 s | 4.69 s | [2.25, 7.16] s | 0.975 |

## F.7 World-Level Bayesian Numerical Table

| Fault | World | n pairs | Observed world mean degradation | Posterior median | 95% CrI | P(effect > 0) | P(effect > 5 s) |
|---|---:|---:|---:|---:|---|---:|---:|
| Masking | 8 | 6 | 6.81 | 6.28 | [3.16, 9.65] | 1.000 | 0.810 |
| Masking | 76 | 6 | 5.16 | 6.15 | [2.59, 9.27] | 0.999 | 0.772 |
| Masking | 86 | 6 | 8.15 | 6.66 | [3.53, 10.75] | 1.000 | 0.858 |
| Masking | 94 | 6 | 1.01 | 5.35 | [0.23, 8.38] | 0.978 | 0.577 |
| Masking | 173 | 5 | 6.80 | 6.49 | [3.15, 10.85] | 0.999 | 0.834 |
| Masking | 239 | 1 | 11.54 | 6.48 | [2.51, 11.78] | 0.996 | 0.808 |
| Masking | 240 | 6 | 3.94 | 5.82 | [1.94, 8.79] | 0.997 | 0.693 |
| Masking | 250 | 5 | 7.84 | 6.48 | [3.26, 10.27] | 1.000 | 0.848 |
| Masking | 274 | 6 | 7.57 | 6.48 | [3.33, 10.05] | 0.999 | 0.833 |
| Dropout | 8 | 5 | 5.31 | 4.91 | [1.59, 8.52] | 0.996 | 0.476 |
| Dropout | 76 | 5 | 3.66 | 4.32 | [0.59, 7.46] | 0.986 | 0.308 |
| Dropout | 86 | 6 | 3.72 | 4.27 | [0.76, 7.36] | 0.991 | 0.319 |
| Dropout | 94 | 6 | 8.19 | 5.69 | [2.65, 10.07] | 0.999 | 0.659 |
| Dropout | 173 | 2 | 0.60 | 4.01 | [-2.14, 8.13] | 0.920 | 0.292 |
| Dropout | 239 | 1 | 10.55 | 5.32 | [0.94, 12.26] | 0.988 | 0.566 |
| Dropout | 240 | 6 | 6.47 | 5.29 | [2.31, 8.89] | 0.999 | 0.576 |
| Dropout | 250 | 3 | -4.06 | 2.22 | [-5.04, 6.16] | 0.710 | 0.117 |
| Dropout | 274 | 6 | 6.00 | 5.13 | [2.12, 8.75] | 0.998 | 0.542 |

# Appendix G — Propagation and Recovery Supporting Evidence

## G.1 Typical and Extreme Case Selection

![Typical and extreme case selection scatter](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/03_figures_for_dissertation/thesis_figures_v4/png/fig_06_case_selection.png)

## G.2 Representative Direct Propagation Traces

![World 8 frontal masking direct propagation trace](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/06_direct_propagation_tracing/w8_masking_timeline.png)

![World 240 LiDAR dropout direct propagation trace](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/06_direct_propagation_tracing/w240_dropout_timeline.png)

Topic coverage for the direct traces:

| Trace | `/cmd_vel` | `/fault/scan_active` | `/front/scan_faulted` | `/global_costmap/costmap` | `/local_costmap/costmap` | `/plan` | `/platform/odom/filtered` |
|---|---:|---:|---:|---:|---:|---:|---:|
| W8 masking | 1826 | 737 | 737 | 15 | 32 | 90 | 909 |
| W240 dropout | 1939 | 665 | 665 | 15 | 30 | 95 | 819 |

## G.3 Preliminary Scan-Only Classifier False-Alarm Boundary

A preliminary scan-only detector was tested using scan summary features such as maximum-range ratio and scan-span ratio. Although injected masking and dropout episodes produced changes in these features, similar values could also occur during nominal navigation in open or sparse geometry. Therefore, scan-only autonomous fault-presence detection was excluded from the final scope.

The final design assumed a controlled fault-presence signal (`/fault/scan_active`) and used a short observation window only to identify the fault type.

![Stage 1 scan signature diagnostics for W8](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/05_classifier_evidence/stage1_signature_diagnostics_dev/world_008_scan_signature_timeseries.png)

## G.4 Conditional Classifier Evidence

| Validation stage | Evidence mode | Observation window | Episodes | Correct | Wrong type | Unknown | Mean identification latency |
|---|---|---:|---:|---:|---:|---:|---:|
| Development | online | 2.0 s | 6 | 6 | 0 | 0 | 2.0 s |
| Held-out final-logic revalidation | online | 2.0 s | 4 | 4 | 0 | 0 | 2.0 s |

Claim boundary: this is not a general autonomous fault detector. It is a conditional episode-level fault-type classifier operating after controlled fault-presence indication.

## G.5 Closed-Loop Integration Evidence

| World | Fault | Timing | Predicted type | Selected policy | Outcome | Completion time | Interpretation |
|---:|---|---|---|---|---|---:|---|
| 8 | masking | start 5 s, duration 20 s | MASKING | masking Nav2 recovery | succeeded | 97.9390 s | Both classification and policy routing branch executed. |
| 8 | dropout | start 5 s, duration 20 s | DROPOUT | dropout scan filter | succeeded | 101.9310 s | Both classification and policy routing branch executed. |
| 240 | dropout | start 5 s, duration 20 s | DROPOUT | dropout scan filter | succeeded | 283.7023 s | Routing worked but task nearly reached timeout. |
| 240 | masking | start 5 s, duration 20 s | MASKING | masking Nav2 recovery | collided | 45.6221 s | Correct routing did not guarantee safe task recovery. |
| 240 | dropout | start 15 s, duration 20 s | no final decision | no policy enabled | succeeded | 99.0186 s | Formal timing was navigable but classifier evidence was ambiguous. |
| 240 | masking | start 15 s, duration 20 s | no final decision | no policy enabled | succeeded | 112.6154 s | Formal timing was navigable but did not produce a complete selector-policy decision. |

## G.6 Dropout Recovery OFF/ON Layer Trace

![Dropout recovery OFF/ON layer comparison](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/10_recovery_layer_trace_w8_dropout/w8_dropout_recovery_off_on_layer_bars.png)

| Metric | Recovery OFF | Recovery ON | ON - OFF |
|---|---:|---:|---:|
| Mission outcome | succeeded | succeeded | — |
| Completion time | 84.9901 s | 93.0634 s | +8.0733 s |
| Scan range-max ratio | 0.8320 | 0.4593 | -0.3727 |
| Scan span ratio | 0.8139 | 0.4302 | -0.3838 |
| Local occupied ratio | 0.2081 | 0.2044 | -0.0037 |
| Local lethal ratio | 0.1408 | 0.1379 | -0.0028 |
| Commanded linear x | 0.6720 | 0.6720 | -0.0000 |
| Odom speed | 0.6750 | 0.6756 | +0.0007 |

![Dropout recovery OFF timeline](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/10_recovery_layer_trace_w8_dropout/analysis/w8_dropout_recovery_off_timeline.png)

![Dropout recovery ON timeline](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/10_recovery_layer_trace_w8_dropout/analysis/w8_dropout_recovery_on_timeline.png)

Interpretation: the dropout scan filter produced a clear scan-layer effect, but this single targeted trace did not demonstrate mission-level improvement.

## G.7 Masking Recovery OFF/ON Layer Trace

![Masking recovery OFF/ON layer comparison](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/11_recovery_layer_trace_w8_masking/w8_masking_recovery_off_on_layer_bars.png)

| Metric | Recovery OFF | Recovery ON | ON - OFF |
|---|---:|---:|---:|
| Mission outcome | succeeded | succeeded | — |
| Completion time | 86.0834 s | 112.2875 s | +26.2041 s |
| Scan range-max ratio | 1.0000 | 1.0000 | 0.0000 |
| Scan span ratio | 1.0000 | 1.0000 | 0.0000 |
| Local occupied ratio | 0.0593 | 0.0696 | +0.0103 |
| Local lethal ratio | 0.0393 | 0.0441 | +0.0047 |
| Commanded linear x | 0.6111 | 0.3802 | -0.2309 |
| Commanded angular z | -0.0053 | -0.0530 | -0.0477 |
| Odom speed | 0.6218 | 0.3932 | -0.2287 |

![Masking recovery OFF timeline](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/11_recovery_layer_trace_w8_masking/analysis/w8_masking_recovery_off_timeline.png)

![Masking recovery ON timeline](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/11_recovery_layer_trace_w8_masking/analysis/w8_masking_recovery_on_timeline.png)

Interpretation: the masking recovery intervention was visible at the behaviour/action layer, but it did not repair the scan stream or improve mission-level completion time in this representative trace.

## G.8 Persistent-Fault Sensitivity Evidence

Persistent fault runs were treated as stress/sensitivity evidence rather than as replacements for the formal 20 s transient campaign. The persistent tests asked what happens when the fault does not disappear by itself. These runs were useful for recovery design discussion, but the formal campaign conclusions are based on the fixed 15-35 s transient fault window.

