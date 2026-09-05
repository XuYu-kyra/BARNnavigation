# Appendix A — Project Outline

This appendix should contain the submitted project outline as an unaltered administrative document.

| Item | Source file |
|---|---|
| Project outline | `/home/student24/Downloads/project outline3.0.docx` |

Final-dissertation assembly note: insert the submitted project-outline document here in its original form. It should not be rewritten as part of the experimental evidence appendix, because it is a school-required administrative record rather than a generated research result.

# Appendix B — Risk Assessment

This appendix should contain the submitted risk assessment as an unaltered administrative document.

| Item | Source file |
|---|---|
| Risk assessment | `/home/student24/Downloads/YuXu_RA 1.pdf` |

Final-dissertation assembly note: insert the submitted risk assessment here in its original form. The project was simulation-only and did not involve physical robot testing, hazardous materials, electrical modification or workshop activity.

# Appendix C — Experimental Configuration and Environment Selection

## C.1 Software and Simulation Platform

| Item | Configuration used |
|---|---|
| ROS version | ROS 2 Jazzy |
| Navigation stack | Nav2 |
| Robot platform | Simulated Clearpath Jackal |
| Simulator | Gazebo |
| Benchmark environments | BARN ROS 2 navigation benchmark |
| Total available BARN worlds | 300 |
| Original comparison setup | `original_clean` |
| Formal experiment setup | `tuned_clean` |
| Global planner | `nav2_navfn_planner::NavfnPlanner` |
| Local controller | `nav2_mppi_controller::MPPIController` |
| Global frame | `odom` |
| Robot base frame | `base_link` |
| Odometry topic | `/platform/odom/filtered` |
| Formal run timeout | 300 s |

The formal campaigns used the same `tuned_clean` navigation configuration for both baseline and fault-injected runs. This kept the navigation stack fixed while only the injected fault condition changed.

## C.2 Purpose of `tuned_clean`

The `tuned_clean` configuration was used as an experimental control condition, not as a claimed contribution in navigation tuning. The original BARN ROS 2 setup produced a large number of nominal failures. If those nominal failures were left unresolved, later fault effects would be confounded with baseline instability.

The role of `tuned_clean` was therefore to make nominal navigation sufficiently stable before fault injection. This allowed the fault campaigns to compare paired baseline and fault runs under a cleaner baseline condition.

## C.3 Original to `tuned_clean` Changes

Only `nav2.yaml` differed between `original_clean` and `tuned_clean` in the local configuration diff.

| Nav2 component | Parameter | Original value | Tuned value | Intended role |
|---|---:|---:|---:|---|
| MPPI controller | `FollowPath.vx_max` | 0.5 | 1.0 | Increased allowed forward speed to reduce overly slow nominal navigation. |
| MPPI `PathAlignCritic` | `cost_weight` | 14.0 | 10.0 | Reduced strict path-alignment pressure. |
| MPPI `PathFollowCritic` | `cost_weight` | 5.0 | 7.0 | Increased incentive to follow the reference path. |
| Local costmap inflation layer | `inflation_radius` | 0.8 | 0.65 | Reduced local obstacle-inflation conservatism. |
| Global costmap inflation layer | `inflation_radius` | 0.8 | 0.65 | Reduced global obstacle-inflation conservatism. |

## C.4 Key Fixed Nav2 Parameters

This table records the main fixed parameters needed to understand and reproduce the experiments. It intentionally lists the parameters that define the planner/controller and sensing-costmap interface, rather than every default parameter in the Nav2 configuration file.

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
| Progress checker | `required_movement_radius` | 0.5 m |
| Progress checker | `movement_time_allowance` | 10.0 s |
| Goal checker | `xy_goal_tolerance` | 0.25 m |
| Goal checker | `yaw_goal_tolerance` | 0.25 rad |
| Planner plugin | `GridBased` | `nav2_navfn_planner::NavfnPlanner` |
| Planner tolerance | `tolerance` | 0.5 m |
| Planner | `use_astar` | false |
| Planner | `allow_unknown` | true |

## C.5 Key Costmap and Scan Parameters

