# 可选 Jev 接入

依据 [HTTP API](https://docs.typesafe.ai/api)、[模型页](https://docs.typesafe.ai/models) 和 [原语](https://docs.typesafe.ai/primitives)，核查于 2026-10-17。

脚本只向 https://api.typesafe.ai/v1/systemone 发请求，默认 dry-run，不打印 state 或密钥。从 skill 目录运行：

```bash
python3 scripts/jev_client.py assets/jev-request.json
python3 scripts/jev_client.py assets/jev-request.json --execute --out jev-result.json
```

第二条需要环境变量 TYPESAFE_API_KEY，会向 TypeSafe 发送请求材料并可能产生费用。已有数据范围和费用授权时才运行。不要把密钥写入仓库、报告或示例。

客户端验证三类文本原语的请求/响应、选项、分布、评分与模型字段；保存 request_sha256、questions_sha256、时间、请求模型、实际返回和原始 response，校准默认 unvalidated。gate 的 question_set_id 可采用 questions_sha256。

这是简洁文本客户端，不实现 Box、图像、压缩或实验性长上下文。2 MiB 输入上限是本项目限制，非供应商上限；字节不等于 token。依赖其他答案的问题必须分轮。整数运算与统计交给代码。

请求有超时；限流/过载和部分 5xx 最多重试两次，单次退避不超过 10 秒；更长 Retry-After 停止。认证、参数、无效响应失败不自动换服务。错误信息不暴露原始请求或服务端回显内容。

state 放相关原文、source_id 和条件，不只放模型摘要。Jev 判断引用关系或单一评估维度，不负责检索与长文生成。用原文/摘要、选项顺序、边界条件、中英文进行抽查，明显不稳时复核。普通模型模拟不能标成真实 Jev 调用。
