# Fault Campaign Analysis Audit Summary

Generated after re-running the local analysis scripts on `/home/student24/dissertation/barn_ros2/fault_campaigns`.

## File Status

Usable outputs:

- `thesis_main_paired_effects.csv`: main paired frequentist/bootstrap summaries, 12 rows covering 2 faults x 6 metrics.
- `thesis_world_heterogeneity.csv`: world-level heterogeneity summary, 18 rows covering 2 faults x 9 worlds.
- `thesis_pair_level_metric_differences.csv`: pair-level input table, 648 rows covering 2 faults x 9 worlds x 6 pairs x 6 metrics.
- `bayesian/bayesian_fault_effects.csv`: lightweight Bayesian paired-effect results, regenerated and non-empty.
- `bayesian/bayesian_world_completion_effects.csv`: lightweight Bayesian world-level completion-time results, regenerated and non-empty.
- `hierarchical_bayes/hierarchical_bayes_fault_effects.csv`: dependency-free hierarchical Bayesian results, regenerated and non-empty.
- `hierarchical_bayes/hierarchical_bayes_world_effects.csv`: world-level hierarchical Bayesian effects, regenerated and non-empty.
- `hierarchical_bayes/hierarchical_bayes_diagnostics.csv`: R-hat diagnostics for the dependency-free hierarchical model, regenerated and non-empty.

Not usable yet:

- `pymc_hierarchical/*`: currently empty on this host because PyMC/ArviZ are not installed in the local analysis environment. Do not cite these files unless re-run successfully in a PyMC-enabled environment.

## Main Mission-Level Completion-Time Effects

| Fault | Pairs | Mean fault-baseline slowdown | Bootstrap 95% CI | Degradation pair fraction |
|---|---:|---:|---:|---:|
| Frontal LiDAR masking | 54 | 9.21 s | [1.27, 20.14] s | 0.796 |
| Intermittent LiDAR dropout | 54 | 6.43 s | [-0.58, 15.72] s | 0.778 |

Interpretation: both faults tend to slow navigation, but frontal masking has clearer evidence at the campaign level because its bootstrap interval is fully positive for completion time.

## Hierarchical Bayesian Completion-Time Effects

| Fault | Posterior median global slowdown | 95% credible interval | P(global slowdown > 0) | P(global slowdown > 5s) | World heterogeneity tau | R-hat(mu) |
|---|---:|---:|---:|---:|---:|---:|
| Frontal LiDAR masking | 9.08 s | [-7.77, 26.41] s | 0.866 | 0.693 | 19.49 | 1.000 |
| Intermittent LiDAR dropout | 6.48 s | [-8.39, 21.08] s | 0.818 | 0.583 | 16.67 | 1.001 |

Interpretation: the hierarchical model is more conservative than the pooled bootstrap analysis because it explicitly models world-to-world heterogeneity. This is useful for dissertation framing: the faults do not affect all worlds equally.

## Most Sensitive Worlds by Mean Completion-Time Slowdown

Frontal LiDAR masking:

| Rank | World | Class | Mean slowdown | Stop-ratio delta |
|---:|---:|---|---:|---:|
| 1 | 173 | class2_tune_dependent_recovered | 44.95 s | 0.000 |
| 2 | 86 | class2_tune_dependent_recovered | 8.15 s | 0.128 |
| 3 | 274 | class1_stable_success | 7.57 s | 0.060 |
| 4 | 8 | class1_stable_success | 6.81 s | 0.035 |

Intermittent LiDAR dropout:

| Rank | World | Class | Mean slowdown | Stop-ratio delta |
|---:|---:|---|---:|---:|
| 1 | 76 | class2_tune_dependent_recovered | 35.60 s | 0.132 |
| 2 | 239 | class2_tune_dependent_recovered | 10.72 s | -0.043 |
| 3 | 94 | class1_stable_success | 8.19 s | 0.012 |
| 4 | 240 | class1_stable_success | 6.47 s | 0.051 |

## Meeting-Safe Interpretation

- The formal campaigns are complete for fault1 and fault2: 2 faults, 9 worlds, 6 paired repetitions per world, 108 paired runs per fault campaign if counting baseline/fault runs together as 54 pairs x 2 runs.
- Frontal LiDAR masking shows the clearest mission-level degradation, especially in completion time, stop ratio, mean speed, controller path updates, and maximum stop streak.
- Intermittent LiDAR dropout also shows directional degradation, but the uncertainty is larger and world dependence is stronger.
- The hierarchical Bayesian model gives a more cautious conclusion than pooled analysis because it accounts for world heterogeneity instead of treating all 54 pairs as exchangeable.
- This supports the dissertation argument that fault impact propagates through the navigation stack in a world-dependent way, rather than simply making every run uniformly worse.

## Recommended Next Step

Use the regenerated non-empty Bayesian and hierarchical Bayesian tables for the meeting. Do not use the empty `pymc_hierarchical` directory until PyMC is installed and the model is re-run successfully.

## PyMC Hierarchical Model Update

A dissertation-grade PyMC version was also run locally after installing a dedicated Bayesian virtual environment at:

```text
/home/student24/dissertation/barn_ros2/.venv_bayes_local
```

Final PyMC all-metrics output directory:

```text
/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_all_metrics
```

Status:

- `pymc_hierarchical_fault_effects.csv`: 12 rows, covering 2 faults x 6 metrics.
- `pymc_hierarchical_world_effects.csv`: 108 rows, covering 2 faults x 6 metrics x 9 worlds.
- `pymc_hierarchical_diagnostics.csv`: 12 rows.
- NetCDF inference data: 12 `.nc` files saved successfully.
- Maximum `R-hat(mu)`: 1.003475.
- Minimum `ESS_bulk(mu)`: 1092.275627.

These diagnostics are acceptable for a supervisor-facing initial PyMC model.

### PyMC Completion-Time Results

| Fault | Posterior median global slowdown | 95% credible interval | P(slowdown > 0) | P(slowdown > 5s) | R-hat(mu) | ESS_bulk(mu) |
|---|---:|---:|---:|---:|---:|---:|
| Frontal LiDAR masking | 6.28 s | [3.66, 8.81] s | 1.000 | 0.848 | 1.001 | 3537.6 |
| Intermittent LiDAR dropout | 3.18 s | [0.85, 5.52] s | 0.991 | 0.058 | 1.000 | 1589.6 |

Interpretation: the PyMC Student-t hierarchical model is more conservative than the raw paired mean because it is robust to long-tail simulation outliers. It still supports a strong directional slowdown effect for both faults, while only frontal masking shows substantial posterior probability of exceeding the 5 s practical threshold.

Meeting-safe wording:

> I implemented a PyMC hierarchical Bayesian model as a robustness check. Compared with the pooled paired mean, the Student-t hierarchical model gives a more conservative estimate because it downweights long-tail simulation outliers and separates global fault effect from world-level susceptibility. The diagnostics are acceptable for an initial supervisor-facing result, with all R-hat values near 1 and ESS above 1000.
