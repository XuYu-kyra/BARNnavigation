# ROS 2 Nav2 Fault Injection & Navigation Reliability

[English](#english) · [中文](#中文) · [Upstream BARN Challenge](https://github.com/Saadmaghani/The-Barn-Challenge-Ros2)

**Tech stack:** ROS 2 Jazzy · Nav2 · Gazebo Harmonic · Clearpath Jackal · Python · PyMC · pandas/NumPy · BARN · statistical experimentation

## English

This repository contains my MSc Robotics dissertation work on a practical reliability question: when LiDAR data degrades, how does the effect propagate through sensing, costmaps, planning, control, robot motion, and the final navigation outcome?

### Research question and approach

A success flag hides a great deal of behaviour. A robot may still reach the goal after extra replanning, repeated stops, or a substantial time penalty. I therefore built a controlled, paired experiment pipeline that connects mission outcomes to intermediate signals instead of treating navigation as a black box.

```text
LaserScan -> costmaps -> planner/controller activity -> cmd_vel
          -> odometry-derived motion -> mission status -> statistical analysis
```

### My dissertation contribution

- Implemented parameterised ROS 2 injectors for frontal LiDAR masking and intermittent sector-level dropout.
- Built a resumable paired-campaign runner with timeout handling, process cleanup, structured logs, and reproducibility checks.
- Traced behaviour across layers, from scan data and costmaps to replanning, velocity commands, motion, and mission state.
- Analysed paired effects with cluster-bootstrap confidence intervals, sensitivity analysis, and hierarchical Bayesian models for world-level heterogeneity.
- Prototyped a lightweight conditional fault classifier and fault-specific recovery policies.
- Curated the evidence index, manifests, figures, and build scripts so that reported claims can be followed back to stored experiment outputs.

### Experimental design and results

The formal evaluation contains **108 matched experimental pairs, or 216 individual navigation runs**, across 9 BARN worlds. Each fault condition contributes 54 baseline-versus-fault pairs.

| Fault condition | Matched-success pairs | Mean completion-time increase | 95% bootstrap CI |
| --- | ---: | ---: | --- |
| Frontal masking | 47 | **+5.97 s** | [3.36, 8.46] |
| Structured LiDAR dropout | 40 | **+4.77 s** | [2.11, 7.03] |

A separate sensitivity analysis retained all 54 pairs per fault by assigning the 300 s cap to timeout/collision outcomes; it estimated +9.21 s for frontal masking and +6.43 s for dropout. These two analyses answer different questions and are intentionally reported separately.

In a small held-out validation set, the classifier identified 4/4 episodes within a 2 s observation window, with no wrong-type or unknown decisions. This is exploratory evidence from a limited set, not a production safety claim.

### Reproduce one paired run

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

### Where to inspect the evidence

- `jackal_helper/`: ROS 2 integration and fault-injection nodes.
- `tools/`: campaign runners, analysis, Bayesian modelling, and figure generation.
- `fault_campaigns/`: campaign definitions and selected outputs.
- `dissertation_evidence_index/`: curated tables, diagnostics, figures, classifier evidence, and provenance.
- `GITHUB_ARCHIVE_GUIDE.md`: map from dissertation claims to repository evidence.

### Scope and attribution

This is a controlled simulation study, not a validated autonomous-safety system. Fault severity is an experimental setting, and the recovery modules are exploratory prototypes. BARN worlds and the base simulation come from the upstream benchmark; the fault injection, experiment orchestration, cross-layer tracing, analysis, recovery experiments, and evidence curation are my dissertation work.

## 中文

这是我的 MSc Robotics 毕业论文项目，研究一个具体的导航可靠性问题：当 LiDAR 数据退化时，影响会怎样沿着 **传感器、costmap、规划、控制、机器人运动和最终任务结果** 逐层传播？

### 研究思路

只看“是否到达目标”会漏掉很多信息。机器人即使成功，也可能经历额外重规划、反复停车或明显的时间损失。因此我设计了受控的成对实验，把任务结果与中间层信号对应起来，而不是把 Nav2 当作黑盒。

### 我的工作

- 实现正面 LiDAR 遮挡和间歇扇区丢失的参数化 ROS 2 故障注入器；
- 编写可恢复的成对实验运行器，处理超时、进程清理、结构化日志和复现检查；
- 从 `LaserScan`、costmap、规划/控制行为一路追踪到 `cmd_vel`、里程计运动和任务状态；
- 使用配对比较、cluster bootstrap 置信区间、敏感性分析和分层 Bayesian 模型分析故障影响及不同环境的差异；
- 实现轻量级故障类型分类器和按故障类型选择策略的恢复原型；
- 整理论文证据索引、manifest、图表和生成脚本，让结论可以回溯到具体实验文件。

### 实验规模与结果

正式评估覆盖 9 个 BARN 世界，共 **108 组成对实验、216 次独立导航运行**；两种故障各包含 54 组 baseline-versus-fault 对照。

| 故障 | 同为成功的配对数 | 平均完成时间增量 | 95% bootstrap CI |
| --- | ---: | ---: | --- |
| 正面遮挡 | 47 | **+5.97 秒** | [3.36, 8.46] |
| 结构化 LiDAR dropout | 40 | **+4.77 秒** | [2.11, 7.03] |

另一组敏感性分析把超时/碰撞按 300 秒上限计入，因此每种故障都保留全部 54 对样本；对应估计为 +9.21 秒和 +6.43 秒。两组数字的统计口径不同，所以在这里分开说明。

小规模留出验证中，分类器在 2 秒观察窗口内识别出 4/4 个 episode，未出现错误类型或 unknown；这只是有限样本上的探索性结果，不代表生产级安全保证。

### 复现与证据

上面的命令可运行一组代表性成对实验。ROS 2 实现位于 `jackal_helper/`，实验与分析脚本位于 `tools/`，结果和来源记录位于 `fault_campaigns/` 与 `dissertation_evidence_index/`；`GITHUB_ARCHIVE_GUIDE.md` 提供论文结论到仓库文件的索引。

### 边界与署名

这是受控仿真研究，不是已经通过真实道路或生产安全验证的自动导航系统。BARN 世界和基础仿真来自上游 benchmark；故障注入、实验编排、跨层追踪、统计分析、恢复实验和证据整理由我完成。
