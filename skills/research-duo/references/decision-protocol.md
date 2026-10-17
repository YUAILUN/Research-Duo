# 类型化判断与可复现决策

这里的结构是 Research Duo 的本地契约，不是 Jev 请求格式。先审查科学含义再运行计算。脚本验证类型、依赖与公式，不代替文献核实、因果识别或偏好征询。

## 运行方式

在技能目录运行（安装后先定位包含本 SKILL.md 的目录）：

```bash
python3 scripts/decision_tools.py gate assets/gate-example.json
python3 scripts/decision_tools.py audit assets/evidence-graph-example.json
python3 scripts/decision_tools.py rank assets/ranking-example.json
python3 scripts/decision_tools.py voi assets/voi-example.json
python3 scripts/decision_tools.py robust assets/robust-example.json
python3 scripts/decision_tools.py calibrate assets/calibration-example.json --bins 5 --threshold 0.8
```

所有示例都是合成输入。输出为 JSON；无外部调用，无自动执行动作。输入不合法返回退出码 2；不能把报错当作“不支持此科学主张”。Python 3.9+，不需 pip。可用对应 JSON 示例改写自己的输入。

## 1. 原子判断契约与门控 gate

每个判断恰有以下字段：

| 字段 | 含义 |
| --- | --- |
| id / question | 稳定 ID、单一有边界的问题 |
| kind | choice、ordinal 或 predicate |
| criteria | choice：至少两个不同选项字符串；ordinal：至少两个由低至高、明确锚点的级别字符串；predicate：含 true/false 判据的对象 |
| value | choice 选项字符串；ordinal 从 0 开始的级别整数；predicate 真/假；未知为 null |
| status | grounded / provisional / unknown / conflicted |
| basis | observed / inferred / assumed |
| evidence_ids | 已登记的证据 ID 列表，可空，但 grounded 必须有证据且不能 assumed |
| rationale | 说明判据、证据与值之间关系的简短依据 |

`grounded` 是需要审查的输入声明，不是脚本授予的事实认证。`unknown` 只允许 null；`conflicted` 可保留临时值或 null，但不能快速推荐。序数级别不是等距效用，不能直接用于数学排序。假设通常标 provisional + assumed。

[gate-example.json](../assets/gate-example.json) 给出完整输入。上下文字段：

- `decision_id`：正在判断的具体候选行动。
- `risk`：low/medium/high；`reversible`：布尔值。
- `framing_status`：sound/needs_reframe；`evidence_status`：verified/partial/missing/conflicted。
- `distribution_shift`：none/possible/unknown；`decision_stability`：stable/sensitive/untested。
- `evidence_ids`：账本已登记 ID；`judgments`：判断数组。
- `requirements`：判断 ID → 该行动所要求的允许值数组，如 `{"J1":[true]}`。已知“否”不能因类型正确就通过必要条件。

主要路由依优先级是：重构问题 → 高影响审查 → 冲突审议 → 补证 → 修订不符合条件的方案 → 迁移审查 → 压力测试/情景比较 → 暂定判断审查 → 推荐。返回全部 `blockers`，不要只处理第一条后忽略其余；推荐也只代表输入声明满足条件。`execute` 始终 false。

风险/稳定性必须来自前面的实质分析，不能为了通过门控而自填“稳定”。未用作必要条件的探索判断可以仍未知；它不会无故阻断一个已经充分支持的局部行动。

## 2. 证据依赖图 audit

[evidence-graph-example.json](../assets/evidence-graph-example.json) 的 `nodes` 中，每个节点有 `id / kind / label / depends_on`。类型为 evidence、assumption、claim、judgment、decision。evidence 还需 `source / cluster`；evidence 与 assumption 是根节点；其他节点至少引用一个依赖。自循环、循环、悬空 ID 都报错。

返回每个节点可追溯的证据、声明的同源簇、假设，以及 `changed_ids` 引发的全部 `affected_ids` 与 `decisions_to_revisit`。两篇同队列材料会保留两条引用但只有一个簇。簇由研究者识别，不会自动证明独立性；同簇相关材料应按实际情况一并放入 changed_ids。图通过不等于论证充分，也不等于因果 DAG 有效。

