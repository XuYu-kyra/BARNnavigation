# 实验记录整理版（截至 2026-08-09）

## 1. 文档说明

本文件用于替代原先较为碎片化的过程记录。整理原则如下：

- 只保留已经实际发生的实验、明确做出的决策、以及可复述的数据结论。
- 删除大量“边做边想”的即时讨论，改为按实验阶段组织。
- 每个关键决定尽量回答四个问题：`What / Why / Evidence / How`。
- 这是一份过程记录，而不是最终论文稿，因此会保留中途尝试过但没有成为主结论的方案分支。

本阶段工作的主线是：

1.  跑完整个 BARN 300-world benchmark，对 `original` 与 `tuned`
    配置做全量比较。

<!-- -->

1.  根据 600 次实验结果建立 world 分类，并选出 dissertation 用的
    fault-injection 世界集合。
2.  校准 repeated trial count。
3.  建立 fault injection pipeline。
4.  完成两组正式 fault campaign：
    - Frontal LiDAR sector masking

    <!-- -->

    - Intermittent LiDAR dropout
5.  验证 odometry fault injector
    的可行性，并据此判断其是否适合作为当前主线 fault。
6.  启动最小 recovery pilot
    的工程实现，并评估其是否值得进入后续正式实验。

## 2. 项目目标

本 dissertation 的目标不是单纯证明“fault
会让机器人变差”，而是建立一条可解释的分析链：

`fault -> perception / state estimation -> planning / control -> robot motion -> mission-level outcome`

因此，实验设计需要同时满足三个要求：

- 可以稳定重复运行；

<!-- -->

- fault 可控、可记录；

<!-- -->

- 结果不仅能看最终成败，还能解释传播过程。

## 3. Phase 1：600 次 benchmark 基线实验

### 3.1 实验目的

先跑满 `300` 个 BARN worlds 的 `original` 与 `tuned` 两套配置，总计
`600` 次实验。  
目的不是以后每个 fault 都跑满 300 worlds，而是先建立完整的
`world difficulty landscape`，避免一开始就凭直觉挑世界。

### 3.2 核心结果

| 指标                         | 数值 |
|------------------------------|------|
| 总 world 数                  | 300  |
| original 成功数              | 126  |
| tuned 成功数                 | 210  |
| tune-dependent recovered 数  | 96   |
| main candidate count         | 144  |
| supplemental candidate count | 108  |

### 3.3 四分类结果

根据 `merged_world_metrics.csv` 的整理，300 个 worlds 被分为四类：

| 类别                              | 定义                                                 | 数量 |
|-----------------------------------|------------------------------------------------------|------|
| Class 1: stable success           | original 与 tuned 都成功，且 tuned 具有较稳定 margin | 102  |
| Class 2: tune-dependent recovered | original 失败，但 tuned 成功                         | 96   |
| Class 3: marginal success         | tuned 虽成功，但离 timeout 较近，属于边界成功        | 12   |
| Class 4: persistent hard          | tuned 也未成功                                       | 90   |

### 3.4 几何压力类别统计

自动分类中得到的 stress case 计数如下：

| 几何类别       | 数量 |
|----------------|------|
| dense_clutter  | 7    |
| mixed_moderate | 33   |
| open_straight  | 1    |
| turning_slalom | 259  |

### 3.5 本阶段结论

- `tuned` 相比 `original` 明显提高了总体可完成性：`126 -> 210`。

<!-- -->

- 如果不先跑满 300 worlds，就无法知道哪些 worlds 稳定、哪些 worlds
  只是边界成功、哪些本身过难。

<!-- -->

- 后续 fault-injection world selection 的合法性，依赖这一步的全量
  benchmark。

## 4. Phase 2：world selection 与实验范围收缩

### 4.1 初始自动推荐结果

基于 `selection_original0-299__tune0-299`
目录中的选择脚本，最初自动推荐的 8 个 worlds 为：

`173, 274, 94, 240, 3, 7, 8, 172`

这组结果可以作为“算法 shortlist”，但 dissertation
正式实验集合后来做了人工重整。

### 4.2 正式 dissertation 世界集合

最终正式 fault campaign 采用 `9` 个 worlds，而不是继续沿用自动推荐的 8
个。  
正式集合按 `4 / 4 / 1` 的比例，从前三类中分层抽取：

| 类别                              | 选择原则                               | 选中 worlds      |
|-----------------------------------|----------------------------------------|------------------|
| Class 1: stable success           | 稳定可完成，适合观察 fault effect 本身 | 240, 274, 94, 8  |
| Class 2: tune-dependent recovered | 对 tuning 敏感，适合观察脆弱性         | 86, 173, 76, 239 |
| Class 3: marginal success         | 边界成功，用于保留“接近失败”的代表     | 250              |
| Class 4: persistent hard          | 不进入第一轮正式 fault study           | 排除             |

### 4.3 为什么排除 Class 4

Class 4 worlds 在 tuned 条件下本身就无法稳定完成。  
如果在第一轮主实验中直接纳入，会把两件事混在一起：

- world 本身过难；

<!-- -->

- 外加 fault 带来的退化。

这会削弱 fault propagation 解释性，所以 Class 4 更适合作为后续 stress /
extension 集合，而不是第一轮正式 fault campaign。

