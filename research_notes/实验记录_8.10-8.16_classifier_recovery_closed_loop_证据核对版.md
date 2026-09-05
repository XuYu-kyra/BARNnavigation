# 8.10-8.16 实验记录：Classifier, Recovery, Closed-loop Integration（证据核对版）

记录日期：2026-08-16  
项目环境：ROS 2 Jazzy, Nav2, Gazebo/BARN, Jackal platform  
工作空间：`~/dissertation/barn_ros2`  
TBCR 路径：`~/dissertation/barn_ros2/src/The-Barn-Challenge-Ros2`  
证据 zip：`~/dissertation/barn_ros2/week_recovery_classifier_evidence.zip`

## 0. 本周工作的定位

8 月 10 日之前，项目已经完成两个 LiDAR fault 的 formal injection campaign 和论文级别数据分析：

| Item | Status |
|---|---|
| Fault 1 | Frontal LiDAR sector masking |
| Fault 2 | Intermittent LiDAR dropout |
| Worlds | 9 selected BARN worlds |
| Repetition | 6 paired runs per world per fault |
| Main analysis | matched-success slowdown, bootstrap CI, Bayesian/hierarchical model, world heterogeneity, pipeline proxy metrics |

8 月 10 日之后，本周工作的目标不再是继续扩展更多 fault，而是回答三个后续问题：

1. 两种 LiDAR fault 能否被系统在线区分？
2. fault type 能否自动路由到对应 fault-aware policy？
3. recovery prototype 做过哪些尝试，结果和限制是什么？

本周最终结论需要严格限定：

| Component | Final status | Claim boundary |
|---|---|---|
| Stage 2B conditional classifier | implemented and validated on development + held-out episodes | 可以说 fault-type identification 在当前两个 LiDAR fault 上可行；不能说 full autonomous fault diagnosis 已完全证明 |
| Masking recovery prototypes | implemented, but task-level benefit not demonstrated | 可以作为 recovery exploration / limitation evidence |
| Dropout recovery filter | implemented and can be enabled by selector | 只证明 branch 可执行，不证明普遍 performance improvement |
| Closed-loop integration | W8 masking + W8 dropout two-branch smoke test passed | 证明 classifier → selector → policy wiring 打通；不证明 cross-world recovery effectiveness |
| W240 extra runs | retained as stress/sanity observations | 不作为 closed-loop validation 的核心证据 |

## 1. 研究计划如何调整

### 1.1 原始思路

原本计划是：

```text
persistent fault pilot
→ recovery pilot
→ maybe expand recovery campaign
```

但实际实验发现：persistent masking/dropout 并没有稳定制造“必须 recovery 才能成功”的场景。很多 world 在 persistent fault 下仍然能成功。因此，如果强行把 recovery 写成 performance improvement，会很弱。

### 1.2 本周实际采用的主线

最终调整为更清晰的工程研究链条：

```text
Stage 0: injector semantics audit
→ Stage 1: scan signature diagnostics
→ Stage 2A: autonomous classifier attempt
→ Stage 2B: conditional episode-level fault classifier
→ fault-specific recovery prototype
→ closed-loop classifier-to-policy integration smoke test
```

这样每个实验回答一个明确问题：

| Experiment | Main question |
|---|---|
| Stage 0 | fault 在 ROS graph 和 scan message 中到底怎么表现？ |
| Stage 1 | masking/dropout 的 scan signature 是否可分离？ |
| Stage 2A | 完全 autonomous scan-only classifier 是否可靠？ |
| Stage 2B | 给定 fault-presence trigger 后，能否判断 fault type？ |
| Recovery prototypes | 对应 recovery action 是否能执行？ |
| Closed-loop smoke | classifier 输出能否自动选择 policy？ |

这个边界很重要：本周不是证明 recovery 已经有效，而是完成从 fault identification 到 policy selection 的可执行 pipeline，并记录 recovery prototype 的失败和限制。

## 2. Persistent fault characterisation

### 2.1 为什么做 persistent fault

