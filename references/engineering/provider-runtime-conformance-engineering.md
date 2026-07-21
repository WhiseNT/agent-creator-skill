# Provider Runtime Conformance Engineering 细粒度工程设计

> 本文定义 Provider Runtime 的跨 Provider 一致性验证、适配器合规和发布门禁。它沿用 `Provider`、`ApiFamily`、`Model`、`Deployment`、`ModelRef`、`ResolvedModel`、`ModelCapabilities`、`RoutingSnapshot`、`Attempt`、`CircuitBreaker`、`UsageLedger`、`ContextPlan`、`ArtifactRef`、`Harness`、`ProviderAdapter` 与 canonical event 等术语。
>
> 本设计只整理当前目录已有参考架构、Agent API 模式、能力矩阵、Harness、Provider Runtime、Provider Routing、Context、Tool、State/Memory、Artifact、Event/Observability、Evaluation、Permission/Sandbox、Multi-tenant、Host Adapter 与 Coding Agent 文档中的源码调研结论；不把 README 当作规范，不新增网络调研结论。

## 目录

1. [设计目标与非目标](#设计目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [职责边界](#职责边界)
4. [总体架构与包布局](#总体架构与包布局)
5. [Provider-neutral Contract](#provider-neutral-contract)
6. [能力矩阵与声明校验](#能力矩阵与声明校验)
7. [核心数据模型](#核心数据模型)
8. [请求语义](#请求语义)
9. [响应、流和事件语义](#响应流和事件语义)
10. [Tool 与 Structured Output](#tool-与-structured-output)
11. [多模态语义](#多模态语义)
12. [Fixture、Golden 与录制回放](#fixturegolden-与录制回放)
13. [Contract Test 与 Adapter Compliance](#contract-test-与-adapter-compliance)
14. [Event Normalization](#event-normalization)
15. [错误、Usage 与 Cost](#错误usage-与-cost)
16. [Context Overflow、Retry 与 Fallback](#context-overflowretry-与-fallback)
17. [Schema Drift 与 Versioning](#schema-drift-与-versioning)
18. [Conformance Levels](#conformance-levels)
19. [隔离、故障注入与负向测试](#隔离故障注入与负向测试)
20. [Cross-provider Comparison](#cross-provider-comparison)
21. [CI、Release Gate 与 Real-provider Smoke](#cirelease-gate-与-real-provider-smoke)
22. [可观测性与审计](#可观测性与审计)
23. [安全与隐私](#安全与隐私)
24. [生命周期与状态机](#生命周期与状态机)
25. [实施清单](#实施清单)
26. [反模式](#反模式)
27. [五个参考项目的启发来源](#五个参考项目的启发来源)

## 设计目标与非目标

### 目标

Provider Runtime Conformance 必须能够：

- 以 provider-neutral contract 描述一次 `Attempt` 的输入、输出、流、工具、结构化输出、多模态、错误和计量语义。
- 把 `ProviderAdapter` 的差异限制在协议映射、认证、传输、原始 payload 解析和 provider 特有能力边界内。
- 用 `ModelCapabilities` 和 capability matrix 表达“支持什么、以何种强度支持、有哪些限制”，而不是用一个布尔 `supportsTools` 代替。
- 对 request、response、stream、tool call、structured output、multimodal、usage、cost、error 和 event normalization 建立可重复的 contract test。
- 用 fixture、golden、录制回放和 deterministic test doubles 验证协议语义，同时明确它们不能证明真实 provider 的当前可用性。
- 对 schema drift、版本升级、context overflow、retry、fallback、circuit breaker 和未知结果提供可审计的处理路径。
- 允许不同 provider 使用不同文本、tokenizer、工具调用格式和流粒度，但仍比较可观测的语义等价性。
- 将单元测试、跨 adapter contract、真实 provider smoke、CI/release gate 和生产指标连接起来。

### 非目标

本文不定义：

- 哪个 provider、model 或 deployment 应被业务路由优先选择；选择属于 `Provider Routing`。
- prompt、Context 选择、memory 检索、工具业务逻辑或最终 UI 展示；这些分别属于 Prompt/Context、State/Memory、Tool 和 Host Adapter。
- 让所有 provider 对同一段文本产生相同 token、相同措辞或相同分数。
- 用录制的成功响应证明实时 endpoint、价格、配额、区域和模型版本仍然可用。
- 把 provider SDK 类型直接暴露给上层 Harness，或让 adapter 决定 tenant 授权和 sandbox。
- 无隔离地重放真实工具、文件、网络、支付、部署或其他外部副作用。

## 核心判断与术语

### 核心判断

```text
Conformance = 语义契约 + 能力声明 + 事件规范化 + 可重复测试 + 可审计限制
```

```text
Provider Runtime 负责调用和归一化。
Provider Routing 负责选择和 fallback 顺序。
Context Runtime 负责生成可发送的 ContextPlan。
Tool Runtime 负责工具 schema、调度与执行。
Policy/Sandbox 负责是否允许、能影响什么和副作用边界。
State/Event Store 记录 durable truth。
Harness 监督生命周期、预算、恢复和控制命令。
```

### Conformance 不是相同文本得分

不同 provider 的 tokenizer、system message 语义、工具协议、采样参数、模型快照和安全策略可能不同。Conformance 的对象是：

- 请求字段是否按 contract 被保留、拒绝或降级。
- 能力声明是否与实际 adapter 行为一致。
- response/stream 是否能还原为稳定的 canonical message/part/event。
- 工具调用、结构化输出、usage、错误和终止原因是否可区分。
- provider 特有差异是否以 capability、warning、error taxonomy 或 evidence 公开。

因此，`same prompt -> same text` 既不是必要条件，也不是充分条件。

### 术语

- `Provider`：外部模型服务或兼容协议服务的逻辑提供方。
- `ApiFamily`：provider 暴露的请求/响应协议族。
- `ModelRef`：用户或路由层请求的 provider/model/deployment/region/variant 引用。
- `ResolvedModel`：路由后冻结的具体模型、部署、能力和配置快照。
- `ProviderAdapter`：将 provider-neutral request 映射到原始协议并解析结果的边界实现。
- `Attempt`：一次具体 provider/model/deployment 的调用尝试；重试和 fallback 产生新的 attempt。
- `ModelCapabilities`：模型或 deployment 在当前 adapter/version 下的能力和限制声明。
- `CanonicalEvent`：内部事件流中可持久化、可排序、可投影的事件。
- `UsageLedger`：按 attempt/turn/run/session/tenant 结算 usage、预算和成本的账本。
- `Fixture`：固定输入或原始响应样本；`Golden`：经过规范化后的期望语义结果。

## 职责边界

### Provider Runtime 负责

- 校验和冻结 `ResolvedModel`、`ModelCapabilities`、adapter version 与 request contract。
- 构造 provider 请求，执行 transport，解析 response/stream，并生成 canonical result/event。
- 处理 provider 认证、超时、连接、协议错误、原始错误 payload 和 usage extraction。
- 对 context overflow、retryable error、non-retryable error、unknown outcome 进行分类并返回 Harness。
- 向 `UsageLedger` 提交原始 usage、估算 usage、价格版本和 cost evidence。
- 保持 adapter contract test、fixture/golden、录制策略和 compliance evidence。

### Provider Runtime 不负责

- 选择 primary/fallback provider；这由 Routing 使用 `RoutingSnapshot` 决定。
- 在未授权时执行 tool；Tool Runtime、Policy/Sandbox 和 Approval 负责执行边界。
- 将 provider 的 free-form 文本强行当作结构化事实；schema validator 必须验证。
- 把 stream 已关闭当作业务成功；终止事实须由 response、事件和 ledger 共同确认。
- 让 provider 返回的 tenant、session、run 或 artifact 标识覆盖服务器端 scope。

### 强制边界

```text
Harness
  -> ContextPlan + ToolsetSnapshot + PolicySnapshot + ResolvedModel
  -> Provider Runtime
  -> ProviderAdapter
  -> Transport / Provider API
  -> raw response
  -> Adapter parser
  -> Canonical response/events + UsageLedger
```

```text
Provider Runtime 不越过 Policy/Sandbox 执行工具，
不越过 State/Event Store 写入业务事实，
不越过 Routing 改写 route policy。
```

## 总体架构与包布局

```text
Provider-neutral Request
  -> Contract Validator
  -> Capability Guard
  -> Attempt Builder
  -> ProviderAdapter
  -> Transport
  -> Raw Response / Stream
  -> Normalizer
  -> Schema/Tool/Multimodal Validator
  -> Usage & Cost Extractor
  -> Canonical Events
  -> Harness / State / Host Projection
```

推荐包布局：

```text
packages/provider-runtime/
  contracts.ts
  capabilities.ts
  model-ref.ts
  request-builder.ts
  response-parser.ts
  stream-parser.ts
  tool-normalizer.ts
  structured-output.ts
  multimodal.ts
  usage-ledger.ts
  errors.ts
  retry-classifier.ts
  normalization.ts
  versioning.ts
  adapter.ts
  transport.ts
  conformance/
    fixtures.ts
    golden.ts
    contract-suite.ts
    fault-injection.ts
    comparison.ts
    smoke.ts
  adapters/
    <provider>.ts
  testkit/
```

依赖方向：

```text
Harness -> ProviderRuntime contracts
Routing -> ResolvedModel / RoutingSnapshot
ProviderRuntime -> ProviderAdapter port
Adapter -> transport and provider SDK boundary
Normalizer -> canonical contracts only
Conformance -> adapter port, fixtures, test doubles
```

Adapter 不能反向依赖具体 Host、UI、State ORM 或业务工具实现。

## Provider-neutral Contract

### Contract 层次

契约分为五层：

1. `Input Contract`：message/part、system instruction、toolset、response format、sampling、budget、attachments。
2. `Capability Contract`：当前 model/deployment/adapter 支持和限制。
3. `Execution Contract`：timeout、cancellation、retry classification、idempotency 和 attempt identity。
4. `Output Contract`：message/part、tool call、structured result、usage、finish reason、warnings。
5. `Event Contract`：started、delta、tool call、usage、completed、failed、cancelled、unknown outcome。

### Request 语义不变量

- 每个请求必须带 `requestId`、`attemptId`、`ResolvedModel`、`ContextPlan`、`PolicySnapshot` 和 contract version。
- 原始 provider 字段只能由 adapter 生成，不能由模型文本或 tool arguments 注入。
- 未支持的 capability 必须 `reject`、`degrade with warning` 或 `omit by policy`，不能静默改变语义。
- 空 message、非法 part、重复 tool call ID、互相冲突的 response format 必须在发出请求前发现。
- `ContextPlan` 的截断和摘要必须在 Context Runtime 完成；adapter 不能擅自删除任意 message。

### TypeScript 接口

```typescript
interface ProviderRequest {
  requestId: string;
  attemptId: string;
  model: ResolvedModel;
  messages: CanonicalMessage[];
  tools?: ToolDefinition[];
  responseFormat?: ResponseFormat;
  sampling?: SamplingOptions;
  modalities?: ModalityRequest;
  context: ContextPlan;
  policy: PolicySnapshot;
  timeoutMs: number;
  cancellation?: CancellationToken;
  contractVersion: string;
}

interface ProviderResult {
  attemptId: string;
  message?: CanonicalMessage;
  toolCalls: CanonicalToolCall[];
  structured?: StructuredResult;
  finish: FinishState;
  usage: UsageRecord;
  warnings: RuntimeWarning[];
  rawReceipt?: RawResponseReceipt;
}

interface ProviderStream {
  events: AsyncIterable<ProviderRuntimeEvent>;
  completion: Promise<ProviderResult | UnknownOutcome>;
  cancel(reason: string): Promise<void>;
}
```

## 能力矩阵与声明校验

### Capability matrix

`ModelCapabilities` 至少应区分：

```typescript
interface ModelCapabilities {
  textInput: boolean;
  textOutput: boolean;
  streaming: CapabilityLevel;
  tools: CapabilityLevel;
  parallelToolCalls: CapabilityLevel;
  structuredOutput: StructuredOutputCapability;
  multimodalInput: ModalityCapability[];
  multimodalOutput: ModalityCapability[];
  reasoningEvents: CapabilityLevel;
  usage: UsageCapability;
  cancellation: CapabilityLevel;
  maxContextTokens?: number;
  maxOutputTokens?: number;
  providerLimits: Record<string, unknown>;
  capabilityVersion: string;
}
```

`CapabilityLevel` 不应只有 true/false，可使用 `"unsupported" | "best_effort" | "native" | "emulated"`。

### 声明与实际行为

- adapter 注册时必须提供能力声明来源：静态配置、探测结果、版本化 fixture 或真实 smoke evidence。
- `emulated` 能力必须记录实现方式和残余差异；例如通过文本约束模拟 structured output 不能声明为 native。
- capability matrix 的每个限制都应有测试 ID，例如最大 context、最大工具数量、流事件粒度和附件 MIME。
- 运行时若 provider 返回与声明冲突，当前 attempt 失败或降级，并生成 `capability_mismatch` 事件。
- mismatch 不应直接修改全局能力；更新能力需要版本化 registry、审核和回归测试。

### Capability negotiation 流程

```text
ModelRef
  -> RoutingSnapshot
  -> ResolvedModel
  -> capability lookup
  -> request feature check
  -> reject / degrade / emulate
  -> Attempt snapshot
```

`Attempt` 必须保存能力快照，避免运行中 registry 变化导致不可重放。

## 请求语义

### Message 与 Part

Canonical message 至少保留 `role`、稳定 `messageId`、顺序、parts、来源和敏感度。Part 需要明确：

- `text`、`image`、`audio`、`video`、`file`、`document`、`tool_call`、`tool_result`、`redacted` 等种类。
- inline bytes 与 `ArtifactRef` 的区别。
- MIME、尺寸、哈希、来源、是否允许外发。
- provider 不支持的 part 的处理策略和 warning。

适配器可以把 canonical parts 转为 provider 特有 content blocks，但不能改变顺序、角色或工具关联。

### Sampling 与预算

Sampling 参数应区分 provider-neutral 字段和 provider-specific extension。未知字段不能从用户文本传入。`maxOutputTokens`、timeout、budget 和 cancellation 是 Harness 约束，不应只依赖 provider 接受。

### Toolset

发送给 provider 的工具集必须来自冻结的 `ToolsetSnapshot`：

- schema、name、description、visibility、policyRef、version 和 hash 都可审计。
- provider 不支持某种 schema 特性时，必须在 contract gate 中降级或拒绝。
- 工具可见不等于工具可执行；provider 仅产生 call，Tool Runtime 仍须重新授权。
- provider 返回的 tool name、arguments 和 call ID 需要 schema、scope 和大小校验。

### Structured output

结构化输出请求包含 schema、strictness、fallback strategy 和 validator version。adapter 需要区分：

- 原生 JSON/schema 模式；
- provider 的 grammar 或 tool-call 模拟；
- 仅文本提示的 best effort；
- 返回 JSON 但 schema 校验失败。

失败时不得把未验证文本写成结构化业务事实，应返回 `structured_output_invalid` 并保留原始结果的受控 `ArtifactRef`。

## 响应、流和事件语义

### 完整响应

完整响应必须能表达：

- assistant message 及其 parts；
- 零个或多个 tool call；
- structured result 及验证状态；
- finish reason、provider stop reason 和 cancellation 状态；
- usage、cost evidence、warnings 和 adapter version。

### Stream 语义

流是事件序列，不是若干字符串拼接。至少支持：

```text
attempt.started
message.started
message.delta
tool_call.started
tool_call.delta
usage.observed
message.completed
attempt.completed
attempt.failed
attempt.cancelled
attempt.unknown_outcome
```

要求：

- 每个事件有 `attemptId`、单调 `seq`、schema version 和 source。
- delta 可重复应用，或具有明确 dedup key；重连不能重复追加文本。
- parser 必须处理空 delta、乱序 provider metadata、重复终止帧和流中错误。
- provider 没有增量 usage 时，completion 阶段补发最终 usage，并标记 `observedAt` 和精度。
- stream EOF 不是 completion；只有合法 finish 或可确认的 provider receipt 才能生成 completed。

### 取消与未知结果

取消请求分为“尚未发送”“已发送但未确认”“已收到终止”三个阶段。网络断开、超时或进程崩溃时，如果不能确认 provider 是否接受请求，应生成 `unknown_outcome`，交给 Harness 决定是否新建 attempt，而不是盲目重试。

## Tool 与 Structured Output

### Tool call normalization

```typescript
interface CanonicalToolCall {
  callId: string;
  name: string;
  argumentsText: string;
  arguments?: unknown;
  argumentsState: "partial" | "complete" | "invalid";
  providerCallId?: string;
  index?: number;
  sourceAttemptId: string;
}
```

parser 必须支持：

- 多个 call 的顺序和并行标志；
- arguments 跨多个 stream delta；
- JSON 前后存在 provider wrapper；
- 缺失或重复 call ID；
- provider 把 tool result 误当 assistant text。

解析成功不等于执行成功；`ToolRuntime` 必须生成独立的 tool execution 与 result 事件。

### Structured output compliance

测试至少覆盖 schema required、additionalProperties、enum、数组、嵌套对象、null、Unicode、超长字段和拒绝响应。golden 应保存“规范化值 + validator outcome”，不能只保存漂亮打印后的文本。

## 多模态语义

### 能力和边界

多模态 conformance 关注内容类型、顺序、引用可访问性、尺寸限制、编码方式、拒绝原因和输出 part，而不是模型对图像内容的主观描述是否相同。

- `ArtifactRef` 发送前须经过 tenant、egress、MIME、大小和 retention 检查。
- inline 与 URL 输入要在 contract 中区分；URL 不应绕过网络策略。
- provider 不支持某 MIME 时应产生可诊断的 `unsupported_modality`。
- adapter 不能把附件内容写入日志；fixture 使用哈希或安全小样本。
- 多模态输出应记录 part 类型、尺寸、artifact hash 和可交付策略。

## Fixture、Golden 与录制回放

### Fixture 类型

- `request fixture`：canonical request、能力、policy 和 context snapshot。
- `raw response fixture`：脱敏后的 provider payload，包含协议版本和 adapter version。
- `stream fixture`：原始帧、延迟、断开、重复和错误注入。
- `tool fixture`：provider tool call 结果，不执行真实工具。
- `error fixture`：状态码、错误 body、headers 摘要和网络故障。
- `usage fixture`：输入、输出、缓存、推理和 provider-specific usage 字段。

### Golden 内容

Golden 应优先保存：

- canonical message/part；
- tool call 顺序和参数解析状态；
- structured validation outcome；
- finish、warning、error taxonomy；
- normalized event sequence；
- usage 精度与 cost calculation inputs。

Golden 不应把 provider 原始字段未经筛选地当作跨 provider 事实。

### 录制回放边界

录制回放适合验证 parser、normalizer、retry classifier、schema migration、resume 和 event projector。它不证明：

- provider 当前 endpoint、凭据、区域、配额或模型 alias 仍存在；
- 实时延迟、TLS、限流、价格和服务稳定性；
- 真实工具、副作用或外部系统一致性。

真实 provider smoke 只能使用隔离 tenant、最小 prompt、无副作用 toolset 和明确预算。

## Contract Test 与 Adapter Compliance

### 合规测试层次

```text
pure parser tests
  -> adapter contract tests
  -> capability behavior tests
  -> fault and stream tests
  -> cross-provider semantic comparison
  -> isolated real-provider smoke
```

每个 adapter 必须实现同一套 `ProviderContractSuite`，并声明跳过项及理由。禁止只运行 provider 自己的 SDK 示例。

### Contract suite

核心测试组：

1. 最小文本请求、system/user/assistant 顺序和空内容。
2. 多 message、Unicode、长文本、特殊字符和 metadata。
3. stream delta、终止、usage、重连和重复帧。
4. 单工具、多工具、并行工具、跨 delta arguments 和非法 JSON。
5. structured output native/emulated/invalid/拒绝。
6. 图片、文件、混合 parts、大小和不支持 MIME。
7. timeout、cancel、429、5xx、4xx、认证、schema error、上下文溢出。
8. usage 缺失、部分 usage、估算、价格版本和 ledger idempotency。
9. provider 返回未知字段、未知 event type、未来 schema version。
10. tenant、artifact、secret、日志 redaction 和错误信息泄漏。

### Compliance evidence

每次 suite 产出 `ConformanceReport`：

```typescript
interface ConformanceReport {
  provider: string;
  adapterVersion: string;
  capabilityVersion: string;
  contractVersion: string;
  suiteVersion: string;
  passed: string[];
  failed: ConformanceFailure[];
  skipped: ConformanceSkip[];
  fixtures: string[];
  generatedAt: string;
  environment: TestEnvironment;
}
```

失败项必须包含最小重现 fixture、normalized diff、原始响应 hash、是否阻断 release 和 remediation owner。

## Event Normalization

### Normalized event envelope

```typescript
interface ProviderRuntimeEvent {
  eventId: string;
  attemptId: string;
  seq: number;
  type: ProviderEventType;
  occurredAt: string;
  provider: string;
  adapterVersion: string;
  payload: ProviderEventPayload;
  rawRef?: ArtifactRef;
  redactionProfile: string;
}
```

### 规范化规则

- 将 provider event type 映射到有限 canonical vocabulary；未知类型进入 `provider.event.unknown`，不能静默丢弃。
- 保留 provider sequence、request ID 和 raw receipt 的受控引用，便于审计但不扩大敏感数据暴露。
- 使用 attempt-local sequence；跨 attempt 顺序由 Harness/Event Store 的 parent sequence 解释。
- parser 可合并 provider 的细粒度帧，但必须保持语义边界：tool call、message completion、usage、error 不得混入普通 text delta。
- canonical event schema 变更必须升级 schema version，并提供 projector compatibility。

### Event 与 durable truth

Provider event 是 runtime evidence。`attempt.completed` 只有在 runtime 能确认完成时生成；State/Session 的最终 durable entry 由 Harness reducer/projector 根据结果和策略写入。Host Adapter 只投影这些事实。

## 错误、Usage 与 Cost

### Error taxonomy

错误最少分为：

```text
validation_error
capability_mismatch
authentication_error
authorization_error
rate_limited
context_overflow
provider_unavailable
network_timeout
transport_error
protocol_error
schema_error
tool_call_invalid
structured_output_invalid
multimodal_unsupported
cancelled
unknown_outcome
internal_error
```

每个错误包括 `retryable`、`safeMessage`、`providerCode`、`httpStatus`、`attemptId`、`rawRef`、`classificationVersion` 和建议动作。不要把所有非 2xx 都归为 retryable。

### UsageLedger

`UsageLedger` 要支持 reservation、observation、settlement、correction 和 idempotency：

- 账单维度至少包括 tenant、project、session、run、turn、attempt、provider、model 和 deployment。
- 记录输入、输出、缓存、推理、音视频和 provider-specific usage；未知字段保留扩展空间。
- 估算 usage 必须标记 `estimated`，不可与 provider observed 值混淆。
- cost 使用带版本的 pricing snapshot；价格更新不修改历史结算。
- 重试/fallback 每个 attempt 单独计量；最终回答不能掩盖失败 attempt 成本。

## Context Overflow、Retry 与 Fallback

### Context overflow

overflow 可能在本地 token 估算、provider 预检或 provider response 中发现。处理顺序：

```text
preflight estimate
  -> ContextPlan shrink/summarize
  -> capability limit check
  -> provider request
  -> classify provider overflow
  -> new ContextPlan or terminal failure
```

不能通过 adapter 静默删除 system policy、tool schema、审批事实或最近用户输入。每次 shrink 都生成 ContextPlan hash、策略原因和 warning。

### Retry

retry 由 Harness/RetryPolicy 决定，adapter 只提供分类证据。重试必须：

- 创建新 `Attempt`，保留 parent attempt 和 route snapshot；
- 具有预算、次数、指数退避、jitter 和 circuit breaker 检查；
- 对已产生未知副作用的请求默认不重试；
- 对 stream 已产生 tool call 或部分 output 时区分可重试与不可安全重试；
- 将每次 attempt 的 usage、error 和 receipt 写入 ledger/event。

### Fallback

fallback 不是“换一家再发同一文本”这么简单。必须重新校验：

- `ModelCapabilities` 是否满足请求；
- data residency、tenant allowlist、secret/egress policy；
- ContextPlan 是否超限；
- tool/structured/multimodal 语义是否可保持；
- 成本、延迟和用户可接受的 degradation。

fallback 产生新的 `RoutingSnapshot` 或明确引用原 snapshot 的候选项，并在最终结果中保留 route history。

## Schema Drift 与 Versioning

### Drift 来源

- provider 增删字段、改变 null/empty 语义或调整 event 顺序；
- SDK 默认值、API version、model alias 和 deployment 配置变化；
- tool/schema validator 行为变化；
- usage 字段改变或价格口径变化。

### 版本层次

```text
contractVersion
adapterVersion
providerApiVersion
modelSnapshotVersion
capabilityVersion
eventSchemaVersion
pricingVersion
fixtureSuiteVersion
```

这些版本必须分开记录。升级 adapter 不得无提示地重写历史 event 或 usage。

### 兼容策略

- 解析器允许未知字段，拒绝破坏必需字段和类型不一致。
- 新 event type 进入 unknown bucket 并触发监控；无法保证顺序时 fail closed。
- event projector 支持旧 schema 的向前读取，migration 产出新 canonical event 而非修改原始事实。
- golden 更新必须有 drift reason、变更 diff、reviewer 和 release gate 结果。
- provider alias 解析后冻结为 `ResolvedModel`，避免回放时 alias 指向另一模型。

## Conformance Levels

### Level 0：Transport Reachability

验证认证、请求发送、状态码、超时、基础错误和最小文本 response。只能说明 endpoint 可达。

### Level 1：Canonical Response

验证 message/part、finish、基础 usage、错误 taxonomy 和完整响应解析。

### Level 2：Streaming and Events

验证增量、终止、重复帧、断线、取消、event ordering 和 canonical event normalization。

### Level 3：Capability Semantics

验证 tools、parallel calls、structured output、多模态、context limit、degradation 和 warning。

### Level 4：Operational Conformance

验证 usage/cost ledger、retry/fallback、circuit breaker、schema drift、redaction、tenant isolation、故障注入和 release evidence。

### Level 5：Production Evidence

在隔离环境中完成定期 real-provider smoke、告警、回滚、模型快照和持续 drift detection。Level 5 不是永久认证，需随 provider/API/model 版本失效。

适配器注册时必须声明 level、未覆盖能力、已知差异和有效期。

## 隔离、故障注入与负向测试

### Test isolation

测试环境至少隔离：

- tenant、credential、workspace、artifact root、event partition、cache namespace；
- provider endpoint、网络代理、录制文件和价格配置；
- test run 的 session、run、attempt 与生产 session；
- tool executor、文件系统、子进程、网络和 webhook。

fixture 不得包含真实 token、用户 transcript、生产 artifact URL 或不可撤销的外部标识。

### Fault injection

必须能注入：

- DNS/TLS/connect timeout、慢响应、半关闭、断流、重复帧、乱序帧；
- 429、5xx、invalid JSON、truncated body、未知 event、错误 content type；
- usage 缺失、finish 缺失、tool call 参数断裂、schema drift；
- context overflow、认证过期、circuit open、ledger 写入失败；
- provider 已接受但客户端未知的中断。

### Negative/security tests

- 伪造 provider request ID、tenant ID、artifact ref、tool name 和 call ID；
- 将敏感内容塞入 error、tool arguments、metadata、URL 和 provider headers；
- 越权读取 raw fixture 或跨 tenant cache hit；
- 通过 unsupported capability 绕过 policy，或通过 fallback 绕过 region allowlist；
- schema bomb、超大 stream delta、递归 JSON、Unicode confusable 和 header injection；
- 将 provider 返回的 instruction 当作系统 policy 或授权事实。

## Cross-provider Comparison

### 可比维度

跨 provider 比较应针对相同的 canonical request class、能力和 policy snapshot，比较：

- 是否接受/拒绝，以及拒绝分类；
- message/part 与 tool call 的结构语义；
- stream 事件边界、首 token/完成延迟和断流行为；
- structured validator outcome；
- usage 字段完整度、估算误差和 cost evidence；
- context overflow、retry、rate limit 和 cancellation 语义；
- 多模态输入输出的支持矩阵；
- warnings、degradation 和不可兼容差异。

### 不应比较的对象

- 不应把不同 provider 的自然语言逐字相等作为 conformance gate。
- 不应忽略 model snapshot、temperature、system policy、toolset 和 ContextPlan 差异。
- 不应将某 provider 的更长回答自动视为更高合规度。
- 质量 evaluation 可以另行比较，但必须与 runtime conformance 分离。

### Comparison report

```typescript
interface ProviderComparisonReport {
  requestClass: string;
  providers: ProviderEvidence[];
  semanticDiffs: SemanticDiff[];
  incomparableReasons: string[];
  latencyAndUsage?: ComparisonMetrics;
  generatedAt: string;
}
```

报告必须区分 `equivalent`、`degraded`、`provider_specific`、`incomparable` 和 `failed`。

## CI、Release Gate 与 Real-provider Smoke

### CI 层次

```text
lint/typecheck
  -> pure parser + normalizer
  -> all adapter contract suites with fixtures
  -> fault injection and security tests
  -> cross-provider comparison
  -> optional recorded replay
  -> isolated real-provider smoke
```

### Release gates

阻断发布的条件包括：

- 必需 contract suite 失败；
- capability 声明与行为不一致；
- canonical event 无法被当前 projector 读取；
- retry 将 unknown outcome 当作安全成功重试；
- usage/cost ledger 非幂等或泄漏 tenant；
- structured/tool/multimodal 失败被静默转换；
- schema migration 丢事件、丢 usage 或降低 redaction；
- 真实 smoke 发现认证、endpoint、model snapshot 或关键能力失效。

允许不阻断但必须登记的情况：provider-specific optional capability 缺失、已知 stream 粒度差异、成本/延迟基线变化。每项需有 owner、expiry 和用户可见 degradation。

### Real-provider smoke 边界

real-provider smoke 只验证最小调用链和关键能力，不执行真实副作用：

- 使用专用 credential、tenant、region 和预算；
- 工具只连接 fake executor 或 quarantine sandbox；
- prompt 和附件采用无敏感、可重放 fixture；
- 禁止支付、删除、发布、写生产文件、发消息或外部 webhook；
- 失败保存安全 receipt 和分类，不保存完整敏感 payload；
- smoke 结果必须标记时间、provider API version、model/deployment snapshot 和有效期。

## 可观测性与审计

### 必备字段

日志、metric 和 trace 应关联：

```text
tenantId / workspaceId / projectId / sessionId / runId / turnId / attemptId
provider / apiFamily / model / deployment / region
adapterVersion / contractVersion / capabilityVersion / routeSnapshotId
requestHash / contextPlanHash / toolsetHash / policySnapshotId
errorClass / finishReason / usageReceiptId / costReceiptId
```

默认只记录 hash、长度、类型和引用，不记录完整 prompt、附件、secret 或 tool result。

### 指标

- contract pass/fail/skipped、capability mismatch、unknown event；
- request acceptance、stream completion、unknown outcome、cancel latency；
- context overflow、retry、fallback、circuit open；
- usage extraction completeness、estimated usage ratio、ledger correction；
- structured/tool/multimodal validation failure；
- provider latency、TTFT、completion latency、rate limit 和 transport error；
- real smoke freshness、fixture drift 和 release gate status。

审计记录 adapter 版本、能力快照、错误分类、fallback 理由、原始 receipt 引用和人工覆盖，不把 trace span 当作唯一业务事实。

## 安全与隐私

### Secret 与 Egress

Provider credential 只能由受控 secret broker 按 tenant、principal、provider、purpose、expiry 和 region 发放。adapter 不得把 credential 写入 raw fixture、error、事件或 artifact。

所有外发内容须经过：

```text
Tenant policy -> data classification -> artifact/attachment authorization
-> provider egress policy -> redaction -> transport
```

### Raw payload

raw payload 仅用于诊断和 parser 演进，必须：

- 加密、短 retention、最小访问；
- 记录 hash、schema 和来源；
- 按 policy 删除 prompt、附件、token、PII 和 secret；
- 通过 `ArtifactRef` 引用，不直接进入一般日志。

## 生命周期与状态机

### Attempt 状态

```text
created
  -> validated
  -> dispatched
  -> streaming
  -> completed
  -> failed
  -> cancelled
  -> unknown_outcome
```

只有 `validated` 才能发出 provider 请求；`completed` 必须有合法终止与 usage 处理；`unknown_outcome` 不得自动转为 `failed` 或 `completed`。

### Conformance run 状态

```text
planned -> fixture_ready -> executing -> normalized
         -> compared -> reviewed -> passed/failed/expired
```

`expired` 表示 real-provider evidence 超过有效期，不等同于失败。

### 幂等与恢复

contract runner、usage settlement、event append 和 report publication 都要有 idempotency key。崩溃恢复时先读取 attempt receipt、最后 canonical sequence、ledger 状态和 circuit state，再决定继续解析、标记 unknown 或新建 attempt。

## 实施清单

### Contract 与模型

- [ ] 固定 `ProviderRequest`、`ProviderResult`、`ProviderRuntimeEvent` 和错误 taxonomy。
- [ ] 为所有 capability 定义 level、限制、证据来源和 version。
- [ ] 冻结 `ResolvedModel`、`RoutingSnapshot`、`ContextPlan`、`ToolsetSnapshot`、`PolicySnapshot`。
- [ ] 约定 raw receipt、ArtifactRef、redaction 和 retention。

### Adapter

- [ ] 每个 provider 只实现 adapter port，不向上层泄漏 SDK 类型。
- [ ] 完成 request/response/stream/tool/structured/multimodal parser。
- [ ] 实现 usage/cost extraction、错误分类、cancel 和 unknown outcome。
- [ ] 对 provider 特有差异提供 warning、degradation 或显式 unsupported。

### Conformance

- [ ] 建立 fixture/golden 目录和 fixture schema version。
- [ ] 实现公共 contract suite 与 adapter compliance report。
- [ ] 覆盖正常、边界、故障注入、负向和安全测试。
- [ ] 建立跨 provider semantic comparison，禁止文本逐字 gate。
- [ ] 为每个 adapter 声明 conformance level、known gaps、owner、expiry。

### 运维与发布

- [ ] 在 CI 配置必需 gate、可选 gate 和 real smoke 环境。
- [ ] 配置 model/adapter/API/schema/pricing version 观测。
- [ ] 建立 drift 告警、回滚、circuit breaker 和 fallback 审计。
- [ ] 验证多租户 cache、artifact、日志、secret 和 fixture 隔离。
- [ ] 定期清理 raw payload、旧 fixture 和过期 smoke receipt。

## 反模式

- 用“所有 provider 返回同一段文本”定义 conformance。
- 只测 SDK happy path，不测 raw stream、断流、重复帧和未知字段。
- 把 provider 4xx/5xx 全部标为 retryable。
- 网络断开后直接重试，忽略 provider 可能已经接受请求。
- 让 adapter 私自截断 ContextPlan 或删掉 policy/tool 信息。
- 把 structured output 的 JSON parse 成功当作 schema 合规。
- 把 tool call parse 成功当作工具执行成功。
- 用全局 capability registry 覆盖 attempt 已冻结的能力快照。
- 用生产 credential、真实 artifact 或真实 webhook 运行 smoke。
- 将 raw payload、prompt、secret 写入 golden、日志或普通 trace。
- 把 fallback 当作绕过 tenant、region、预算和数据外发策略的后门。
- 通过修改 golden 隐藏 schema drift、usage 变化或事件丢失。

## 五个参考项目的启发来源

- `earendil-works/pi`：启发 adapter 与 agent loop 解耦、流事件和工具调用需要稳定边界；本设计进一步把这些边界提升为 provider-neutral contract 和合规套件。
- `xai-org/grok-build`：启发模型/provider 配置、流式响应和 provider-specific 字段必须在运行时可观察；本设计将其扩展为能力快照、版本和 drift evidence。
- `anomalyco/opencode`：启发 provider/model 多态、工具与消息 part 的规范化以及失败路径的显式建模。
- `claude-code-best/claude-code`：启发 coding harness 中 context、tool、approval、artifact 和验证证据不能由 provider adapter 混合承担。
- `openclaw/openclaw`：启发多宿主、插件、外部连接和长生命周期任务必须保留 scope、事件、隔离和恢复边界。

这些启发只用于解释本地调研中已经记录的架构模式；本设计的合规结论仍以本地 contract、capability、event、policy、ledger 和 Harness 边界为准。
