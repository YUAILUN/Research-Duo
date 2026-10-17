# 决策与校准

## 不确定性分开报告

研究证据（测量、效应区间、偏倚、外推）、模型分布、决策偏好（成本、效用、风险）是三种不同对象。confidence 描述分布集中度，不等于实证正确率，也不宜跨选项数不同的问题简单平均。共用模型与证据的判断通常相关，不能随意将概率相乘。

## gate 输入与优先级

scripts/decision_tools.py gate 接收资产中的 gate-example.json 格式：

- risk: low/medium/high；evidence_status: verified/partial/missing/conflicted。
- in_distribution、reversible: 布尔。
- provider: jev/llm/human/fixture；model、question_set_id: 实际版本。
- calibration: validated、model、question_set_id、validation_ref。验证声明必须有真实依据。
- answer: Choice 回答，包括 type、choice、probabilities、confidence。
- policy: min_probability、min_margin，按代价和验证表现制定。
- abstain_options: 不能变为推荐的选项名，例如 insufficient。

优先级：高影响/不可逆 → review；缺失/部分证据 → gather_evidence；冲突 → deliberate；分布外 → review；校准不匹配或非 Jev → review；弃权或概率/领先差不足 → deliberate；其余 → recommend。所有路线 execute=false。

示例阈值不是科学标准。输入声明不是安全证明，调用方负责核实证据与验证记录。工具不能检测所有语义错误，也不会执行建议。

## rank

排除 eligible=false 的候选，以 [0,1] 的“越大越好”分数与非负权重计算效用。成本先反向并解释尺度，主观评分需依据。输出基准与逐个权重 ±20% 后归一化的情景；并列时返回全部首选。

仅测试局部权重扰动，不覆盖联合变化、证据误差或全部合理情景。分数不是成功概率；首选不稳时给条件化结论。

## calibrate

输入 [{"p":0.8,"y":1}, ...] 的已标注二元数据，输出 Brier、等宽分箱 ECE、每箱样本量/平均预测/发生率，以及阈值下的覆盖率与错误率。对称接受 p≥t 或 p≤1−t，不是 confidence 阈值评价。

训练、调阈值、测试分开，按来源簇或时间分割，防止同研究泄漏；按语种、学科、少数类别分层。中文需中文验证。报告样本量与误差范围，小样本无法证明校准，ECE 依赖分箱。

二元指标用于 Noul 或预定义 Choice 选项的 one-vs-rest；不声称完整多类验证，必要时逐类并补多类 Brier/log loss。脚本从不自动设置 validated=true。

记录预测时间、模型/题目版本、输入哈希、分布、后续结果、评价人与结果时间，保留失败样本。模型、选项、领域、翻译变化后重新评估。
