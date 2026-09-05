# Dissertation Bayesian Diagnostics Pack

Model directory: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/pymc_hierarchical_matched_success_completion`
Output directory: `/home/student24/dissertation/barn_ros2/fault_campaigns/thesis_fault12_analysis/bayesian_dissertation_diagnostics`

## Model Specification

Primary model for completion-time slowdown uses matched-success paired differences only:

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

Positive effects are oriented as degradation. For completion time, positive means the fault run was slower than its paired baseline run.

The Student-t likelihood was used because Gazebo/Nav2 experiments can produce occasional long-tail timing outliers; this reduces sensitivity compared with a Normal likelihood.

## Prior Specification

The model uses weakly regularising scale priors. `prior_scale` is chosen from the observed paired-difference scale and the practical threshold, so priors remain broad relative to the observed data while keeping sampling stable. The practical threshold for completion time is 5s, matching the pre-registered repeat-count stopping rule and the smallest slowdown treated as operationally meaningful in this analysis.

## Convergence Diagnostics

R-hat threshold: <= 1.01; ESS threshold: >= 400.0.

All reported key parameters passed the R-hat and ESS thresholds.
Sampling diagnostics showed no divergences, no max-treedepth saturation, and acceptable BFMI for all primary models.

## Posterior Predictive Checks

Posterior predictive checks compare observed paired slowdowns with simulated replicated datasets from the fitted model. The generated table reports predictive intervals for mean, standard deviation, maximum slowdown, pointwise 95% coverage, and threshold exceedance fractions.

- `frontal_masking`: observed mean 5.97s; PPC mean median 6.21s [3.26, 9.05]; pointwise 95% PPC coverage 0.96.
- `lidar_dropout`: observed mean 4.77s; PPC mean median 4.69s [2.25, 7.16]; pointwise 95% PPC coverage 0.97.

## Tau / World Heterogeneity

`tau` is the posterior scale of world-level effects. It quantifies how much slowdown varies between worlds after accounting for within-world run noise. A non-zero tau supports the thesis claim that environment susceptibility is heterogeneous rather than uniform.

- `frontal_masking`: tau median 1.30s [0.06, 5.07], P(tau>2s)=0.309.
- `lidar_dropout`: tau median 2.10s [0.08, 6.70], P(tau>2s)=0.522.

## Robustness / Sensitivity Statement

The Bayesian model is used as a probabilistic summary of the primary matched-success completion-time outcome. It should be reported together with the non-parametric paired/bootstrap results and the all-pair/capped sensitivity analysis. Agreement in direction between these analyses supports robustness; differences in practical-threshold probability should be interpreted as uncertainty about effect magnitude rather than a contradiction of directional degradation.

## Files Generated

- `convergence_diagnostics_full.csv`
- `sampling_diagnostics.csv`
- `posterior_predictive_checks.csv`
- `tau_heterogeneity_interpretation.csv`
- `*_ppc_hist.svg`
