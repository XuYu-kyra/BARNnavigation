# PPT v4 Speaker Notes

## Key wording changes from v3

- Put task outcome transitions before completion-time inference.
- Primary completion-time estimand is matched-success only.
- All-pair/capped completion-time analysis is sensitivity evidence, not the primary estimate.
- Pipeline metrics are mechanism-consistent proxy evidence, not formal proof of propagation.
- Do not claim dropout has greater heterogeneity unless tau posterior intervals are explicitly compared.
- Use 'smaller / less threshold-stable estimated effect' for dropout rather than 'not meaningful'.

## Actual Bayesian model details

```text
d_ij ~ StudentT(nu, theta_j, sigma)
theta_j = mu + tau * theta_offset_j
theta_offset_j ~ Normal(0, 1)
mu ~ Normal(0, 10 * prior_scale)
tau ~ HalfNormal(5 * prior_scale)
sigma ~ HalfNormal(5 * prior_scale)
nu_minus_two ~ Exponential(1/30)
nu = nu_minus_two + 2
```

The model uses a Student-t likelihood to reduce sensitivity to long-tail Gazebo/Nav2 timing outliers.

## Primary matched-success Bayesian results

- Frontal masking: n=47, posterior median 6.25s, 95% CrI [3.73, 8.83], P(>0)=>0.999, P(>5s)=0.843.
- LiDAR dropout: n=40, posterior median 4.54s, 95% CrI [1.63, 7.27], P(>0)=0.998, P(>5s)=0.342.

## Safe one-sentence conclusion

Both faults probably slow successful navigation under the fitted model, but evidence for a larger slowdown above the exploratory 5s threshold is much stronger for frontal masking.