## 3. 偏好排序 rank

[ranking-example.json](../assets/ranking-example.json)：`weights` 是非负权重（总和大于零）；`options` 各含唯一 id、eligible；不符合条件者需 exclusion_reason，符合者需全部 criteria 的 scores。分数限定 0–1，方向统一为越高越好，必须交代归一化锚点；缺值报错，不补零。硬约束在此之前审查。

`U(a) = Σ w(k) × score(a,k) / Σ w(k)`。效用不是成功概率，不应用于未经解释的序数级别。脚本保留平局，并逐一把权重乘以 0.8/1.2；`stable_first_choice` 仅指这些局部扰动下的稳定，不代表所有合理情景都稳定。正式决策另测联合权重变化、删去同源证据和关键假设反转。

## 4. 实验信息价值 voi

只在能明确说明概率来源、效用单位与候选动作时使用；否则转 robust 或定性区分实验。不要为了计算而让模型随口给先验、似然和成本。经解释的主观先验可用于条件分析，但需要展示范围敏感性。

[voi-example.json](../assets/voi-example.json) 字段：`priors`（state → 概率）；`utilities`（action → state → 效用）；`experiments`（id、cost、likelihoods）；likelihoods 是 state → outcome → P(outcome|state)，每个状态的结果分布总和为 1，结果集合一致。`basis` 标 empirical/elicited/hypothetical，`assumptions` 说明 priors/likelihoods/utilities 来源，`utility_unit` 明确共同单位。cost 须转成同一效用单位，不能直接从“效用点”扣人民币。

```text
EU_now = max_a Σ_s P(s) U(a,s)
P(y) = Σ_s P(s) P(y|s)
P(s|y) = P(s) P(y|s) / P(y)
EVSI = Σ_y P(y) max_a Σ_s P(s|y) U(a,s) − EU_now
net_value = EVSI − experiment_cost
EVPI = Σ_s P(s) max_a U(a,s) − EU_now
```

零概率结果无后验，不影响期望。完整、有限状态模型且可忽略信息时 0 ≤ EVSI ≤ EVPI。脚本同时比较 `no_experiment`（净价值 0），允许不做实验。示例信息试验 EVSI=30、成本=5、净价值=25，EVPI=50；无信息试验 EVSI=0。数字均为教学设定。

这是一次实验、观察后仍可选择同一组动作的有限模型。不支持自适应多轮、实验本身改变状态或试验后动作集合改变等情形；这些需要显式扩展模型。EVSI 衡量改善决定的期望效用，不是统计显著性、一般知识价值或熵下降。必须重跑合理先验/似然/效用情景；单次输出不能证明稳健。

## 5. 无概率情景 robust

[robust-example.json](../assets/robust-example.json)：给 `scenarios`、action → scenario 的 `utilities`、共同 `utility_unit` 和 `assumptions`。不允许漏掉某行动的某情景值。先排除违反必要条件的行动；候选集应包含适当的维持现状/延后或可逆选项。

```text
regret(a,s) = max_b U(b,s) − U(a,s)
minimax_regret = argmin_a max_s regret(a,s)
maximin = argmax_a min_s U(a,s)
```

两者可能不同：前者控制错失机会的最大损失，后者保护绝对最差收益。脚本同时报告，保留平局，不替用户决定风险偏好。结果只对列出的情景成立；不能漏掉重要失败情景后宣称“最优”。效用仍须有意义，未知效用也不能任填。

## 6. 结果验证 calibrate

输入事前预测/实际结局数组 `[{"p":0.8,"y":1}, ...]`；y 为 0/1，p 为该结局的概率。报告 Brier、等宽 ECE、各箱样本数/均值、接受覆盖率与选择性错误率。接受规则 `max(p,1-p) >= threshold`，0.5 < threshold ≤ 1；没有接受样本时错误率为 null。

这是回顾性描述统计，不会拟合校准器、生成置信区间或认证任何阈值。见 [更新与验证](learning-loop.md)。不要输入角色共识比例、偏好分数或伪装成实际结局的自评。
