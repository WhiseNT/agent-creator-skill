---
name: agent-creator-skill
description: 指导 AI 设计、实现、迁移和审查基于 LLM API 的 Agent。凡是用户提到编写 Agent、智能体、工具调用、function calling、MCP、结构化输出、流式事件、会话状态、RAG、Agent runtime，或需要在 OpenAI、Anthropic、Gemini、Azure AI Foundry、Amazon Bedrock、Vertex AI 等模型接口之间选型与迁移时，都应优先使用本 Skill；即使用户只说“接入一个模型并调用工具”，也应触发。不要把所有提供商都假设成 OpenAI Chat Completions。
compatibility: 需要文件读写和代码搜索能力；查询快速变化的 API、模型、配额、价格或弃用状态时需要访问官方文档。
---

# Agent Creator Skill

## 目标

帮助用户产出可运行、可测试、可迁移的 LLM Agent，而不只是一个能返回文本的 API 示例。

Agent 至少包含以下闭环：

```text
用户输入
  -> 模型推理
  -> 模型提出工具调用
  -> 应用校验并执行工具
  -> 将工具结果回传模型
  -> 模型继续推理或生成最终答案
```

根据任务需要，再增加状态持久化、流式输出、结构化结果、RAG、记忆、审批、安全边界、追踪和托管运行时。

## 核心原则

1. **先确定 API family，再写代码。** 同一厂商可能同时提供原生接口、OpenAI 兼容接口和云平台统一接口。
2. **把模型输出视为不可信输入。** 工具名、参数、路径、URL、SQL 和 shell 参数都必须校验。
3. **工具调用是协议，不是自动执行。** 除非使用明确的服务端工具，否则由应用负责执行并回传结果。
4. **流式输出是事件流，不只是字符串 token。** 必须处理工具参数增量、usage、finish reason、安全事件和错误事件。
5. **OpenAI 兼容只表示部分请求形状兼容。** 不代表模型能力、状态、错误、配额、文件、工具和流式语义完全一致。
6. **保留 provider metadata。** 统一抽象不能丢失 reasoning、citation、grounding、safety、trace 和原始响应字段。
7. **快速变化的信息只信官方文档。** 模型列表、价格、配额、预览状态和弃用日期不要依赖记忆。

## 工作流

### 1. 识别任务类型

将需求归入一个或多个类别：

- 从零实现 Agent
- 给现有聊天应用增加工具调用
- 在提供商之间迁移
- 设计 provider adapter
- 接入托管 Agent runtime
- 增加 RAG、记忆、文件、代码执行或 MCP
- 调试工具循环、流式解析、结构化输出或重试问题
- 审查 Agent 的安全性、可靠性和可观测性

先阅读现有代码、依赖和配置，不要立即引入新框架。

### 2. 收集最小需求

优先从用户输入和代码库推断；仅在无法安全决定时询问：

- 语言与运行环境
- 目标提供商、云平台和 API family
- 模型或部署标识
- 同步、异步、流式或实时
- 客户端工具还是服务端工具
- 是否需要多轮状态、持久记忆或人工审批
- 输入模态与输出格式
- 数据驻留、身份、网络和合规限制
- 延迟、吞吐、成本与可靠性目标

### 3. 选择架构与接口

使用 [机器可读路由](references/routes.json) 选择资料，并以 [Agent Canonical Contract](references/canonical-contract.md) 统一术语和不变量。

路由步骤：

1. 从用户目标中识别实现、迁移、调试、审查、评测或事故处理意图。
2. 按 `defaults.selection_order` 依次排除负向命中、比较精确意图命中数、正向信号命中数、`priority`、最长信号，再以 route ID 字典序稳定决胜；不要依赖数组顺序。
3. 默认只读取一个 `primary` 和最多两个 `supplements`，不要把整个 `references/` 加入上下文。
4. 先读取该路由声明的 `contract_ids`；专题文档若与 Canonical Contract 冲突，以 Contract 为准并修复漂移。
5. 只有跨模块设计、架构审查或事故调查才扩大读取范围；人类浏览可使用 [工程文档导航](references/engineering/index.md)。

快速入口：

- 完整 Agent 或平台架构：`architecture.reference`。
- 最小工具循环、流式或结构化输出：`implementation.api_patterns`。
- Provider/API 选型：`selection.api_capability`。
- 工具、权限、状态或评测：分别选择 `tool.engineering`、`permission.sandbox`、`state.memory.engineering`、`evaluation.runner` 或 `evaluation.dataset`。
- 指定云平台或协议：选择对应的 `provider.*` 或 `protocol.*` 路由。

如果目标提供商尚无本地 reference：

1. 只查询该提供商官方文档；
2. 确认推荐 API、认证、模型标识、工具调用、结构化输出、流式和错误语义；
3. 将提供商差异局部封装，不要改坏通用中间层；
4. 若用户要求维护本 Skill，再补充对应 provider reference 和路由。

### 4. 设计 Agent 边界

先区分两个概念：

- **Agent Kernel**：headless 的模型—工具循环、统一消息和事件协议、停止与取消。
- **Agent Harness**：围绕 Kernel 的上下文、provider、工具、权限、沙箱、状态、扩展、反馈、评测和交付环境。

不要把所有能力塞入单个 `Agent` 类。把系统拆为独立职责：