老师可能会质疑 transient 20s fault：如果现实中的 masking 是 dirt / mud / water droplets / foreign object blocking LiDAR，为什么 fault 20 秒后自动消失？

因此将 fault duration 分成两类：

| Study | Fault duration | Purpose |
|---|---|---|
| Study A: transient campaign | active 15-35s | 研究 fault propagation 和 performance degradation |
| Study B: persistent pilot | active from fault start until success/timeout | 作为 recovery stress condition，观察 fault 不自行消失时系统如何表现 |

这不是替代 formal campaign，而是补充回答 duration justification。

### 2.2 参数设置与 justification

| Parameter | Value | Why |
|---|---:|---|
| transient start | 15s | 避免污染 Nav2/Gazebo 初始化，同时足够早影响导航过程 |
| transient duration | 20s | 作为短时外部扰动，用于 propagation/performance characterisation，而不是永久损坏建模 |
| persistent start | 15s | 与 formal campaign 一致，保证可比性 |
| persistent duration | until success/timeout | 用于 recovery stress condition |
| timeout | 300s | 与 formal campaign 保持一致 |
| initial pilot worlds | W8, W240 | W8 是主分析示例；W240 是已知代表性/边界观察 world |

### 2.3 Persistent fault 结果

#### W8 persistent masking

使用 paired study 跑满 6 pairs：

| Metric | Value |
|---|---:|
| complete pairs | 6 |
| mean paired slowdown | +3.942s |
| 95% CI half-width | 1.622s |
| outcome | all runs completed successfully |

解释：persistent masking 在 W8 中没有导致不可恢复 failure，只表现为 mild slowdown。

#### Persistent masking screening

额外测试发现，很多 world 在 persistent masking 下仍然成功：

| World | Fault | Width | Outcome |
|---:|---|---:|---|
| W86 | persistent masking | 90 deg | success, 101.7940s |
| W250 | persistent masking | 90 deg | success, 142.1431s |
| W239 | persistent masking | 90 deg | success, 114.1489s |
| W239 | persistent masking | 180 deg | success, 119.1217s |
| W250 | persistent masking | 180 deg | success, 137.4712s |
| W76 | persistent masking | 180 deg | success, 104.6861s |
| W86 | persistent masking | 180 deg | success, 112.9712s |

W173 在某些 screening 中出现 launch/startup invalid，不应作为 recovery failure 结论使用。

### 2.4 Persistent fault 的结论

Persistent fault pilot 的关键发现不是“permanent fault 一定失败”，而是：

```text
In the current BARN/Nav2 configuration, even persistent frontal LiDAR degradation is often navigable.
```

这导致 recovery 研究问题必须调整：

- 不能把 persistent fault 当作天然 recovery benchmark。
- 不能强行声称 recovery improves success rate。
- 可以将 persistent fault 作为 stress/sanity observation 和 limitation evidence。

## 3. Classifier 方案与实验

## 3.1 Stage 0: injector semantics audit

### 目标

确认 masking/dropout 在实际 ROS graph、topic、QoS 和 LaserScan 内容中如何表现。

### 检查内容

| Item | Checked |
|---|---|
| raw scan topic | `/front/scan` |
| faulted scan topic | `/front/scan_faulted` |
| fault presence topic | `/fault/scan_active` |
| Nav2 consumers | local/global costmap subscribe to faulted/recovered scan path |
| QoS | LaserScan best-effort compatible path |
| scan frequency | around 6-8 Hz in observed runs |
| FOV | 360 degree LiDAR confirmed earlier |

### 关键发现

最重要的语义发现：

```text
Dropout is not message-level dropout.
It is sector-level periodic replacement of ranges by range_max.
```

因此：

| Fault | Actual scan manifestation |
|---|---|
| Masking | frontal sector continuously replaced / degraded |
| Dropout | frontal sector alternates between degraded burst and healthy phase |

`/fault/scan_active` 的语义也必须明确：

```text
/fault/scan_active = fault episode is active
not dropout burst phase is active
```

也就是说，dropout 中 `/fault/scan_active` 在整个 20s episode 中为 true，但 scan 内容在 degraded/healthy 之间周期切换。

