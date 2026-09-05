# Lightweight Bayesian Fault Analysis

Model: paired differences were analysed as `d_i = fault_i - baseline_i` using a normal likelihood with unknown mean and variance.
A weak Jeffreys prior `p(mu, sigma) proportional to 1/sigma` was used, giving a Student-t posterior for the mean effect.

Interpretation: `p_degradation` is the posterior probability that the fault worsens the metric in the expected direction. `p_meaningful_degradation` additionally requires the effect to exceed a pre-defined practical threshold.

## Main Fault-Level Results

| Fault | Metric | n pairs | Posterior median | 95% credible interval | P(degradation) | P(meaningful degradation) | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| frontal_masking | actual_path_length_m | 54 | 0.205 | [-0.091, 0.501] | 0.910 | 0.758 | strong evidence of directional degradation, magnitude may be modest |
| frontal_masking | completion_time_s | 54 | 9.201 | [-0.791, 18.925] | 0.965 | 0.799 | strong evidence of directional degradation, magnitude may be modest |
| frontal_masking | controller_new_path_count | 54 | 9.320 | [0.744, 17.957] | 0.984 | 0.837 | strong evidence of directional degradation, magnitude may be modest |
| frontal_masking | whole_max_stop_streak_s | 54 | 14.068 | [4.443, 23.732] | 0.998 | 0.967 | strong evidence of practically meaningful degradation |
| frontal_masking | whole_mean_speed_mps | 54 | -0.001 | [-0.002, -0.000] | 0.986 | 0.000 | strong evidence of directional degradation, magnitude may be modest |
| frontal_masking | whole_stop_ratio | 54 | 0.049 | [0.028, 0.071] | 1.000 | 0.480 | strong evidence of directional degradation, magnitude may be modest |
| lidar_dropout | actual_path_length_m | 54 | 0.127 | [-0.154, 0.408] | 0.810 | 0.575 | moderate evidence of degradation |
| lidar_dropout | completion_time_s | 54 | 6.428 | [-1.893, 14.686] | 0.935 | 0.632 | strong evidence of directional degradation, magnitude may be modest |
| lidar_dropout | controller_new_path_count | 54 | 5.626 | [-2.264, 13.766] | 0.919 | 0.563 | strong evidence of directional degradation, magnitude may be modest |
| lidar_dropout | whole_max_stop_streak_s | 54 | 11.411 | [-1.335, 24.022] | 0.962 | 0.844 | strong evidence of directional degradation, magnitude may be modest |
| lidar_dropout | whole_mean_speed_mps | 54 | -0.001 | [-0.002, -0.000] | 0.986 | 0.000 | strong evidence of directional degradation, magnitude may be modest |
| lidar_dropout | whole_stop_ratio | 54 | 0.026 | [-0.007, 0.058] | 0.937 | 0.073 | strong evidence of directional degradation, magnitude may be modest |

## World-Level Completion-Time Susceptibility

| Fault | World | n pairs | Posterior median slowdown (s) | 95% credible interval | P(slowdown) | P(slowdown > 5s) | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| frontal_masking | 274 | 6 | 7.571 | [1.993, 13.192] | 0.992 | 0.855 | strong evidence of directional degradation, magnitude may be modest |
| frontal_masking | 8 | 6 | 6.818 | [2.804, 10.849] | 0.996 | 0.848 | strong evidence of directional degradation, magnitude may be modest |
| frontal_masking | 173 | 6 | 44.691 | [-53.957, 142.804] | 0.854 | 0.827 | moderate evidence of degradation |
| frontal_masking | 86 | 6 | 8.103 | [-2.194, 18.408] | 0.952 | 0.763 | strong evidence of directional degradation, magnitude may be modest |
| frontal_masking | 76 | 6 | 5.153 | [-0.841, 11.040] | 0.961 | 0.526 | strong evidence of directional degradation, magnitude may be modest |
| frontal_masking | 250 | 6 | 4.582 | [-5.555, 14.692] | 0.853 | 0.460 | moderate evidence of degradation |
| frontal_masking | 239 | 6 | 0.430 | [-57.481, 58.131] | 0.507 | 0.428 | uncertain / mixed effect |
| frontal_masking | 240 | 6 | 3.936 | [0.560, 7.345] | 0.984 | 0.233 | strong evidence of directional degradation, magnitude may be modest |
| frontal_masking | 94 | 6 | 0.992 | [-8.649, 10.587] | 0.596 | 0.170 | uncertain / mixed effect |
| lidar_dropout | 94 | 6 | 8.172 | [0.235, 16.208] | 0.977 | 0.820 | strong evidence of directional degradation, magnitude may be modest |
| lidar_dropout | 76 | 6 | 35.556 | [-46.841, 116.494] | 0.842 | 0.807 | moderate evidence of degradation |
| lidar_dropout | 240 | 6 | 6.483 | [2.232, 10.783] | 0.995 | 0.795 | strong evidence of directional degradation, magnitude may be modest |
| lidar_dropout | 274 | 6 | 6.004 | [2.079, 9.991] | 0.995 | 0.731 | strong evidence of directional degradation, magnitude may be modest |
| lidar_dropout | 239 | 6 | 10.624 | [-11.633, 33.028] | 0.861 | 0.726 | moderate evidence of degradation |
| lidar_dropout | 86 | 6 | 3.765 | [-1.941, 9.513] | 0.924 | 0.301 | strong evidence of directional degradation, magnitude may be modest |
| lidar_dropout | 8 | 6 | -10.559 | [-52.558, 29.965] | 0.268 | 0.187 | uncertain / mixed effect |
| lidar_dropout | 173 | 6 | 0.192 | [-4.872, 5.301] | 0.536 | 0.030 | uncertain / mixed effect |
| lidar_dropout | 250 | 6 | -2.040 | [-5.605, 1.635] | 0.104 | 0.002 | little evidence of degradation |

## How to Present This

- This is not a full hierarchical Bayesian model; it is a lightweight Bayesian paired-effect analysis.
- It is appropriate as a supervisor-facing robustness check because it answers: how probable is degradation, not just whether a p-value crosses 0.05.
- A future dissertation extension can replace this with a hierarchical model that shares information across worlds and fault types.
