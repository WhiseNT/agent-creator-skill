# Agent Event / Observability Engineering 详细设计
> Event 是 Agent Kernel、Harness、Host、持久化、恢复、审计与评测之间的主协议；Observability 是从事件派生的 trace、span、log、metric 与诊断视图。事件系统不能退化为“把 token 字符串打印到终端”。
## 目录
1. [设计目标](#设计目标)
2. [职责边界](#职责边界)
3. [总体架构](#总体架构)
4. [事件分层](#事件分层)
5. [Canonical Event Envelope](#canonical-event-envelope)
6. [事件分类与载荷](#事件分类与载荷)
7. [生命周期与状态机](#生命周期与状态机)
8. [Provider Stream Normalization](#provider-stream-normalization)
9. [顺序、序列与关联](#顺序序列与关联)
10. [Durable 与 Ephemeral](#durable-与-ephemeral)
11. [Event Router 与 Backpressure](#event-router-与-backpressure)
12. [Coalescing、采样与容量](#coalescing采样与容量)
13. [Event Store](#event-store)
14. [Replay 与 Projector](#replay-与-projector)
15. [多客户端交付](#多客户端交付)
16. [Trace、Span、Log 与 Metric](#tracespanlog-与-metric)
17. [Usage、Cost 与 Latency](#usagecost-与-latency)
18. [Redaction、安全与 Audit](#redaction安全与-audit)
19. [OpenTelemetry 映射](#opentelemetry-映射)
20. [SLO 与告警](#slo-与告警)
21. [Diagnostic Snapshot](#diagnostic-snapshot)
22. [故障与恢复](#故障与恢复)
23. [测试策略](#测试策略)
24. [反模式](#反模式)
25. [实施清单](#实施清单)
26. [项目启发来源](#项目启发来源)
## 设计目标
事件与可观测性系统应满足：
- **协议化**：事件是有版本的联合类型，不是任意字符串或无约束 JSON。
- **分层**：Provider、Kernel、Harness、Host 各自拥有稳定语义和转换边界。
- **完整**：文本、推理、工具、审批、usage、错误、恢复、交付均可表达。
- **可恢复**：关键状态由 durable event 或 semantic entry 重建。
- **可关联**：session、run、attempt、turn、model request、tool call、approval 形成因果链。
- **可扩展**：未知 provider 字段与扩展事件不会被静默丢弃。
- **可控流**：慢消费者不阻塞模型网络读取，关键事件不静默丢失。
- **可审计**：能解释谁在何时基于何种策略执行了什么动作。
- **隐私安全**：默认最小化采集，在进入低信任 sink 前脱敏。
- **可评测**：测试可断言轨迹、状态、顺序、预算和真实副作用。
- **可运营**：支持 SLO、告警、成本归因、诊断快照和容量规划。
```text
Events are protocol.
Telemetry is a projection.
Durable state is not a UI buffer.
Audit is not debug logging.
```
### 非目标
本文不规定具体数据库、消息队列、观测厂商或 TUI 样式；不复制任一 provider 的完整原始 schema；不要求默认永久保存完整 prompt、reasoning、工具参数或工具输出；不允许用 telemetry 替代 session repository 的业务一致性。
## 职责边界
### Event Protocol
负责 canonical envelope、事件种类、schema version、sequence、correlation、causation、durability、sensitivity、retention、payload codec 和未知事件兼容。
### Stream Normalizer
负责把 provider 原始 frame 转换为 Kernel Event，重组文本与工具参数增量，识别 finish reason、usage、安全、拒答和错误；在完整边界前不得解析或执行工具参数。
### Event Router
负责 publish/subscribe、消费者隔离、bounded queue、backpressure、coalescing、flush 和 settlement；关键 durable consumer 失败必须通知 Run Supervisor。
### Event Store
负责 durable event 原子追加、幂等、乐观并发、游标读取、checkpoint、retention、归档以及 replay/projector 的稳定输入。
### Observability Pipeline
负责从 canonical events 派生 trace/span/log/metric，计算 latency、usage、cost、queue depth 和错误率，并执行 redaction、采样与 attribute cardinality 控制；不得修改业务状态。
### Audit Pipeline
负责保存身份、策略、审批、高风险工具、sandbox、外部副作用与治理操作的最小审计事实；使用独立 retention、访问控制和完整性策略，不把普通 debug log 当作 audit log。
### Kernel 不负责
Kernel 不认识具体 provider chunk，不直接写 OpenTelemetry exporter，不管理 WebSocket/SSE 客户端，不决定企业日志保留期，也不记录完整敏感 prompt。
### Host 不负责
Host 不推断缺失 durable state，不重新解释 finish reason，不自行决定 tool call 是否完整，不以 UI 到达顺序替代 canonical sequence。
## 总体架构
```text
Provider SDK / HTTP stream
  -> Provider Adapter
  -> Stream Normalizer
  -> Kernel Event Port
  -> Agent Kernel
  -> Harness Event Router
      ├─ Durable Event Writer
      ├─ Session Projector
      ├─ Trace / Metric Exporter
      ├─ Audit Writer
      ├─ Evaluation Recorder
      └─ Host Delivery Adapters
           ├─ CLI / TUI / IDE
           ├─ RPC / SSE / WebSocket
           ├─ Gateway / Channel
           └─ Batch / Background notification
```
控制面事件包括 run、model selection、fallback、policy、approval、checkpoint、recovery、subscription 和 delivery acknowledgement；数据面事件包括文本、reasoning、tool arguments、tool progress、content、artifact 和 usage。两者分队列或分优先级，避免控制面被高频 delta 淹没。
### 推荐包边界
```text
packages/
  event-protocol/       # envelope, payload unions, codecs, versioning
  provider-normalizer/  # provider event -> kernel event
  event-router/         # subscriptions, queues, backpressure
  event-store/          # durable append/query/checkpoint
  projectors/           # transcript, run state, usage, approvals
  observability/        # trace/log/metric mapping and exporters
  audit/                # security audit records and integrity
  host-delivery/        # CLI, SSE, WebSocket, channels
  testkit/              # recorder, scripted stream, replay, assertions
```
小项目可以合包，但依赖方向保持 `Host -> Harness -> Kernel -> Protocol`，基础设施实现端口，Kernel 不导入 UI、数据库或 provider SDK。
## 事件分层
### Provider Event
Provider Event 是外部 API/SDK 的原始协议事实，例如 response/content block 生命周期、text/reasoning/tool arguments delta、citation、safety、usage 和 terminal。它允许 provider 特有字段，但不是稳定公共 API，也不能直接进入 UI。
### Kernel Event
Kernel Event 表达模型—工具闭环的最小通用语义：
```text
ModelAttemptStarted
ContentPartStarted
TextDelta
ReasoningDelta
ToolCallStarted
ToolArgumentsDelta
ToolCallReady
ModelUsageUpdated
ModelAttemptCompleted
ModelAttemptFailed
ToolBatchStarted
ToolExecutionStarted
ToolProgress
ToolExecutionCompleted
TurnCompleted
KernelStopped
```
Kernel Event 不包含 UI 颜色、spinner、SDK 对象、数据库主键、WebSocket connection ID 或企业告警配置。
### Harness Event
Harness Event 加入运行监督与产品能力：
```text
RunStarted / ContextCompiled / PromptCompiled / ModelSelected
AttemptStarted / AttemptFailed / RetryScheduled / FallbackSelected
PolicyEvaluated / ApprovalRequested / ApprovalResolved / SandboxAttested
ToolScheduled / ToolCompleted / ArtifactCreated / CheckpointWritten
CompactionStarted / CompactionCompleted / SubagentStarted / SubagentCompleted
DeliveryStateChanged / RunCompleted / RunFailed / RunCancelled
```
它是 Event Store、projector、observability、audit、evaluation recorder 和 host adapter 的主要输入。
### Host Event
Host Event 是具体客户端的裁剪表示，如 `RenderTextDelta`、`ShowToolCard`、`UpdateToolProgress`、`RequestUserApproval`、`ShowArtifact`、`ShowFinalResult`、`ConnectionResyncRequired`。Host 可合并 delta、翻译文案或拆分 channel 消息，但不得改变 canonical 事实。
### 转换方向
```text
Provider Event -> Kernel Event -> Harness Event -> Host Event
```
禁止 `Provider Event -> UI`、`UI string -> durable session truth`、`exporter span -> recovery state`。
每次转换保留 source layer/kind/version、raw event hash 或 artifact reference、normalizer version、transform diagnostics 和未映射字段。
## Canonical Event Envelope
### 基础接口
```typescript
type EventLayer = "provider" | "kernel" | "harness" | "host";
type EventDurability = "durable" | "ephemeral";
type Sensitivity = "public" | "internal" | "confidential" | "secret" | "regulated";
interface CanonicalEvent<TKind extends string = string, TPayload = unknown> {
  eventId: string;
  schemaVersion: string;
  layer: EventLayer;
  kind: TKind;
  durability: EventDurability;
  occurredAt: string;
  observedAt: string;
  monotonicTimeNs?: string;
  tenantId?: string;
  workspaceId?: string;
  sessionId: string;
  branchId?: string;
  runId: string;
  attemptId?: string;
  turnId?: string;
  sequence: EventSequence;
  correlation: EventCorrelation;
  source: EventSource;
  security: EventSecurity;
  payload: TPayload;
  extensions?: Record<string, unknown>;
}
```
### Sequence 与 Correlation
```typescript
interface EventSequence {
  streamId: string;
  streamSeq: number;
  sessionVersion?: number;
  producerSeq?: number;
  partition?: string;
}
interface EventCorrelation {
  traceId: string;
  spanId?: string;
  parentSpanId?: string;
  correlationId?: string;
  causationEventId?: string;
  requestId?: string;
  modelRequestId?: string;
  providerRequestId?: string;
  toolCallId?: string;
  toolExecutionId?: string;
  approvalId?: string;
  subagentRunId?: string;
  idempotencyKeyHash?: string;
}
```
`correlationId` 表示同一业务流程，`causationEventId` 表示直接原因，`traceId/spanId` 表示观测调用树；`toolCallId` 是模型协议身份，`toolExecutionId` 是一次实际执行尝试，二者不得混用。
### Source 与 Security
```typescript
interface EventSource {
  component: string;
  instanceId?: string;
  version: string;
  hostKind?: string;
  provider?: string;
  apiFamily?: string;
  model?: string;
  extensionId?: string;
}
interface EventSecurity {
  sensitivity: Sensitivity;
  containsUserContent: boolean;
  containsModelContent: boolean;
  containsToolContent: boolean;
  redactionState: "raw" | "redacted" | "tokenized" | "metadata_only";
  retentionClass: string;
  accessScope?: string[];
}
```
### 联合类型
```typescript
type HarnessEvent =
  | CanonicalEvent<"run.started", RunStartedPayload>
  | CanonicalEvent<"context.compiled", ContextCompiledPayload>
  | CanonicalEvent<"model.attempt.started", ModelAttemptStartedPayload>
  | CanonicalEvent<"content.text.delta", TextDeltaPayload>
  | CanonicalEvent<"tool.call.ready", ToolCallReadyPayload>
  | CanonicalEvent<"tool.execution.completed", ToolExecutionCompletedPayload>
  | CanonicalEvent<"approval.requested", ApprovalRequestedPayload>
  | CanonicalEvent<"usage.updated", UsageUpdatedPayload>
  | CanonicalEvent<"checkpoint.written", CheckpointWrittenPayload>
  | CanonicalEvent<"run.completed", RunCompletedPayload>
  | CanonicalEvent<"run.failed", RunFailedPayload>
  | CanonicalEvent<"extension.event", ExtensionEventPayload>;
```
### Envelope 不变量
- `eventId` 全局唯一，同一 `streamId` 的 `streamSeq` 严格递增。
- durable event 提交后不得原地修改；payload 必须匹配 `kind + schemaVersion`。
- `occurredAt` 是事实发生时间，`observedAt` 是当前组件接收时间；严格顺序依赖 sequence，不依赖 wall clock。
- terminal event 必须包含最终状态和 settlement 摘要；terminal 后不得出现新的业务事件。
- 敏感字段不能藏进无类型 `extensions` 绕过 redaction；unknown extension 必须可安全忽略。
### Schema 演进
新增 optional 字段使用 minor 版本；删除字段、改变语义或破坏兼容使用 major 版本；消费者对扩展 enum 必须有 unknown 分支；projector 声明支持范围；event store 保留原始版本；migration 重建 projection，不重写审计事实。
## 事件分类与载荷
推荐命名 `<domain>.<entity>.<phase>`，phase 使用 `requested/scheduled/started/progressed/completed/failed/cancelled/denied/expired/recovered`。`completed` 若不等于成功，payload 必须显式给出 outcome。
### 内容事件
```typescript
interface TextDeltaPayload {
  itemId: string;
  partId: string;
  delta: string;
  utf8Bytes: number;
  cumulativeChars?: number;
}
interface ReasoningDeltaPayload {
  itemId: string;
  partId: string;
  delta?: string;
  summaryDelta?: string;
  visibility: "model_internal" | "user_visible_summary" | "metadata_only";
}
```
不得假设所有 provider 都提供可公开 reasoning；默认只保存允许展示的 summary 或 metadata。
### Tool 事件
```typescript
interface ToolCallReadyPayload {
  callId: string;
  toolName: string;
  arguments: unknown;
  argumentsHash: string;
  sourceItemId: string;
  callOrdinal: number;
  parseDiagnostics: Diagnostic[];
}
interface ToolExecutionCompletedPayload {
  callId: string;
  executionId: string;
  toolName: string;
  status: "success" | "error" | "denied" | "cancelled" | "unknown";
  durationMs: number;
  resultSummary?: ContentPart[];
  artifactRefs?: ArtifactRef[];
  sideEffect?: SideEffectSummary;
  error?: NormalizedError;
}
```
### Usage 与 Error
```typescript
interface UsageUpdatedPayload {
  scope: "attempt" | "turn" | "run" | "session";
  inputTokens?: number;
  outputTokens?: number;
  reasoningTokens?: number;
  cachedInputTokens?: number;
  cacheWriteTokens?: number;
  toolTokens?: number;
  estimatedCost?: Money;
  isFinal: boolean;
  source: "provider" | "estimated" | "reconciled";
}
interface NormalizedError {
  category: "provider_transport" | "provider_rate_limit" | "provider_context_overflow"
    | "provider_capability" | "model_output_invalid" | "tool_validation"
    | "tool_permission" | "tool_execution" | "sandbox" | "session_conflict"
    | "event_delivery" | "extension" | "cancelled" | "internal";
  code: string;
  message: string;
  retryable: boolean;
  outcomeKnown: boolean;
  detailsRef?: ArtifactRef;
}
```
## 生命周期与状态机
### Run 状态机
```text
Created -> Starting -> Running
Running -> WaitingForApproval -> Running
Running -> Recovering -> Running
Running -> Settling -> Completed | Failed | Cancelled | Suspended
```
`RunStarted` 只出现一次，terminal event 只允许一个；settlement 期间仅允许 flush、delivery 和 exporter 状态；`Suspended` 必须包含 checkpoint；恢复 run 必须关联原 run。
### Model Attempt 状态机
```text
Created -> Requesting -> Streaming -> Completed | Failed | Cancelled
```
Streaming 中允许 usage、安全、citation、text 和 tool delta 交错；attempt terminal 后禁止 delta；truncated tool arguments 不得 ready；fallback 必须创建新 attempt ID。
### Tool Execution 状态机
```text
Proposed -> Validating -> Authorized -> WaitingForApproval
WaitingForApproval -> Scheduled -> Running
Running -> Succeeded | Failed | Denied | Cancelled | UnknownOutcome
```
`UnknownOutcome` 表示副作用可能发生但因进程崩溃、远端超时或 acknowledgement 丢失而无法确认；恢复器不得盲目重放。
### Delivery 状态机
```text
Pending -> Enqueued -> Sent -> Acknowledged
Sent -> Failed -> Retrying -> Sent | DeadLettered
```
TUI 可不要求 acknowledgement；外部消息、Webhook 和 background notification 应明确至少一次、至多一次或可查询结果语义。
### 状态校验器
```typescript
interface EventStateValidator {
  accept(event: CanonicalEvent): EventValidationResult;
  snapshot(): EventStateSnapshot;
}
```
校验前置事件、terminal uniqueness、call/result pairing、attempt/run 归属、sequence gap、durable commit 位置、重复 event ID 和 payload/状态一致性。
## Provider Stream Normalization
### 分层
```text
HTTP/SDK Transport
  -> Raw Frame Decoder
  -> Provider Event Decoder
  -> Provider Semantic Adapter
  -> Canonical Stream Normalizer
  -> Kernel Event Stream
```
Transport 只处理连接和 framing；Provider Adapter 理解原生语义；Normalizer 生成 canonical 事件；网络重试不应藏在 Normalizer。
### 接口与状态
```typescript
interface StreamNormalizer<TRaw> {
  push(raw: TRaw): NormalizedEventBatch;
  finish(reason: StreamFinishReason): NormalizedEventBatch;
  snapshot(): NormalizerSnapshot;
}
interface NormalizerSnapshot {
  attemptId: string;
  openItems: Record<string, OpenContentItem>;
  openToolCalls: Record<string, ToolArgumentAccumulator>;
  lastProviderSequence?: number;
  finishReason?: string;
  usage?: Usage;
  unknownEventKinds: string[];
}
```
### Tool Arguments 算法
```text
tool start
  -> 收集零个或多个 argument delta
  -> 等待 provider 明确 completion boundary
  -> 按 provider sequence 拼接 bytes
  -> UTF-8/framing 校验
  -> JSON parse
  -> 结构校验
  -> emit ToolCallReady
```
只有 provider 明确完成、无 sequence gap、UTF-8 完整、JSON 可解析、call ID/tool name 已知且 finish reason 不表示截断时，才允许 `ToolCallReady`。
### 文本与 Usage
文本 delta 保持 provider 语义顺序，处理空 delta 和 Unicode 跨 frame；coalescing 发生在 Router/Host，不改变 canonical content。Usage 可增量更新，最终 durable 记录 reconciled 值；缺失时可估算但标记 source；retry/fallback 每个 attempt 独立计量，run 汇总包含失败 attempt。
### 未知事件
未知 provider event 生成 diagnostic，保存安全裁剪后的 kind/version/metadata；若可能影响完整性则失败 attempt，仅可确认无关键语义时继续，禁止静默吞掉所有未知事件。
### Finish Reason 决策
```text
normal/tool completion -> finalize items -> validate calls -> completed
length/context truncation -> mark incomplete -> never execute incomplete call
safety/refusal -> typed safety/refusal outcome, not empty success
transport EOF without terminal -> abnormal EOF -> retry policy
```
## 顺序、序列与关联
分布式系统通常只能保证 producer 局部顺序、单 run writer append 顺序和 causation，不能用 timestamp 建立全局总序。
推荐顺序模型：
```text
producerSeq -> router streamSeq -> durable sessionVersion
```
`producerSeq` 检测输入 gap，`streamSeq` 支持客户端 resume，`sessionVersion` 支持 projector 和并发写入。
### 并行工具
并行工具同时保留：模型 call ordinal、scheduled/started/completed time、model feedback ordinal。UI 按真实完成顺序显示，返回模型的 tool result 保持原 tool-call 顺序，避免并发改变上下文语义。
### Causation 示例
```text
user.input.accepted -> model.attempt.started -> tool.call.ready
-> policy.evaluated -> approval.requested -> approval.resolved
-> tool.execution.started -> tool.execution.completed
-> model.attempt.started -> run.completed
```
### 去重与 Gap
去重维度包括 event ID、provider frame ID、delivery message ID、tool execution ID 和 durable append transaction ID；重复 delivery 不等于重复业务执行。
检测 gap 后暂停 projector，从 last acknowledged cursor 请求 replay；若游标过期则从 snapshot 重建；仍无法补齐时 projection 标记 incomplete，不得用后续事件掩盖缺口。
## Durable 与 Ephemeral
### 判定规则
若事件对崩溃恢复、session 语义、真实副作用、审批、usage/cost 结算、安全审计或多客户端重连任一项必需，则应 durable。
### Durable
- user input accepted、assistant item completed、tool call ready、tool execution outcome。
- policy decision、approval requested/resolved、sandbox attestation、side-effect receipt。
- model/toolset/config change、retry/fallback、checkpoint、compaction、artifact reference。
- terminal run status、final reconciled usage/cost、audit-critical identity/config change。
### Ephemeral
- text/reasoning delta、spinner、heartbeat、queue hint。
- 高频 tool progress、瞬时连接状态、估算中的局部 metric。
### 一致性边界
Event Store 作为 source of truth，或 session append 与 outbox 同事务，或单写者先提交 semantic entry 再发布；durable event 必须带 session version，消费者幂等投影。禁止无协议双写 session 和 event log。
默认不永久保存每个 token delta；确需逐字 replay 时使用短 retention、批量压缩、最终内容 hash 对账和独立存储，对 reasoning 采用更严格策略。
## Event Router 与 Backpressure
### 接口
```typescript
interface EventRouter {
  publish(event: HarnessEvent): Promise<PublishReceipt>;
  subscribe(spec: SubscriptionSpec): EventSubscription;
  flush(scope?: FlushScope): Promise<void>;
  close(reason?: string): Promise<void>;
}
interface EventSubscription {
  id: string;
  events: AsyncIterable<HarnessEvent>;
  acknowledge?(cursor: EventCursor): Promise<void>;
  close(reason?: string): Promise<void>;
}
```
### Consumer 等级
- Critical durable：event writer、session projector、audit writer。
- Important recoverable：trace exporter、evaluation recorder，可从 durable event 补偿。
- Best effort：TUI renderer、typing indicator、live dashboard。
### QueuePolicy
```typescript
interface QueuePolicy {
  capacity: number;
  overflow: "block_producer" | "coalesce" | "drop_oldest_ephemeral"
    | "drop_newest_ephemeral" | "disconnect_consumer" | "fail_run";
  maxBlockMs?: number;
}
```
durable writer 可短暂 block，超时后 fail/suspend run；TUI text delta coalesce；progress 保留最新；metrics 批处理并记录 dropped count；audit 在高安全策略下 fail-closed；慢远程客户端断开并通过 cursor resume。
### 网络流保护与 Flush
```text
provider reader -> bounded normalization queue -> canonical router -> per-client queues
```
慢 UI 不得使 provider stream 读超时。`flush()` 必须说明等待哪些 consumer、是否要求 durable commit/exporter 发送、超时状态和 terminal 是否已可查询；settlement 至少等待 durable writer 与关键 projector。
## Coalescing、采样与容量
### Text Delta Coalescing
只合并同一 run/attempt/item/part、sequence 连续、无控制事件穿插、未超过时间/字节窗口且不跨 redaction 边界的 delta。
```typescript
interface CoalescingPolicy {
  maxDelayMs: number;
  maxBytes: number;
  flushOnKinds: string[];
}
```
Progress 对同一 `toolExecutionId + progressKey` 保留首次、最新和最终值，记录合并数量；error/warning 不得被覆盖。
### 采样
可采样 heartbeat、重复 debug log、低价值 span event；不可采样掉 run terminal、tool side effect、approval、policy deny、audit-critical event 和 SLO 分母。Tail sampling 应强制保留错误、高成本、policy violation 和 recovery run。
### 容量预算
为每类事件定义平均/峰值 event rate、payload bytes、queue capacity、最大 lag、retention 和 exporter batch。容量规划同时考虑高频 token、并行工具、subagent、长 session replay 和多客户端 fan-out。
## Event Store
### 接口
```typescript
interface EventStore {
  append(
    stream: EventStreamRef,
    events: DurableHarnessEvent[],
    expectedVersion: number,
  ): Promise<AppendResult>;
  read(stream: EventStreamRef, cursor?: EventCursor): AsyncIterable<DurableHarnessEvent>;
  readRun(runId: string, cursor?: EventCursor): AsyncIterable<DurableHarnessEvent>;
  latestVersion(stream: EventStreamRef): Promise<number>;
  putCheckpoint(checkpoint: ProjectionCheckpoint): Promise<void>;
}
```
### Append 不变量
单批原子提交；expected version 冲突不得覆盖；event ID 唯一；stream sequence 由 store 或单写者分配；append receipt 返回 committed version；写入失败不能发布“已 durable”假象。
### Partition 与索引
优先 `tenant + session` 或 `tenant + run`。session partition 便于 transcript，run partition 便于并行和容量隔离；两者都要防热 partition。
索引建议包含 tenant/session/version、run/sequence、trace ID、tool call/execution ID、approval ID、event kind/time、terminal status、retention class；索引中避免未脱敏自由文本。
### Retention 与 Compaction
Ephemeral buffer 通常秒到小时，operational telemetry 天到月，durable session 和 audit 按产品/合规策略。删除时保留删除审计、projection invalidation 和 artifact 引用一致性。
Event Store compaction 可生成 projection snapshot、归档旧事件、合并高频批次，但不得删除恢复、审计或 side-effect 证明所需事实；它与对话 Context Compaction 是不同概念。
## Replay 与 Projector
### 接口
```typescript
interface Projector<TState> {
  name: string;
  version: string;
  initial(): TState;
  apply(state: TState, event: DurableHarnessEvent): TState;
  validate?(state: TState): Diagnostic[];
}
```
常见 projector：transcript、run state、pending approval、active model/toolset、usage/cost、delivery、audit view、evaluation trajectory、diagnostic snapshot。
### 不变量
Projector 必须 deterministic、side-effect free，不读取当前 wall clock，不调用模型或工具；重复事件可检测或幂等；unknown optional event 可忽略并诊断；不兼容 major version 必须停止。
### Replay
```text
选择 stream/target version
  -> 加载兼容 snapshot
  -> 验证 source hash/version
  -> 读取 tail events
  -> 校验 sequence/schema
  -> deterministic apply
  -> 校验 invariants
  -> 发布新 projection
```
必须验证 `live state == full replay == snapshot + tail replay`。Replay 只重建状态，不重新执行工具、Webhook、邮件、付款、删除或外部 delivery；模拟执行必须使用 fake backend/dry-run。
## 多客户端交付
### Subscription
```typescript
interface SubscriptionSpec {
  clientId: string;
  sessionId?: string;
  runId?: string;
  fromCursor?: EventCursor;
  kinds?: string[];
  includeEphemeral: boolean;
  maxSensitivity: Sensitivity;
  deliveryMode: "live" | "replay_then_live" | "snapshot_then_live";
}
```
### 连接与 Resume
```text
authenticate -> authorize tenant/session -> negotiate version
-> load snapshot/cursor -> replay missed durable events
-> attach live stream -> deduplicate overlap -> acknowledge
```
客户端保存 stream ID、last acknowledged sequence、projection/protocol version。Cursor 在 retention 内则增量 replay；过期则返回 resync required 和 snapshot。服务端不得假设断线前最后一个 frame 已送达。
### Host 独立交付
同一事件可投影为 TUI delta、IDE tool card、SSE JSON、WebSocket frame、channel typing/message 或 background notification。不同 host 的 delivery status 独立，一个渠道失败不得污染其他渠道。
慢客户端先 coalesce ephemeral、丢弃 stale progress、发送 lag diagnostic，再 disconnect/resume；权限变化时立即重评 subscription，停止敏感事件，历史 replay 也必须重新授权并产生 access audit。
## Trace、Span、Log 与 Metric
Event 是运行协议事实；Trace/Span 是调用链和阶段耗时；Log 是离散诊断；Metric 是可聚合数值；Audit 是治理事实；Projection 是业务视图。不得互相替代。
### Span 层级
```text
run span
  context.compile span
  prompt.compile span
  attempt span
    model.request span
    stream.normalize span
  policy.evaluate span
  approval.wait span
  tool.execute span
  compaction span
  subagent span
  delivery span
```
长 session 不应默认建成永不结束的 span，可用 span link 关联多个 run。
### Attributes 与 Logs
低基数属性包括 provider、api family、model、agent mode、run status、tool name/effect、policy decision、sandbox profile、error category。Run/session/user/file path/error message 等高基数值不能作为 metric label。
```typescript
interface StructuredLogRecord {
  timestamp: string;
  severity: "debug" | "info" | "warn" | "error";
  message: string;
  traceId?: string;
  spanId?: string;
  runId?: string;
  eventId?: string;
  attributes: Record<string, string | number | boolean>;
  redactionState: string;
}
```
Log 不得默认复制完整 event payload。
### Metrics
- Counter：run、attempt、tool、retry、fallback、policy deny、drop、recovery outcome。
- Histogram：run/model/tool/approval/delivery latency、TTFT、token、cost、queue lag。
- Gauge：active runs、pending approvals、in-flight tools、queue depth、projector lag、connected clients。
## Usage、Cost 与 Latency
### Usage Ledger
```typescript
interface UsageLedgerEntry {
  runId: string;
  attemptId?: string;
  operation: "main_model" | "retry" | "fallback" | "compaction"
    | "memory_extraction" | "embedding" | "rerank" | "subagent";
  provider?: string;
  model?: string;
  usage: Usage;
  cost?: Money;
  source: "provider" | "estimated" | "reconciled";
  pricingVersion?: string;
}
```
Provider usage 与估算分开；pricing version 可追溯；retry、fallback、compaction、memory、embedding、rerank、subagent 全部归因；预算使用保守估算，最终可按账单 reconciliation。
### Latency 分解
```text
request queue / context compile / prompt compile / provider connect
time to first event / first text / first tool call / model stream
policy evaluation / approval wait / tool queue / tool execution
model feedback / delivery / settlement
```
Tool 记录 scheduledAt、lockAcquiredAt、startedAt、firstProgressAt、completedAt、timeout、backend、retry 和 result/artifact bytes。
并行工具的 run critical path 是顺序模型阶段、依赖工具批次最长路径、approval wait 和必要 settlement 的总和，不是所有工具耗时简单相加；同时保存总资源时间用于容量和成本。
## Redaction、安全与 Audit
### 数据最小化
默认记录 ID、kind、状态、hash、长度、计数、provider/model、latency/usage 和 error category；默认不记录完整 system prompt、隐藏 reasoning、原始工具参数、完整工具输出、密钥、cookie、受监管数据或未脱敏用户文件。
### Redaction Pipeline
```text
classify payload -> field policy -> secret/PII detection
-> replace/tokenize/drop -> forbidden-field validation
-> attach redaction metadata -> route by sink clearance
```
```typescript
interface EventRedactor {
  redact(event: CanonicalEvent, target: TelemetrySinkPolicy): Promise<RedactedEvent>;
}
```
先脱敏后离开可信边界；hash 需要防字典攻击时使用 keyed hash；redaction 失败时外部 sink fail-closed；diagnostic 不得泄漏原值；extension payload 使用 schema/allowlist。
### AuditEvent
```typescript
interface AuditEvent {
  auditId: string;
  occurredAt: string;
  tenantId: string;
  actor: AuditActor;
  action: string;
  resource: AuditResource;
  decision?: "allow" | "ask" | "deny" | "transform";
  approval?: ApprovalAudit;
  outcome: "success" | "failure" | "cancelled" | "unknown";
  policyVersion?: string;
  configSnapshotHash?: string;
  causationEventId?: string;
  evidenceRefs?: ArtifactRef[];
  integrity?: AuditIntegrity;
}
```
Audit 覆盖身份/租户、project trust、tool visibility、policy、approval、高风险工具、sandbox attestation/降级、external receipt、敏感 trace 访问和 retention/delete/export。完整性可用 append-only、WORM、hash chain、批次签名和严格 IAM，但不得把普通日志宣称为不可篡改。
### 多租户
Tenant ID 来自认证上下文；event store partition/query 强制 tenant filter；artifact 与 event 同租户；replay 和 diagnostic snapshot 重新授权；cross-tenant correlation 被拒绝并审计。
## OpenTelemetry 映射
Canonical Event 是内部 source of truth，OpenTelemetry 是可替换投影。Exporter 失败不决定业务成功；不得把每个 delta 建成 span，不得把高基数 ID 作为 metric attributes，也不得让 vendor 字段进入公共协议。
```typescript
interface OtelMappingPolicy {
  spanForKinds: string[];
  spanEventForKinds: string[];
  logForKinds: string[];
  metricRules: MetricMappingRule[];
  attributeAllowlist: string[];
  contentCapture: "none" | "hash" | "redacted";
}
```
推荐 run、model attempt、tool、approval、compaction、subagent、delivery 建 span；retry、fallback、checkpoint、truncation、artifact offload 建 span event；error 设置 span status 并输出结构化 log；usage/cost 同时进入 span attributes 与 metrics。
Trace context 随 RunScope 传播；tool subprocess/remote worker 只注入必要 headers；不可信工具不获得多余 baggage；subagent 使用 child span 或 link；background resume 用 link；replay 标记 `replay=true`，不伪装成原始实时 span。
内部属性命名示例：
```text
agent.run.id / agent.session.id / agent.turn.id / agent.attempt.id
agent.mode / agent.event.schema_version
llm.provider / llm.api_family / llm.model / llm.request.id
tool.name / tool.call.id / tool.execution.id / tool.effect
policy.decision / sandbox.profile
```
## SLO 与告警
### SLO
- Availability：请求启动、durable terminal 可查询、event append、关键 projector 可用。
- Latency：time to first meaningful event、run p95/p99、tool queue、approval resume、replay catch-up。
- Correctness：sequence gap、duplicate terminal、projection mismatch、call/result pairing、usage reconciliation、unknown outcome。
- Delivery：live delivery、resume、dead letter、slow consumer disconnect。
- Security：redaction breach、cross-tenant violation、unaudited high-risk action、sandbox fail-open 均为零目标。
SLI 必须明确分母，例如：
```text
terminal durability
  = runs with queryable terminal durable event
    / runs with accepted RunStarted
```
不能只统计成功 run。
Page：durable writer 持续失败、敏感数据泄漏、跨租户访问、terminal 大量缺失、关键 projector 停滞、fail-closed audit sink 不可用。Ticket：cost 漂移、unknown event 增加、drop/coalesce 异常、模型 latency 退化、频繁 full resync。单客户端断线或可恢复 exporter 失败通常只做 diagnostic。
Error budget 按 provider、api family、model、tool/backend、host、deployment/config version 归因，不按用户 ID 等高基数维度建 metric。
## Diagnostic Snapshot
Diagnostic Snapshot 在不读取完整敏感 transcript 的情况下回答 run 卡点、队列积压、模型/工具/策略、pending approval、unknown side effect 和最近错误。
```typescript
interface DiagnosticSnapshot {
  generatedAt: string;
  runId: string;
  sessionIdHash: string;
  runState: string;
  currentPhase?: string;
  configSnapshot: DiagnosticConfigView;
  activeAttempt?: DiagnosticAttemptView;
  activeTools: DiagnosticToolView[];
  pendingApproval?: DiagnosticApprovalView;
  budgets: BudgetSnapshot;
  queues: QueueSnapshot[];
  projectors: ProjectorSnapshot[];
  delivery: DeliverySnapshot[];
  recentErrors: DiagnosticError[];
  lastDurableCursor?: EventCursor;
  recovery: RecoveryDiagnostic;
  redactionState: string;
}
```
内容包含 config/prompt/context/toolset/policy/sandbox 版本或 hash、provider/model/api family、session version、current attempt、in-flight tool、approval age、budget、queue depth、projector/client lag、last durable event、drop/coalesce counters 和 extensions。
默认 metadata-only；tool arguments 只显示 schema-safe summary；路径相对化或 hash；prompt 仅显示 section ID/hash；stack 进入受限 artifact；读取 snapshot 本身授权并审计；snapshot 使用短 TTL。
## 故障与恢复
### Provider Stream
保存已接收 sequence，标记 open item/tool call incomplete，不执行不完整调用；按 retry policy 创建新 attempt；保留失败 attempt 的 usage 和 latency。
### Durable Append
```text
stop advancing durable-dependent state
-> bounded safe retry
-> unresolved: suspend/fail run
-> local emergency diagnostic
-> never claim completion before terminal commit
```
### Projector
隔离失败 projector，保存 last good cursor，从 snapshot 或零状态重建，比较 live/replay；关键 projector 长期失败则 readiness=false。
### Exporter/Audit
普通 exporter 失败不影响业务，使用 bounded buffer、有限重试和 dropped counter；audit 在安全策略要求时 fail-closed；shutdown 有限 flush，不能无限占内存。
### Host Disconnect
Run 是否继续由产品策略决定；background run 不依赖连接；durable cursor 支持重连；ephemeral 丢失可接受；approval UI 消失不得自动允许。
### Process Crash
1. 加载最后 durable cursor/checkpoint。
2. Replay run state。
3. 识别 open attempt、pending approval、in-flight tool。
4. 查询 side-effect idempotency/receipt。
5. 无法确认则标记 `UnknownOutcome`。
6. 重建 projector 和 subscriptions。
7. 写 recovery event。
8. 继续、暂停或要求人工处理。
### Clock 与 Schema
顺序依赖 sequence，duration 优先 monotonic clock；occurredAt/observedAt 分开并检测异常时间。Unknown optional 字段可继续；unknown critical kind 或不支持 major version 时暂停消费，保留原 event 供升级后 replay。
## 测试策略
### Testkit
```text
ScriptedProviderStream / RawFrameFixture / StreamNormalizerHarness
DeterministicClock / DeterministicIds / InMemoryEventStore
EventRecorder / SlowConsumer / FailingConsumer
ProjectorTestHarness / ReplayRunner / CrashInjector
RedactionScanner / FakeOtelExporter
```
### 协议与 Normalizer
- Envelope codec、版本、unknown enum、event ID、sequence、sensitivity、retention。
- 文本任意分块、Unicode 跨 frame、空 delta、多 tool call 交错。
- Arguments 任意拆分，只在完成后解析；截断、gap、异常 EOF 不执行。
- Safety/refusal/empty output、usage 增量/reconciliation、unknown provider event、重复 frame。
### 状态机与 Router
- 合法 run、duplicate terminal、terminal 后 delta、fallback 新 attempt。
- Approval pending cancel、tool unknown outcome、recovery、delivery retry/dead letter。
- 慢 TUI 不阻塞 provider；delta coalesce；progress 保留最终值。
- Durable 不静默 drop；overflow、consumer crash、critical failure、flush timeout、多游标。
### Event Store 与 Replay
- 原子 append、version conflict、duplicate append、cursor、retention、partition isolation。
- Crash between append/publish、outbox recovery、snapshot hash。
- `live == full replay == snapshot + tail`，gap、upgrade、incompatible schema。
- Replay 不触发真实工具/交付，大事件流重建性能。
### Multi-client 与 Observability
- Replay/live overlap 去重、cursor 过期 resync、权限变化、慢客户端隔离。
- SSE/WebSocket framing、channel split、ack/retry。
- Span tree/link、metric count/histogram、高基数拒绝、exporter 隔离。
- Retry/fallback/compaction/subagent 成本归因、critical path、SLI 分母。
### Security 与 Fault Injection
- Synthetic secret 出现在 prompt、tool args、stack、artifact、snapshot 和 extension payload。
- Redaction fail-closed、跨租户引用、敏感 trace 授权、audit 完整性。
- 在 ToolCallReady、side effect、durable result、terminal、projector checkpoint、delivery ack 前后注入 crash。
- 高频 delta、并行 progress、多客户端、长 replay、热 partition、redaction 和 shutdown flush 性能。
### 必测断言
不能只断言最终文本；必须同时断言事件种类/顺序、状态机终态、tool call/result 关联、durable boundary、真实副作用次数、usage/cost、redaction、replay 后状态、多客户端交付和恢复语义。
## 反模式
1. 事件流定义为 `AsyncIterable<string>`。
2. Provider Event 直接进入 UI 或业务层。
3. 四层事件共用无版本 JSON。
4. 用 timestamp 排序并行/分布式事件。
5. session/run/attempt/turn/tool ID 混用。
6. 每个 token delta 永久写主 session 表。
7. durable/ephemeral 共用无界队列。
8. UI 慢消费阻塞 provider 网络读取。
9. 队列满时无差别丢最旧事件。
10. Tool arguments 未完成即解析执行。
11. Stream 异常结束仍提交完整 tool call。
12. Retry/fallback 复用 attempt ID。
13. 并行工具丢失模型 call ordinal。
14. Session 与 event 双写没有 outbox/版本协议。
15. Projector 调用外部工具或读取当前时间。
16. Replay 重新执行真实副作用。
17. 完整 prompt/reasoning/tool output 默认进入 telemetry。
18. Redaction 在 exporter 之后执行。
19. Debug log 冒充 audit log。
20. Metric label 使用 run ID、文件路径或错误消息。
21. Exporter 失败杀死 Kernel，或完全不记录失败。
22. 只统计最终成功 attempt 的 token/cost。
23. 遗漏 compaction、memory、embedding、rerank、subagent 成本。
24. Diagnostic snapshot 泄露参数、路径和 prompt。
25. 客户端重连不 replay durable gap。
26. 所有 host 共用 delivery 状态。
27. Terminal durable commit 前宣称成功。
28. 测试只看最终文本，不看轨迹、状态和副作用。
## 实施清单
### 协议与归一化
- [ ] 定义 Provider/Kernel/Harness/Host 四层事件和转换边界
- [ ] 定义 CanonicalEvent、schema version、codec 和 unknown 分支
- [ ] 定义 session/run/attempt/turn/tool/approval ID
- [ ] 定义 sequence、correlation、causation、sensitivity、retention
- [ ] Transport/decoder/provider adapter/normalizer 分层
- [ ] 文本、Unicode、tool arguments 任意分片正确重组
- [ ] 截断、gap、异常 EOF 不执行不完整工具
- [ ] Usage 增量、最终值和 provider metadata 可追溯
### Router、Store 与 Replay
- [ ] EventRouter 支持独立 subscription 和 consumer criticality
- [ ] 所有 queue bounded，durable event 不静默 drop
- [ ] Text/progress coalescing 和慢客户端 resume
- [ ] Flush/close/settlement 语义明确
- [ ] Event Store 原子 append、expected version、event ID 幂等
- [ ] Session state/event 使用 source-of-truth 或 outbox 协议
- [ ] Checkpoint/snapshot 带 source version/hash
- [ ] Transcript/run/approval/usage/delivery/diagnostic projectors
- [ ] Live/full replay/snapshot-tail 等价，replay 无真实副作用
### Observability、安全与运营
- [ ] Run/model/tool/approval/compaction/subagent/delivery spans
- [ ] 结构化 log allowlist 和低基数 metrics
- [ ] TTFT、tool queue/execution、delivery、projector lag 指标
- [ ] Retry/fallback/compaction/subagent 成本归因
- [ ] OpenTelemetry exporter 可替换且失败隔离
- [ ] Field-level redaction、sink clearance、fail-closed
- [ ] Audit 覆盖高风险工具、审批、policy、sandbox 和敏感访问
- [ ] Diagnostic Snapshot 授权、脱敏、短 TTL
- [ ] Availability/latency/correctness/delivery/security SLI 与告警
### 测试
- [ ] ScriptedProviderStream、Deterministic clock/IDs
- [ ] Slow/Failing consumer、InMemoryEventStore
- [ ] ReplayRunner、Projector harness、CrashInjector
- [ ] RedactionScanner、Fake OpenTelemetry exporter
- [ ] 轨迹、状态、副作用、成本和多客户端联合断言
## 项目启发来源
- **Pi**：headless loop、统一 EventStream、流式事件与最终结果并存、AgentSession/session tree、可恢复 compaction、CLI/TUI/RPC 共用 runtime；启发事件协议独立于 Host，并同时提供 live stream 与 final result。
- **Grok Build**：Session/ChatState/Sampler actor、HTTP/协议转换/状态管理分层、permission decision、并行工具、路径锁和独立 harness trace；启发单写者顺序、normalizer 分层和工具完成顺序/模型反馈顺序分离。
- **OpenCode**：client/server、message/part、event bus、durable event/projector、snapshot/patch/revert；启发 durable backbone、投影、replay、cursor 和多客户端交付。
- **Claude Code**：permission modes、hooks、subagents、skills、memory、MCP 和多种交互界面；启发事件覆盖审批、扩展、子 Agent 和产品模式；公开能力与安全语义应以 Anthropic 官方文档为准。
- **OpenClaw**：AgentHarness registry、agent-core、Gateway/channel、provider runtime、tool/sandbox/elevated 分层、后台运行与事务化插件；启发 Host/channel 独立 delivery、后台任务不依赖前台连接、扩展事件带来源和信任。
