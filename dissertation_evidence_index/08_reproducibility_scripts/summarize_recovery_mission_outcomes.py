#!/usr/bin/env python3
"""Summarize mission-level outcomes for recovery / closed-loop pilot logs.

This intentionally reports what can be claimed from logs:
- whether a recovery/policy branch was enabled or executed;
- final navigation status, completion time, and metric;
- whether the run has no final BARN outcome in the copied log.

It does not infer performance improvement unless a matched baseline is explicitly
available elsewhere.
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
OUTCOME_RE = re.compile(r"Navigation (succeeded|timeout|collided) with time ([0-9.]+) \(s\)")
METRIC_RE = re.compile(r"Navigation metric: ([0-9.]+)")
WORLD_RE = re.compile(r"world[_-]0*(\d+)|world_idx[:=](\d+)|/world_0*(\d+)/")

POLICY_PATTERNS = {
    "classifier_policy_selected": "policy_selected:",
    "dropout_filter_enabled": "Dropout recovery filter enabled by selector",
    "dropout_filter_active": "Dropout recovery filter active",
    "masking_policy_enabled": "Nav2 masking recovery policy enabled by selector",
    "masking_policy_monitoring_started": "Nav2 masking recovery monitoring started",
    "masking_nav2_recovery_started": "Nav2 masking recovery started",
    "masking_reorientation_started": "Masking reorientation recovery started",
    "masking_reorientation_complete": "Masking reorientation recovery complete",
    "goal_failed": "Goal failed",
    "progress_failure": "Failed to make progress",
    "fault_active": "Fault active",
    "fault_type_estimated": "fault_type_estimated:",
}


def clean(text: str) -> str:
    return ANSI_RE.sub("", text)


def infer_world(path: Path, text: str) -> str:
    haystack = f"{path}\n{text[:20000]}"
    m = WORLD_RE.search(haystack)
    if not m:
        return ""
    return next(g for g in m.groups() if g)


def infer_fault(path: Path, text: str) -> str:
    # Prefer filename semantics; parent directories may contain both fault names.
    name = path.name.lower()
    if "dropout" in name:
        return "dropout"
    if "masking" in name or "mask" in name:
        return "masking"
    lower = text.lower()
    if "mode=dropout" in lower or "cycling frontal sector dropout" in lower:
        return "dropout"
    if "mode=mask" in lower or "replacing frontal sector scan ranges continuously" in lower:
        return "masking"
    return "unknown"


def infer_recovery_type(path: Path, text: str, selected_policy: str, flags: dict[str, str]) -> str:
    lower = f"{path} {text}".lower()
    if "no_recovery" in lower or "fault_only" in lower:
        return "none_fault_only"
    if selected_policy == "dropout_scan_filter" or flags["dropout_filter_enabled"] == "True" or flags["dropout_filter_active"] == "True":
        return "dropout_scan_filter_enabled"
    if flags["masking_nav2_recovery_started"] == "True":
        return "masking_nav2_supervisor_action_started"
    if selected_policy == "masking_nav2_recovery" or flags["masking_policy_enabled"] == "True":
        return "masking_nav2_supervisor_policy_enabled"
    if flags["masking_reorientation_started"] == "True":
        return "masking_cmdvel_reorientation_action_started"
    return "no_recovery_policy_enabled"


def infer_timing(path: Path, text: str) -> str:
    name = path.name.lower()
    lower = f"{path} {text}".lower()
    if "start5" in name or "start=5" in lower or "start=5.0" in lower:
        return "start5_duration20"
    if "start15" in name or "start=15" in lower or "start=15.0" in lower:
        return "start15_duration20"
    if "persistent" in lower:
        return "persistent"
    return "unspecified"


def parse_log(path: Path) -> dict[str, str]:
    text = clean(path.read_text(errors="replace"))
    outcome = "no_final_outcome"
    completion_time = ""
    metric = ""
    for m in OUTCOME_RE.finditer(text):
        outcome = m.group(1)
        completion_time = m.group(2)
    for m in METRIC_RE.finditer(text):
        metric = m.group(1)
    if outcome == "no_final_outcome" and "Goal failed" in text:
        outcome = "goal_failed"

    flags = {name: str(pattern in text) for name, pattern in POLICY_PATTERNS.items()}
    predicted_type = ""
    selected_policy = ""
    m = re.search(r"fault_type_estimated: predicted_type=([A-Z_]+)", text)
    if m:
        predicted_type = m.group(1)
    m = re.search(r"policy_selected: predicted_type=[A-Z_]+, selected_policy=([^,\.]+)", text)
    if m:
        selected_policy = m.group(1)

    progress_failure_count = text.count("Failed to make progress")
    dropout_active_count = text.count("Dropout recovery filter active")

    return {
        "relative_log": "",
        "world_idx": infer_world(path, text),
        "fault": infer_fault(path, text),
        "timing": infer_timing(path, text),
        "condition": "baseline" if "baseline" in path.name.lower() else ("fault" if "fault" in path.name.lower() else "single_run"),
        "recovery_type": infer_recovery_type(path, text, selected_policy, flags),
        "predicted_type": predicted_type,
        "selected_policy": selected_policy,
        "fault_active_logged": flags["fault_active"],
        "classifier_policy_selected": flags["classifier_policy_selected"],
        "dropout_filter_enabled": flags["dropout_filter_enabled"],
        "dropout_filter_active": flags["dropout_filter_active"],
        "dropout_filter_active_count": str(dropout_active_count),
        "masking_policy_enabled": flags["masking_policy_enabled"],
        "masking_policy_monitoring_started": flags["masking_policy_monitoring_started"],
        "masking_nav2_recovery_started": flags["masking_nav2_recovery_started"],
        "masking_reorientation_started": flags["masking_reorientation_started"],
        "masking_reorientation_complete": flags["masking_reorientation_complete"],
        "progress_failure_count": str(progress_failure_count),
        "goal_failed_logged": flags["goal_failed"],
        "mission_outcome": outcome,
        "completion_time_s": completion_time,
        "nav_metric": metric,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-root", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    args = ap.parse_args()

    logs = sorted(args.log_root.rglob("*.log"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for log in logs:
        row = parse_log(log)
        row["relative_log"] = str(log.relative_to(args.log_root))
        rows.append(row)

    fieldnames = [
        "relative_log", "world_idx", "fault", "condition", "timing", "recovery_type",
        "predicted_type", "selected_policy", "fault_active_logged",
        "classifier_policy_selected", "dropout_filter_enabled", "dropout_filter_active",
        "dropout_filter_active_count", "masking_policy_enabled",
        "masking_policy_monitoring_started", "masking_nav2_recovery_started",
        "masking_reorientation_started",
        "masking_reorientation_complete", "progress_failure_count", "goal_failed_logged",
        "mission_outcome", "completion_time_s", "nav_metric",
    ]
    csv_path = args.output_dir / "recovery_mission_outcomes.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_recovery = defaultdict(Counter)
    by_fault_recovery = defaultdict(Counter)
    for r in rows:
        by_recovery[r["recovery_type"]][r["mission_outcome"]] += 1
        by_fault_recovery[(r["fault"], r["recovery_type"])][r["mission_outcome"]] += 1

    md = []
    md.append("# Recovery Mission-Level Outcome Audit")
    md.append("")
    md.append("This audit parses copied recovery/closed-loop logs and reports final task outcomes only. It does not claim recovery improvement unless matched no-recovery baselines exist for the same world/fault/timing setup.")
    md.append("")
    md.append(f"Parsed logs: {len(rows)}")
    md.append("")
    md.append("## Outcome Counts By Recovery Type")
    md.append("")
    md.append("| Recovery type | succeeded | timeout | collided | goal_failed | no_final_outcome |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for rec, c in sorted(by_recovery.items()):
        md.append(f"| {rec} | {c['succeeded']} | {c['timeout']} | {c['collided']} | {c['goal_failed']} | {c['no_final_outcome']} |")
    md.append("")
    md.append("## Outcome Counts By Fault And Recovery Type")
    md.append("")
    md.append("| Fault | Recovery type | succeeded | timeout | collided | goal_failed | no_final_outcome |")
    md.append("|---|---|---:|---:|---:|---:|---:|")
    for (fault, rec), c in sorted(by_fault_recovery.items()):
        md.append(f"| {fault} | {rec} | {c['succeeded']} | {c['timeout']} | {c['collided']} | {c['goal_failed']} | {c['no_final_outcome']} |")
    md.append("")
    md.append("## Interpretation Boundary")
    md.append("")
    md.append("- Mission-level outcome can be checked directly from `Navigation succeeded/timeout/collided`, completion time, and navigation metric.")
    md.append("- A run with `policy_selected` or `filter enabled` plus successful navigation proves the recovery branch was operational, not that it improved performance.")
    md.append("- To prove mission-level improvement, compare matched conditions: same world, same fault mode, same timing, same timeout, with recovery disabled vs enabled, ideally with paired repeats.")
    md.append("- Existing logs support a mission-level audit and functional branch evidence; they do not yet form a rigorous recovery-effectiveness campaign.")
    md_path = args.output_dir / "recovery_mission_outcome_audit.md"
    md_path.write_text("\n".join(md) + "\n")

    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
