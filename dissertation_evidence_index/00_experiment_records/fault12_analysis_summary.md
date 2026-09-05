# Tonight Fault Analysis Summary

## Main Paired Effects

| Fault | Metric | n pairs | Mean diff | Median diff | Bootstrap 95% CI | Degradation pairs |
|---|---|---:|---:|---:|---|---:|
| frontal_masking | Completion time (s) | 54 | 9.210 | 6.048 | [1.267, 20.141] | 43/54 |
| frontal_masking | Actual path length (m) | 54 | 0.205 | 0.020 | [-0.002, 0.546] | 34/54 |
| frontal_masking | Whole-run stop ratio | 54 | 0.049 | 0.042 | [0.029, 0.070] | 32/54 |
| frontal_masking | Controller new-path count | 54 | 9.315 | 6.500 | [3.463, 18.575] | 44/54 |
| lidar_dropout | Completion time (s) | 54 | 6.431 | 3.706 | [-0.576, 15.722] | 42/54 |
| lidar_dropout | Actual path length (m) | 54 | 0.126 | 0.011 | [-0.052, 0.425] | 29/54 |
| lidar_dropout | Whole-run stop ratio | 54 | 0.026 | 0.000 | [-0.002, 0.062] | 22/54 |
| lidar_dropout | Controller new-path count | 54 | 5.685 | 4.000 | [-0.908, 14.185] | 40/54 |

## World Susceptibility: strongest completion slowdown

| Fault | World | Class | Completion slowdown (s) | Stop-ratio delta | Controller path delta |
|---|---:|---|---:|---:|---:|
| frontal_masking | 173 | class2_tune_dependent_recovered | 44.946 | 0.000 | 43.833 |
| frontal_masking | 86 | class2_tune_dependent_recovered | 8.146 | 0.128 | 7.500 |
| frontal_masking | 274 | class1_stable_success | 7.568 | 0.060 | 7.167 |
| frontal_masking | 8 | class1_stable_success | 6.809 | 0.035 | 6.667 |
| frontal_masking | 76 | class2_tune_dependent_recovered | 5.158 | 0.110 | 5.167 |
| lidar_dropout | 76 | class2_tune_dependent_recovered | 35.604 | 0.132 | 34.833 |
| lidar_dropout | 239 | class2_tune_dependent_recovered | 10.725 | -0.043 | 4.000 |
| lidar_dropout | 94 | class1_stable_success | 8.193 | 0.012 | 7.833 |
| lidar_dropout | 240 | class1_stable_success | 6.472 | 0.051 | 6.500 |
| lidar_dropout | 274 | class1_stable_success | 6.000 | 0.062 | 6.500 |

## Mission Reliability Transitions

| Fault | Baseline status | Fault status | Pair count |
|---|---|---|---:|
| frontal_masking | collided | succeeded | 1 |
| frontal_masking | succeeded | succeeded | 47 |
| frontal_masking | succeeded | timeout | 2 |
| frontal_masking | timeout | succeeded | 3 |
| frontal_masking | timeout | timeout | 1 |
| lidar_dropout | collided | succeeded | 1 |
| lidar_dropout | succeeded | succeeded | 40 |
| lidar_dropout | succeeded | timeout | 1 |
| lidar_dropout | timeout | succeeded | 1 |
| lidar_dropout | timeout | timeout | 11 |

## Representative Propagation Cases

| Fault | Role | World | Class | Why this case | Evidence to collect next |
|---|---|---:|---|---|---|
| frontal_masking | typical_case | 76 | class2_tune_dependent_recovered | Closest to median completion slowdown; useful as a non-extreme propagation example. | trajectory; scan/faulted scan; costmap snapshot; cmd_vel timeline; controller path-update events |
| frontal_masking | high_susceptibility_case | 173 | class2_tune_dependent_recovered | Largest completion slowdown; useful for explaining environment-dependent susceptibility. | trajectory; scan/faulted scan; costmap snapshot; cmd_vel timeline; controller path-update events |
| frontal_masking | boundary_case | 250 | class3_marginal_success | Marginal-success world retained to show boundary-case behaviour. | trajectory; scan/faulted scan; costmap snapshot; cmd_vel timeline; controller path-update events |
| lidar_dropout | typical_case | 274 | class1_stable_success | Closest to median completion slowdown; useful as a non-extreme propagation example. | trajectory; scan/faulted scan; costmap snapshot; cmd_vel timeline; controller path-update events |
| lidar_dropout | high_susceptibility_case | 76 | class2_tune_dependent_recovered | Largest completion slowdown; useful for explaining environment-dependent susceptibility. | trajectory; scan/faulted scan; costmap snapshot; cmd_vel timeline; controller path-update events |
| lidar_dropout | boundary_case | 250 | class3_marginal_success | Marginal-success world retained to show boundary-case behaviour. | trajectory; scan/faulted scan; costmap snapshot; cmd_vel timeline; controller path-update events |

## Interpretation Draft

- Use paired effects as the primary comparison, because each fault run is matched with a baseline run in the same world/pair.
- Treat world-level differences as environment-dependent susceptibility, not as a strong class-level statistical claim yet.
- Use matched 15-35s window outputs to discuss fault-window behaviour; use whole-run metrics for mission-level outcome.
- Keep Bayesian hierarchical modelling as an enhancement after the audit, paired summaries, and propagation evidence are stable.
