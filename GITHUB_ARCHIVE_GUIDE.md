# GitHub Archive Guide

This repository is intended to preserve the ROS 2/Nav2 fault-injection project in a form that is easy to inspect, rebuild, and cite later. Keep the git repository focused on source code, experiment configuration, lightweight analysis outputs, and curated thesis evidence. Keep large transfer bundles and raw archives outside normal git history, or attach them to a GitHub Release.

## What Should Go Into Git

- `jackal_helper/`: modified ROS 2 launch files, Nav2 integration, fault injectors, classifier nodes, and recovery prototype nodes.
- `tools/`: experiment runners, campaign summarizers, analysis scripts, Bayesian scripts, classifier builders, and figure-generation scripts.
- `experiment_setups/`: `original_clean` and `tuned_clean` configuration used for the experiments.
- `docs/`: design notes and methodology notes.
- `fault_campaigns/`: formal campaign logs, per-world summaries, parsed CSV outputs, and thesis analysis tables. No file currently exceeds the normal GitHub single-file limit.
- `dissertation_evidence_index/`: curated dissertation evidence index, including final figures, campaign summaries, Bayesian diagnostics, classifier evidence, direct-propagation outputs, recovery summaries, and a manifest.
- `BARN_structure_analysis.md`, `BARN_week_plan.md`, and experiment-record markdown files if you want the project history preserved.

## What Should Not Go Into Git

The `.gitignore` intentionally excludes these:

- `.venv*/`: local Python environments, including PyMC dependencies.
- `build/`, `install/`, `log/`: generated ROS 2/colcon output.
- `_raw_imports/`: unpacked transfer workspace used to build the curated evidence index.
- `*.zip`, `*.tar.gz`: transfer bundles and raw-data archives.
- `*.docx`, `*.pptx`, `*.pdf`: office/export files that are better stored as final submission artifacts or release assets.
- `*.sif`: Singularity images.

## Archive Bundles To Keep Outside Git

These files should be retained locally and/or uploaded as GitHub Release assets:

- `baseline_selection_original0-299_tune0-299_full.tar.gz`
- `direct_propagation_trace_start5_for_plotting.tar.gz`
- `recovery_layer_trace_w8_dropout_v2.tar.gz`
- `recovery_layer_trace_w8_masking.tar.gz`
- `fault_campaigns.zip`
- `dissertation_evidence_index_2026-08-16.zip`
- `week_recovery_classifier_evidence.zip`
- `methodological_cleanup_evidence_2026-08-16.zip`
- `classifier_final_logic_revalidation.zip`

The key raw rosbag MCAP files are already preserved inside the direct-propagation and recovery-layer trace tarballs above. The curated, lightweight outputs are in `dissertation_evidence_index/`.

## Recommended Repository Setup

Create a new GitHub repository under your own account, then replace or add a remote from this local repository:

```bash
cd ~/dissertation/barn_ros2

git remote rename origin upstream
git remote add origin git@github.com:<your-user>/<your-repo>.git
git remote -v
```

If you prefer HTTPS:

```bash
git remote add origin https://github.com/<your-user>/<your-repo>.git
```

## Recommended Commit

Check what will be committed:

```bash
git status --short
git add .gitignore README.md GITHUB_ARCHIVE_GUIDE.md docs experiment_setups tools jackal_helper fault_campaigns dissertation_evidence_index
git status --short
```

Then commit:

```bash
git commit -m "Archive dissertation fault-injection experiments"
git push -u origin master
```

## Optional Release Upload

After the first push, create a GitHub Release such as `dissertation-evidence-archive-2026`. Attach the large `.tar.gz` and `.zip` files listed above. This keeps the git clone lightweight while preserving the raw evidence needed for long-term reproducibility.

## Sanity Checks Before Pushing

Run these checks before the final push:

```bash
git status --short
find . -type f -size +90M -not -path './.git/*' -print
```

The second command should print nothing except ignored local virtual-environment files. If it prints a tracked project file, do not push until it is moved to a Release asset or ignored deliberately.
