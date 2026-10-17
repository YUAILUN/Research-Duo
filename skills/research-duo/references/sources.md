# 来源与设计归属

核查日期：2026-10-17。Research Duo 为独立项目，与 K-Dense、TypeSafe AI 没有隶属或官方合作关系。以下均为官方一手来源，接口可能变化。

| 来源 | 核实内容及本项目用途 |
| --- | --- |
| [Pantheon 介绍](https://www.k-dense.ai/blog/introducing-pantheon-80-voices) | 80 个 AI persona、四类视角、引用、共识、分歧和下一步；提炼探索结构，非真人意见 |
| [Pantheon 应用](https://pantheon.k-dense.ai/) | 公开界面；可接收用户导出观点，不假设公开 API |
| [mimeo](https://github.com/K-Dense-AI/mimeo) / [mimeographs](https://github.com/K-Dense-AI/mimeographs) | 推理风格 skill 的项目及目录；只作设计参考，未复制 persona 文本 |
| [Jev 发布](https://typesafe.ai/blog/introducing-system-one-models-and-jev) | System One、RLCD、类型判断；性能宣传有评测条件，不继承其性能保证 |
| [Introduction](https://docs.typesafe.ai/introduction) | state 与独立问题，代码组合答案 |
| [HTTP API](https://docs.typesafe.ai/api) | 客户端请求和响应契约 |
| [Choice](https://docs.typesafe.ai/primitives/choice)、[Score](https://docs.typesafe.ai/primitives/score)、[Noul](https://docs.typesafe.ai/primitives/noul) | 三类判断保留各自语义 |
| [Confidence](https://docs.typesafe.ai/confidence) | 分布统计量，不是独立测量的正确率 |
| [Models](https://docs.typesafe.ai/models) | 版本/别名、上下文与语种范围 |
| [已知局限](https://docs.typesafe.ai/model-jaggedness/jev-1.13) | 数值、无关上下文、注入、选项顺序等；数学由代码完成，做扰动验证 |
| [引用检查](https://docs.typesafe.ai/cookbooks/citation_check) | 引文定位与语义支持分开核查 |

Research Duo 原创部分：证据 ID、竞争假设卡、少数意见、分流、权重敏感性、实验反馈与校准日志之间的连接。80 个视角是原创功能标签，不是 Pantheon 真人风格文件。多视角不构成统计独立，共识不增加实验证据。

“蒸馏”指方法与编排；没有训练模型、获取 Jev 权重或复现 RLCD。类型正确不能证明事实正确。没有将“零格式错误”扩展为“零科学错误”，也没有将官方评测倍率写成本项目性能。

核查当日官方列出 jev-1.13.0 与 jev-1.14.0，jev-latest 指向前者，jev-preview 指向后者。正式复现应固定经评估版本，并记录实际响应 model。示例默认别名便于入门。

工程测试只验证本地契约、分流和计算逻辑，不证明任何特定领域的模型准确率。真实 API 需配置密钥另行运行；离线示例均明确标记为合成。