### Stage 0 结论

Stage 0 没有推翻之前 fault campaign。它确认了：

- injector 确实存在；
- `/front/scan_faulted` 确实发布；
- Nav2 costmap 确实订阅 faulted/recovered scan path；
- fault injection 不是白跑；
- classifier 必须基于 scan signature，而不能只看 topic 是否存在。

## 3.2 Stage 1: scan signature diagnostics

### 目标

验证 masking 与 dropout 是否能从 `/front/scan_faulted` 的内容中区分。

### 初始问题与修正

第一次 Stage 1 图中，fault window shading 与实际 record 时间没有对齐，导致 masking/dropout signature 看起来异常。修正 timestamp/fault-window alignment 后，signature 清楚显现。

### 使用的特征

| Feature | Meaning |
|---|---|
| frontal range_max ratio | frontal sector 中接近 `range_max` 的 beam 比例 |
| changed/reference ratio | 与 fault 前 reference scan 的差异比例 |
| degraded fraction | observation window 内 degraded scan 占比 |
| switching rate | degraded/healthy 状态切换频率 |
| longest degraded streak | 连续 degraded 持续时间 |
| longest healthy streak | 连续 healthy 持续时间 |

### Signature observation

| Fault | Signature |
|---|---|
| Masking | sustained degradation, degraded_fraction 接近 1, switching_rate 接近 0 |
| Dropout | periodic degraded/healthy alternation, switching_rate 高，有 degraded 和 healthy streak |

Stage 1 结论：两种 fault 在 scan signature 上可分离，但必须使用 temporal window，而不是单帧分类。

## 3.3 Stage 2A: autonomous sliding-window classifier

### 目标

Stage 2A 尝试完全 autonomous classifier：

```text
scan stream → NORMAL / MASKING / DROPOUT / UNKNOWN
```

不使用 `/fault/scan_active`。

### 结果

Stage 2A 跑通了流程，但没有通过验证。主要问题是 normal false alarm。

原因：BARN world geometry 本身会产生大量 `range_max`，例如开阔区域、远距离墙面、视野边缘等。这些正常环境特征会被 scan-only detector 误判为 fault degradation。

### 结论

Stage 2A 应记录为：

```text
FAILED / insufficient for deployment
```

它的价值是澄清了问题边界：完全 autonomous fault-presence detection 在当前数据与时间限制下不稳健，不适合作为 recovery trigger。

## 3.4 Stage 2B: conditional episode-level fault-type classifier

### 重新定义任务

Stage 2B 不再同时解决“有没有 fault”和“是什么 fault”。它只解决：

```text
Given a fault episode trigger, identify whether the active LiDAR fault is MASKING or DROPOUT.
```

输入：

```text
/fault/scan_active + /front/scan_faulted
```

输出：

```text
MASKING / DROPOUT / UNKNOWN
```

### 为什么这个定义合理

在本项目中，recovery 并不需要每秒精确分类；它需要的是 fault episode 开始后尽快知道应该选择哪条 recovery branch。

因此任务从“continuous diagnosis”收缩为“episode-level type identification”。这更符合 dissertation scope，也更容易 defend。

### Stage 2B 参数 justification

| Parameter | Value | Why |
|---|---:|---|
| observation window | 2s | dropout period = 1s，2s 可覆盖约两个 cycles；比 1s 更稳，比 3s latency 更低 |
| evidence input | `/front/scan_faulted` | 这是 Nav2 实际消费/将被恢复滤波处理的 scan path |
| trigger | `/fault/scan_active` | 表示 fault episode started；不提供 fault type |
| masking rule | sustained degraded evidence | masking 是连续遮挡，degraded_fraction 高且 switching_rate 低 |
| dropout rule | switching evidence | dropout 是周期性 degradation，switching_rate 高且 degraded/healthy streak 都存在 |
| UNKNOWN | safety rejection | 证据不足时不强行选择错误 policy |

### Development validation

在 W8/W94/W240 的 6 个 development episodes 上：