### 4.4 为什么从 8 改到 9

最终从自动推荐 8 worlds，转为 dissertation 正式 9
worlds，主要基于三个考虑：

1.  需要显式覆盖 `Class 1 / Class 2 / Class 3`
    三类，而不只是接受一次自动 shortlist。

<!-- -->

1.  `world 8` 已被用于 repeat-count calibration 和 early fault pipeline
    validation，保留它可以让 calibration narrative 与正式实验 narrative
    连贯。

<!-- -->

1.  `9 worlds x 2 conditions x 6 pairs = 108 runs / fault`，在工程成本上仍可接受，同时比
    8-world 方案具有更清晰的分层覆盖逻辑。

<!-- -->

1.  4：4：1是通过比例确定的

### 4.5 本阶段结论

- 正式实验集合不是“挑看起来顺眼的世界”，而是基于 benchmark
  四分类后的分层抽样。

<!-- -->

- 这组 9 worlds
  的角色是：`代表性 ``+ ``可执行性 ``+ ``与 ``pilot narrative ``连贯`。

## 5. Phase 3：repeat count 校准

### 5.1 目标

确定在固定配置下，`baseline vs fault`
的最小充分重复次数，而不是拍脑袋说“跑 3 次”或“跑 10 次”。

### 5.2 校准 world 与分析单位

- calibration world：`world 8`

<!-- -->

- 比较对象：`baseline` vs `fault`

<!-- -->

- 分析单位：pair difference

\[ d_i = T\_{fault,i} - T\_{baseline,i} \]

### 5.3 停止规则

采用 sequential paired design：先跑 6 pairs，然后每增加 2 pairs
评估一次。  
预设停止标准：

- `95% CI half-width < 5 s`

<!-- -->

- 或 `95% CI half-width < 0.25 * mean(d)`

### 5.4 停止规则的参数 justify

这里真正需要 justify 的不是“为什么用 CI”，而是：

- 为什么是 `5 s`

<!-- -->

- 为什么是 `0.25 * mean(d)`

这两个数都不是统计学里的天然常数，而是为本项目预先设定的
`practical precision targets`。

`5 s` 被用作绝对误差目标，原因有三点：

1.  相对 `300 s` timeout，它只占 `1.67%`，属于较严格但仍可执行的误差界。

<!-- -->

1.  相对很多成功运行的 `150–250 s` 完成时间，它大约是 `2%–3%`
    的量级，已经足以区分“基本没变化”和“确实存在 slowdown”。

<!-- -->

1.  它小于本项目正式 campaign 中关注的 mission-level effect 量级：
    - frontal masking：`+9.21 s`

    <!-- -->

    - lidar dropout：`+6.43 s`

`0.25 * mean(d)` 被用作相对误差目标，原因是：

- 不希望不确定性大到接近 effect 本身；

<!-- -->

- `25%` 比 `50%` 更严格，但又没有 `10%` 那么激进，不会把 run
  数推到不可执行的水平；

<!-- -->

- 它能防止在 effect 较小的时候，仅凭“绝对 half-width
  不大”就误判结果已经足够稳定。

因此，这两个阈值的角色分别是：

- `5 s`：控制绝对误差；

<!-- -->

- `25%`：控制相对误差。

两者一起使用，是为了兼顾大 effect 和小 effect 的可解释性。后续仍可用
`3/5/7 s` 与 `0.20/0.25/0.33` 做 sensitivity check，确认 stop decision
不对单一阈值过分敏感。

### 5.5 实际结果

在 `world 8 + tuned_clean + frontal masking(15s,20s,90deg)`
条件下，校准结果为：

- `pairs = 6`

<!-- -->

- `mean_d = 4.827 s`

<!-- -->

- `ci95_halfwidth = 2.391 s`

<!-- -->

- `stop = True`

因此，正式 campaign 采用固定 `6 pairs` 设计。

### 5.6 为什么最后统一用 6 pairs

这里的结论不是“任何 world、任何 fault 永远都应该跑 6 pairs”，而是：

- 在当前 dissertation 的 fault campaign 范围内，6 pairs
  已经足以支撑第一轮比较；

<!-- -->

- 更高的 pairs 会显著增加总运行量；

<!-- -->

- `9 worlds x 2 conditions x 6 pairs = 108 runs / fault`
  是一个能自动化落地、又不至于失控的规模。

## 6. Phase 4：fault 候选、排序与组合演化

### 6.1 选择原则

fault 不是只按“现实性最高”一维排序，而是同时看两维：

1.  `Real-world plausibility`

<!-- -->

1.  `Experimental suitability for cross-layer propagation analysis`

### 6.2 打分锚点

为了避免“先有结论再找理由”，fault prioritisation
采用了透明的、FMEA-inspired 的定性评分法。

#### Real-world plausibility

| 分数 | 含义                                                    |
|------|---------------------------------------------------------|
| 5    | 有较明确文献或成熟工程共识支持，且是常见传感器/定位退化 |
| 4    | 文献支持较充分，但更依赖特定场景或环境                  |
| 3    | 现实中可能发生，但不是一线主问题                        |
| 2    | 更像软件/系统异常，不是最常见现实故障                   |
| 1    | 主要是人工构造的极端 stressor                           |

#### Experimental suitability

