# Fault Data Analysis PPT Speaker Script

## Slide 1: 1. Analysis objective

Open by saying this is not a whole-project update. It is specifically about the data-analysis design: what question the analysis answers, why each statistical layer exists, and what the final data shows.

## Slide 2: 2. Data structure

Explain pair clearly. Pair does not mean original-vs-tuned; it means baseline-vs-fault under the same tuned setup and world.

## Slide 3: 3. Expected metric directions

This slide is important for justify. You are showing that the analysis had pre-defined expectations, not post-hoc interpretation.

## Slide 4: 4. Analysis design layers

Describe the three levels: observed paired summaries, bootstrap uncertainty, Bayesian probability and hierarchical world effects.

## Slide 5: 5. Practical thresholds

This is the answer to “why not just p-value”. You define practically meaningful degradation before interpreting Bayesian probabilities.

## Slide 6: 6. Completion time

Masking supports the hypothesis clearly. Dropout is directionally slower but more uncertain by bootstrap CI.

## Slide 7: 7. Pipeline metrics

This slide links to propagation. Faults increase stop behaviour, reduce speed, increase controller path activity, and lengthen stop streaks.

## Slide 8: 8. World heterogeneity

Emphasise that this justifies hierarchical modelling. A global mean alone hides sensitive worlds such as W173 and W76.

## Slide 9: 9. Bayesian probability

Explain P(slowdown > 0) and P(slowdown > 5s). Dropout is probably worse but not likely to exceed the practical threshold.

## Slide 10: 10. Hierarchical Bayesian model

This slide explains why the model exists, not just that Bayesian was used. Tie it back to world heterogeneity.

## Slide 11: 11. PyMC result and diagnostics

Say this is not replacing the paired summaries; it is a robustness check that gives a conservative probability-based interpretation.

## Slide 12: 12. Representative cases

Use these to transition from statistics to fault propagation narrative. They are visual anchors, not final causal proof.

## Slide 13: 13. Hypotheses vs evidence

This is the clean answer to: what did you expect and what did you find.

## Slide 14: 14. Closing

End with the contribution: not just fault makes things worse, but structured evidence of world-dependent pipeline degradation.