| Evidence mode | Observation window | Episodes | Correct | Wrong type | Unknown | Correct rate | Mean latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| online | 1s | 6 | 6 | 0 | 0 | 1.0 | 1.0s |
| online | 2s | 6 | 6 | 0 | 0 | 1.0 | 2.0s |
| online | 3s | 6 | 6 | 0 | 0 | 1.0 | 3.0s |
| oracle | 1s | 6 | 6 | 0 | 0 | 1.0 | 1.0s |
| oracle | 2s | 6 | 6 | 0 | 0 | 1.0 | 2.0s |
| oracle | 3s | 6 | 6 | 0 | 0 | 1.0 | 3.0s |

最终选择 2s 不是因为 1s 不工作，而是因为 2s 对 1Hz dropout 更有物理解释：它覆盖多个 degraded/healthy phases，同时 latency 仍可接受。

### Held-out validation

在未用于 development 的 W173/W274 上，使用 frozen 2s online classifier：

| World | Ground truth | Predicted | Reason | Correct | Degraded fraction | Switching rate | Latency |
|---:|---|---|---|---|---:|---:|---:|
| W173 | DROPOUT | DROPOUT | clear_dropout_switching | True | 0.5125 | 2.025/s | 2.0s |
| W173 | MASKING | MASKING | clear_sustained_masking | True | 1.0000 | 0.000/s | 2.0s |
| W274 | DROPOUT | DROPOUT | clear_dropout_switching | True | 0.5000 | 2.025/s | 2.0s |
| W274 | MASKING | MASKING | clear_sustained_masking | True | 1.0000 | 0.000/s | 2.0s |

Summary：

| Episodes | Correct | Wrong type | Unknown | Accuracy | Mean latency |
|---:|---:|---:|---:|---:|---:|
| 4 | 4 | 0 | 0 | 1.0 | 2.0s |

### Stage 2B 结论

可以准确写成：

```text
A conditional episode-level fault-type classifier was implemented and validated on development and held-out episodes for the two studied LiDAR fault models.
```

不能过度写成：

```text
The system achieved fully autonomous fault diagnosis.
```

因为 Stage 2B 依赖 external fault-presence trigger `/fault/scan_active`，它不解决 general fault detection。

## 4. Recovery prototype 尝试

## 4.1 Recovery 目标重新定义

经过 persistent fault 和 masking screening 后，recovery 不再被定义为“大规模性能提升实验”，而是定义为：

```text
Can a fault-aware supervisory layer execute fault-specific mitigation policies selected from online fault-type identification?
```

即 recovery 在本周主要是 architecture/prototype evidence，而不是 performance claim。

为避免把 recovery 结果写得过强，后续解释采用两层评价：

| Evaluation level | Metrics | Claim boundary |
|---|---|---|
| Mission-level outcome | success/timeout/collision, completion time, final navigation metric | 用来判断 recovery 是否真正改善任务完成结果 |
| Process-level behaviour | `cmd_vel` stability, odom speed recovery, stop/stall duration, progress after action, filter activation, controller progress warnings | 用来判断 recovery 是否在局部过程上产生稳定化效果 |

因此，即使 completion time 没有明显改善，也不能直接等同于 recovery 完全无效；但如果只有 process-level 改善而没有 mission-level 改善，论文中只能写成 local/process stabilisation evidence，不能写成 robust task recovery。

## 4.2 Masking Recovery M1: cmd_vel reorientation gate

### 设计

初始 masking recovery 方案是拦截 `/cmd_vel`，在检测到 masking 后执行 60 degree reorientation：

```text
fault active
→ block Nav2 cmd_vel
→ rotate robot 60 deg
→ release cmd_vel back to Nav2
```

参数：

| Parameter | Value | Justification |
|---|---:|---|
| rotation angle | 60 deg | 足够改变被遮挡 frontal sector 与障碍物/路径的相对方向，但不会像 180 deg 那样完全背离目标 |
| angular speed | 0.45 rad/s | 保守旋转速度，避免过激控制 |
| settle duration | 1s | 给 costmap/controller 一个短暂稳定时间 |
| trigger policy | immediate / progress_stall | 分别测试立即执行和只在停滞后执行 |
| progress stall window | 5s | 避免因瞬时速度波动误触发 |