| 分数 | 含义                                         |
|------|----------------------------------------------|
| 5    | 易于稳定注入、可重复、传播链清晰、可跨层观测 |
| 4    | 基本可控，但偶尔会引入较大波动               |
| 3    | 能做，但传播链不总是清晰或易与其他因素混淆   |
| 2    | 容易直接退化成 crash/timeout，解释价值有限   |
| 1    | 很难稳定注入或难以解释结果                   |

### 6.3 候选 fault 全表与定性排序

下表反映的是本阶段真实使用过的候选集，而不只是最后挑出来的 fault。

| Fault                                    | Real-world plausibility | Experimental suitability | 优先级 | 本阶段状态                                 |
|------------------------------------------|-------------------------|--------------------------|--------|--------------------------------------------|
| Frontal LiDAR sector masking             | 5                       | 5                        | 1      | 已执行正式 campaign                        |
| Intermittent LiDAR dropout               | 4                       | 5                        | 2      | 已执行正式 campaign                        |
| Odometry drift / encoder bias            | 5                       | 4                        | 3      | injector 已验证，做过 exploratory pilot    |
| LiDAR range bias / inflation             | 4                       | 4                        | 4      | 进入候选，但本阶段未实现                   |
| Localization jump / pose offset          | 3                       | 4                        | 5      | 进入候选，但本阶段未实现                   |
| Actuation degradation / velocity scaling | 3                       | 4                        | 6      | 中途被考虑，后改作 recovery 机制而非 fault |
| TF interruption                          | 2                       | 3                        | 7      | 进入候选，但未实现                         |
| Planner server stall / action timeout    | 2                       | 2                        | 8      | 进入候选，但未实现                         |
| Random Nav2 node crash                   | 1                       | 2                        | 9      | 仅保留为极端 stressor，不进入主线          |

### 6.4 文献与方法学支撑

这套排序不是“直接从文献里抄来的分数”，而是：

- `literature` 用于支撑 realism；

<!-- -->

- `project-specific methodology judgement` 用于支撑 experimental
  suitability。

本阶段实际引用或参考的 fault 类型依据包括：

- LiDAR degradation / masking / dropout 的 adverse weather 与
  contamination 文献；

<!-- -->

- odometry drift / wheel slip / sensor fusion fault-tolerance 文献；

<!-- -->

- FMEA / FMEDA 在 mobile robot fault analysis 中的使用思路。

因此，更准确的表达应是：

> fault ranking was literature-informed for realism, and FMEA-inspired
> for experimental suitability.

### 6.5 组合方案的中途演化

本阶段 fault
组合并不是一开始就完全固定，而是经历过一次明显的方法学修正。

初始较稳定的一版是：

- Frontal LiDAR sector masking

<!-- -->

- Intermittent LiDAR dropout

<!-- -->

- Odometry drift / encoder bias

中途曾出现过一个“为了增强 cross-layer coverage，把
`actuation degradation / velocity scaling` 纳入第三个正式
fault”的设计分支。  
但后续判断认为这会带来两个问题：

1.  它没有先在候选 fault 全表中获得一致的方法学定位；

<!-- -->

1.  它和后续的 recovery idea
    在机制上高度重合，容易让“fault”和“mitigation”边界混乱。

因此最终修正为：

- 将 `velocity scaling` 从“fault 候选”中移出主执行组合；

<!-- -->

- 把它重新定义为 `fault-aware recovery mechanism`；

<!-- -->

- 保留 `masking + dropout` 作为两条正式感知层主线；

<!-- -->

- 保留 `odom drift` 作为状态估计层 exploratory branch。

### 6.6 为什么先做 frontal masking

因为它最适合建立第一条完整、可解释的传播链：

`/scan -> costmap -> planner -> controller -> robot motion -> outcome`

同时它满足：

- 现实中可解释：前向激光被污染、遮挡、雨雾影响并不罕见；

<!-- -->

- 注入稳定；

<!-- -->

- 最容易观察 propagation。

### 6.7 为什么 dropout 作为第二个正式 fault

dropout 与 masking 共享同样的几何区域，但 temporal mechanism 不同。  
这意味着可以在尽量控制空间覆盖一致的前提下，比较：

- steady occlusion

<!-- -->

- intermittent disappearance / reappearance

这样更容易回答：**同样是前向感知退化，不同时间结构会怎样影响 planning 与
control。**

### 6.8 odom drift 的当前定位

odometry fault injector 已经技术上跑通，但在当前配置下：

- effect 存在；

<!-- -->

- 但传播链不如 LiDAR faults 直接；

<!-- -->

- 更容易被 localization / controller feedback / replanning 部分抵消。

因此当前结论不是“odom 注入失败”，而是：

> 它暂时不是最适合作为本轮 dissertation 主线 fault 的第二个正式
> campaign。

## 7. Phase 5：fault 参数校准

### 7.1 Frontal masking 正式参数

| 参数     | 数值   |
|----------|--------|
| start    | 15 s   |
| duration | 20 s   |
| center   | 0 deg  |
| width    | 90 deg |

### 7.2 参数依据

这组参数来自前期轻度/重度试验后的折中：

- 过强版本会直接把实验打成 timeout，不利于做 nuanced propagation study；

<!-- -->

- 过弱版本 effect 太小，难以稳定区分；

<!-- -->