| Component | Parameter | Value |
|---|---:|---:|
| Local costmap | `update_frequency` | 5.0 Hz |
| Local costmap | `publish_frequency` | 2.0 Hz |
| Local costmap | `width`, `height` | 5 m, 5 m |
| Local costmap | `resolution` | 0.06 m |
| Local costmap | `rolling_window` | true |
| Local costmap plugins | plugins | `voxel_layer`, `inflation_layer` |
| Local inflation layer | `cost_scaling_factor` | 4.0 |
| Local inflation layer | `inflation_radius` | 0.65 m |
| Global costmap | `update_frequency` | 1.0 Hz |
| Global costmap | `publish_frequency` | 1.0 Hz |
| Global costmap | `width`, `height` | 40 m, 40 m |
| Global costmap | `resolution` | 0.06 m |
| Global costmap | `rolling_window` | false |
| Global costmap plugins | plugins | `obstacle_layer`, `inflation_layer` |
| Global inflation layer | `cost_scaling_factor` | 4.0 |
| Global inflation layer | `inflation_radius` | 0.65 m |
| LaserScan obstacle max range | `obstacle_max_range` | 2.5 m |
| LaserScan raytrace max range | `raytrace_max_range` | 3.0 m |

## C.6 Baseline Characterisation Runs

Before formal fault injection, all 300 BARN worlds were evaluated under both the original and tuned configurations.

| Quantity | Value |
|---|---:|
| Total BARN worlds | 300 |
| Configurations tested | `original_clean`, `tuned_clean` |
| Total baseline-characterisation runs | 600 |
| Original configuration successes | 126 |
| Tuned configuration successes | 210 |
| Tune-dependent recovered worlds | 96 |

## C.7 Four-Category Operational Definitions

Worlds were classified using navigation outcome and a 60 s completion-time margin relative to the 300 s timeout.

| Category | Operational definition | Count |
|---|---|---:|
| Stable success | Original and tuned configurations both succeeded, with sufficient tuned margin. | 102 |
| Tune-dependent recovered | Original configuration failed, but tuned configuration succeeded. | 96 |
| Marginal success | Tuned configuration succeeded but with less than 60 s margin to timeout. | 12 |
| Persistent hard | Tuned configuration did not succeed. | 90 |
| Total | All BARN worlds | 300 |

## C.8 Selected Formal Experiment Worlds

| Category | Selected worlds | Count |
|---|---|---:|
| Stable success | 240, 274, 94, 8 | 4 |
| Tune-dependent recovered | 86, 173, 76, 239 | 4 |
| Marginal success | 250 | 1 |
| Persistent hard | excluded | 0 |

## C.9 4:4:1 Allocation Calculation

Persistent-hard worlds were excluded from formal campaigns because the objective was to measure fault-induced degradation under navigable baseline conditions, not to evaluate worlds that already failed under the tuned nominal setup. This left 210 retained worlds.

| Category | Count | Proportion among retained worlds | Expected count in 9-world subset |
|---|---:|---:|---:|
| Stable success | 102 | 48.6% | 4.37 |
| Tune-dependent recovered | 96 | 45.7% | 4.11 |
| Marginal success | 12 | 5.7% | 0.51 |

The expected 9-world allocation was rounded into a practical 4:4:1 design: four stable worlds, four tune-dependent worlds and one marginal world. The marginal category was retained rather than rounded to zero so that near-timeout successful navigation remained represented.

# Appendix D — Fault Screening and Fault Realism

## D.1 Scoring Rubric

Candidate faults were screened using two first-level criteria. The scores were qualitative engineering judgements used for selection, not estimates of real-world occurrence probability.

| Criterion | Meaning |
|---|---|
| Practical plausibility | Whether the fault has a defensible real-world manifestation in mobile robot operation. |
| Experimental suitability | Whether the fault can be implemented, repeated, observed and compared in the simulation campaign. |

Experimental suitability included the following practical considerations:

- Repeatability: the same fault can be applied consistently across worlds and repetitions.
- Controllability: fault start, duration, spatial extent or intensity can be set explicitly.
- Observability: effects can be measured through logged Nav2 and robot signals.
- Comparability: baseline and fault runs can be paired under the same world and navigation setup.
- Automation: the fault can be run repeatedly without manual intervention.
- Avoiding trivial catastrophic failure: the fault should not simply crash the system or make all runs fail immediately.

## D.2 Full Candidate Fault Ranking

This table records the complete candidate set considered during fault selection, not only the faults that were eventually used in formal campaigns.

| Priority | Fault candidate | Practical plausibility | Experimental suitability | Decision |
|---:|---|---:|---:|---|
| 1 | Frontal LiDAR sector masking | 5 | 5 | Formal campaign |
| 2 | Intermittent LiDAR dropout | 4 | 5 | Formal campaign |
| 3 | Odometry drift / encoder bias | 5 | 4 | Exploratory branch only |
| 4 | LiDAR range bias / inflation | 4 | 4 | Not implemented |
| 5 | Localisation jump / pose offset | 3 | 4 | Not implemented |
| 6 | Actuation degradation | 3 | 4 | Moved to recovery/reconfiguration discussion |
| 7 | TF interruption | 2 | 3 | Not implemented |
| 8 | Planner server stall / action timeout | 2 | 2 | Not implemented |
| 9 | Random Nav2 node crash | 1 | 2 | Stress case only |