### 实验结果

W8 immediate/progress_stall 和 W240 progress_stall 均出现相似现象：

- recovery node 启动；
- fault active 后 monitoring started；
- reorientation started；
- rotation complete；
- recovery complete；
- 但之后 Nav2 反复 `Failed to make progress`；
- 最终 `Goal failed`。

代表日志结果：

| World | Trigger | Recovery action | Final observation |
|---:|---|---|---|
| W8 | immediate | rotate 60 deg + release Nav2 | repeated progress failure, Goal failed |
| W8 | progress_stall | rotate 60 deg + release Nav2 | repeated progress failure, Goal failed |
| W240 | progress_stall | rotate 60 deg + release Nav2 | repeated progress failure, Goal failed |

### M1 失败原因

M1 的问题不是 action 没执行，而是架构层面不够完整：

```text
cmd_vel-level rotation changed robot orientation,
but did not coordinate with Nav2 goal/action state, BT recovery state, or replanning lifecycle.
```

因此 Nav2 controller 仍可能保留原来的 progress-check/action context，导致 repeated progress failure。

结论：M1 作为 low-level cmd_vel intervention 不适合作为最终 recovery claim，但它提供了重要 negative evidence。

## 4.3 Masking Recovery M2: Nav2 action-level recovery supervisor

### 设计

M2 改为使用 Nav2 action-level coordination：

```text
fault active / policy enabled
→ optionally wait for progress stall
→ cancel current NavigateToPose goal
→ send Nav2 Spin action
→ resend original NavigateToPose goal
```

这是对 M1 的架构修正：不再只改 `/cmd_vel`，而是与 Nav2 action server 对齐。

参数：

| Parameter | Value | Why |
|---|---:|---|
| spin angle | 60 deg | 延续 M1 的 reorientation hypothesis |
| trigger policy | immediate or progress_stall | 测试 forced action 和 conditional action |
| progress window | 5s | 判断是否真的停滞 |
| world tests | W8, W240 | 主示例和 stress/sanity world |

### Forced M2 结果

| World | Trigger | Evidence | Outcome |
|---:|---|---|---|
| W8 | immediate | spin goal sent/accepted; navigation goal resent/accepted | success, 107.6900s, metric 0.1250 |
| W240 | immediate | spin goal sent/accepted; navigation goal resent/accepted | success, 114.9567s, metric 0.1250 |

### Progress-stall M2 结果

| World | Trigger | Observation | Outcome |
|---:|---|---|---|
| W8 | progress_stall | monitoring started, no recovery action needed before success | success, 87.1614s, metric 0.1250 |
| W240 | progress_stall | monitoring started, no recovery action needed before success | success, 91.6376s, metric 0.1250 |

### M2 解释

M2 证明了 action-level recovery architecture 可以执行：

- fault active 后启动 monitoring；
- forced mode 下能够 cancel/Spin/resend goal；
- Nav2 action accepted；
- navigation remained operational。

但它没有证明 recovery 提升了 performance，因为 progress-stall 条件下很多场景本来就成功，没有触发 recovery action。

因此 M2 应写为：

```text
implemented and executable, but no task-level benefit demonstrated.
```

## 4.4 Dropout Recovery: scan recovery filter

### 设计

Dropout 的恢复策略不是停下等待，而是在 scan 层对 dropout burst 做滤波：

```text
/front/scan_faulted
→ dropout_scan_recovery_filter
→ /front/scan_recovered
→ costmap
```

逻辑：

- 当 selector 判断为 DROPOUT 后启用 filter；
- 如果当前 frontal sector `range_max_ratio` 高于阈值，则认为是 dropout burst；
- 用上一帧/最近 healthy scan 的 frontal sector 进行替代；
- healthy phase pass-through。

参数：