- `15s / 20s / 90deg` 形成了中等强度 perturbation，能引起明显 slowdown
  与 stop-go 变化，但多数情况下不直接把任务打死。

### 7.2.1 更强的参数 justification 框架

如果老师进一步追问“为什么偏偏是这些参数，而不是别的值”，最稳妥的回答不应是“因为这个值看起来合适”，而应是：

> 参数不是从文献中直接抄来的固定常数，而是通过 pilot calibration 逐步收敛出来的 practical settings。

本项目中，每组 fault 参数都满足同一套选择原则：

1. `Realistic enough`
   参数量级要对应真实世界中可能出现的退化机制，而不是纯粹把系统打爆。
2. `Observable`
   必须能在日志、分段指标或任务层结果中留下可解释变化。
3. `Non-trivial but non-catastrophic`
   不能弱到几乎没差别，也不能强到大部分 run 直接 timeout。
4. `Comparable`
   不同 worlds、不同 repetitions、甚至不同 fault 类型之间要能比较。
5. `Automatable`
   必须能稳定重复注入，适合 9-world、6-pair 这种批量 campaign。

也就是说，参数选择的逻辑是：

`mechanism plausibility -> small-scale pilot -> severity adjustment -> formal campaign setting`

而不是：

`先定一个值 -> 希望它有用`

### 7.2.2 Frontal masking 的参数为什么是 15s / 20s / 90deg

这一组值可以从四个角度 justify：

- `15 s start`
  避开导航启动初期的初始化和短时瞬态，确保 fault 作用在 active navigation 阶段，而不是把系统启动噪声误当作 fault effect。
- `20 s duration`
  足够跨越多个 sensing-planning-control cycle，能形成 propagation；但又不会变成“几乎整个 mission 都在 fault 中”的极端设置。
- `0 deg center`
  正前方是局部避障和短视距决策最敏感的区域，因此最适合观察 perception fault 对 navigation 的直接影响。
- `90 deg width`
  比较大，但仍然属于“前向扇区退化”，能模拟污染、遮挡、雨雾等导致的 forward-sector degradation，而不是整个 LiDAR 全失效。

更重要的是，这组参数是经过 pilot 校准后留下来的中等强度设置：

- 比更强的持续遮挡更容易保留可解释的过程；
- 比更弱的短时窄角度遮挡更容易形成稳定可观测差异。

### 7.3 Dropout 正式参数

dropout 与 masking 保持相同几何参数，只改变时间结构：

| 参数               | 数值   |
|--------------------|--------|
| start              | 15 s   |
| duration           | 20 s   |
| center             | 0 deg  |
| width              | 90 deg |
| dropout period     | 1.0 s  |
| dropout duty cycle | 0.5    |

这样可以把比较尽量集中在：

> steady masking vs intermittent dropout

而不是把结论混入不同的空间覆盖差异。

这组参数更强的 justification 是：

- `几何参数与 masking 一致`
  这样比较的是时间结构，而不是空间覆盖。
- `1.0 s period`
  表示感知异常不是高频随机噪声，而是肉眼可观察、足以跨越多个 control cycle 的周期性失真。
- `0.5 duty cycle`
  表示一个中等强度的 intermittent fault：既不是极弱闪断，也不是几乎持续遮挡。
- `与 masking 共用 start/duration`
  避免把时间窗差异混入 fault mechanism 比较。

因此，这组参数的真正作用是：

> 在空间范围基本一致的前提下，隔离并比较 steady occlusion 与 intermittent sensing loss 的行为差异。

### 7.4 Odom pilot 参数

探索性 odom fault 试过如下参数：

| 参数          | 数值      |
|---------------|-----------|
| start         | 20 s      |
| duration      | 20 s      |
| linear scale  | 1.08      |
| yaw rate bias | 1.5 deg/s |

后续 stronger 版本进一步增强为：

| 参数          | 数值      |
|---------------|-----------|
| start         | 20 s      |
| duration      | 30 s      |
| linear scale  | 1.12      |
| yaw rate bias | 2.5 deg/s |

这部分的意义在于：

- 证明 odom fault 的参数不是随便拍脑袋定的；

<!-- -->

- 而是经历了从 moderate 到 stronger 的 calibration；

<!-- -->

- 最终仍因为泛化性不稳定而没有进入正式 comparative campaign。

更强的 justify 是：

- 第一档参数的目标不是“直接做出显著退化”，而是先验证 state-estimation fault 能否稳定进入系统；
- stronger 版的目标是检验：如果同时延长 fault window 并增大 bias，任务层 effect 是否能稳定放大；
- 结果说明 stronger 参数虽然在少量 worlds 上能产生更明显 slowdown，但这种 effect 在更异质 world set 上没有稳定保留。

因此，这里的参数选择过程本身就是一个有价值的实验记录：

> odom fault 不是没被认真调过，而是调过之后仍没有像 LiDAR faults 一样稳定传播到 mission layer。

## 8. Phase 6：已完成 fault campaign 与 exploratory branches

### 8.1 Campaign A：Frontal LiDAR sector masking

**状态：已完成**

| 指标             | 数值 |
|------------------|------|
| worlds           | 9    |
| pairs / world    | 6    |
| total pairs      | 54   |
| total valid runs | 108  |
| attempt count    | 115  |
| retry cases      | 7    |