## D.3 Selected-Fault Physical Interpretation

| Formal fault | Real-world manifestation | Experimental abstraction | Literature support |
|---|---|---|---|
| Frontal LiDAR sector masking | Dirt, water droplets, mud, tape, or other foreign material obscuring part of the sensor cover. | Continuous frontal 90 degree sector replacement with maximum-range returns during the active fault window. | Sensor-cover contamination has been experimentally shown to affect LiDAR outputs \cite{schlager2022contaminations}; occlusion masking and field-of-view reduction are recognised structured LiDAR degradation modes \cite{felix2026lidardegradation}; LiDAR fault handling fits the broader FDIIR context \cite{goelles2020fdiir}. |
| Structured intermittent sector-level LiDAR information loss | Intermittent loss of usable LiDAR information due to unstable connection, communication interruption, sensor-driver instability or packet loss affecting part of the scan stream. | Frontal 90 degree sector periodically replaced by `range_max` with a 1.0 s period and 50% duty cycle. This is not whole-topic packet loss; the rest of the scan remains available. | Structured dropout is a recognised LiDAR degradation mode \cite{felix2026lidardegradation}; LiDAR fault detection and recovery are discussed in FDIIR and mobile-robot fault-tolerance contexts \cite{goelles2020fdiir,elsayed2024lidarfaults}. |

The 90 degree sector width, 20 s duration and 50% duty cycle are controlled experimental severity settings. They are not claimed to estimate real-world fault distributions. The purpose of these settings was to create repeatable and observable spatial and temporal LiDAR degradations for controlled Nav2 fault-propagation experiments.

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
| Total formal fault campaigns | 9 | 6 | 2 faults x 2 conditions | 216 |

Each pair consisted of one nominal run and one fault-injected run in the same world. Condition order within a pair was randomised by the campaign script to reduce ordering effects.

## E.4 Sequential Pilot Stopping Criterion

The number of repetitions was selected using a pilot sequential paired design. For each pair, the completion-time difference was calculated as:

`d_i = T_fault,i - T_baseline,i`

After each replication stage, the 95% confidence interval half-width `h` for the paired differences was evaluated. The stopping rule was:

- stop if `h < 5 s`, or
- stop if `h < 0.25 x |mean(d)|`.

The 5 s threshold was treated as a practical precision target: it is 1.67% of the 300 s timeout and small relative to typical successful run times of approximately 150-250 s. The relative 25% rule prevented excessive repetition when the observed effect was larger.

Pilot repeat studies showed that six pairs provided an acceptable balance between paired-effect stability and computational cost. For example, the W8 frontal masking pilot reached `mean_d = 4.827 s` with `ci95_halfwidth = 2.391 s` after six pairs, satisfying the absolute precision rule. Six pairs per world were therefore fixed for both formal campaigns to keep the design consistent across faults and environments.

# Appendix F — Statistical Diagnostics

## F.1 Primary and Sensitivity Analysis

Primary completion-time analysis used matched-success pairs. All-pair/capped analysis used the 300 s campaign cap for non-successful runs and was treated as sensitivity analysis.

| Fault | Analysis | n pairs | Mean paired difference | 95% interval | Interpretation |
|---|---|---:|---:|---|---|
| Frontal masking | matched-success primary | 47 | +5.97 s | [3.36, 8.46] s | Positive slowdown. |
| LiDAR dropout | matched-success primary | 40 | +4.77 s | [2.11, 7.03] s | Positive slowdown. |
| Frontal masking | all-pair capped sensitivity | 54 | +9.21 s | [1.27, 20.14] s | Positive direction with wider uncertainty. |
| LiDAR dropout | all-pair capped sensitivity | 54 | +6.43 s | [-0.58, 15.72] s | Positive direction but interval includes zero. |

The matched-success analysis is the primary analysis because it estimates degradation among runs where both baseline and fault conditions completed the task. The all-pair/capped analysis is retained to show sensitivity to unsuccessful or timeout-adjacent behaviour.

## F.2 Bootstrap Implementation

Uncertainty for descriptive paired effects was estimated using cluster bootstrap resampling. Resampling respected world-level grouping so that repeated pairs from the same world were not treated as fully independent observations from unrelated environments.

## F.3 Bayesian Model Specification

A robust hierarchical Student-t model was fitted to matched-success paired completion-time differences. Effects were oriented so that positive values mean fault-induced degradation.