| Parameter | Value | Why |
|---|---:|---|
| range_max_ratio_threshold | 0.55 | Stage 1 signature 中 dropout/masking degraded sector 明显高于 normal；0.55 是保守 degraded 判据 |
| near_range_max_fraction | 0.98 | 判断 beam 是否接近 range_max，而不是精确等于 range_max，增强数值鲁棒性 |
| dropout period | 1.0s | 与 injected dropout model 一致 |
| dropout duty | 0.5 | 50% degraded / 50% healthy，用于区分 intermittent 与 sustained masking |
| output topic | `/front/scan_recovered` | 让 Nav2 消费恢复后的 scan |

### Smoke test 结果

W8 dropout filter smoke test 中，日志显示：

- injector ready；
- filter ready；
- fault active；
- filter active: rejecting frontal dropout bursts；
- navigation succeeded。

代表结果：

| World | Fault | Filter evidence | Outcome |
|---:|---|---|---|
| W8 | persistent/early dropout smoke | filter active, rejecting frontal dropout bursts | success, 90.9340s in rerun smoke |

解释：dropout filter branch 可执行，但没有单独证明 performance improvement。

更精确地说，dropout filter 的当前证据分成两部分：

| Evidence type | Current status |
|---|---|
| Functional evidence | filter can be enabled by selector and can reject dropout bursts |
| Process-level hypothesis | filter may stabilise the scan stream consumed by costmaps during dropout bursts |
| Mission-level evidence | not yet demonstrated as a reliable reduction in completion time or improvement in success rate |

因此 dropout recovery 在论文中不应表述为“improves navigation performance”。更合适的表述是：

```text
The dropout filter provides a working fault-specific mitigation branch and process-level evidence of burst rejection, but its mission-level benefit remains unproven.
```

## 5. Closed-loop classifier-to-policy integration

## 5.1 为什么需要 closed-loop smoke

在 closed-loop 之前，系统各部分分别成立：

```text
A. fault injector works
B. Stage 2B classifier works offline/diagnostic
C. recovery/filter nodes can run
```

但还缺一个证据：

```text
fault occurs online
→ classifier estimates type
→ selector chooses corresponding policy
→ policy node is enabled
→ navigation remains operational
```

因此做最后一个 closed-loop integration smoke test。

### 注意 claim 边界

closed-loop smoke 的研究问题不是“recovery 是否跨 world 有效”，而是：

```text
Can the implemented online classifier-to-policy routing work without using the injected fault type as an oracle?
```

## 5.2 W8 closed-loop smoke: final core evidence

W8 两条 branch 都成功打通。

| World | Fault | Fault start/duration | Classifier output | Policy selected | Policy evidence | Outcome |
|---:|---|---|---|---|---|---|
| W8 | masking | start=5s, duration=20s | MASKING, latency=2.00s | masking_nav2_recovery | masking policy enabled; monitoring started | success, 97.9390s, metric 0.1250 |
| W8 | dropout | start=5s, duration=20s | DROPOUT, latency=2.00s | dropout_scan_filter | filter enabled; filter active | success, 101.9310s, metric 0.1250 |

Detailed classifier evidence：

| World | Fault | degraded_fraction | switching_rate | evidence_mean | evidence_max | reason |
|---:|---|---:|---:|---:|---:|---|
| W8 | masking | 1.000 | 0.000/s | 1.000 | 1.000 | clear_sustained_masking |
| W8 | dropout | 0.494 | 2.000/s | 0.537 | 1.000 | clear_dropout_switching |

这可以作为最终 closed-loop claim：

```text
The two W8 smoke runs exercised both fault-specific branches of the supervisory loop.
```

## 5.3 W240 supporting observations

W240 不作为 closed-loop validation 的核心证据，而作为 stress/sanity observations。