#### 汇总效果

| 指标                          | 平均变化（fault - baseline） |
|-------------------------------|------------------------------|
| completion slowdown           | +9.2096 s                    |
| completion slowdown ratio     | +0.0432                      |
| actual path length delta      | +0.2046 m                    |
| stop ratio delta              | +0.0494                      |
| mean speed delta              | -0.00103 m/s                 |
| during-fault speed delta      | +0.0446 m/s                  |
| during-fault stop-ratio delta | +0.7284                      |
| controller new path delta     | +9.3148                      |

#### 解释

这一组结果说明：

- frontal masking 并不一定直接造成 mission failure；

<!-- -->

- 但它会显著增加运行期间的 stop-go 特征；

<!-- -->

- 同时增加 controller / replanning 活动；

<!-- -->

- 最终在 mission level 上表现为平均完成时间变长。

### 8.2 Campaign B：Intermittent LiDAR dropout

**状态：已完成**

| 指标             | 数值 |
|------------------|------|
| worlds           | 9    |
| pairs / world    | 6    |
| total pairs      | 54   |
| total valid runs | 108  |
| attempt count    | 114  |
| retry cases      | 6    |

#### 汇总效果

| 指标                          | 平均变化（fault - baseline） |
|-------------------------------|------------------------------|
| completion slowdown           | +6.4309 s                    |
| completion slowdown ratio     | +0.0283                      |
| actual path length delta      | +0.1255 m                    |
| stop ratio delta              | +0.0259                      |
| mean speed delta              | -0.00095 m/s                 |
| during-fault speed delta      | +0.0433 m/s                  |
| during-fault stop-ratio delta | +0.7284                      |
| controller new path delta     | +5.6852                      |

#### 解释

这一组结果说明：

- dropout 也产生了稳定退化；

<!-- -->

- 但在当前参数下，它的平均 mission-level 退化小于 frontal masking；

<!-- -->

- 因此可以初步认为：在当前 tuned_clean
  配置下，**持续的前向扇区遮挡比同几何范围的间歇性 dropout
  更破坏导航表现。**

### 8.3 Exploratory branch：odom drift / encoder bias

#### 已完成内容

- odometry fault injector 已实现并能正常接入 pipeline；

<!-- -->

- smoke test 在 `world 8` 上跑通；

<!-- -->

- fault active 时间窗和注入参数可被日志记录。

#### stronger probe 与后续判断

后续为了检验 odom fault 是否只是“太弱”，还做过 stronger
probe。记录中的关键判断是：

- 在较小代表性集合上，odom drift 一度出现 mission-level slowdown；

<!-- -->

- 但扩到更异质的 world set 后，这个 effect 没有稳定保留；

<!-- -->

- 说明 fault 已经进入系统，但传播更容易被 localization / controller
  feedback / replanning 吸收。

记录中的关键数字判断为：

- 在 3-world stronger probe 中：
  - `mean_completion_slowdown_s ≈ +10.35 s`

  <!-- -->

  - `mean_stop_ratio_delta ≈ +0.087`

<!-- -->

- 但扩到更异质的 9-world 中间汇总后：
  - `mean_completion_slowdown_s ≈ -0.035 s`

  <!-- -->

  - `mean_stop_ratio_delta ≈ +0.0037`

  <!-- -->

  - `mean_controller_new_path_delta ≈ 0`

因此目前更合理的表述不是“injector 失败”，而是：

> odom drift 是已验证但未稳定泛化的 exploratory fault。

#### 本阶段定位

这一分支的重要性在于：

- 它证明了不是所有合理 fault 都会稳定传播到 mission layer；

<!-- -->

- 也证明 fault selection 必须基于数据筛选，而不是把所有“看起来合理”的
  fault 都硬做成主结果。

## 9. Phase 7：recovery pilot 的实际推进情况

### 9.1 Week 3 原始目标

第三周原本的目标不是立刻做完整 fault-tolerant navigation，而是：

- 在 fault propagation 主线已经基本成立的前提下；

<!-- -->

- 启动一个 `minimum recovery pilot`；

<!-- -->

- 先证明“感知到 fault active 后，系统可以切换到一个更保守的 response
  mechanism”。

### 9.2 recovery 假设

本阶段采用的 recovery hypothesis 是：

> When frontal LiDAR masking is active, applying a conservative velocity
> gate is expected to reduce unstable forward motion and stop-go
> oscillation, thereby lowering severe navigation degradation. The
> recovery may slightly increase nominal traversal time, but should
> improve robustness under fault.

也就是说，这个 recovery 不追求“恢复到 baseline 一样快”，而是追求：

- 降低极端 stop-go；

<!-- -->

- 减少 fault window 内的激进前冲；

<!-- -->

- 限制严重退化。

### 9.3 实际做出的工程工作

这部分并不是只停留在想法层面，已经完成了实际实现：