```text
y_ij ~ StudentT(nu, theta_j, sigma)
theta_j = mu + tau * theta_offset_j
theta_offset_j ~ Normal(0, 1)
mu ~ Normal(0, 10 * prior_scale)
tau ~ HalfNormal(5 * prior_scale)
sigma ~ HalfNormal(5 * prior_scale)
nu_minus_two ~ Exponential(1 / 30)
nu = nu_minus_two + 2
```

`prior_scale` was computed separately for each fault and metric in the PyMC script as:

```text
prior_scale = max(sample_sd(y), abs(mean(y)), meaningful_threshold, 1e-3)
```

For the primary completion-time models, the meaningful threshold was 5 s. This gave `prior_scale = 6.981 s` for frontal masking and `prior_scale = 5.698 s` for structured intermittent sector-level dropout. Therefore, the corresponding prior standard deviations were 69.81 s and 56.98 s for `mu`, and 34.91 s and 28.49 s for `tau` and `sigma`. These priors are deliberately weakly regularising relative to the observed paired differences.

`mu` is the global slowdown effect. `theta_j` is the world-specific slowdown effect. `tau` is the between-world heterogeneity scale. `sigma` is within-world residual variation. The Student-t likelihood was used because Gazebo/Nav2 experiments can produce occasional long-tail timing outliers; this reduces sensitivity compared with a Normal likelihood.

The practical threshold for meaningful degradation was 5 s, matching the replication stopping criterion and the smallest slowdown treated as operationally meaningful in the analysis.

## F.4 Sampling Diagnostics

| Fault | Chains | Draws per chain | Posterior draws | Divergences | Max treedepth hits | Mean acceptance rate | Min BFMI | Sampling OK |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Frontal masking | 4 | 1000 | 4000 | 0 | 0 | 0.950 | 0.728 | True |
| LiDAR dropout | 4 | 1000 | 4000 | 0 | 0 | 0.947 | 0.584 | True |

R-hat and effective sample size diagnostics for key parameters met the reporting thresholds of R-hat <= 1.01 and ESS >= 400.

## F.5 Global Bayesian Effects

| Fault | n worlds | n pairs | Posterior median | 95% CrI | P(effect > 0) | P(effect > 5 s) | tau median | sigma median | R-hat(mu) | ESS(mu) |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| Frontal masking | 9 | 47 | 6.25 s | [3.73, 8.83] s | 1.000 | 0.843 | 1.30 | 6.58 | 1.000 | 2601 |
| LiDAR dropout | 9 | 40 | 4.54 s | [1.63, 7.27] s | 0.998 | 0.342 | 2.10 | 5.17 | 1.002 | 1498 |

The posterior probability that slowdown is greater than zero was high for both faults. The probability of exceeding the 5 s practical threshold was higher for masking than dropout, indicating stronger practical evidence for masking under the selected fault settings.

## F.6 Posterior Predictive Checks

| Fault | Observed mean | PPC mean median | PPC mean 95% interval | Pointwise 95% PPC coverage |
|---|---:|---:|---|---:|
| Frontal masking | 5.97 s | 6.21 s | [3.26, 9.05] s | 0.957 |
| LiDAR dropout | 4.77 s | 4.69 s | [2.25, 7.16] s | 0.975 |

Posterior predictive checks compared observed paired slowdowns with simulated replicated datasets from the fitted model. The checks indicated that the model reproduced the observed mean slowdown adequately for both faults.

## F.7 World-Level Bayesian Numerical Table

Use landscape layout in the final dissertation document if this table is retained in full.

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

This appendix summarises supporting evidence for propagation tracing, conditional classifier validation and exploratory recovery. Full raw logs, bags, CSVs and figures are retained in the evidence directory; only the highest-value evidence is summarised here.

## G.1 Typical and Extreme Case Selection Summary

![Typical and extreme case selection summary](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/03_figures_for_dissertation/thesis_figures_v4/png/fig_06_case_selection.png)

The case-selection summary identifies representative cases used for targeted propagation tracing. W8 masking and W240 dropout were retained as characteristic cases for layer-by-layer interpretation, while more extreme cases were kept for sensitivity discussion rather than primary mechanism claims.

## G.2 Representative Direct Propagation Traces

The direct traces were targeted figure-evidence runs rather than additional campaign repetitions. They align the fault-active signal with scan degradation proxies, costmap occupancy, commanded velocity, odometry speed and planner-update count.

![World 8 frontal masking direct propagation trace](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/06_direct_propagation_tracing/w8_masking_timeline.png)

![World 240 structured intermittent sector-level dropout direct propagation trace](/home/student24/dissertation/barn_ros2/dissertation_evidence_index/06_direct_propagation_tracing/w240_dropout_timeline.png)

