# PyMC Hierarchical Bayesian Fault Model

This is the probabilistic-programming version of the hierarchical analysis.
It uses a Student-t likelihood to reduce sensitivity to occasional long-tail Gazebo/Nav2 timing outliers.

```text
y_ij ~ StudentT(nu, theta_j, sigma)
theta_j ~ Normal(mu, tau)
```

All effects are oriented so positive values mean degradation.

## Fault-Level Results

| Fault | Metric | n worlds | n pairs | Median global degradation | 95% credible interval | P(degradation) | P(meaningful degradation) | tau median | sigma median | R-hat(mu) | ESS(mu) | Interpretation |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| frontal_masking | actual_path_length_m | 9 | 54 | 0.013 | [-0.009, 0.035] | 0.885 | 0.000 | 0.011 | 0.056 | 1.002 | 3678.9 | moderate degradation evidence |
| frontal_masking | completion_time_s | 9 | 54 | 6.284 | [3.656, 8.815] | 1.000 | 0.848 | 1.208 | 6.582 | 1.001 | 3537.6 | strong directional degradation |
| frontal_masking | controller_new_path_count | 9 | 54 | 6.251 | [3.850, 8.578] | 1.000 | 0.865 | 0.980 | 5.876 | 1.002 | 3462.7 | strong directional degradation |
| frontal_masking | whole_max_stop_streak_s | 9 | 54 | 8.371 | [3.071, 15.180] | 0.997 | 0.900 | 4.356 | 11.337 | 1.003 | 1220.6 | strong practically meaningful degradation |
| frontal_masking | whole_mean_speed_mps | 9 | 54 | 0.001 | [0.001, 0.002] | 1.000 | 0.000 | 0.000 | 0.001 | 1.000 | 3712.5 | strong directional degradation |
| frontal_masking | whole_stop_ratio | 9 | 54 | 0.048 | [0.012, 0.085] | 0.993 | 0.459 | 0.040 | 0.067 | 1.001 | 1401.7 | strong directional degradation |
| lidar_dropout | actual_path_length_m | 9 | 54 | 0.011 | [-0.027, 0.044] | 0.750 | 0.000 | 0.024 | 0.074 | 1.002 | 1537.4 | moderate degradation evidence |
| lidar_dropout | completion_time_s | 9 | 54 | 3.181 | [0.855, 5.516] | 0.991 | 0.058 | 2.383 | 3.776 | 1.000 | 1589.6 | strong directional degradation |
| lidar_dropout | controller_new_path_count | 9 | 54 | 4.047 | [1.525, 6.761] | 0.997 | 0.211 | 2.837 | 3.847 | 1.000 | 1328.2 | strong directional degradation |
| lidar_dropout | whole_max_stop_streak_s | 9 | 54 | 3.337 | [-0.403, 8.353] | 0.963 | 0.217 | 2.444 | 9.289 | 1.003 | 2027.5 | strong directional degradation |
| lidar_dropout | whole_mean_speed_mps | 9 | 54 | 0.001 | [0.001, 0.001] | 0.998 | 0.000 | 0.000 | 0.001 | 1.001 | 1836.3 | strong directional degradation |
| lidar_dropout | whole_stop_ratio | 9 | 54 | 0.015 | [-0.006, 0.037] | 0.932 | 0.003 | 0.023 | 0.029 | 1.003 | 1092.3 | strong directional degradation |

## Completion-Time World Susceptibility

