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
| frontal_masking | actual_path_length_m | 9 | 54 | 0.204 | [-0.304, 0.737] | 0.808 | 0.671 | 0.592 | 1.000 | moderate evidence of degradation |
| frontal_masking | completion_time_s | 9 | 54 | 9.091 | [-7.641, 26.260] | 0.864 | 0.694 | 19.299 | 0.999 | moderate evidence of degradation |
| frontal_masking | controller_new_path_count | 9 | 54 | 9.184 | [-5.226, 23.582] | 0.900 | 0.728 | 17.042 | 1.001 | strong evidence of directional degradation |
| frontal_masking | whole_max_stop_streak_s | 9 | 54 | 14.155 | [-2.794, 30.215] | 0.946 | 0.859 | 19.092 | 1.000 | strong evidence of directional degradation |
| frontal_masking | whole_mean_speed_mps | 9 | 54 | 0.001 | [-0.001, 0.003] | 0.860 | 0.000 | 0.002 | 1.000 | moderate evidence of degradation |
| frontal_masking | whole_stop_ratio | 9 | 54 | 0.050 | [0.011, 0.090] | 0.993 | 0.496 | 0.048 | 1.001 | strong evidence of directional degradation |
| lidar_dropout | actual_path_length_m | 9 | 54 | 0.129 | [-0.349, 0.615] | 0.712 | 0.550 | 0.566 | 1.000 | uncertain / mixed effect |
| lidar_dropout | completion_time_s | 9 | 54 | 6.698 | [-7.710, 20.801] | 0.827 | 0.588 | 16.715 | 1.000 | moderate evidence of degradation |
| lidar_dropout | controller_new_path_count | 9 | 54 | 5.460 | [-7.848, 19.107] | 0.794 | 0.528 | 16.055 | 0.999 | moderate evidence of degradation |
| lidar_dropout | whole_max_stop_streak_s | 9 | 54 | 11.393 | [-9.526, 31.869] | 0.863 | 0.743 | 24.668 | 1.000 | moderate evidence of degradation |
| lidar_dropout | whole_mean_speed_mps | 9 | 54 | 0.001 | [-0.001, 0.003] | 0.848 | 0.000 | 0.002 | 1.000 | moderate evidence of degradation |
| lidar_dropout | whole_stop_ratio | 9 | 54 | 0.026 | [-0.029, 0.083] | 0.832 | 0.187 | 0.066 | 1.000 | moderate evidence of degradation |

## Most Susceptible Worlds by Completion-Time Effect

| Fault | World | n pairs | Median slowdown (s) | 95% credible interval | P(slowdown > 0) | P(slowdown > 5s) | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| frontal_masking | 173 | 6 | 31.490 | [7.063, 57.135] | 0.996 | 0.983 | strong evidence of practically meaningful degradation |
| frontal_masking | 274 | 6 | 8.265 | [-15.256, 32.093] | 0.758 | 0.612 | moderate evidence of degradation |
| frontal_masking | 86 | 6 | 8.327 | [-16.083, 31.784] | 0.755 | 0.611 | moderate evidence of degradation |
| frontal_masking | 8 | 6 | 7.786 | [-16.067, 31.758] | 0.738 | 0.591 | uncertain / mixed effect |
| frontal_masking | 76 | 6 | 7.126 | [-16.096, 31.282] | 0.737 | 0.574 | uncertain / mixed effect |
| frontal_masking | 250 | 6 | 6.077 | [-18.631, 30.154] | 0.700 | 0.541 | uncertain / mixed effect |
| frontal_masking | 240 | 6 | 5.835 | [-18.143, 29.642] | 0.684 | 0.528 | uncertain / mixed effect |
| frontal_masking | 94 | 6 | 4.118 | [-20.640, 27.550] | 0.639 | 0.473 | uncertain / mixed effect |
| frontal_masking | 239 | 6 | 3.792 | [-19.447, 27.029] | 0.619 | 0.458 | uncertain / mixed effect |
| lidar_dropout | 76 | 6 | 25.629 | [4.804, 46.522] | 0.989 | 0.974 | strong evidence of practically meaningful degradation |
| lidar_dropout | 239 | 6 | 9.443 | [-10.541, 29.320] | 0.826 | 0.664 | moderate evidence of degradation |
| lidar_dropout | 94 | 6 | 7.508 | [-11.763, 26.753] | 0.781 | 0.604 | moderate evidence of degradation |
| lidar_dropout | 274 | 6 | 6.465 | [-13.298, 26.589] | 0.737 | 0.554 | uncertain / mixed effect |
| lidar_dropout | 240 | 6 | 6.342 | [-13.949, 26.868] | 0.735 | 0.545 | uncertain / mixed effect |
| lidar_dropout | 86 | 6 | 4.590 | [-16.201, 24.739] | 0.674 | 0.484 | uncertain / mixed effect |
| lidar_dropout | 173 | 6 | 2.247 | [-17.377, 22.414] | 0.589 | 0.396 | uncertain / mixed effect |
| lidar_dropout | 250 | 6 | 0.978 | [-19.347, 20.469] | 0.543 | 0.347 | uncertain / mixed effect |
| lidar_dropout | 8 | 6 | -5.025 | [-25.164, 16.126] | 0.320 | 0.173 | uncertain / mixed effect |

## Diagnostics

| Fault | Metric | Chains | Posterior samples / chain | R-hat(mu) | Note |
|---|---|---:|---:|---:|---|
| frontal_masking | actual_path_length_m | 4 | 750 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| frontal_masking | completion_time_s | 4 | 750 | 0.999 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| frontal_masking | controller_new_path_count | 4 | 750 | 1.001 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| frontal_masking | whole_max_stop_streak_s | 4 | 750 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| frontal_masking | whole_mean_speed_mps | 4 | 750 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| frontal_masking | whole_stop_ratio | 4 | 750 | 1.001 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| lidar_dropout | actual_path_length_m | 4 | 750 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| lidar_dropout | completion_time_s | 4 | 750 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| lidar_dropout | controller_new_path_count | 4 | 750 | 0.999 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| lidar_dropout | whole_max_stop_streak_s | 4 | 750 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| lidar_dropout | whole_mean_speed_mps | 4 | 750 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |
| lidar_dropout | whole_stop_ratio | 4 | 750 | 1.000 | R-hat near 1.00 suggests chains mixed acceptably for this quick supervisor-facing analysis. |

## Suggested Wording

This should be presented as an initial hierarchical Bayesian analysis, not as the final statistical model.
It strengthens the meeting evidence because it separates global fault effect, world-level susceptibility, and pair-level run noise.
If needed, the dissertation version can later be extended with class-level effects or fitted in PyMC/Stan for more formal diagnostics.