| Run | Timing | Classifier/policy evidence | Outcome | Interpretation |
|---|---|---|---|---|
| W240 masking closed-loop | start=5s, duration=20s | MASKING correctly identified; masking policy enabled | collision, 60.0062s | correct routing does not guarantee task recovery under aggressive early-onset condition |
| W240 dropout closed-loop original | start=5s, duration=20s | DROPOUT identified; filter enabled; filter active | no final outcome captured in that log | routing branch worked but run log incomplete for task outcome |
| W240 dropout 300s debug | start=15s, duration=20s | fault_episode_start only; no final type decision | success, 99.0186s | formal timing navigable; classifier evidence ambiguous because baseline already high |
| W240 dropout start5 300s | start=5s, duration=20s | DROPOUT identified; filter enabled; filter active | success, 283.7023s | routing works under early onset, but task nearly reaches timeout |
| W240 masking start5 300s | start=5s, duration=20s | MASKING identified; masking policy enabled | collision, 45.6221s | early masking is an aggressive stress case; policy does not ensure safety |
| W240 masking start15 300s | start=15s, duration=20s | fault_episode_start only; no final type decision | success, 112.6154s | formal timing navigable, but no observable selector-policy decision |

### W240 结果解释

W240 不能被写成 failed closed-loop system。更准确的解释是：

- W240 的 start=5 early-onset runs 是 stress tests，不是 formal campaign-equivalent setting。
- W240 start=15 formal timing runs 可以成功导航，但 classifier 没有稳定输出 final policy decision，因为 fault episode start 时 baseline range_max/span 已经很高，scan signature 与 normal open-space geometry 混在一起。
- 这说明 classifier-to-policy integration 已经能跑，但 recovery effectiveness 和 difficult-world generalisation 仍未证明。

因此 W240 应写为 supporting observations，而不是核心 validation。

## 6. 参数设置总表与 justification

| Component | Parameter | Value | Justification |
|---|---|---:|---|
| transient fault campaign | start | 15s | 避免初始化阶段污染；足够早影响任务过程 |
| transient fault campaign | duration | 20s | 表示短时外部扰动；适合 propagation/performance characterisation |
| persistent pilot | duration | until success/timeout | 测试 fault 不自行消失时系统表现 |
| masking/dropout sector | center | 0 deg | frontal sector directly affects forward navigation |
| masking/dropout sector | width | 90 deg | 足够强但不完全破坏 360 deg LiDAR；formal campaign 已用 |
| stress screening | width | 180 deg | 用于探索是否能制造 recovery-demanding scenario，不作为主 formal setting |
| dropout model | period | 1.0s | 明确产生 intermittent signature，便于区分 temporal switching |
| dropout model | duty | 0.5 | degraded/healthy 各占一半，保证可观测切换 |
| Stage 2B classifier | observation window | 2s | 覆盖约两个 1Hz dropout cycles；latency 可接受 |
| classifier safety | UNKNOWN state | enabled | 防止证据不足时错误选择 recovery policy |
| M1 recovery | rotation angle | 60 deg | 改变 LiDAR遮挡方向但不过度背离目标 |
| M1 recovery | angular speed | 0.45 rad/s | 保守旋转速度 |
| M2 recovery | spin angle | 60 deg | 与 M1 hypothesis 保持一致，但通过 Nav2 action 执行 |
| dropout filter | range_max threshold | 0.55 | 基于 Stage 1 signature 的 degraded 判据 |
| closed-loop smoke | start | 5s | 让 fault signature 更早出现，保证 smoke test 能观察 routing；不等同 formal campaign timing |
| closed-loop sanity | timeout | 300s | 与 formal campaign 对齐，避免 180s timeout 造成不公平比较 |

## 7. 本周完成情况对照

| Goal | Completed? | Evidence |
|---|---|---|
| clarify injector semantics | yes | Stage 0 ROS graph/topic/QoS/scan audit |
| show masking/dropout scan signatures | yes | Stage 1 corrected signature diagnostics |
| build fully autonomous classifier | attempted but failed | Stage 2A normal false alarm issue |
| build conditional fault-type classifier | yes | Stage 2B development 6/6, held-out 4/4 |
| implement masking recovery | yes, exploratory | M1/M2 implemented; M1 failed; M2 executable but no benefit shown |
| implement dropout recovery | yes, exploratory | dropout filter branch implemented and activatable |
| complete closed-loop integration smoke | yes, scoped | W8 masking + W8 dropout both routed correctly and succeeded |
| prove mission-level recovery improvement | no | not supported by current evidence |
| inspect process-level recovery effects | partially | filter activation and policy execution are logged; full quantitative process-level comparison remains future analysis |
| prove cross-world recovery effectiveness | no | explicitly left as limitation/future work |