| Fault | World | n pairs | Median slowdown | 95% credible interval | P(slowdown) | P(slowdown > threshold) | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| frontal_masking | 86 | 6 | 6.729 | [3.426, 11.064] | 0.999 | 0.863 | strong directional degradation |
| frontal_masking | 173 | 6 | 6.716 | [3.378, 11.272] | 0.999 | 0.862 | strong directional degradation |
| frontal_masking | 274 | 6 | 6.387 | [3.104, 9.875] | 0.999 | 0.807 | strong directional degradation |
| frontal_masking | 8 | 6 | 6.287 | [2.983, 9.507] | 0.999 | 0.806 | strong directional degradation |
| frontal_masking | 76 | 6 | 6.279 | [2.724, 9.594] | 0.999 | 0.800 | strong directional degradation |
| frontal_masking | 250 | 6 | 6.253 | [2.391, 9.813] | 0.997 | 0.782 | strong directional degradation |
| frontal_masking | 239 | 6 | 6.314 | [2.196, 10.725] | 0.995 | 0.778 | strong directional degradation |
| frontal_masking | 240 | 6 | 5.823 | [2.032, 8.678] | 0.997 | 0.703 | strong directional degradation |
| frontal_masking | 94 | 6 | 5.844 | [0.645, 9.170] | 0.982 | 0.677 | strong directional degradation |
| lidar_dropout | 240 | 6 | 4.696 | [1.847, 8.020] | 1.000 | 0.427 | strong directional degradation |
| lidar_dropout | 274 | 6 | 4.535 | [1.563, 8.049] | 0.999 | 0.382 | strong directional degradation |
| lidar_dropout | 8 | 6 | 4.396 | [1.304, 7.906] | 0.996 | 0.357 | strong directional degradation |
| lidar_dropout | 94 | 6 | 4.105 | [1.325, 7.847] | 0.997 | 0.277 | strong directional degradation |
| lidar_dropout | 76 | 6 | 3.604 | [0.697, 6.631] | 0.992 | 0.172 | strong directional degradation |
| lidar_dropout | 86 | 6 | 3.341 | [0.320, 6.615] | 0.985 | 0.150 | strong directional degradation |
| lidar_dropout | 239 | 6 | 1.848 | [-1.221, 5.166] | 0.880 | 0.030 | moderate degradation evidence |
| lidar_dropout | 173 | 6 | 1.269 | [-1.977, 4.248] | 0.790 | 0.007 | moderate degradation evidence |
| lidar_dropout | 250 | 6 | 0.312 | [-2.808, 3.715] | 0.568 | 0.004 | uncertain / mixed |

## Diagnostics Files

- `frontal_masking` / `actual_path_length_m`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/frontal_masking__actual_path_length_m_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/frontal_masking__actual_path_length_m.nc`
- `frontal_masking` / `completion_time_s`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/frontal_masking__completion_time_s_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/frontal_masking__completion_time_s.nc`
- `frontal_masking` / `controller_new_path_count`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/frontal_masking__controller_new_path_count_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/frontal_masking__controller_new_path_count.nc`
- `frontal_masking` / `whole_max_stop_streak_s`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/frontal_masking__whole_max_stop_streak_s_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/frontal_masking__whole_max_stop_streak_s.nc`
- `frontal_masking` / `whole_mean_speed_mps`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/frontal_masking__whole_mean_speed_mps_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/frontal_masking__whole_mean_speed_mps.nc`
- `frontal_masking` / `whole_stop_ratio`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/frontal_masking__whole_stop_ratio_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/frontal_masking__whole_stop_ratio.nc`
- `lidar_dropout` / `actual_path_length_m`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/lidar_dropout__actual_path_length_m_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/lidar_dropout__actual_path_length_m.nc`
- `lidar_dropout` / `completion_time_s`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/lidar_dropout__completion_time_s_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/lidar_dropout__completion_time_s.nc`
- `lidar_dropout` / `controller_new_path_count`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/lidar_dropout__controller_new_path_count_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/lidar_dropout__controller_new_path_count.nc`
- `lidar_dropout` / `whole_max_stop_streak_s`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/lidar_dropout__whole_max_stop_streak_s_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/lidar_dropout__whole_max_stop_streak_s.nc`
- `lidar_dropout` / `whole_mean_speed_mps`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/lidar_dropout__whole_mean_speed_mps_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/lidar_dropout__whole_mean_speed_mps.nc`
- `lidar_dropout` / `whole_stop_ratio`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/lidar_dropout__whole_stop_ratio_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics/lidar_dropout__whole_stop_ratio.nc`

## How This Differs From The Dependency-Free Gibbs Version

- This version uses PyMC NUTS/HMC sampling rather than a hand-written conjugate Gibbs sampler.
- It uses a Student-t likelihood, which is more robust to simulation outliers.
- It stores full ArviZ inference data and diagnostics, so R-hat/ESS/posterior predictive checks can be inspected.
- This is closer to dissertation-grade methodology, but it depends on PyMC/ArviZ and takes longer to run.
