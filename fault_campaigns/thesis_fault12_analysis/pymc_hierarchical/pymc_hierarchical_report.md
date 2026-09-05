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
| frontal_masking | completion_time_s | 9 | 54 | 6.247 | [3.715, 8.904] | 1.000 | 0.844 | 1.231 | 6.545 | 1.000 | 3818.9 | strong directional degradation |
| lidar_dropout | completion_time_s | 9 | 54 | 3.177 | [0.848, 5.455] | 0.994 | 0.057 | 2.386 | 3.777 | 1.001 | 1631.8 | strong directional degradation |

## Completion-Time World Susceptibility

| Fault | World | n pairs | Median slowdown | 95% credible interval | P(slowdown) | P(slowdown > threshold) | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| frontal_masking | 173 | 6 | 6.694 | [3.530, 11.230] | 0.999 | 0.862 | strong directional degradation |
| frontal_masking | 86 | 6 | 6.742 | [3.458, 11.066] | 0.999 | 0.861 | strong directional degradation |
| frontal_masking | 274 | 6 | 6.374 | [3.040, 10.047] | 0.998 | 0.812 | strong directional degradation |
| frontal_masking | 76 | 6 | 6.278 | [2.776, 9.552] | 0.997 | 0.803 | strong directional degradation |
| frontal_masking | 8 | 6 | 6.249 | [2.974, 9.692] | 1.000 | 0.796 | strong directional degradation |
| frontal_masking | 250 | 6 | 6.228 | [2.620, 9.698] | 0.997 | 0.786 | strong directional degradation |
| frontal_masking | 239 | 6 | 6.310 | [1.918, 10.743] | 0.993 | 0.776 | strong directional degradation |
| frontal_masking | 240 | 6 | 5.772 | [2.011, 8.747] | 0.995 | 0.696 | strong directional degradation |
| frontal_masking | 94 | 6 | 5.739 | [0.097, 9.077] | 0.976 | 0.665 | strong directional degradation |
| lidar_dropout | 240 | 6 | 4.741 | [1.919, 7.968] | 0.998 | 0.430 | strong directional degradation |
| lidar_dropout | 274 | 6 | 4.564 | [1.563, 8.160] | 0.998 | 0.388 | strong directional degradation |
| lidar_dropout | 8 | 6 | 4.365 | [0.946, 7.946] | 0.994 | 0.362 | strong directional degradation |
| lidar_dropout | 94 | 6 | 4.137 | [1.328, 7.801] | 0.999 | 0.281 | strong directional degradation |
| lidar_dropout | 76 | 6 | 3.619 | [0.651, 6.692] | 0.989 | 0.169 | strong directional degradation |
| lidar_dropout | 86 | 6 | 3.342 | [0.221, 6.770] | 0.980 | 0.142 | strong directional degradation |
| lidar_dropout | 239 | 6 | 1.840 | [-1.266, 5.400] | 0.867 | 0.038 | moderate degradation evidence |
| lidar_dropout | 173 | 6 | 1.281 | [-2.028, 4.607] | 0.785 | 0.015 | moderate degradation evidence |
| lidar_dropout | 250 | 6 | 0.230 | [-3.068, 3.684] | 0.553 | 0.002 | uncertain / mixed |

## Diagnostics Files

- `frontal_masking` / `completion_time_s`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical/frontal_masking__completion_time_s_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical/frontal_masking__completion_time_s.nc_NOT_WRITTEN_ValueError`
- `lidar_dropout` / `completion_time_s`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical/lidar_dropout__completion_time_s_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical/lidar_dropout__completion_time_s.nc_NOT_WRITTEN_ValueError`

## How This Differs From The Dependency-Free Gibbs Version

- This version uses PyMC NUTS/HMC sampling rather than a hand-written conjugate Gibbs sampler.
- It uses a Student-t likelihood, which is more robust to simulation outliers.
- It stores full ArviZ inference data and diagnostics, so R-hat/ESS/posterior predictive checks can be inspected.
- This is closer to dissertation-grade methodology, but it depends on PyMC/ArviZ and takes longer to run.
