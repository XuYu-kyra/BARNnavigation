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
| frontal_masking | completion_time_s | 9 | 47 | 6.246 | [3.728, 8.828] | 1.000 | 0.843 | 1.300 | 6.584 | 1.000 | 2601.1 | strong directional degradation |
| lidar_dropout | completion_time_s | 9 | 40 | 4.543 | [1.629, 7.272] | 0.998 | 0.342 | 2.099 | 5.174 | 1.002 | 1498.5 | strong directional degradation |

## Completion-Time World Susceptibility

| Fault | World | n pairs | Median slowdown | 95% credible interval | P(slowdown) | P(slowdown > threshold) | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| frontal_masking | 86 | 6 | 6.662 | [3.526, 10.752] | 1.000 | 0.858 | strong directional degradation |
| frontal_masking | 250 | 5 | 6.482 | [3.258, 10.273] | 1.000 | 0.848 | strong directional degradation |
| frontal_masking | 173 | 5 | 6.493 | [3.149, 10.845] | 0.999 | 0.834 | strong directional degradation |
| frontal_masking | 274 | 6 | 6.480 | [3.325, 10.054] | 0.999 | 0.833 | strong directional degradation |
| frontal_masking | 8 | 6 | 6.275 | [3.157, 9.654] | 1.000 | 0.810 | strong directional degradation |
| frontal_masking | 239 | 1 | 6.480 | [2.514, 11.780] | 0.996 | 0.808 | strong directional degradation |
| frontal_masking | 76 | 6 | 6.150 | [2.593, 9.265] | 0.999 | 0.772 | strong directional degradation |
| frontal_masking | 240 | 6 | 5.825 | [1.942, 8.787] | 0.997 | 0.693 | strong directional degradation |
| frontal_masking | 94 | 6 | 5.347 | [0.229, 8.380] | 0.978 | 0.577 | strong directional degradation |
| lidar_dropout | 94 | 6 | 5.687 | [2.650, 10.075] | 0.999 | 0.659 | strong directional degradation |
| lidar_dropout | 240 | 6 | 5.291 | [2.311, 8.888] | 0.999 | 0.576 | strong directional degradation |
| lidar_dropout | 239 | 1 | 5.322 | [0.939, 12.263] | 0.988 | 0.566 | strong directional degradation |
| lidar_dropout | 274 | 6 | 5.131 | [2.116, 8.752] | 0.998 | 0.541 | strong directional degradation |
| lidar_dropout | 8 | 5 | 4.908 | [1.593, 8.524] | 0.996 | 0.476 | strong directional degradation |
| lidar_dropout | 86 | 6 | 4.267 | [0.761, 7.363] | 0.991 | 0.319 | strong directional degradation |
| lidar_dropout | 76 | 5 | 4.324 | [0.588, 7.457] | 0.986 | 0.308 | strong directional degradation |
| lidar_dropout | 173 | 2 | 4.005 | [-2.136, 8.132] | 0.920 | 0.292 | strong directional degradation |
| lidar_dropout | 250 | 3 | 2.223 | [-5.040, 6.164] | 0.710 | 0.117 | uncertain / mixed |

## Diagnostics Files

- `frontal_masking` / `completion_time_s`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_matched_success_completion/frontal_masking__completion_time_s_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_matched_success_completion/frontal_masking__completion_time_s.nc`
- `lidar_dropout` / `completion_time_s`: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_matched_success_completion/lidar_dropout__completion_time_s_arviz_summary.csv` and `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_matched_success_completion/lidar_dropout__completion_time_s.nc`

## How This Differs From The Dependency-Free Gibbs Version

- This version uses PyMC NUTS/HMC sampling rather than a hand-written conjugate Gibbs sampler.
- It uses a Student-t likelihood, which is more robust to simulation outliers.
- It stores full ArviZ inference data and diagnostics, so R-hat/ESS/posterior predictive checks can be inspected.
- This is closer to dissertation-grade methodology, but it depends on PyMC/ArviZ and takes longer to run.
