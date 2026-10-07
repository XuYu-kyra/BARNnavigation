# ROS 2 Nav2 Fault Injection & Navigation Reliability

[English](#english) · [中文](#中文) · [Upstream BARN Challenge](https://github.com/Saadmaghani/The-Barn-Challenge-Ros2)

## English

This is an MSc Robotics dissertation framework for studying how controlled LiDAR degradation propagates through a ROS 2/Nav2 navigation stack: sensing → costmaps → planning → control → motion → mission outcome.

### The research story

“The robot succeeded” is not enough to describe reliability. A degraded scan may still produce a successful mission while causing extra replanning, stops, or a large completion-time penalty. I built an experiment and analysis pipeline that makes those hidden effects measurable and traceable.

### What I owned

- Parameterised ROS 2 fault injectors for frontal LiDAR masking and intermittent sector-level dropout.
- A resumable paired-campaign runner with process cleanup, timeout handling, structured logs, and reproducibility checks.
- Direct cross-layer tracing from `LaserScan` through costmap activity, planner/controller behaviour, `cmd_vel`, odometry-derived motion, and mission status.
- Paired comparisons, cluster-bootstrap confidence intervals, sensitivity analysis, and hierarchical Bayesian models for world-level heterogeneity.
- A lightweight conditional fault-type classifier and fault-specific recovery-policy prototypes.
- A curated dissertation evidence index, manifest, thesis figures, and scripts that connect every claim to an artefact.

### Result snapshot

Formal evaluation covered 216 paired runs across 9 BARN environments. On matched-success runs, frontal masking increased completion time by **5.97 s** (95% CI [3.36, 8.46], n=47); structured dropout increased it by **4.77 s** (95% CI [2.11, 7.03], n=40). A sensitivity analysis that assigned the 300 s cap to timeout/collision outcomes retained all 54 pairs and estimated +9.21 s and +6.43 s respectively.

The classifier identified 4/4 held-out validation episodes within a 2 s observation window in the small validation set, with zero wrong-type and zero unknown decisions. That result is reported as exploratory evidence, not as a production safety guarantee.

### Reproduce a representative run

```bash
source /opt/ros/jazzy/setup.bash
cd ~/dissertation/barn_ros2
colcon build --packages-select jackal_helper
source install/local_setup.bash

python3 tools/run_paired_fault_study.py \
  --world-idx 8 \
  --setup-path experiment_setups/tuned_clean \
  --log-dir manual_fault_runs/readme_smoke \
  --timeout 300 --fault-type scan --initial-pairs 1 --pair-step 1 --max-pairs 1 \
  --scan-fault-start 15 --scan-fault-duration 20 --scan-fault-mode mask \
  --scan-fault-center-deg 0 --scan-fault-width-deg 90
```

Repository map: `jackal_helper/` contains ROS 2 integration and fault nodes; `tools/` contains runners, analysis, Bayesian modelling, and figure builders; `fault_campaigns/` and `dissertation_evidence_index/` contain curated results and provenance.

### Limits and attribution

This is a controlled simulation study, not a production autonomous-safety system. Fault severities are experimental settings, and recovery components are lightweight exploratory prototypes. The BARN worlds and base simulation come from the upstream benchmark; the fault injection, orchestration, analysis, tracing, recovery experiments, and evidence curation are my dissertation work.

## 中文

这是一个 MSc Robotics 毕业论文级别的 ROS 2/Nav2 故障注入与导航可靠性研究框架，用来回答一个比“成功/失败”更重要的问题：LiDAR 退化究竟如何沿着 **传感器 → costmap → 规划器 → 控制器 → 机器人运动 → 任务结果** 传播？

### 项目故事

一次导航即使最终到达目标，也可能经历更多重规划、频繁停车或明显变慢。我搭建了成对实验、跨层追踪和统计分析流水线，把这些通常藏在日志里的可靠性变化变成可复核的证据。

### 我的工作

- 实现正面 LiDAR masking 与间歇扇区 dropout 的参数化 ROS 2 故障注入器；
- 实现可恢复的 paired campaign runner，处理超时、进程清理、结构化日志和复现实验检查；
- 从 `LaserScan` 一路追踪到 costmap、规划/控制行为、`cmd_vel`、里程计运动和任务状态；
- 使用配对比较、cluster bootstrap 置信区间、敏感性分析和分层 Bayesian 模型分析不同世界的异质性；
- 实现轻量级故障类型分类器和按故障类型选择恢复策略的探索性原型；
- 建立论文证据索引、manifest、图表生成脚本，让每个结论都能回到具体 artefact。

### 结果摘要

正式评估覆盖 9 个 BARN 环境、216 次 paired runs。在 matched-success 子集中，正面遮挡使完成时间增加 **5.97 秒**（95% CI [3.36, 8.46]，n=47），结构化 dropout 增加 **4.77 秒**（95% CI [2.11, 7.03]，n=40）。把超时/碰撞按 300 秒计入的敏感性分析保留全部 54 对样本，得到 +9.21 秒和 +6.43 秒。

在一个小规模留出验证集里，分类器在 2 秒观察窗口内识别出 4/4 个 episode，错误类型和 unknown 均为 0；这被定位为探索性结果，不是生产级安全保证。

### 复现实验

环境需要 ROS 2 Jazzy、Nav2、Gazebo 和对应的 BARN benchmark。可从上面的代表性命令开始，详细证据入口是 `fault_campaigns/`、`dissertation_evidence_index/` 和 `GITHUB_ARCHIVE_GUIDE.md`。

### 边界与署名

这是受控仿真研究，不应被描述为已经验证的自动驾驶安全系统；故障强度是实验参数，恢复模块也是轻量探索原型。BARN 世界和基础仿真来自上游项目，故障注入、实验编排、统计分析、跨层追踪、恢复实验和证据整理由我完成。