## G.3 Conditional Fault-Type Identification Evidence

The initial scan-only detector was not retained because normal environment geometry could produce false alarms in open or sparse scenes. The final classifier therefore used a controlled fault-presence signal and a 2 s scan-signature observation window to identify the fault type.

| Validation stage | Evidence mode | Observation window | Episodes | Correct | Wrong type | Unknown | Mean latency |
|---|---|---:|---:|---:|---:|---:|---:|
| Development | online | 2.0 s | 6 | 6 | 0 | 0 | 2.0 s |
| Held-out final-logic revalidation | online | 2.0 s | 4 | 4 | 0 | 0 | 2.0 s |

Claim boundary: this is a conditional episode-level fault-type classifier after controlled fault-presence indication, not a general autonomous detector of unknown real-world faults.

## G.4 Closed-Loop Integration Evidence

### G.4a Primary W8 Integration Smoke Test

The W8 integration smoke test checked whether the implemented system could route both LiDAR fault types through the full software chain:

`controlled fault-presence trigger -> 2 s classifier -> policy selector -> fault-aware policy`

| World | Fault | Timing | Predicted type | Selected policy | Outcome | Completion time |
|---:|---|---|---|---|---|---:|
| 8 | masking | start 5 s, duration 20 s | MASKING | masking Nav2 recovery | succeeded | 97.9390 s |
| 8 | structured intermittent sector-level dropout | start 5 s, duration 20 s | DROPOUT | dropout scan filter | succeeded | 101.9310 s |

This supports the limited claim that both selector branches were exercised end-to-end. It does not establish cross-world recovery effectiveness.

### G.4b Supporting W240 Sanity and Stress Observations

| World | Fault | Timing | Predicted type | Selected policy | Outcome | Completion time | Use in dissertation |
|---:|---|---|---|---|---|---:|---|
| 240 | structured intermittent sector-level dropout | start 5 s, duration 20 s | DROPOUT | dropout scan filter | succeeded | 283.7023 s | Stress observation: routing worked but mission was close to timeout. |
| 240 | masking | start 5 s, duration 20 s | MASKING | masking Nav2 recovery | collided | 45.6221 s | Stress observation: correct routing did not guarantee safe recovery. |
| 240 | structured intermittent sector-level dropout | start 15 s, duration 20 s | no final decision | no policy enabled | succeeded | 99.0186 s | Sanity check: formal timing remained navigable. |
| 240 | masking | start 15 s, duration 20 s | no final decision | no policy enabled | succeeded | 112.6154 s | Sanity check: formal timing remained navigable. |

These W240 runs are supporting observations only. They should not be reported as part of the primary closed-loop validation claim.

## G.5 Recovery Layer Evidence Summary

| Fault | Intended recovery layer | Main layer-level observation | Mission-level result | Claim boundary |
|---|---|---|---|---|
| Masking | Behaviour/action layer | Scan degradation remained unchanged (`range_max` ratio 1.000 -> 1.000), while command and odometry behaviour changed. | Completion time increased from 86.0834 s to 112.2875 s. | Behavioural intervention was visible, but mission-level improvement was not demonstrated. |
| Structured intermittent sector-level dropout | Scan layer | Scan `range_max` ratio decreased from 0.8320 to 0.4593 and scan-span ratio decreased from 0.8139 to 0.4302. | Completion time increased from 84.9901 s to 93.0634 s. | Scan-layer correction was visible, but mission-level improvement was not demonstrated. |

The recovery results should therefore be interpreted as exploratory layer-level evidence. They show that the interventions affected the intended layer, but they do not support a claim of improved navigation performance.

## G.6 Persistent-Fault Sensitivity Evidence

Persistent-fault runs were treated as stress/sensitivity evidence rather than replacements for the formal 20 s transient campaign. They informed recovery design, but formal fault-effect conclusions remain based on the fixed 15-35 s transient fault window.

| Test | Fault | Recovery | Pairs / runs | Outcome summary | Interpretation |
|---|---|---|---:|---|---|
| W8 masking persistent no-recovery smoke | Masking | off | 1 run | succeeded, 79.2973 s | Persistent masking was not automatically catastrophic in W8. |
| W240 structured intermittent sector-level dropout persistent no-recovery retry | Dropout | off | 1 run | succeeded, 85.2632 s | Persistent dropout remained navigable in this retry. |
| W240 persistent dropout paired characterisation | Dropout | off | 6 pairs | all baseline and fault runs succeeded | Persistent dropout produced measurable but non-catastrophic behaviour in W240. |