| 文件 / 模块                    | 实际工作                                                                                                                          |
|--------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| `laser_scan_fault_injector.py` | 发布 `/fault/scan_active`，为 recovery 提供 fault-active 信号                                                                     |
| `fault_aware_cmdvel_gate.py`   | 新增保守速度门控节点，在 fault active 时缩放 `cmd_vel`                                                                            |
| `BARN_runner.launch.py`        | 增加 `recovery_enable`、`recovery_linear_scale`、`recovery_angular_scale`、`recovery_active_timeout` 等参数，并把 gate 接入主链路 |
| `run_paired_fault_study.py`    | 增加 recovery 相关运行参数，支持 fault-only 与 fault+recovery 比较                                                                |
| `analyze_fault_pipeline.py`    | 增加对 recovery gate active 日志的识别支持                                                                                        |

实际接线后的最小恢复路径是：

`Nav2 -> velocity_smoother -> /cmd_vel_recovery_in -> fault_aware_cmdvel_gate -> /cmd_vel`

其中，当 `/fault/scan_active = True` 时，gate
会把速度指令缩放为更保守的输出。

### 9.4 计划参数

最小 recovery gate 的参数设定为：

| 参数           | 数值  |
|----------------|-------|
| linear scale   | 0.35  |
| angular scale  | 0.50  |
| active timeout | 1.0 s |

这组值的设计逻辑是：

- 前向感知退化时优先压低线速度；

<!-- -->

- 保留一定转向能力，让机器人还能慢速纠偏；

<!-- -->

- 目标是稳健性，不是速度最优。

### 9.5 当前结果与限制

就目前仓库代码、实验记录和可定位数据目录来看，recovery 这条线的状态是：

- 实现和接线已完成；

<!-- -->

- smoke-test 方案已设计完毕；

<!-- -->

- recovery 已经从“想法”变成“可运行机制”；

<!-- -->

- 但尚未形成能稳定支撑结论的正式 recovery dataset；

<!-- -->

- 即使做过尝试，也没有留下足够稳定、可复现、可归档的正向结果来支撑“recovery
  已有效”。

因此，这部分不能写成“recovery 已经成功证明有效”，更准确的说法是：

> recovery pilot
> 已经完成机制实现与实验准备，但尚未形成稳定、可归档的正向结果。

这也是为什么当前阶段 recovery 仍应视为：

- 已做出的真实努力；

<!-- -->

- 但尚未完成的下一阶段工作。


### 9.6 如果继续改进 recovery，后续该怎么做

如果 recovery 继续推进，最合理的改进路线不应该是一口气改很多 Nav2 内部参数，而应该按“由外到内、由简单到复杂”的顺序走。

#### Step 1：先把最小 velocity gate 做成可评估版本

目标不是立刻做到最优恢复，而是先让 recovery 有一组可以重复比较的最小结果。

建议：

- 固定 worlds：`8` 和 `86`
- 固定 fault：`frontal masking`
- 条件比较：`fault-only` vs `fault+recovery`
- 每个 world 先跑 `3 pairs`

这一步只回答两个问题：

1. gate 是否稳定在 fault window 内介入；
2. 它是否至少改善一个指标：
   - stop ratio
   - max stop streak
   - controller new path count
   - completion time

#### Step 2：对 recovery 参数做小范围 calibration，而不是拍脑袋固定

当前 recovery gate 参数是：

- `linear_scale = 0.35`
- `angular_scale = 0.50`
- `active_timeout = 1.0 s`

如果继续改进，建议不要大范围网格搜索，而是只做一个小型、可解释的 3 档校准：

- 线速度：`0.25 / 0.35 / 0.50`
- 角速度：`0.40 / 0.50 / 0.70`
- active timeout：`0.5 / 1.0 / 1.5 s`

评估原则：

- 如果线速度压得太低，可能虽然更稳，但 traversal time 过度上升；
- 如果角速度压得太低，可能反而降低纠偏能力；
- 如果 active timeout 太短，gate 会抖动式开关；
- 如果 active timeout 太长，recovery 会拖到 fault 结束后还维持保守状态。

#### Step 3：从“固定缩放”升级到“分级响应”

如果最小 gate 证明有效，下一步最自然的升级不是直接做完整 fault diagnosis，而是做 `severity-aware gating`。

例如按 fault 类型或 fault 活跃程度分层：

- 轻度 fault：只缩放 linear velocity
- 中度 fault：线速度缩放 + 角速度轻度缩放
- 重度 fault：线速度大幅降低，并延长 active timeout

这样仍然保持实现简单，但会比单一固定参数更容易解释。

#### Step 4：再考虑向 Nav2 内部策略延伸

只有在外部 gate 已经证明“方向上有帮助”之后，才值得继续改更深层的策略，例如：

- fault active 时切换更保守的 controller 参数；
- fault active 时调整 local costmap 更新策略；
- fault active 时进入专用 behaviour branch。

否则过早进入 Nav2 内部复杂改动，会让“fault 本身的 effect”和“恢复策略的副作用”混在一起。

#### 9.6.1 recovery 后续计划的一句话版本

如果要继续推进 recovery，本项目最合理的路线是：

> 先把最小 conservative velocity gate 做成可比较、可复现的 pilot result，再做小范围参数校准，最后才考虑更深层的 Nav2-aware recovery。

## 10. 三周主线计划对照：完成了什么，没完成什么

### 10.1 Week 1：实验设计与统计严谨性

原始目标：

- 确定多少次重复实验才足够；

<!-- -->

- 查基础统计 / Bayesian data analysis；

<!-- -->

- 对 world 8 增加 baseline 和 fault repetitions；

<!-- -->