```text
AgentOrchestrator   控制循环、终止条件和预算
ModelClient         调用某个 API family
ToolRegistry        保存工具定义与执行器
ToolValidator       校验名称、schema、权限和参数
StateStore          保存对话、检查点和业务状态
Policy              决定允许、拒绝或要求人工确认
EventSink           输出流式事件、日志和 trace
```

简单任务可以合并类，但不要混淆职责。

推荐的 provider-neutral 数据结构：

```text
ProviderConfig
  provider
  api_family
  endpoint
  region_or_location
  project_or_account
  deployment_or_model_id
  auth_strategy
  api_version

Message
  role
  parts[]

ToolDefinition
ToolCall
ToolResult
StructuredOutputSchema
StreamEvent
Usage
ProviderMetadata
RawRequest
RawResponse
```

`parts[]` 应能表示文本、图片、音频、视频、文档、工具调用和工具结果，而不是只保存字符串。

### 5. 实现可靠工具循环

阅读 [references/agent-api-patterns.md](references/agent-api-patterns.md) 后实现。

基本循环：

1. 发送系统指令、历史消息和工具定义。
2. 收集完整响应或流式事件。
3. 提取全部工具调用，不要只处理第一个。
4. 校验工具是否注册、参数是否符合 schema、调用者是否有权限。
5. 对高风险或不可逆操作执行人工确认。
6. 使用超时、取消、幂等键和隔离边界执行工具。
7. 将每个结果与原始 tool-call ID 对应后回传。
8. 重复调用模型，直到产生最终答案或触发终止条件。
9. 记录 usage、耗时、错误、调用次数和关键 provider metadata。

必须设置：

- 最大迭代次数
- 最大工具调用数
- 单工具超时
- 总执行时间或 token/cost 预算
- 重复调用检测
- 取消信号

### 6. 结构化输出

优先使用提供商的 strict schema / structured output，而不是仅在提示词中要求 JSON。

仍需：

- 使用 provider 支持的 schema 子集；
- 在应用端再次校验；
- 区分拒答、安全拦截、截断、空输出与 schema 错误；
- 对验证失败设置有限重试，不得无限自修复；
- 不要把结构化最终输出与工具参数 schema 混为一谈。

### 7. 流式处理

统一为事件联合类型，而不是直接拼字符串：

```text
TextDelta
ReasoningDelta
ToolCallStart
ToolCallArgumentsDelta
ToolCallComplete
Citation
SafetyUpdate
UsageUpdate
ResponseComplete
ProviderEvent
Error
```

仅在 `ToolCallComplete` 或 provider 明确表示参数完整后解析 JSON。未知事件要保留或记录，避免 SDK 升级后静默丢数据。

### 8. 错误、重试与幂等

分类处理：

- 参数/Schema 错误：修复请求，不重试原请求；
- 身份或权限错误：停止并报告缺少的权限；
- 限流或临时容量错误：读取服务端重试提示，指数退避并加入 jitter；
- 网络和 5xx：仅对安全请求有限重试；
- 工具业务错误：作为结构化工具结果回传，或按策略终止；
- 不确定是否执行成功的写操作：先查询状态，不能盲目重放。

对有副作用的工具生成稳定幂等键，并把模型生成的调用 ID 与业务幂等键分开。

### 9. 安全审查

至少检查：

- Prompt injection 是否能越权调用工具；
- 工具参数是否经过 schema 与业务规则双重校验；
- 凭据是否只存在服务端和环境变量/密钥服务；
- 文件路径、URL、SQL、shell 和代码执行是否有沙箱或 allowlist；
- 检索内容和工具结果是否被当作不可信数据；
- 日志是否泄漏密钥、个人信息或完整提示词；
- 是否为删除、付款、发送、发布、权限修改等动作增加确认；
- 多租户状态、文件、向量库和 trace 是否隔离。

### 10. 测试

至少覆盖：

1. 无工具调用的普通回答；
2. 单工具调用；
3. 并行或连续多工具调用；
4. 非法工具名和非法参数；
5. 工具超时与业务失败；
6. 达到最大迭代次数；
7. 流式工具参数被拆成多个事件；
8. 结构化输出验证失败；
9. 429、5xx 和网络中断；
10. 有副作用工具的重复调用与幂等；
11. Prompt injection 诱导越权；
12. provider 返回未知字段或未知事件。

优先使用录制响应、fake transport 或 provider adapter mock，避免单元测试依赖真实付费 API。另保留少量受控集成测试。

## 框架选择

不要为了“像 Agent”就自动引入框架。

直接使用官方 SDK，适合：

- 工具数量少；
- 单 Agent；
- 控制流清晰；
- 需要精确掌握 API 和流式事件。

考虑 Agent 框架或托管 runtime，适合：

- 长时间任务和检查点恢复；
- 多 Agent 协作；
- 大量工具、MCP 或 A2A；
- 托管沙箱、浏览器、代码执行和身份代理；
- 需要平台级追踪、评估、伸缩与治理。

即使使用框架，也要明确底层 provider、api_family、状态所有权和失败恢复语义。

## 输出要求

实现任务结束时，简要说明：

- 选择了哪个 provider 和 API family；
- Agent 循环与工具安全边界；
- 新增或修改的文件；
- 已运行的测试；
- 尚需用户配置的环境变量、云资源或权限；
- 使用了哪些预览能力或提供商特有限制。

不要输出真实密钥，不要把未经验证的模型名、价格、配额或弃用时间写成确定事实。
