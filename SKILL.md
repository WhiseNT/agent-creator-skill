---
name: agent-creator-skill
description: 帮助 AI 设计、实现、迁移、调试和测试完善的 LLM Agent。用户提到 Agent、智能体、工具调用、function calling、MCP、结构化输出、流式事件、会话状态、RAG、Provider 迁移或 Agent runtime 时触发。默认聚焦单 Agent 或有限规模的可靠实现；不要把所有 Provider 都假设成 OpenAI Chat Completions。
compatibility: 需要文件读写和代码搜索能力；查询快速变化的 API、模型、配额、价格或弃用状态时必须访问官方文档。
---

# Agent Creator Skill

## 目标

帮助用户产出**可运行、可测试、可恢复、可迁移**的 LLM Agent，而不只是一个返回文本的 API 示例。

最小闭环：

```text
用户输入 -> 模型推理 -> Tool Call -> 应用校验与执行
         -> Tool Result -> 模型继续推理 -> 最终输出
```

根据需求再增加流式输出、结构化结果、持久状态、RAG、Memory、审批、安全边界、追踪或托管运行时。

## 不可违反的原则

1. **先识别 Provider 和 API family，再写请求代码。** 同一 Provider 可能同时提供原生接口、OpenAI-compatible 接口和云平台接口。
2. **模型输出是不可信输入。** 工具名、参数、路径、URL、SQL、Shell 和目标资源必须在应用侧校验。
3. **Tool Call 不等于 Tool Execution。** 模型提出的动作必须经过注册检查、Schema 校验、业务规则、Policy、Approval 和执行边界。
4. **流式输出是事件流。** 工具参数必须等到明确完成事件后再解析；未知事件要保留或记录。
5. **OpenAI-compatible 不等于语义完全兼容。** 认证、模型标识、文件、工具、状态、错误、配额和流式协议仍需验证。
6. **保留 Provider metadata。** reasoning、citation、grounding、safety、usage、trace 和未知原始事件不能被统一层静默丢弃。
7. **快速变化的信息只信官方文档。** 模型列表、价格、配额、预览状态和弃用日期不要依赖记忆。

## 工作流

### 1. 先读代码，再确定最小需求

先检查现有代码、依赖、配置、测试和运行方式，不要为了“像 Agent”立即引入框架。

从需求中识别：

- 语言、运行环境和部署方式；
- Provider、API family、Model、Deployment；
- 同步、异步、流式或实时；
- 是否有工具、MCP、文件、图片、音频或视频；
- 是否需要 Session、Checkpoint、Memory、RAG 或人工审批；
- 数据驻留、身份、网络、延迟、成本和可靠性约束。

### 2. 选择资料并保持渐进加载

使用 [机器可读路由](references/routes.json) 选择资料，并用 [Canonical Contract](references/canonical-contract.md) 统一术语和不变量。

1. 根据用户目标识别实现、迁移、调试、审查或评测意图。
2. 按 `defaults.selection_order` 稳定选择一条最具体的路由，不依赖数组顺序。
3. 默认只读取一个 `primary` 和最多两个 `supplements`，不要把整个 `references/` 加入上下文。
4. 先读取该路由声明的 `contract_ids`；专题文档与 Contract 冲突时以 Contract 为准。
5. 只有跨模块设计或明确的架构审查才扩大读取范围。

常用入口：

- Agent 边界和最小架构：`architecture.reference` 或 `architecture.harness.quick`；
- 工具循环、流式、结构化输出：`implementation.api_patterns`；
- Provider/API 选型：`selection.api_capability`；
- 工具、权限、状态、事件和测试：选择对应的核心 engineering route；
- 指定云平台或协议：选择对应 `provider.*` 或 `protocol.*` route。

如果目标 Provider 没有本地 Reference：只查询其官方文档，确认认证、API family、模型/部署、工具、结构化输出、流式和错误语义，再把差异局部封装进 adapter。

### 3. 设计清晰的 Agent 边界

区分：