- 观察均值、标准差、置信区间是否稳定；

<!-- -->

- 明确后续统一重复次数；

<!-- -->

- 写清楚为什么选 8 个 worlds；

<!-- -->

- 建立候选 fault 清单和定性现实性排序。

实际完成情况：

| 子任务                        | 状态               | 说明                                                                    |
|-------------------------------|--------------------|-------------------------------------------------------------------------|
| 重复次数判断方法              | 已完成             | 建立 sequential paired design 与 CI-based stopping rule                 |
| world 8 repetitions           | 已完成             | 实际用 world 8 完成校准                                                 |
| mean / std / CI 稳定性观察    | 已完成             | 用 paired difference 与 CI half-width 做停止判断                        |
| 统一 repeats                  | 已完成             | 第一轮正式 campaign 统一为 6 pairs                                      |
| world selection justification | 已完成，但形式升级 | 原本是“justify 8 worlds”，后来升级为更强的 9-world stratified selection |
| 候选 fault 清单与排序         | 已完成             | 建立 FMEA-inspired qualitative ranking                                  |
| 统计学阅读                    | 部分完成           | 已完成方法落地与解释，但未单独整理成系统 literature note                |

Week 1 的总体判断：

> 已完成到可以作为后续全部实验的统一方法框架。

### 10.2 Week 2：完整传播证据与 fault characterisation

原始目标：

- 系统分析 frontal LiDAR masking；

<!-- -->

- 形成
  `LiDAR masking -> perception/costmap -> planning/controller -> motion degradation -> mission-level impact`
  的证据链。

实际完成情况：

| 子任务                                    | 状态   | 说明                                                                                                            |
|-------------------------------------------|--------|-----------------------------------------------------------------------------------------------------------------|
| frontal masking 正式 campaign             | 已完成 | 9 worlds x 6 pairs                                                                                              |
| propagation 代理指标                      | 已完成 | completion time、path length、stop ratio、mean speed、controller new path count、pre/during/post fault 分段指标 |
| raw `/scan` vs `/scan_faulted` 直接可视化 | 未完成 | 尚未整理成系统图证                                                                                              |
| local/global costmap 直接证据             | 未完成 | 尚缺截图或日志提取                                                                                              |
| planner path / local plan 直接证据        | 未完成 | 尚缺代表性图证                                                                                                  |
| `cmd_vel` waveform                        | 未完成 | 尚未形成整理后的时序图                                                                                          |
| baseline 同时间窗严格 counterfactual      | 未完成 | 还需要为代表性 case 单独整理                                                                                    |

Week 2 的总体判断：

> 已完成到足以进入下一阶段，但 direct layer-by-layer evidence
> 还没有补满。

### 10.3 Week 3：fault 扩展，并在条件允许时开始 recovery pilot

原始目标：

- 把同一种 LiDAR fault 扩展到不同 severity / duration；

<!-- -->

- 在若干代表性 worlds 中验证；

<!-- -->

- 再加入第二种高优先级 fault；

<!-- -->

- 如果 logging / analysis 稳定，则启动 minimum recovery pilot。

实际完成情况：

| 子任务                      | 状态         | 说明                                                     |
|-----------------------------|--------------|----------------------------------------------------------|
| fault 参数校准              | 已完成       | masking / dropout / odom 都做了参数层面的 calibration    |
| fault 扩展                  | 已完成一部分 | dropout 成为第二条正式主线；odom 成为 exploratory branch |
| 代表性 worlds 验证          | 已完成       | masking 与 dropout 都扩展到 9-world formal campaign      |
| 第二种高优先级 fault        | 已完成       | intermittent LiDAR dropout                               |
| minimum recovery pilot 实现 | 已完成       | recovery gate 节点与 launch / tooling 已接好             |
| recovery 正式评估结果       | 未完成       | 尚未形成稳定可汇报的 recovery dataset                    |

Week 3 的总体判断：

> 主线已经进入 recovery 阶段，但 recovery
> 目前完成的是“实现与实验准备”，不是“稳定有效性结论”。

## 11. 本阶段最重要的结论

### 11.1 关于 benchmark 与 world selection

- `tuned` 相比 `original` 有明确提升：`126 -> 210` successes。

<!-- -->

- 300-world benchmark 成功建立了 world difficulty landscape。

<!-- -->

- 正式 9-world 集合具有明确分层逻辑，而非任意挑选。

### 11.2 关于 repeated trials

- 通过 `world 8` 的 sequential paired calibration，当前主线实验采用
  `6 pairs` 是有数据支持的。

<!-- -->

- 这不是抽象真理，而是对当前 dissertation fault campaign 的工程化折中。

### 11.3 关于 fault propagation

- Frontal masking 与 dropout 都已成功跑通完整自动化 campaign。

<!-- -->

- 两者都能在 `tuned_clean` 配置下造成可测量的跨层退化。

<!-- -->

- 当前数据最支持的主结论是：  
  **前向 LiDAR 感知退化会首先改变局部感知与规划行为，再通过
  stop-go、replanning 和时间损失反映到 mission-level outcome。**

### 11.4 关于 fault portfolio

- 第一轮主线已经形成两条完整感知层 fault campaign：
  - frontal masking

  <!-- -->

  - intermittent dropout

<!-- -->

