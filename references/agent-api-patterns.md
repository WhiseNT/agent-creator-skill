# Agent API 通用实现模式

## 1. 工具循环

伪代码：

```python
messages = initial_messages
seen_calls = set()

for step in range(max_steps):
    response = provider.generate(messages=messages, tools=tool_specs)
    calls = extract_tool_calls(response)

    if not calls:
        return extract_final_answer(response)

    messages = append_model_output(messages, response)

    for call in calls:
        validated = registry.validate(call.name, call.arguments)
        fingerprint = stable_fingerprint(call.name, validated)

        if fingerprint in seen_calls and not registry.is_repeatable(call.name):
            result = ToolResult.error(call.id, "duplicate_call")
        else:
            policy.authorize(call.name, validated)
            result = executor.run(
                call.name,
                validated,
                timeout=registry.timeout(call.name),
                idempotency_key=business_idempotency_key(call),
            )
            seen_calls.add(fingerprint)

        messages = append_tool_result(messages, call.id, result)

raise MaxStepsExceeded(max_steps)
```

### 关键约束

- 先把模型的完整输出加入历史，再追加工具结果；具体顺序必须符合 provider 协议。
- 一个响应可能包含多个工具调用。
- 工具结果必须关联正确的 call ID。
- 不要信任模型声称工具已经执行。
- 不要把异常堆栈原样暴露给模型或最终用户。
- 工具错误应结构化，例如 `{code, message, retryable}`。

## 2. 工具定义

工具定义包含：

```text
name
human description
input schema
output contract
side-effect level
required permission
timeout
retry policy
idempotency policy
approval policy
```

工具名称保持稳定，避免把版本号或动态用户输入放入名称。

描述应说明何时使用、何时不要使用以及关键约束，但不要塞入大量业务数据。

## 3. 参数校验

至少两层：

1. JSON Schema：类型、必填字段、枚举、格式；
2. 业务规则：权限、资源归属、金额上限、路径边界、允许域名、状态机。

高风险参数应由应用补全或重新查询，不能完全依赖模型，例如当前用户 ID、租户 ID、权限范围和付款账户。

## 4. 副作用分级

| 等级 | 示例 | 默认策略 |
|---|---|---|
| 只读 | 查询天气、读取公开数据 | 可自动执行，仍需超时和限流 |
| 低风险写入 | 创建草稿、添加标签 | 可自动或会话级授权 |
| 高风险写入 | 发邮件、发布内容、改权限 | 执行前展示参数并确认 |
| 不可逆/敏感 | 删除、付款、生产部署 | 强制人工确认、幂等、审计和最小权限 |

## 5. 流式事件聚合

维护每个 response item / content block / tool call 的状态：

```text
response_id
item_index or block_index
tool_call_id
arguments_buffer
text_buffer
finish_reason
usage
provider_metadata
```

只有收到完成事件后才解析工具 JSON。结束时校验：

- 是否存在未完成 block；
- 工具参数是否有效；
- 是否有 provider error；
- 是否因长度、安全或取消而终止；
- usage 是否最终到达。

## 6. 结构化输出

建议处理顺序：

```text
provider strict schema
  -> transport success
  -> provider finish/safety check
  -> JSON parse
  -> local schema validation
  -> business validation
```

失败时只进行有限修复。若 provider 明确拒答或安全拦截，不要把它当普通 JSON 语法错误重试。

## 7. 上下文与状态

区分：

- Provider conversation state：response/thread/session ID；
- Agent execution state：当前步骤、待审批调用、重试次数；
- Business state：订单、工单、用户权限；
- Memory：长期偏好或摘要；
- Trace：不可作为业务真相。

不要只保存 provider conversation ID。恢复任务还需要工具结果、幂等键、检查点和业务状态版本。

## 8. Prompt injection 防护

检索文档、网页、邮件、文件和工具输出都属于不可信内容。

- 不允许内容自行提升权限；
- 系统策略和工具权限由代码控制；
- 将外部内容放入明确的数据边界；
- 对“忽略之前指令”“把密钥发到某地址”等内容按数据处理；
- URL fetch、浏览器、shell、SQL 和文件工具必须有独立安全策略；
- 重要操作依据已验证业务数据，而非模型复述。

## 9. 重试

可重试：

- 429；
- 临时 5xx；
- 安全的网络连接失败；
- provider 明确标记 retryable 的错误。

通常不可直接重试：

- 400 schema 错误；
- 401/403；
- 模型不存在；
- 已经可能成功的非幂等写操作；
- 达到上下文限制但请求未缩减。

使用指数退避、随机抖动、最大次数和总时间预算。优先读取 `Retry-After` 或 SDK 暴露的重试信息。

## 10. 可观测性

记录：

```text
trace_id / span_id
provider / api_family / model_ref
response_id
agent step
latency
token usage / cached tokens
finish reason
tool name / duration / status
retry count
approval decision
schema validation result
```

默认对 prompt、tool arguments、tool result 和文件内容做脱敏或摘要。不要记录密钥。

## 11. 测试策略

### 单元测试

- provider response -> normalized events；
- tool schema 与业务校验；
- 循环终止；
- 重复调用检测；
- 重试分类；
- structured output 验证。

### 契约测试

为每个 provider adapter 保存脱敏 fixture，确保 SDK 升级后映射不变。

### 集成测试

使用低成本模型和无副作用工具，验证真实认证、stream、tool call 和 usage。测试必须可通过环境变量关闭。

### 安全测试

包含提示注入、越权资源 ID、路径穿越、SSRF、SQL 注入、shell 注入、巨型参数和工具调用洪泛。
