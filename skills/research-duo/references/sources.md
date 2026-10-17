# 来源与设计归属

核查日期：2026-10-17。Research Duo 是独立方法型 skill，与 K-Dense、TypeSafe AI 没有官方隶属关系。不调用 Pantheon 或 Jev，不复制 persona 文本、模型权重或训练算法。

| 一手来源 | 核实内容及用途 |
| --- | --- |
| [Pantheon 介绍](https://www.k-dense.ai/blog/introducing-pantheon-80-voices) / [应用](https://pantheon.k-dense.ai/) | 80 个 AI persona、多类视角、引用、共识与分歧；借鉴探索结构 |
| [mimeo](https://github.com/K-Dense-AI/mimeo) / [mimeographs](https://github.com/K-Dense-AI/mimeographs) | 推理风格 skill 的公开背景，只作参考 |
| [Fusion Intelligence 固定版本](https://github.com/YUAILUN/Fusion-Intelligence/tree/22253d7dfecacb0a50a797388582ffcf193bff16) | 用户已有技能：证据分层、交叉质疑、因果/预测/测量检查、条件化动作；用于避免重复堆叠 |
| [Jev 发布文章](https://typesafe.ai/blog/introducing-system-one-models-and-jev) | System One 的设计目标与 RLCD 背景；不移植其性能声称 |
| [TypeSafe Introduction](https://docs.typesafe.ai/introduction) | 状态、原子问题、类型化输出、显式逻辑组合 |
| [Confidence](https://docs.typesafe.ai/confidence) | 输出分布统计不能直接当实测任务正确率 |
| [已知能力边界](https://docs.typesafe.ai/model-jaggedness/jev-1.13) | 数值和输入扰动等局限；提醒不要把类型保证当科学正确性 |
| [引用检查](https://docs.typesafe.ai/cookbooks/citation_check) | 来源定位与语义支持分别核查 |
| [Chaloner & Verdinelli：Bayesian Experimental Design](https://www.stat.cmu.edu/tr/tr599/tr599.html) | 实验设计作为期望效用决策的经典方法背景 |
| [Anderson & Zachary：Minimax decision rules](https://arxiv.org/abs/2203.01420) | 无概率情景的 minimax 思路，以及对情景/选项集合的敏感性 |
| [Agent Skills 规范](https://agentskills.io/specification) | 标准 SKILL.md 和相对资源结构 |
| [Claude Code](https://code.claude.com/docs/en/skills) | 个人/项目技能位置与调用方式 |
| [Codex](https://learn.chatgpt.com/docs/build-skills) | .agents/skills 与技能发现 |
| [Antigravity](https://antigravity.google/docs/skills) | 当前 .agents/skills、全局 .gemini/config/skills 及旧路径兼容 |

Research Duo 的具体实现包括科研闭环编排、本地判断契约、证据依赖检查、实验价值与情景遗憾计算、安装器和回归测试。EVSI、minimax regret、证据审查等是通用方法，不宣称为本项目发明。80 个功能视角为原创标签，不是真实专家意见。

方法蒸馏不是模型训练；没有执行 Jev 服务性能测试，也没有独立证明整体胜过其他技能。软件验证和科研能力评估分开记录。