- **Agent Kernel**：模型—工具循环、标准消息/事件、停止、取消和预算；
- **Agent Harness**：Context、Provider、Tool、Policy、Sandbox、State、Event、Artifact 和交付环境。

不要把所有能力塞进一个 `Agent` 类。至少明确：

```text
Orchestrator   循环、终止条件、取消和预算
ModelClient    某个 API family 的调用
ToolRegistry   工具定义和执行器
ToolValidator  名称、Schema、权限和业务参数校验
StateStore     Session、Checkpoint 和业务状态
Policy         allow / deny / require approval
EventSink      流式事件、日志和 trace
```

简单任务可以合并实现，但不能混淆职责和状态所有权。

### 4. 实现可靠工具循环

1. 发送系统指令、历史消息和工具定义。
2. 收集完整响应或流式事件。
3. 提取全部 Tool Call，不要只处理第一个。
4. 校验工具注册、参数 Schema、业务规则和调用权限。
5. 对删除、付款、发送、发布、权限修改等高风险动作要求明确审批。
6. 使用超时、取消、幂等键和沙箱/allowlist 执行工具。
7. 每个 Tool Result 必须关联原始 Tool Call ID。
8. 继续调用模型，直到最终答案或触发终止条件。
9. 记录 usage、耗时、错误、调用次数和关键 Provider metadata。

必须设置：最大迭代次数、最大工具调用数、单工具超时、总时间或成本预算、重复调用检测和取消信号。

### 5. 处理输出、流式和失败

**Structured Output：**

- 区分最终响应 Schema 和 Tool Argument Schema；
- 使用 Provider 支持的 Schema 子集；
- 应用侧再次执行 Schema 和业务校验；
- 区分拒答、安全拦截、截断、空输出和 Schema 错误；
- 验证失败只允许有限重试，不得无限自修复。

**Streaming：**

统一处理 `TextDelta`、`ReasoningDelta`、`ToolCallStart`、`ToolCallArgumentsDelta`、`ToolCallComplete`、`UsageUpdate`、`ProviderEvent` 和 `Error`。未完成 JSON、截断参数或错误事件不得执行工具。

**Retry / Idempotency：**

- 参数或 Schema 错误：修复请求，不重试原请求；
- 身份或权限错误：停止并报告；
- 限流、网络和 5xx：仅对安全请求有限重试，并尊重服务端提示；
- 工具业务错误：作为结构化结果回传或按策略终止；
- 不确定写操作是否成功：先查询权威状态或使用幂等 Receipt，不能盲目重放。

### 6. 安全、状态与测试

至少检查：

- Prompt Injection、RAG 内容和 Tool Result 是否能越权；
- 工具参数是否经过 Schema 与业务规则双重校验；
- 凭据是否只在服务端/密钥服务；
- 文件、URL、SQL、Shell 和代码执行是否有沙箱或 allowlist；
- Session、Business State、Memory、Artifact 和 Trace 是否各有权威所有者；
- 日志是否泄漏 Secret、PII 或完整 Prompt。

至少测试：普通回答、单/多工具调用、非法工具和参数、超时与业务失败、最大步骤、流式参数分片、结构化输出失败、429/5xx/网络中断、幂等与重复调用、Prompt Injection、未知字段和未知事件。优先使用 fake transport、录制响应或 Provider adapter mock，并保留少量受控集成测试。

## 高级平台边界

本 Skill 不默认加载多租户平台、生产运维、工作流调度与容量、隐私/数据治理、成本治理、Provider 事故响应、复杂 Memory 治理、Coding Agent 工作区隔离等资料。

如果任务明确涉及这些主题，切换到同级的 `agent-platform-engineering-skill`，先完成本 Skill 的 Kernel/Harness 基础，再加载平台级专题。

## 输出要求

实现或审查结束时，简要说明：

- 选定的 Provider、API family、Model/Deployment；
- Agent 循环、工具安全边界和状态所有权；
- 修改的文件与运行过的测试；
- 用户仍需配置的环境变量、权限或云资源；
- 已确认的 Provider 特有限制。

不要输出真实密钥，不要把未经官方资料验证的模型名、价格、配额或弃用时间写成确定事实。