- odom drift 作为状态估计层 fault 已完成 injector
  验证，但暂不作为当前正式 comparative set 的核心对象。

<!-- -->

- recovery 已从想法推进到实际实现，但还没有形成正式可报告结论。

## 12. 当前产出与数据位置

以下路径为 VM 侧实验数据与分析产物的主要位置：

### 12.1 300-world benchmark 与 world selection

- `~/dissertation/barn_ros2/src/The-Barn-Challenge-Ros2/experiment_runs/selection_original0-299__tune0-299/`

### 12.2 Frontal masking campaign

- `~/dissertation/barn_ros2/src/The-Barn-Challenge-Ros2/experiment_runs/fault_campaigns/frontal_masking_tuned_clean_campaign1/`

### 12.3 LiDAR dropout campaign

- `~/dissertation/barn_ros2/src/The-Barn-Challenge-Ros2/experiment_runs/fault_campaigns/lidar_dropout_tuned_clean_campaign2/`

### 12.4 Odom pilot / smoke tests

- `~/dissertation/barn_ros2/src/The-Barn-Challenge-Ros2/manual_fault_runs/`

### 12.5 Recovery 相关代码位置

- `~/dissertation/barn_ros2/jackal_helper/scripts/fault_aware_cmdvel_gate.py`

<!-- -->

- `~/dissertation/barn_ros2/jackal_helper/launch/BARN_runner.launch.py`

<!-- -->

- `~/dissertation/barn_ros2/tools/run_paired_fault_study.py`

<!-- -->

- `~/dissertation/barn_ros2/tools/analyze_fault_pipeline.py`

## 13. 未来目标：基于未完成部分怎么继续做

### 13.1 先补 propagation 直接证据，而不是再扩大 world 数

建议优先选两个代表性 case：

- `frontal masking` 选 `world 8` 或 `world 86`

<!-- -->

- `dropout` 选 `world 8` 或 `world 86`

对每个 case 补齐：

- raw `/scan` vs `/scan_faulted`

<!-- -->

- fault timing

<!-- -->

- trajectory

<!-- -->

- stop ratio / speed timeline

<!-- -->

- local/global costmap

<!-- -->

- planner path 或 local plan

<!-- -->

- `cmd_vel`

这样能把目前“代理指标已齐、直接图证不足”的问题补起来。

### 13.2 把 recovery 从“可运行”推进到“可报告”

下一步最合理的 recovery 试验规模不是直接上 9 worlds，而是：

- worlds：`8, 86`

<!-- -->

- conditions：`fault-only` vs `fault+recovery`

<!-- -->

- repeats：每个 world 先做 `3 pairs`

先回答两个问题：

1.  recovery gate 是否真的能稳定介入 fault window；

<!-- -->

1.  它是否至少改善一个指标：
    - completion time

    <!-- -->

    - stop ratio

    <!-- -->

    - max stop streak

    <!-- -->

    - controller new path count

### 13.3 对 odom branch 做“继续 or 冻结”的明确决策

当前更推荐的做法是：

- 把 odom drift 先冻结为 `negative / exploratory result`

<!-- -->

- 除非后续 recovery 或 state-estimation
  章节特别需要，再决定是否重新加强注入

这能避免时间继续消耗在一个尚未稳定泛化的分支上。

### 13.4 补一个简短的 sensitivity check

为了让 Week 1 的 repeat-count design 更稳，可以后续补一个小型
sensitivity note：

- half-width threshold：`3 / 5 / 7 s`

<!-- -->

- relative threshold：`0.20 / 0.25 / 0.33`

目标不是重做实验，而是证明：

> stop decision 不会因为单一阈值的微小变化而完全翻转。

## 14. 建议作为下一阶段工作的起点

基于当前状态，后续最合理的工作顺序为：

1.  对 `frontal masking` 做更系统的 propagation evidence 整理：
    - raw scan / faulted scan

    <!-- -->

    - local/global costmap

    <!-- -->

    - planner path updates

    <!-- -->

    - controller behaviour

    <!-- -->

    - stop ratio / speed / timeline

<!-- -->

1.  对 `dropout` 选 1 个代表性 world 做同样的链式分析，用来和 masking
    做机制对比。

<!-- -->

1.  在此基础上开始 `minimum recovery pilot`，优先围绕 frontal masking 做
    conservative response / velocity gating 一类最小恢复策略。

## 15. 一句话总结

本阶段已经完成了从 **benchmark 建模、world selection、repeat-count
calibration、fault injector 建立，到两组正式 fault campaign 落地**
的完整闭环。  
但作为过程记录，更准确的结论是：  
**Week 1 的方法框架已基本固定，Week 2 的 fault characterisation
已经完成到足以支撑主线，Week 3 的 recovery
已完成工程实现但尚未形成稳定实验结论。**  
下一阶段重点不再是“有没有 fault effect”，而是把已有结果进一步整理成
**可解释的 propagation evidence**，并把 recovery
从“可运行机制”推进到“可报告结果”。

16.问题

（1）基于想要拿distinction，甚至是想要之后可能读博的一些科研能力证据，我现在是完成了两种fault的记录，我需要接着进行第三种fault吗？还是认真分析好前两种fault+可视化证据就够了？

（2）基于同样的想法，我需要让recovery pilot落地吗？