## 8. 可用于论文/汇报的准确表述

### 8.1 可以写的 strong claim

```text
The dissertation implements a fault-aware supervisory pipeline for two LiDAR degradation modes. A conditional episode-level classifier distinguishes frontal masking from intermittent dropout using a two-second observation window over the navigation-consumed scan stream. The classifier achieved correct identification on both development and held-out diagnostic episodes, and a W8 closed-loop smoke test verified that the estimated fault type can automatically route the system to the corresponding fault-aware policy branch.
```

### 8.2 必须限制的 claim

```text
The recovery prototypes should be treated as exploratory. Although masking and dropout policies were implemented and executed, the current evidence does not demonstrate robust mission-level recovery improvement or cross-world recovery effectiveness. Process-level effects, such as dropout burst rejection or short-term command stabilisation, can be reported only as local mechanism evidence rather than as task-level recovery success.
```

### 8.3 不应这样写

不要写：

```text
The recovery system improves navigation performance under masking/dropout faults.
```

不要写：

```text
The classifier performs fully autonomous fault diagnosis.
```

不要写：

```text
W240 proves closed-loop failure.
```

更准确写法是：

```text
W240 revealed that correct fault-type routing does not necessarily imply task-level recovery under aggressive early-onset stress conditions.
```

## 9. 后续计划

### 9.1 立即停止新增实验 campaign

当前实验已经足够支撑 dissertation 的 narrative：

```text
fault injection → propagation analysis → fault signature → classifier → recovery prototype → closed-loop integration smoke → limitations
```

继续增加 recovery campaign 的收益低，且容易分散论文主线。

### 9.2 下一步应做

| Priority | Task |
|---:|---|
| 1 | 把本周 evidence 整理进 dissertation experiment log |
| 2 | 更新 PPT：明确区分 classifier validation、closed-loop smoke、recovery limitation |
| 3 | 整理 W8 closed-loop 两条 branch 的日志截图/表格 |
| 4 | 将 W240 作为 supporting stress observations，而非主 validation |
| 5 | 开始写论文方法章节和实验章节 |

### 9.3 Future work/recovery 改进方向

如果论文中需要写未来工作，建议这样写：

1. fault-presence detection 应从 `/fault/scan_active` oracle trigger 扩展为 real sensor health monitor。
2. masking recovery 需要与 planner/costmap/BT recovery 更深集成，而不是只做 single spin action。
3. dropout recovery filter 需要在更多 worlds 和 matched baselines 下评估是否减少 stop ratio 或 completion time。
4. recovery evaluation 应专门选择 recovery-demanding worlds，而不是默认所有 BARN worlds 都会因 fault 失败。
5. recovery metric 应从 completion time 扩展到 safe-stop rate, time-to-restore-progress, recovery action count, collision avoidance。
6. 如果继续分析已有 recovery logs，应明确区分 mission-level outcome 和 process-level stabilisation，例如比较 filter enabled 前后的 scan burst rejection、`cmd_vel` continuity、odom speed recovery 和 controller progress warnings。

## 10. 总结

本周最重要的成果不是 recovery performance improvement，而是完成并验证了一个更完整的 fault-aware supervisory architecture：

```text
LiDAR fault injection
→ fault-presence episode trigger
→ scan-signature based fault-type classifier
→ policy selector
→ masking/dropout-specific policy branch
→ closed-loop smoke validation
```

最重要的限制也已经明确：

```text
The system can identify and route studied LiDAR faults. Recovery branches are executable, but robust mission-level recovery effectiveness is not yet demonstrated; any observed local stabilisation should be reported separately as process-level evidence.
```

这个结论比强行声称 recovery 成功更稳健，也更适合作为 dissertation 里的 honest engineering result。
