# Dissertation Evidence Index

Updated: 2026-08-16T23:28:31

This directory is a curated index/copy of thesis-relevant evidence. Original experiment directories are not moved or modified.

## Directory Map

- `00_experiment_records/`: narrative experiment records and audit summaries.
- `01_campaign_raw_summaries/`: raw campaign status, attempts, and parsed summaries for each fault campaign.
- `02_fault12_analysis_tables/`: primary thesis analysis CSV tables for masking/dropout.
- `03_figures_for_dissertation/`: reusable final figures, captions, and clean assets.
- `04_bayesian_dissertation_diagnostics/`: PyMC model outputs, convergence diagnostics, PPC, tau interpretation.
- `05_classifier_evidence/`: scan signature diagnostics, Stage2B development validation, held-out final-logic revalidation.
- `06_direct_propagation_tracing/`: W8/W240 time-aligned tracing figures and CSVs.
- `07_classifier_recovery_closed_loop_raw/`: raw logs and outputs for classifier/recovery/closed-loop exploratory work.
- `08_reproducibility_scripts/`: scripts needed to regenerate major analyses.
- `09_recovery_mission_outcome_analysis/`: mission-level outcome audit for recovery-enabled pilot logs.
- `10_recovery_layer_trace_w8_dropout/`: targeted W8 dropout recovery OFF/ON layer-level trace.
- `11_recovery_layer_trace_w8_masking/`: targeted W8 masking recovery OFF/ON layer-level trace.

## File Counts By Category

- `bayesian_diagnostic`: 9
- `bayesian_primary_model`: 8
- `campaign_raw_summary`: 30
- `classifier_final_revalidation`: 2
- `classifier_stage1`: 5
- `classifier_stage2b_dev`: 36
- `direct_propagation`: 6
- `experiment_record`: 4
- `figure_asset`: 29
- `main_analysis_table`: 7
- `recovery_closed_loop_raw`: 68
- `recovery_layer_trace_w8_dropout`: 14
- `recovery_layer_trace_w8_masking`: 14
- `recovery_mission_outcome_audit`: 3
- `script`: 7
- `script_recovery_audit`: 1

## Core Thesis Evidence

1. Main fault campaign results: `02_fault12_analysis_tables/` and `03_figures_for_dissertation/thesis_figures_v4/`.
2. Bayesian thesis diagnostics: `04_bayesian_dissertation_diagnostics/bayesian_dissertation_diagnostics_report.md`.
3. Direct propagation tracing: `06_direct_propagation_tracing/`.
4. Classifier final-logic held-out validation: `05_classifier_evidence/stage2b_heldout_final_logic_revalidation/`.
5. Classifier/recovery record: `00_experiment_records/week_2026-08-10_to_08-16_classifier_recovery_record.md`.
6. Raw recovery/closed-loop logs: `07_classifier_recovery_closed_loop_raw/`.
7. Recovery mission-level outcome audit: `09_recovery_mission_outcome_analysis/recovery_mission_outcome_audit.md`.
8. Targeted dropout recovery layer trace: `10_recovery_layer_trace_w8_dropout/w8_dropout_recovery_layer_summary.md`.
9. Targeted masking recovery layer trace: `11_recovery_layer_trace_w8_masking/w8_masking_recovery_layer_summary.md`.

## Missing / VM-only Items

No expected items are currently marked missing.

## Manifest

Use `evidence_manifest.csv` to locate source paths, intended thesis use, file sizes, and hashes.
