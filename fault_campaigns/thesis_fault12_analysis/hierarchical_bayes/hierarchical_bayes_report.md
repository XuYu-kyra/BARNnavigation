# Hierarchical Bayesian Fault Model

This report fits a hierarchical normal model to paired baseline-vs-fault differences.
Each pair difference is assigned to a world; each world has its own latent fault effect; those world effects are drawn from a fault-level distribution.

Model:

```text
y_ij ~ Normal(theta_j, sigma)
theta_j ~ Normal(mu, tau)
```

All metrics are oriented so positive values mean degradation. For example, lower mean speed under fault is converted into a positive speed-degradation effect.

## Fault-Level Effects

| Fault | Metric | n worlds | n pairs | Median global degradation | 95% credible interval | P(global degradation) | P(meaningful degradation) | World heterogeneity tau | R-hat | Interpretation |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| frontal_masking | actual_path_length_m | 9 | 54 | 0.201 | [-0.316, 0.709] | 0.795 | 0.662 | 0.591 | 1.001 | moderate evidence of degradation |
| frontal_masking | completion_time_s | 9 | 54 | 9.077 | [-7.775, 26.415] | 0.866 | 0.693 | 19.490 | 1.000 | moderate evidence of degradation |
| frontal_masking | controller_new_path_count | 9 | 54 | 9.149 | [-5.578, 23.965] | 0.895 | 0.723 | 17.185 | 1.000 | moderate evidence of degradation |
| frontal_masking | whole_max_stop_streak_s | 9 | 54 | 14.122 | [-1.964, 30.312] | 0.958 | 0.863 | 18.913 | 1.000 | strong evidence of directional degradation |
| frontal_masking | whole_mean_speed_mps | 9 | 54 | 0.001 | [-0.001, 0.003] | 0.857 | 0.000 | 0.002 | 1.000 | moderate evidence of degradation |
| frontal_masking | whole_stop_ratio | 9 | 54 | 0.049 | [0.011, 0.088] | 0.993 | 0.488 | 0.048 | 1.000 | strong evidence of directional degradation |
| lidar_dropout | actual_path_length_m | 9 | 54 | 0.131 | [-0.344, 0.620] | 0.715 | 0.555 | 0.568 | 1.000 | uncertain / mixed effect |
| lidar_dropout | completion_time_s | 9 | 54 | 6.481 | [-8.386, 21.080] | 0.818 | 0.583 | 16.675 | 1.001 | moderate evidence of degradation |
| lidar_dropout | controller_new_path_count | 9 | 54 | 5.691 | [-7.766, 19.485] | 0.803 | 0.543 | 15.992 | 1.000 | moderate evidence of degradation |
| lidar_dropout | whole_max_stop_streak_s | 9 | 54 | 11.607 | [-9.725, 32.626] | 0.864 | 0.734 | 24.656 | 1.000 | moderate evidence of degradation |
| lidar_dropout | whole_mean_speed_mps | 9 | 54 | 0.001 | [-0.001, 0.003] | 0.847 | 0.000 | 0.002 | 1.000 | moderate evidence of degradation |
| lidar_dropout | whole_stop_ratio | 9 | 54 | 0.027 | [-0.031, 0.083] | 0.830 | 0.207 | 0.067 | 1.000 | moderate evidence of degradation |

## Most Susceptible Worlds by Completion-Time Effect

| Fault | World | n pairs | Median slowdown (s) | 95% credible interval | P(slowdown > 0) | P(slowdown > 5s) | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| frontal_masking | 173 | 6 | 32.145 | [7.588, 57.308] | 0.995 | 0.984 | strong evidence of practically meaningful degradation |
| frontal_masking | 86 | 6 | 8.190 | [-15.264, 31.378] | 0.761 | 0.610 | moderate evidence of degradation |
| frontal_masking | 274 | 6 | 8.163 | [-15.810, 31.477] | 0.755 | 0.607 | moderate evidence of degradation |
| frontal_masking | 8 | 6 | 7.430 | [-15.576, 31.317] | 0.731 | 0.584 | uncertain / mixed effect |
| frontal_masking | 76 | 6 | 6.538 | [-17.263, 30.186] | 0.706 | 0.554 | uncertain / mixed effect |
| frontal_masking | 240 | 6 | 6.174 | [-17.734, 29.486] | 0.696 | 0.540 | uncertain / mixed effect |
| frontal_masking | 250 | 6 | 6.124 | [-17.976, 29.732] | 0.692 | 0.537 | uncertain / mixed effect |
| frontal_masking | 94 | 6 | 4.251 | [-20.849, 28.026] | 0.637 | 0.474 | uncertain / mixed effect |
| frontal_masking | 239 | 6 | 4.108 | [-19.870, 27.380] | 0.630 | 0.468 | uncertain / mixed effect |
| lidar_dropout | 76 | 6 | 25.295 | [4.983, 46.456] | 0.992 | 0.975 | strong evidence of practically meaningful degradation |
| lidar_dropout | 239 | 6 | 9.163 | [-10.765, 28.973] | 0.818 | 0.663 | moderate evidence of degradation |
| lidar_dropout | 94 | 6 | 7.841 | [-12.477, 27.623] | 0.781 | 0.607 | moderate evidence of degradation |
| lidar_dropout | 240 | 6 | 6.853 | [-13.690, 26.537] | 0.744 | 0.575 | uncertain / mixed effect |
| lidar_dropout | 274 | 6 | 6.242 | [-13.573, 25.746] | 0.730 | 0.545 | uncertain / mixed effect |
| lidar_dropout | 86 | 6 | 4.551 | [-15.546, 24.266] | 0.676 | 0.483 | uncertain / mixed effect |
| lidar_dropout | 173 | 6 | 2.320 | [-17.799, 22.352] | 0.590 | 0.398 | uncertain / mixed effect |
| lidar_dropout | 250 | 6 | 0.961 | [-18.763, 20.915] | 0.536 | 0.347 | uncertain / mixed effect |
| lidar_dropout | 8 | 6 | -4.876 | [-25.508, 14.634] | 0.313 | 0.165 | uncertain / mixed effect |

## Diagnostics

| Fault | Metric | Chains | Posterior samples / chain | R-hat(mu) | Note |
|---|---|---:|---:|---:|---|
| frontal_masking | actual_path_length_m | 4 | 2000 | 1.001 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| frontal_masking | completion_time_s | 4 | 2000 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| frontal_masking | controller_new_path_count | 4 | 2000 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| frontal_masking | whole_max_stop_streak_s | 4 | 2000 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| frontal_masking | whole_mean_speed_mps | 4 | 2000 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| frontal_masking | whole_stop_ratio | 4 | 2000 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| lidar_dropout | actual_path_length_m | 4 | 2000 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| lidar_dropout | completion_time_s | 4 | 2000 | 1.001 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| lidar_dropout | controller_new_path_count | 4 | 2000 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| lidar_dropout | whole_max_stop_streak_s | 4 | 2000 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| lidar_dropout | whole_mean_speed_mps | 4 | 2000 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| lidar_dropout | whole_stop_ratio | 4 | 2000 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |

## Suggested Wording

This should be presented as an initial hierarchical Bayesian analysis, not as the final statistical model.
It strengthens the meeting evidence because it separates global fault effect, world-level susceptibility, and pair-level run noise.
If needed, the dissertation version can later be extended with class-level effects or fitted in PyMC/Stan for more formal diagnostics.
