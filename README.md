# ROS 2 Nav2 Fault Injection & Navigation Reliability

**MSc Robotics dissertation on how LiDAR degradation propagates through a ROS 2 navigation stack**

[English](#english) · [中文](#中文) · [Evidence index](dissertation_evidence_index/) · [Upstream BARN Challenge](https://github.com/Saadmaghani/The-Barn-Challenge-Ros2)

| Experimental scope | Fault models | Primary result |
| --- | --- | --- |
| **108 matched pairs / 216 navigation runs** across 9 BARN worlds | Frontal masking and intermittent sector dropout | Successful runs still incurred mean completion-time increases of **5.97 s** and **4.77 s** |

---

## English

### Research question

A navigation system can still report success while becoming slower, less stable, or more dependent on replanning. This dissertation asks a more useful reliability question:

> When LiDAR data degrades, how does the effect propagate from sensing into costmaps, planning, control, robot motion, and the final mission outcome?

I built a controlled fault-injection and experiment pipeline around ROS 2 Nav2 and the BARN benchmark. Instead of evaluating navigation as a single success/failure flag, the project connects mission-level outcomes to intermediate system behaviour.

```text
LaserScan
    ↓
global / local costmaps
    ↓
planner and controller activity
    ↓
cmd_vel
    ↓
odometry-derived motion
    ↓
mission outcome and completion time
    ↓
paired and hierarchical statistical analysis
```

### What I built

This repository contains the engineering and experimental work completed for my MSc Robotics dissertation:

- **Parameterised ROS 2 fault injection:** implemented frontal LiDAR masking and intermittent sector-level dropout with configurable onset, duration, angle, width, period, and duty cycle.
- **Paired experiment orchestration:** built a runner that randomises baseline/fault order within each pair, enforces timeouts, clears stale ROS/Gazebo processes, samples resource usage, and resumes campaigns without losing completed work.
- **Cross-layer observability:** traced scan behaviour, costmap responses, planner/controller activity, velocity commands, odometry motion, stop intervals, and final mission state.
- **Statistical analysis:** compared paired outcomes with cluster-bootstrap confidence intervals, timeout-aware sensitivity analysis, and hierarchical Bayesian models for world-level heterogeneity.
- **Fault classification and recovery exploration:** implemented a lightweight conditional classifier and fault-specific recovery prototypes, then evaluated them with held-out episodes and layer-level traces.
- **Evidence engineering:** curated manifests, analysis tables, figures, diagnostics, source paths, and regeneration scripts so that dissertation claims can be traced back to stored outputs.

The project therefore combines ROS 2 integration, experiment automation, system-level debugging, statistical modelling, and reproducible research practice.

### Experimental design

The formal study uses matched baseline-versus-fault pairs. Both runs in a pair use the same BARN world and navigation setup; the condition order is randomised to reduce ordering effects.

| Design element | Implementation |
| --- | --- |
| Environment | 9 selected BARN worlds in Gazebo Harmonic |
| Robot and navigation | Clearpath Jackal with ROS 2 Jazzy and Nav2 |
| Fault 1 | Persistent frontal LiDAR masking |
| Fault 2 | Intermittent structured dropout in a configurable scan sector |
| Pairing | Baseline and fault runs matched within each world/repetition |
| Campaign size | 54 pairs per fault, 108 pairs in total |
| Individual runs | 216 navigation runs |
| Primary comparison | Completion-time difference among pairs where both runs succeeded |
| Sensitivity comparison | All pairs retained, with timeout/collision outcomes assigned the 300 s cap |

Pairing makes each run serve as a control for the same environment. The campaign runner records attempt history separately from accepted runs, allowing failed launches or invalid attempts to be audited without silently entering the analysis.

### Results

#### Primary matched-success analysis

| Fault condition | Matched-success pairs | Mean completion-time increase | 95% cluster-bootstrap CI |
| --- | ---: | ---: | --- |
| Frontal masking | 47 | **+5.97 s** | [3.36, 8.46] |
| Structured LiDAR dropout | 40 | **+4.77 s** | [2.11, 7.03] |

The result is important because both rows contain only pairs where the robot reached the goal in baseline and fault conditions. The faults therefore imposed measurable mission cost even when the top-level outcome remained “success.”

#### Timeout-aware sensitivity analysis

The sensitivity analysis retains all 54 pairs for each fault by assigning the 300 s campaign cap to timeout or collision outcomes:

- frontal masking: **+9.21 s**;
- structured dropout: **+6.43 s**.

The primary and sensitivity estimates answer different questions. The first isolates degradation among matched successful missions; the second includes the cost of severe outcomes. They are reported separately rather than mixed into one headline number.

#### Exploratory classifier result

In a small held-out validation set, the conditional classifier identified **4/4 episodes within a 2 s observation window**, with no wrong-type or unknown decisions. This result is reported as limited-sample exploratory evidence and is linked to the stored validation artifacts.

### Engineering decisions

#### Evaluate the propagation path, not only the endpoint

A binary mission result cannot distinguish a clean traversal from one with repeated stops, delayed planning, or recovery behaviour. Collecting signals at each layer makes it possible to locate where degradation first becomes visible and how it reaches the mission outcome.

#### Pair runs within the same world

BARN environments vary substantially in geometry and difficulty. Matched baseline/fault pairs reduce between-world variation and make the measured difference more directly attributable to the injected condition.

#### Separate primary and sensitivity estimands

Dropping timeout and collision outcomes would hide the most severe effects, while replacing them with a cap changes the meaning of the estimate. Keeping both analyses explicit avoids conflating “delay among successful missions” with “overall campaign cost.”

#### Treat evidence provenance as part of the system

The repository preserves accepted-run summaries, attempt histories, manifests, hashes, figures, and regeneration scripts. This turns the dissertation from a collection of plots into an auditable experiment record.

### Technology stack

| Technology | Role in this project |
| --- | --- |
| **ROS 2 Jazzy / rclpy / rclcpp** | Fault-injection nodes, recovery prototypes, topic instrumentation, and experiment integration |
| **Nav2** | Planning, control, costmaps, lifecycle management, and navigation mission execution |
| **Gazebo Harmonic / ros_gz** | Physics simulation and ROS–Gazebo integration |
| **Clearpath Jackal** | Mobile-robot platform used by the benchmark setup |
| **BARN** | Procedurally generated navigation environments and benchmark tasks |
| **Python** | Campaign orchestration, process management, logging, analysis, and figure generation |
| **pandas / NumPy / SciPy** | Paired summaries, trace processing, sensitivity analysis, and descriptive statistics |
| **PyMC / ArviZ** | Hierarchical Bayesian modelling and convergence/posterior diagnostics |
| **rosbag2 / MCAP** | Time-aligned cross-layer traces for selected fault and recovery episodes |
| **colcon / ament** | Building and packaging the ROS 2 workspace |

### Reproduce one paired experiment

```bash
source /opt/ros/jazzy/setup.bash
cd ~/dissertation/barn_ros2

colcon build --packages-select jackal_helper
source install/local_setup.bash

python3 tools/run_paired_fault_study.py \
  --world-idx 8 \
  --setup-path experiment_setups/tuned_clean \
  --log-dir manual_fault_runs/readme_smoke \
  --timeout 300 \
  --fault-type scan \
  --initial-pairs 1 \
  --pair-step 1 \
  --max-pairs 1 \
  --scan-fault-start 15 \
  --scan-fault-duration 20 \
  --scan-fault-mode mask \
  --scan-fault-center-deg 0 \
  --scan-fault-width-deg 90
```

The runner creates structured outputs for run status, timing, process/resource observations, and paired evaluation. Campaign-level scripts under `tools/` aggregate accepted runs and regenerate the statistical tables and figures.

### Evidence map

| Path | Contents |
| --- | --- |
| `jackal_helper/` | ROS 2 integration, launch files, fault injectors, classifier nodes, and recovery prototypes |
| `tools/` | Campaign runners, parsers, statistical analysis, Bayesian models, audits, and figure generation |
| `experiment_setups/` | Original and tuned navigation configurations used by experiments |
| `fault_campaigns/` | Campaign definitions, accepted-run summaries, attempt histories, and per-world outputs |
| `dissertation_evidence_index/` | Curated thesis tables, figures, Bayesian diagnostics, classifier evidence, recovery traces, and manifest |
| `GITHUB_ARCHIVE_GUIDE.md` | Repository/archive strategy and map of long-term evidence |

### Attribution

The BARN environments and base ROS 2 simulation originate from the [upstream BARN Challenge repository](https://github.com/Saadmaghani/The-Barn-Challenge-Ros2). My dissertation work covers the fault models, ROS 2 injection and recovery nodes, experiment orchestration, cross-layer instrumentation, statistical analysis, classifier/recovery experiments, and evidence curation described above.

---

## 中文

### 研究问题

导航任务显示“成功”，并不代表系统在整个过程中都保持稳定。机器人可能经历额外重规划、反复停车、控制振荡或明显的时间损失，最后仍然到达目标。

因此，我的 MSc Robotics 毕业论文没有只比较成功率，而是研究一个更具体的可靠性问题：

> 当 LiDAR 数据发生退化时，这种影响会怎样从传感器进入 costmap、规划与控制，并最终反映到机器人运动和任务结果中？

我围绕 ROS 2 Nav2 和 BARN benchmark 搭建了受控故障注入与成对实验流水线，把导航任务拆成一条可观察的传播链：

```text
LaserScan
    ↓
全局 / 局部 costmap
    ↓
规划器与控制器活动
    ↓
cmd_vel
    ↓
由里程计计算的实际运动
    ↓
任务状态与完成时间
    ↓
成对统计与分层 Bayesian 分析
```

### 我完成的工作

这个仓库保存了我在毕业论文中完成的工程实现、实验设计和分析工作：

- **ROS 2 参数化故障注入**：实现正面 LiDAR 遮挡和间歇扇区 dropout，可配置开始时间、持续时间、中心角度、扇区宽度、周期和 duty cycle。
- **成对实验编排**：编写 baseline/fault 成对运行器，在每一对内部随机条件顺序，同时处理超时、残留 ROS/Gazebo 进程、资源采样、日志落盘和断点恢复。
- **跨层可观测性**：从扫描数据、costmap、规划/控制活动一路追踪到速度指令、里程计运动、停车区间和最终任务状态。
- **统计分析**：使用配对差值、cluster bootstrap 置信区间、包含超时的敏感性分析，以及刻画不同世界差异的分层 Bayesian 模型。
- **分类与恢复探索**：实现轻量级条件分类器和按故障类型选择的恢复原型，并通过留出 episode 与层级 trace 检查其行为。
- **证据工程**：整理 manifest、分析表、图表、诊断结果、来源路径和再生成脚本，使论文结论能够回溯到具体实验输出。

这个项目不仅体现 ROS 2 节点开发，也覆盖实验自动化、系统级调试、统计建模和可复现研究。

### 实验设计

正式实验采用 baseline-versus-fault 匹配设计。同一组 pair 使用相同 BARN 世界和导航配置，只改变是否注入故障；pair 内的运行顺序随机化，以降低顺序效应。

| 设计要素 | 具体设置 |
| --- | --- |
| 实验环境 | Gazebo Harmonic 中的 9 个 BARN 世界 |
| 机器人与导航 | Clearpath Jackal、ROS 2 Jazzy 与 Nav2 |
| 故障 1 | 持续的正面 LiDAR 遮挡 |
| 故障 2 | 指定扫描扇区内的间歇结构化 dropout |
| 配对方式 | 同一世界、同一 repetition 下匹配 baseline 与 fault |
| 每种故障 | 54 组配对实验 |
| 总实验规模 | **108 组 pair，即 216 次独立导航运行** |
| 主分析 | baseline 与 fault 均成功的 pair，其完成时间差 |
| 敏感性分析 | 保留全部 pair，将超时/碰撞按 300 秒上限计入 |

成对设计让每一次故障运行都拥有相同环境下的对照，减少不同世界难度带来的混淆。运行器还将所有尝试记录与最终接受的运行分开保存，因此启动失败或无效尝试可以审计，但不会无声进入正式统计。

### 主要结果

#### 同为成功任务的配对分析

| 故障条件 | 同为成功的配对数 | 平均完成时间增量 | 95% cluster-bootstrap CI |
| --- | ---: | ---: | --- |
| 正面 LiDAR 遮挡 | 47 | **+5.97 秒** | [3.36, 8.46] |
| 结构化 LiDAR dropout | 40 | **+4.77 秒** | [2.11, 7.03] |

这里比较的 pair 都是在 baseline 和 fault 条件下成功到达目标的任务。结果说明，即使顶层状态仍然是“成功”，传感器退化也会形成可测量的任务代价。仅报告成功率会漏掉这类可靠性下降。

#### 包含严重结果的敏感性分析

敏感性分析将超时或碰撞按 300 秒 campaign 上限计入，因此每种故障都保留完整的 54 组 pair：

- 正面遮挡：平均增加 **9.21 秒**；
- 结构化 dropout：平均增加 **6.43 秒**。

主分析衡量的是“成功任务中的额外时间”，敏感性分析衡量的是“把严重结果也包含在内的总体任务代价”。两组数字回答的问题不同，因此单独报告，而不是混成一个更醒目的结论。

#### 探索性分类结果

在小规模留出验证中，条件分类器在 **2 秒观察窗口内识别出 4/4 个 episode**，没有出现错误类型或 unknown。该结果作为有限样本上的探索性证据呈现，并可从仓库中的验证产物回溯。

### 关键工程判断

#### 1. 不只观察终点，而是追踪传播路径

任务成功/失败无法区分一次平稳导航与一次包含反复停车、规划延迟或恢复行为的导航。跨层采集让问题可以被定位到首次出现异常的系统层，并进一步观察它怎样影响最终任务。

#### 2. 在同一世界内配对

BARN 世界的几何结构和难度差异很大。让 baseline 和 fault 在同一环境、同一 repetition 下匹配，可以减少世界间差异，使测得的变化更接近故障本身造成的影响。

#### 3. 分开报告主分析与敏感性分析

直接删除超时和碰撞会忽略最严重的结果；用上限值替代又会改变统计量的含义。因此项目保留两种 estimand：一个回答成功任务受到多少影响，另一个回答包含严重结果时的整体代价。

#### 4. 把证据来源当作系统的一部分

仓库不仅保存最终图表，还保存 accepted-run summary、attempt history、manifest、hash、诊断输出和再生成脚本。这样，论文中的数字不是孤立结果，而是一条能够从结论回到原始实验文件的证据链。

### 技术栈

| 技术 | 在项目中的作用 |
| --- | --- |
| **ROS 2 Jazzy / rclpy / rclcpp** | 故障注入节点、恢复原型、topic 观测和实验系统集成 |
| **Nav2** | 规划、控制、costmap、lifecycle 管理和导航任务执行 |
| **Gazebo Harmonic / ros_gz** | 物理仿真及 ROS–Gazebo 数据桥接 |
| **Clearpath Jackal** | BARN 实验使用的移动机器人平台 |
| **BARN** | 提供程序化生成的导航环境与 benchmark 任务 |
| **Python** | campaign 编排、进程管理、日志处理、统计分析与图表生成 |
| **pandas / NumPy / SciPy** | 配对结果、trace 处理、敏感性分析和描述性统计 |
| **PyMC / ArviZ** | 分层 Bayesian 建模、收敛诊断和 posterior 检查 |
| **rosbag2 / MCAP** | 保存并对齐典型故障与恢复 episode 的跨层 trace |
| **colcon / ament** | 构建和组织 ROS 2 workspace |

### 复现一组成对实验

```bash
source /opt/ros/jazzy/setup.bash
cd ~/dissertation/barn_ros2

colcon build --packages-select jackal_helper
source install/local_setup.bash

python3 tools/run_paired_fault_study.py \
  --world-idx 8 \
  --setup-path experiment_setups/tuned_clean \
  --log-dir manual_fault_runs/readme_smoke \
  --timeout 300 \
  --fault-type scan \
  --initial-pairs 1 \
  --pair-step 1 \
  --max-pairs 1 \
  --scan-fault-start 15 \
  --scan-fault-duration 20 \
  --scan-fault-mode mask \
  --scan-fault-center-deg 0 \
  --scan-fault-width-deg 90
```

运行器会保存任务状态、完成时间、进程/资源观测和配对评估结果；`tools/` 中的 campaign 分析脚本用于汇总 accepted runs，并重新生成论文中的统计表和图。

### 证据索引

| 路径 | 内容 |
| --- | --- |
| `jackal_helper/` | ROS 2 集成、launch 文件、故障注入器、分类节点和恢复原型 |
| `tools/` | campaign runner、解析器、统计分析、Bayesian 模型、审计和绘图脚本 |
| `experiment_setups/` | 实验使用的原始与调优导航配置 |
| `fault_campaigns/` | campaign 定义、accepted-run 汇总、attempt history 和各世界输出 |
| `dissertation_evidence_index/` | 论文表格、图表、Bayesian 诊断、分类器证据、恢复 trace 和 manifest |
| `GITHUB_ARCHIVE_GUIDE.md` | 仓库归档策略与长期证据组织说明 |

### 来源说明

BARN 环境和基础 ROS 2 仿真来自 [The BARN Challenge ROS 2](https://github.com/Saadmaghani/The-Barn-Challenge-Ros2)。本论文中的故障模型、ROS 2 注入与恢复节点、实验编排、跨层观测、统计分析、分类/恢复实验和证据整理均由我完成。

