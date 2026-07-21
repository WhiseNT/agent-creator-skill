# Host Adapter Engineering 细粒度工程设计
> 本文把 Host Adapter 设计为 Harness 外部接入与交付层：它负责协议、会话边界、事件投影和结果交付，不负责推断 durable truth。术语沿用 `Harness Engineering`、`Event/Observability Engineering`、`Artifact Engineering`、`Multi-tenant Agent Engineering`、`Permission/Sandbox Engineering`、`Provider Runtime Engineering` 与 `State/Memory Engineering`。
>
> 依据仅来自当前目录已有参考架构、接口模式、能力矩阵、harness 分层和五个参考项目的本地源码调研归纳；不把 README 当作规范，不新增网络调研结论。
## 目录
1. [设计目标与非目标](#设计目标与非目标)
2. [术语与核心判断](#术语与核心判断)
3. [职责边界](#职责边界)
4. [总体架构与包布局](#总体架构与包布局)
5. [HostPort 与适配器分层](#hostport-与适配器分层)
6. [核心数据模型](#核心数据模型)
7. [TypeScript 接口](#typescript-接口)
8. [CLI 与 TUI Adapter](#cli-与-tui-adapter)
9. [IDE Adapter](#ide-adapter)
10. [RPC、HTTP、Batch 与 Channel Adapter](#rpchttpbatch-与-channel-adapter)
11. [Capability Negotiation](#capability-negotiation)
12. [Event Projection 与 framing](#event-projection-与-framing)
13. [Stream、Resume 与 Backpressure](#streamresume-与-backpressure)
14. [Correlation、Approval、Steering 与 Cancel](#correlationapprovalsteering-与-cancel)
15. [Auth、Tenant Context 与 Session Browsing](#authtenant-context-与-session-browsing)
16. [Artifact Delivery](#artifact-delivery)
17. [Idempotency、Disconnect 与多客户端一致性](#idempotencydisconnect-与多客户端一致性)
18. [生命周期与状态机](#生命周期与状态机)
19. [端到端决策流程](#端到端决策流程)
20. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
21. [失败恢复与未知结果](#失败恢复与未知结果)
22. [安全、隐私与数据外发](#安全隐私与数据外发)
23. [可观测性与运营](#可观测性与运营)
24. [测试策略与 Evaluation](#测试策略与-evaluation)
25. [反模式](#反模式)
26. [实施清单](#实施清单)
27. [五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
Host Adapter 必须能够：
；把 CLI、TUI、IDE、RPC、HTTP、Batch 和 Channel 的输入规范化为同一个 `HostRequest`；把同一个 Harness 事件流投影成不同宿主可消费的事件，不改变事件的 durable 语义；在连接、请求、run、session、tenant 四个层次保持明确的 request/response correlation；协商宿主能力，包括流式、resume、approval、steering、cancel、artifact、session browsing 和多模态显示；为不同协议定义稳定 framing、版本、错误码、心跳和结束标记；处理 stream、resume、backpressure、断线重连和重复投递；将审批、转向、取消作为控制命令送回 Harness，而不是在 adapter 内直接改变工具或状态；提供认证、tenant/workspace context、scope 和审计字段；以 artifact reference、安全下载和宿主投影交付大结果；支持多客户端观察同一 session 的一致性和权限隔离；使用 fake host、recorded events、断线注入、协议 fuzz、重放和 side-effect oracle 验证交付。
### 非目标
Host Adapter 不负责：
；推断或重建 durable truth；session、run、turn、tool 或 artifact 的事实必须来自 State/Event/Harness；决定模型、provider、deployment 或 route；选择逻辑属于 Provider Routing，调用逻辑属于 Provider Runtime；决定真实权限、审批策略、文件边界、网络边界、secret 或进程隔离；Policy/Sandbox 必须在执行面强制；解释业务语义或自动合并冲突；在断线后猜测工具是否成功；将 UI 状态当作执行状态；把 host capability 当作授权；绕过 schema、事件版本或 tenant boundary；把任何单一协议作为内部 canonical model。
### 质量公式
```text
Host Delivery Reliability
  = Authentication Correctness
  × Correlation Integrity
  × Event Ordering
  × Resume Completeness
  × Backpressure Safety
  × Policy Preservation
  × Artifact Integrity
  × Multi-client Consistency
```
任一乘项接近零，宿主看到的“成功”都不能作为可靠事实。
## 术语与核心判断
### Host-neutral 术语
；`Host`：发起请求或消费事件的外部宿主，可为终端、编辑器、服务端或消息渠道；`HostAdapter`：负责协议适配、投影、连接和交付的边界组件；`HostPort`：Harness 暴露给适配器的稳定端口，不泄漏内部存储和 provider SDK 类型；`HostRequest`：规范化后的用户意图、session target、能力声明、认证上下文和交付偏好；`HostResponse`：一次请求的确认、最终摘要、错误或恢复提示；`HostEvent`：面向宿主的投影事件；`CanonicalEvent`：Harness/Event Store 中的内部事件；`ProjectionCursor`：宿主确认已收到或已应用的事件位置；`Frame`：协议上的完整消息单元；`Connection`：传输层连接及其认证、心跳和能力状态；`Client`：一个可观测或可控制 session 的宿主实例；`ArtifactRef`：可寻址、可授权、可校验的大结果引用。
### 核心判断
```text
Host Adapter 负责协议与交付。
Harness 负责生命周期、事实、恢复与预算。
State/Event Store 负责 durable truth。
Policy/Sandbox 负责真实权限与执行边界。
Routing 负责选择，Provider Runtime 负责调用。
Host capability 影响投影和交付，不等于 authorization。
```
Adapter 可以说明“已收到事件”或“无法继续交付”，但不能自行声称工具已成功、审批已生效或 artifact 已持久化。
## 职责边界
### Adapter 负责
；认证连接并构造 `TenantContext`；校验协议版本、frame 大小和 request schema；把外部输入转换为 `HostRequest` 或 `ControlCommand`；从 `HostPort` 读取 canonical event、snapshot 和 artifact metadata；将事件投影成宿主能力范围内的 frame；维护 cursor、ack、resume token、heartbeat 和发送窗口；在断线、超时、客户端取消时向 Harness 发送可审计控制命令；把大输出转为 artifact delivery；记录 transport、projection、delivery 和 security telemetry；将错误映射为稳定 host error，但保留内部 error reference。
### Adapter 不负责
；直接写 session、run、turn、tool、artifact 或 approval 的 durable 表；凭本地缓存推断 durable truth；修改 PolicySnapshot、SandboxSnapshot、TenantContext 或 RoutingSnapshot；直接执行工具、发送 provider 请求或读取 secret；把客户端发来的 `tenantId` 当作可信身份；因客户端显示限制而删除安全告警、审批信息或错误事实；在多客户端之间私自仲裁控制命令；将 ack 当作执行成功。
### 强制边界
```text
Transport -> HostAdapter -> HostPort -> Harness
                           -> Event/State/Artifact/Policy ports
HostAdapter 只提交命令与游标，不拥有事实。
Policy/Sandbox 在 Harness/Tool 执行面强制，adapter 不能替代。
```
## 总体架构与包布局
```text
CLI/TUI/IDE/RPC/HTTP/Batch/Channel
  -> Transport Listener
  -> Auth + Tenant Context Resolver
  -> Protocol Decoder + Framing
  -> Host Capability Negotiator
  -> HostRequest / ControlCommand Normalizer
  -> HostPort
  -> Harness Run/Session/Control
  -> Canonical Event Stream + State Snapshot
  -> Projection Planner
  -> Artifact Delivery Port
  -> Protocol Encoder + Backpressure Queue
  -> Host Client
```
推荐包布局：
```text
packages/host-adapter/
 contracts.ts
 host-port.ts
 auth-context.ts
 capability-negotiation.ts
 framing.ts
 request-normalizer.ts
 control-command.ts
 event-projector.ts
 resume.ts
 backpressure.ts
 correlation.ts
 artifact-delivery.ts
 session-browser.ts
 redaction.ts
 adapters/
  cli.ts
  tui.ts
  ide.ts
  rpc.ts
  http.ts
  batch.ts
  channel.ts
 testkit/
```
依赖方向：
```text
Adapter -> HostPort contracts
HostPort -> Harness contracts
Projection -> CanonicalEvent + HostCapabilities
Artifact delivery -> ArtifactPort + Policy/Sandbox checks
Transport -> protocol implementation only
```
Routing、Model、Tool、State 的实现不能反向依赖具体 CLI、IDE 或消息 SDK。
## HostPort 与适配器分层
### HostPort 设计原则
`HostPort` 是适配器和 Harness 的唯一业务入口；它必须支持 request submit、event subscribe、snapshot read、control command、artifact resolve 和 session browse。
端口返回的是不可变引用、版本和 cursor，不返回可变 ORM entity。
端口方法必须显式携带 `AuthContext`、`TenantContext`、`requestId` 和 `idempotencyKey`。
端口拒绝隐式使用当前用户、当前 workspace 或全局 session。
### 端口动作
；`submit(request)`：创建或附着 run，返回 acceptance receipt；`subscribe(query)`：按 session/run/cursor 获取 canonical event；`readSnapshot(target)`：读取指定版本的状态快照；`sendControl(command)`：提交 approval、steering、cancel、resume 等命令；`resolveArtifact(ref)`：返回经过权限检查的交付描述；`browseSessions(query)`：分页列出调用者可见 session；`ackDelivery(ack)`：记录交付确认，不修改执行事实。
### 适配器分层
Transport 层只处理 socket、stdio、HTTP body、websocket、RPC stream 或 channel webhook。
Protocol 层处理 frame、版本、编码、错误码和压缩。
Host boundary 层处理 auth、tenant、capability、correlation 和 idempotency。
Projection 层处理 canonical event 到 host event 的映射。
Delivery 层处理 queue、ack、resume、artifact 和 disconnect。
Observability 层处理日志、metric、trace 和审计引用。
## 核心数据模型
### HostRequest
```typescript
interface HostRequest {
 requestId: string;
 clientRequestId?: string;
 sessionId?: string;
 workspaceId?: string;
 tenant: TenantContext;
 auth: AuthContext;
 input: HostInput;
 capabilities: HostCapabilities;
 delivery: DeliveryPreferences;
 idempotencyKey?: string;
 correlation: CorrelationContext;
 createdAt: string;
}
```
`HostRequest` 的 `tenant`、`auth` 和 `policyRef` 由认证与 Harness 解析，不能信任普通文本字段。
### HostInput
```typescript
interface HostInput {
 kind: 'prompt' | 'command' | 'resume' | 'inspect';
 text?: string;
 attachments?: AttachmentInput[];
 command?: string;
 target?: SessionTarget;
 metadata?: Record<string, string>;
}
```
文本、命令和控制输入必须分开，不能因为同一个输入框而共享执行语义。
### HostCapabilities
```typescript
interface HostCapabilities {
 protocolVersion: string;
 streaming: boolean;
 resume: boolean;
 acknowledgements: boolean;
 approvals: boolean;
 steering: boolean;
 cancellation: boolean;
 toolEvents: boolean;
 reasoningEvents: boolean;
 multimodalInput: string[];
 multimodalOutput: string[];
 artifacts: boolean;
 sessionBrowsing: boolean;
 maxFrameBytes?: number;
 maxInflightFrames?: number;
}
```
### DeliveryPreferences
```typescript
interface DeliveryPreferences {
 mode: 'stream' | 'snapshot' | 'events' | 'batch';
 includeReasoning?: boolean;
 includeToolDetails?: boolean;
 includeArtifacts?: boolean;
 redactionProfile?: string;
 resumeCursor?: ProjectionCursor;
 ackMode?: 'none' | 'per-frame' | 'cumulative';
 heartbeatMs?: number;
}
```
宿主偏好只能控制可见投影和交付，不可关闭安全、审批、错误或审计事实。
### CanonicalEvent 与 HostEvent
```typescript
interface CanonicalEvent {
 eventId: string;
 sessionId: string;
 runId?: string;
 turnId?: string;
 seq: number;
 type: string;
 schemaVersion: number;
 occurredAt: string;
 durable: boolean;
 payloadRef: string;
 causationId?: string;
 correlationId?: string;
}
interface HostEvent {
 frameId: string;
 cursor: ProjectionCursor;
 kind: string;
 data: unknown;
 durable: boolean;
 sourceEventId?: string;
 redactions?: string[];
 terminal?: boolean;
}
```
`HostEvent` 可以合并、拆分或降级显示，但必须保留 source event reference 和 cursor 语义。
### Frame、Receipt 与 Ack
```typescript
interface HostFrame {
 version: string;
 frameType: 'hello' | 'request' | 'event' | 'ack' | 'error' | 'complete' | 'ping' | 'pong';
 frameId: string;
 requestId?: string;
 sessionId?: string;
 seq?: number;
 payload: unknown;
}
interface AcceptanceReceipt {
 requestId: string;
 runId?: string;
 status: 'accepted' | 'attached' | 'rejected' | 'duplicate';
 durableRef?: string;
 cursor?: ProjectionCursor;
}
interface DeliveryAck {
 connectionId: string;
 sessionId: string;
 cursor: ProjectionCursor;
 frameIds: string[];
 receivedAt: string;
}
```
ack 只证明宿主收到了 frame；它不证明用户看到了内容，也不证明执行成功。
## TypeScript 接口
```typescript
interface HostPort {
 submit(request: HostRequest): Promise<AcceptanceReceipt>;
 subscribe(query: EventQuery): AsyncIterable<CanonicalEvent>;
 readSnapshot(target: SnapshotTarget): Promise<StateSnapshot>;
 sendControl(command: ControlCommand): Promise<ControlReceipt>;
 browseSessions(query: SessionBrowseQuery): Promise<SessionPage>;
 resolveArtifact(request: ArtifactDeliveryRequest): Promise<ArtifactDeliveryPlan>;
 ackDelivery(ack: DeliveryAck): Promise<void>;
}
interface HostAdapter {
 accept(connection: HostConnection): Promise<void>;
 close(connectionId: string, reason: CloseReason): Promise<void>;
}
interface ProtocolCodec {
 decode(bytes: Uint8Array): DecodeResult;
 encode(frame: HostFrame): Uint8Array;
 maxFrameBytes(): number;
}
```
### 控制命令
```typescript
interface ControlCommand {
 commandId: string;
 requestId?: string;
 sessionId: string;
 tenant: TenantContext;
 auth: AuthContext;
 kind: 'approve' | 'deny' | 'steer' | 'cancel' | 'resume' | 'ack';
 payload: unknown;
 expectedVersion?: number;
 idempotencyKey: string;
}
interface ControlReceipt {
 commandId: string;
 status: 'accepted' | 'duplicate' | 'conflict' | 'rejected';
 durableRef?: string;
}
```
`expectedVersion` 用于防止旧 UI 对新审批状态进行覆盖。
## CLI 与 TUI Adapter
### CLI
CLI 以 stdin/stdout 或进程参数承载协议；默认采用 line-delimited JSON 或稳定文本模式。
非交互执行必须让 stdout 只包含机器可解析结果，诊断日志写 stderr。
CLI 需要处理 stdin EOF、SIGINT、SIGTERM、退出码、pipe close 和子进程孤儿清理。
一次命令对应一个 `requestId`，附着已有 session 时必须显式传入 session target。
流式模式下每行是完整 frame，不能以“看起来像 JSON”判断结束。
### TUI
TUI 可以把多个 HostEvent 合并为屏幕模型，但必须保留 cursor、未确认审批和 terminal error。
光标移动、重绘和终端尺寸变化不应向 Harness 发送业务 steering。
TUI 的输入模式应区分 prompt、command、approval、cancel 和 search。
终端断开时优先发送 graceful disconnect；无法发送时由 Harness 的 lease/heartbeat 识别连接消失。
### 终端安全
禁止把 token、secret、原始 prompt、工具参数和 artifact 内容写到进程标题、shell history 或未脱敏 stderr。
颜色、Unicode 和宽度只是投影问题，不能改变事件顺序和文本内容。
## IDE Adapter
### IDE 请求模型
IDE 请求通常携带 document URI、selection、workspace root、language、diagnostic 和 editor capability。
这些字段必须进入 `HostInput.metadata` 或结构化 attachment，不得隐式提升为 filesystem 权限。
IDE host capability 只说明可以显示 diff、诊断、artifact 或 inline action，不代表 Sandbox 允许写文件。
### IDE 事件投影
`turn.started` 投影为进度；`model.delta` 投影为文本增量；`tool.requested` 投影为待审批动作；`tool.started` 和 `tool.finished` 投影为任务状态；`artifact.created` 投影为可点击引用；`run.completed` 投影为终态。
差异内容应优先交付 artifact/diff reference，避免把大文件全文塞进 event frame。
### 编辑器一致性
Adapter 不直接修改编辑器缓冲区；写入必须经过 Tool/Sandbox，IDE 只显示 proposed patch 或已提交 patch。
文档版本号、selection range 和 workspace revision 应作为乐观并发条件。
旧 revision 的 apply 请求必须返回 conflict，而不是静默覆盖。
## RPC、HTTP、Batch 与 Channel Adapter
### RPC
RPC 使用强类型 method、metadata、deadline、status code 和 stream semantics。
客户端断开不等于 server cancel；需要根据 cancel token、租约和产品语义决定是否提交 cancel command。
服务端必须把 RPC status 与 Harness terminal outcome 分开记录。
### HTTP
HTTP unary 请求返回 acceptance receipt；长任务通过 SSE、WebSocket、polling 或 resume endpoint 获取事件。
SSE 每条事件带 `id`、`event`、`data`；Last-Event-ID 只能作为 resume hint，最终 cursor 由 HostPort 校验。
HTTP body、header、query 中的 tenant、session 和 artifact scope 必须经过 auth context 绑定。
### Batch
Batch 适合离线、可重试和结果导出；输入文件必须有稳定 item id，输出必须带 item-level receipt。
Batch 重跑依赖 idempotency key 与输入内容 hash，不能按文件行号推断已完成事实。
部分成功必须显式表达，不得用进程退出码覆盖 item 结果。
### Channel
消息渠道 adapter 处理 webhook 签名、重复投递、消息长度、线程/回复关系、速率和用户映射。
渠道消息只产生 prompt 或 control command，不直接成为系统身份。
长输出优先拆分、摘要或 artifact 引用，并在每段中保持 correlation。
## Capability Negotiation
### 握手顺序
```text
transport connected
  -> protocol hello
  -> authenticate
  -> resolve tenant/workspace context
  -> exchange host capabilities
  -> negotiate projection and frame limits
  -> establish cursor/heartbeat
  -> accept request or browse session
```
认证失败必须在能力协商前终止；能力协商失败不能降级到未经认证的匿名模式。
### 协商规则
协议版本采用 major/minor；major 不兼容直接拒绝，minor 可按 feature intersection 运行。
服务端声明必须支持的能力，客户端声明可选能力；最终 profile 由两者交集加 policy 强制项决定。
`resume`、`ack`、`approval`、`cancel` 和安全事件属于语义能力，不能仅靠 UI 是否显示决定。
宿主声明 `maxFrameBytes` 时，adapter 必须使用更小的服务端限制。
不支持 reasoning 的宿主可收到摘要或计量事件，但不能要求系统删除审计引用。
### 能力矩阵
| 能力 | CLI | TUI | IDE | RPC | HTTP | Batch | Channel |
|---|---|---|---|---|---|---|---|
| streaming | 可选 | 必须 | 可选 | 必须 | SSE/WS | 可选 | 渠道相关 |
| resume | 可选 | 必须 | 必须 | 必须 | 必须 | item cursor | 渠道相关 |
| approval | stdin | UI | UI action | RPC command | command endpoint | policy preset | reply action |
| artifact | path/ref | ref | diff/ref | ref | signed ref | file/manifest | link/ref |
| browsing | command | panel | tree | method | endpoint | manifest | thread |
## Event Projection 与 framing
### Canonical 到 Host 的投影
投影器以事件类型、schema version、host profile、redaction profile 和 delivery preference 为输入。
它不能根据当前屏幕状态改变 canonical event 的事实含义。
投影可做字段裁剪、文本聚合、delta 合并、artifact 替换、类型映射和兼容降级。
每个投影结果必须可以追溯到一个或多个 `sourceEventId`。
### 事件类别
；生命周期：`session.created`、`run.started`、`turn.started`、`run.completed`；模型：`model.requested`、`model.delta`、`model.completed`、`model.failed`；工具：`tool.requested`、`tool.approval_required`、`tool.started`、`tool.progress`、`tool.finished`；状态：`state.snapshot_available`、`context.compacted`、`memory.updated`；交付：`artifact.created`、`artifact.ready`、`delivery.warning`、`delivery.completed`；安全：`policy.denied`、`sandbox.blocked`、`redaction.applied`；控制：`approval.accepted`、`steering.accepted`、`cancel.accepted`。
### Framing
每个 frame 必须可独立解析、校验和关联；禁止依赖 TCP packet 边界或 UI newline 作为事实边界。
Frame header 至少包含 protocol version、frame type、frame id、request id、session id、cursor/seq、payload length 和 checksum 或完整性校验。
未知 frame type 应返回可处理的 protocol error，并保留原始 frame reference，不得让连接进入半解析状态。
超出 frame 限制时使用 chunk 或 artifact，不得截断 JSON、UTF-8、tool call 或安全事件。
### 版本与兼容
事件 schema version 与 protocol version 分离；adapter 可以将新 canonical event 投影为旧 host event，但不伪造不存在的字段。
弃用字段至少保留到约定兼容窗口，并在 telemetry 标记 deprecated feature。
## Stream、Resume 与 Backpressure
### Stream 模式
Stream 以 `hello`、`accepted`、事件帧、`complete` 或 `error` 组成。
每个事件拥有单调 cursor；同一个 session 的投影必须遵守 canonical seq 的偏序。
`complete` 只表示本次交付流结束，不代表 Harness 的 durable run 已成功，除非它引用终态事实。
### Resume
Resume 请求携带 session、run、projection profile、last cursor、protocol version 和 auth context。
服务端先验证 cursor 所属 tenant/session/profile，再决定从 event log 重放还是发送 snapshot + tail。
cursor 过旧、已压缩或 schema 不可投影时返回 `RESUME_REQUIRES_SNAPSHOT`，不能从内存队列猜测。
resume 后可能重复发送最后一帧，客户端必须按 frame id 或 source event/cursor 幂等应用。
### Backpressure
发送队列有最大 frame 数、最大字节数、最大等待时间和优先级。
安全事件、审批请求、错误和终态的优先级高于 token delta 和普通进度。
低优先级 delta 可聚合、丢弃或转 artifact，但必须发出 projection warning。
队列满时 adapter 先暂停读取，再请求 Harness 降低产生速率；不能无限缓冲在进程内存。
连续背压超过阈值时发送 `delivery.slow_consumer`，必要时断开并提供 resume cursor。
### Ack
累计 ack 只推进已连续收到的 cursor；乱序 ack 不得删除中间帧。
没有 ack 的协议只能提供 best-effort delivery，必须在 receipt 和 telemetry 中标记。
## Correlation、Approval、Steering 与 Cancel
### Correlation 层级
```text
connectionId
  -> clientId
  -> requestId
  -> runId
  -> turnId
  -> attemptId
  -> toolCallId / artifactId
```
任何事件缺少所属层级时，adapter 应拒绝投影或附带明确 unknown reference，而不是填充当前活动对象。
### Request/Response
客户端 `clientRequestId` 可跨重连复用，服务端 `requestId` 必须全局或 tenant 范围唯一。
响应必须包含 request id、status、durable reference 或错误 reference。
异步事件不能被误当作 unary response；协议必须有明确 frame type。
### Approval
approval frame 必须包含 approval id、tool call id、风险摘要、policy reference、expiresAt 和允许动作。
用户响应转成带 idempotency key 的 control command，由 Harness/Policy 验证并写 durable event。
adapter 不能把按钮点击直接映射为 `tool.execute`。
过期、重复、版本冲突和无权限的 approval 都返回稳定错误并保留审计。
### Steering
steering 只能在 Harness 声明可插入的生命周期窗口提交。
adapter 传递用户意图和 correlation，不自行拼接 system prompt 或修改 context。
被拒绝、延迟或应用的 steering 都需要显式 event。
### Cancel
cancel 是请求 Harness 停止或标记取消；transport close 只是连接事实。
若 provider/tool 不可立即停止，Harness 必须返回 `cancel.pending`，最终由 canonical terminal event 决定。
客户端重复 cancel 使用同一 command idempotency key。
## Auth、Tenant Context 与 Session Browsing
### AuthContext
```typescript
interface AuthContext {
 subject: string;
 credentialRef: string;
 authenticationMethod: 'api-key' | 'oauth' | 'mTLS' | 'service' | 'channel-signature';
 scopes: string[];
 issuedAt: string;
 expiresAt?: string;
 sessionBinding?: string;
}
interface TenantContext {
 tenantId: string;
 workspaceId?: string;
 organizationId?: string;
 policySnapshotRef: string;
 residencyProfile: string;
 auditPrincipal: string;
}
```
`credentialRef` 只引用 secret manager 句柄；adapter 不读取明文 credential。
### Context 解析
tenant/workspace 从可信认证声明、服务端映射或签名 channel identity 解析。
请求中的 tenant 字段只能作为 hint，并必须与解析结果一致，否则拒绝。
workspace root、document URI、channel thread 和 session id 都要做 tenant scope 校验。
代理转发时保留原始 principal、代理 principal、链路 id 和授权依据。
### Session Browsing
浏览接口支持按 tenant、workspace、principal、时间、状态和标签过滤，并强制分页上限。
结果只返回调用者可见的 summary、cursor、artifact refs 和状态；敏感 prompt、secret、原始 tool args 需按 redaction profile 处理。
按 session attach 前必须再次校验 policy、workspace 和 session ownership。
分页 token 绑定 query hash、tenant、principal、过期时间，不能跨租户复用。
## Artifact Delivery
### 交付原则
大文本、diff、日志、图片、音频、视频、文档和模型原始响应优先以 `ArtifactRef` 交付。
artifact 的存在、内容 hash、mime、size、retention、owner 和 policy scope 来自 Artifact/State，不由 adapter 推断。
### 交付计划
```typescript
interface ArtifactDeliveryPlan {
 artifactId: string;
 mode: 'inline' | 'download' | 'stream' | 'manifest';
 contentType: string;
 byteLength?: number;
 sha256?: string;
 expiresAt?: string;
 downloadRef?: string;
 redactionProfile: string;
}
```
adapter 先向 ArtifactPort 请求授权计划，再按宿主能力选择 inline、signed download、chunked stream 或 manifest。
下载引用必须短时有效、绑定 tenant/session 或 subject，并支持撤销。
### 交付一致性
先发送 `artifact.created`，内容准备好后发送 `artifact.ready`；失败则发送 `artifact.failed`。
客户端收到引用后自行拉取，不应把未校验内容显示为可信文件。
artifact download 的 range、resume、checksum 和 content-disposition 必须记录 telemetry。
## Idempotency、Disconnect 与多客户端一致性
### Idempotency
submit、control、ack、artifact download initiation 和 batch item 都需要稳定 idempotency key。
幂等记录至少保存 key、tenant、operation kind、request hash、结果 reference 和 expiry。
同 key 不同 payload 返回 conflict，不得复用第一次结果。
### Disconnect
连接断开分为 graceful close、transport error、heartbeat timeout、server shutdown 和 auth expiry。
adapter 记录 disconnect reason 与最后已发送/已确认 cursor。
Harness 继续运行还是取消由 run policy、client lease 和 command 语义决定。
重连后客户端必须重新认证并重新协商能力，不能信任旧 connection state。
### 多客户端一致性
多个客户端订阅同一 session 时，每个客户端拥有独立 projection cursor 和 redaction profile。
canonical event seq 是一致性基准；客户端局部 ack、滚动位置和折叠状态不进入 durable run truth。
控制命令按 command id、expectedVersion 和 Harness 顺序处理。
两个客户端同时审批时，一个成功，另一个收到 duplicate 或 conflict，而不是各自显示成功。
新客户端 attach 先读 snapshot，再接 tail；不能只从另一个客户端的缓存复制状态。
## 生命周期与状态机
### Connection 状态
```text
Created
  -> TransportOpen
  -> HelloReceived
  -> Authenticated
  -> CapabilitiesNegotiated
  -> Ready
  -> Draining
  -> Closed
```
非法跳转：未认证不能订阅；未协商不能提交请求；Closed 不能恢复旧 connection object。
### Request 状态
```text
Received
  -> Decoded
  -> Authenticated
  -> Normalized
  -> Submitted
  -> Accepted | Duplicate | Rejected
  -> Streaming
  -> Completed | Failed | CancelPending
```
`Submitted` 只表示 command 已交给 HostPort；`Accepted` 需要 Harness receipt；`Completed` 必须引用 canonical terminal event。
### Delivery 状态
```text
Planned -> Queued -> Sent -> Acked
                     \\-> Expired
                     \\-> Disconnected -> Resumable
```
状态由 adapter delivery ledger 记录，不能覆盖 Harness 的执行状态。
### 控制状态
```text
ControlReceived -> Validated -> Submitted -> Accepted
                                      \-> Conflict | Rejected | Expired
```
控制状态机与 tool/run 状态机通过 durable event 关联，不在 adapter 内联动修改。
## 端到端决策流程
### 新请求
1. Transport 接收 bytes/body/message。
2. Protocol codec 校验版本、frame size、encoding、checksum 和 schema。
3. Auth resolver 验证 credential/signature，并建立 principal。
4. Tenant resolver 绑定 tenant、workspace、policy snapshot 和 residency profile。
5. Capability negotiator 计算 host profile。
6. Request normalizer 生成 request id、correlation、idempotency 和 delivery preference。
7. Adapter 调用 `HostPort.submit`。
8. Harness 返回 acceptance receipt，adapter 立即发送 accepted 或稳定 rejection。
9. Adapter 建立 event subscription，按 cursor 投影并排队。
10. Delivery writer 发送 frame、记录发送状态并处理 ack。
11. canonical terminal event 到达后发送 complete，并等待必要的 delivery flush。
### Attach/resume
1. 客户端重新认证并声明 session/run/cursor。
2. Adapter 验证 tenant、principal、projection profile 和 cursor。
3. HostPort 返回 snapshot、event tail 或 resume error。
4. Adapter 先发送 snapshot frame，再发送严格递增 tail。
5. 客户端按 source event/cursor 去重。
6. adapter 更新 delivery cursor，不更改 session durable truth。
### 控制请求
1. 解码 control frame。
2. 校验 session target、command kind、auth scope、expectedVersion 和 idempotency。
3. 调用 HostPort.sendControl。
4. 返回 control receipt。
5. 通过 canonical control event 让所有客户端最终一致。
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### Model 与 Provider Runtime
Host Adapter 只接收模型事件的规范投影，不知道 provider SDK 私有 stream 类型。
`model.requested` 可显示 selected model summary，但 credential、raw headers 和敏感 request 不应默认外发。
Model delta 可按 token、句子或时间窗口聚合；聚合不能改变 final text artifact。
provider failure 映射为 host error 时保留 attempt、route snapshot 和 retry reference。
### Prompt
Prompt 输入由 Harness/Prompt 层构造；adapter 只传递用户输入、附件引用和显式 metadata。
adapter 不把 UI placeholder、快捷键或 channel prefix 直接写入 system prompt。
展示 prompt 时遵守 redaction profile，不能因为 debug mode 绕过 policy。
### Context
Context compaction、truncation、overflow 和 memory retrieval 通过 canonical events 投影。
宿主可以显示“已压缩”或“上下文不足”，不能自行删除消息再重试。
attachment 的 mime、size、hash 和 source scope 必须进入 HostRequest。
### Tool
tool request 是待审批或待执行的事实；adapter 显示名称、风险和参数摘要，真实参数由 Policy/Sandbox 控制。
tool progress 可以被节流；tool finished 必须保留 exit status、artifact refs 和 error reference。
工具结果过大时使用 artifact，不在 host frame 中截断成看似完整的结果。
### State 与 Memory
State/Event Store 是 session、run、turn、approval、artifact 和 cursor 的事实来源。
Memory 事件可以投影为引用或摘要，不应在 adapter 内拼接为 durable memory。
浏览历史使用 StatePort 分页，不能扫描本地 UI cache 代替权限过滤。
### Policy 与 Sandbox
PolicySnapshot 决定可见性、可控性、artifact 外发、reasoning 显示和 session attach 条件。
SandboxSnapshot 决定工具执行、文件、网络、进程和 secret 边界；adapter 不能替代。
被 policy 隐藏的事件应返回稳定 redacted projection，不能让错误码泄漏资源是否存在。
### Harness
Harness 负责 run 生命周期、预算、retry、cancel、恢复、事件写入和交付语义。
Adapter 通过 HostPort 提交命令，通过事件订阅观察结果，通过 artifact port 获取内容。
适配器崩溃不会改变 Harness run；恢复依赖 durable cursor 和 snapshot。
## 失败恢复与未知结果
### 错误分类
```text
ProtocolError       -> frame 无法解析或版本不兼容
AuthError           -> 身份、scope、签名或过期失败
TenantError         -> tenant/workspace/session 不匹配
CapabilityError     -> 宿主不能表达所需交付能力
SubmissionError     -> HostPort 未接受请求
DeliveryError       -> 发送、ack、frame 或 artifact 交付失败
ControlError        -> approval/steering/cancel 被拒绝或冲突
TerminalOutcome     -> Harness 已产生成功、失败、取消或未知事实
```
不同类别必须有不同 error code、retry hint 和内部 reference。
### 未知结果
如果连接在请求提交后断开，adapter 不得返回“未执行”或“已失败”。
重连时通过 request id、idempotency key、run id 和 StatePort 查询真实结果。
如果 Harness 也无法确认 provider/tool side effect，状态为 `unknown`，交给 recovery policy。
客户端可收到 `OUTCOME_PENDING`、`OUTCOME_UNKNOWN` 或 `RESUME_REQUIRED`，而不是猜测。
### 恢复矩阵
| 故障 | Adapter 动作 | Harness/State 动作 |
|---|---|---|
| decode failure | 返回 protocol error，关闭坏 frame | 无业务变化 |
| auth expiry | 停止发送，要求 re-auth | 保持 run 事实 |
| client disconnect | 记录 cursor/reason | 按 lease policy 继续或取消 |
| queue full | 节流、聚合或断开 | 保留 canonical events |
| artifact download fail | 返回 retryable delivery error | artifact 状态不变 |
| duplicate submit | 返回原 receipt | 不创建第二个 run |
| control conflict | 返回 conflict | 记录 rejection event |
| unknown terminal | 提供查询/恢复 | 由 Harness 解析真实 outcome |
## 安全、隐私与数据外发
### 威胁模型
攻击面包括伪造 tenant、重放 control、跨 session attach、frame injection、恶意 artifact、日志泄漏、channel spoofing、过大 frame、压缩炸弹和多客户端旁路读取。
### 身份与授权
每个 connection、request、control、artifact download 和 browse 都进行 auth 与 tenant scope 检查。
长连接需支持 credential expiry、key rotation、server initiated close 和重新握手。
权限判定使用 PolicySnapshot 版本引用，不能使用客户端传来的 allow 字段。
### Redaction
redaction 应区分 secret、PII、credential、internal prompt、tool raw args、provider headers、reasoning 和 artifact content。
脱敏结果带 profile、规则版本和 source reference，便于审计。
不能通过错误消息、frame length、session count 或 artifact name 侧信道泄漏被隐藏事实。
### 输入与输出安全
严格限制 frame、header、attachment、batch item、channel message 和 artifact metadata 大小。
对 JSON、protobuf、multipart、SSE、markdown、HTML 和 terminal escape 做上下文安全编码。
禁止把未经信任文本作为 shell、SQL、路径、IDE command 或 channel markup 执行。
### 审计
认证、授权拒绝、session attach、control command、artifact download、redaction、disconnect 和 resume 都产生审计引用。
审计事件不应包含明文 secret；必要内容使用 hash、reference 或受控 artifact。
真实权限由 Policy/Sandbox 强制，Host Adapter 只能拒绝额外交付，不能放宽执行边界。
## 可观测性与运营
### Telemetry 维度
记录 connection、client、request、run、session、tenant、workspace、protocol、adapter、frame、cursor、artifact 和 command correlation。
高基数原始文本、token、secret 和完整 payload 不作为普通 metric label。
### Metrics
；`host_connections_open`、`host_connections_closed_total`；`host_requests_accepted_total`、`host_requests_rejected_total`；`host_projection_latency_ms`、`host_delivery_latency_ms`；`host_frames_sent_total`、`host_frames_acked_total`、`host_frames_retried_total`；`host_resume_total`、`host_resume_gap_total`；`host_backpressure_seconds`、`host_queue_bytes`；`host_control_conflict_total`；`host_artifact_download_total`、`host_artifact_failure_total`；`host_redaction_total`。
### 日志与追踪
结构化日志必须带 connectionId、requestId、sessionId、tenantId hash、cursor、frameId 和 error reference。
trace span 分为 transport、decode、auth、normalize、host-port、projection、artifact、encode、send 和 ack。
禁止将 raw prompt、tool secret、provider token 和未授权 artifact 内容写入 trace。
### SLO 与告警
SLO 应分别衡量 acceptance latency、first event latency、terminal delivery latency、resume completeness、duplicate rate 和 artifact success。
告警关注跨租户错误、cursor gap、重复 control、队列积压、redaction failure、auth failure spike 和协议错误 spike。
## 测试策略与 Evaluation
### 单元测试
测试 codec 的版本、长度、UTF-8、checksum、未知类型、半 frame、重复 frame 和恶意嵌套。
测试 request normalizer 的 correlation、tenant binding、idempotency、默认 capability 和 preference。
测试 projector 的事件映射、聚合、降级、redaction、artifact replacement、terminal semantics 和 source references。
测试 resume validator 的 tenant/session/profile/cursor 校验、snapshot fallback 和重复 tail。
测试 backpressure queue 的优先级、公平、聚合、超时、溢出和 slow consumer。
### 契约测试
HostPort contract test 固定 submit、subscribe、snapshot、control、artifact、browse 和 ack 语义。
每个 adapter 与同一 contract suite 运行，确保 CLI、IDE、RPC、HTTP 和 Channel 不改变业务事实。
协议兼容测试覆盖旧客户端、新服务端、未知字段、字段弃用和错误码映射。
### 集成测试
使用 fake Harness、fake State/Event Store、fake Policy/Sandbox 和 fake ArtifactPort。
验证提交后断线、重连 resume、多个客户端 attach、并发 approval、cancel pending、artifact range 和 auth expiry。
验证 provider/tool 失败只通过 canonical event 影响宿主，不被 adapter 私自重试成另一事实。
### 故障注入
注入 partial write、socket reset、HTTP 502、SSE gap、RPC deadline、webhook duplicate、slow reader、queue full 和 artifact checksum mismatch。
注入 StatePort 暂时不可用，确认 adapter 不用内存缓存声称 durable truth。
注入 policy denial、sandbox block、session ownership conflict，确认错误不会泄漏资源。
### Evaluation 场景
用录制事件重放评估不同 host profile 的信息完整性和噪声。
用 side-effect oracle 验证 approval、cancel、steering 和 artifact download 的真实调用次数。
以黄金 cursor 序列比较 resume 后事件集合、顺序、terminal outcome 和 artifact refs。
评估 CLI/TUI 文本、IDE diff、HTTP SSE、RPC stream、Batch manifest 和 Channel 长消息的等价事实。
### 性质测试
任意 frame 分片重组后 decode 结果等价；重复 submit 不增加 run 数；重复 control 不增加执行数；ack 单调推进；不同 projection 不改变 source event；未授权 session 永远不可 attach；客户端断线重连最终不丢 durable event。
## 反模式
### 把断线当取消
连接断开是 transport fact，取消是 Harness control command；混用会造成工具副作用和用户认知不一致。
### Adapter 持有业务状态
本地 map、UI cache 或进程内 queue 只能做性能缓存，不能成为 session/run 的唯一事实。
### 直接执行审批
按钮事件不能调用 tool；必须经过 ControlCommand、Policy、Harness 和 durable approval event。
### 以 host capability 代替权限
“支持文件写入”只表示可显示或传输，不表示 Sandbox 允许写入。
### 静默丢事件
为节省带宽丢弃安全、审批、错误或终态事件会破坏审计；低优先级事件也要有聚合或 warning。
### 猜测未知结果
提交成功后失去连接不能凭空返回失败；必须查询 State/Harness 或明确 unknown。
### 跨客户端私自同步
客户端之间不能直接广播控制状态；所有事实通过 canonical event 统一投影。
### 复用旧身份
重连复用旧 connection token、tenant context 或 capability profile 会造成权限漂移。
### 把 artifact 当文本
截断 artifact 伪装成完整结果会造成数据损坏；应交付 hash、size、range 和引用。
### 协议即业务模型
HTTP、RPC、stdio 和 channel 的差异不能污染 Harness 的 canonical model。
## 实施清单
### 契约与基础设施
- 定义 HostPort、HostRequest、HostEvent、ControlCommand、ArtifactDeliveryPlan 和 cursor contract。
- 定义 protocol major/minor、frame header、错误码、heartbeat、ack 和 close reason。
- 定义 AuthContext、TenantContext、PolicySnapshotRef 和 redaction profile。
- 定义 canonical event 到 host event 的 projection registry 与 schema version。
- 定义 connection、request、delivery、control 和 idempotency ledger 的存储边界。
### 适配器
- 实现 CLI line protocol、stderr 诊断和信号处理。
- 实现 TUI projection、审批界面、重绘与终端断开。
- 实现 IDE request metadata、diff/artifact 投影和 revision conflict。
- 实现 RPC method/stream、HTTP SSE/WS/polling、Batch manifest、Channel webhook。
- 实现统一 auth、tenant binding、capability negotiation 和 correlation。
### 交付
- 实现 frame decoder/encoder、chunk、checksum、最大尺寸和协议错误。
- 实现 event subscribe、snapshot+tail、cursor、resume、ack 和重复去重。
- 实现优先级队列、delta 聚合、slow consumer 和 disconnect recovery。
- 实现 artifact inline/download/stream/manifest、range、checksum 和过期。
- 实现 approval、steering、cancel、expectedVersion 和 idempotency。
### 安全与运维
- 接入 Policy/Sandbox 强制检查，禁止 adapter 放宽执行边界。
- 接入审计、trace、metric、redaction、租户隔离和密钥轮换。
- 建立 protocol compatibility、fuzz、fault injection、replay 和 side-effect oracle。
- 建立 resume completeness、delivery latency、duplicate control 和 queue backlog SLO。
- 进行多客户端、跨协议、跨版本和长时间 stream soak test。
### 发布门槛
- 所有 adapter 通过 HostPort contract suite。
- 所有 terminal event 都可从 source event/cursor 追溯。
- 所有 control command 都有 durable receipt 或明确 rejection。
- 断线、重连、重复提交和未知结果均有可操作恢复路径。
- 安全事件、审批事件、policy denial 和 sandbox block 不被降级吞掉。
## 五个参考项目的启发来源
### pi
本地架构启发：交互入口保持轻量，核心 agent loop 与宿主交互解耦；Host Adapter 应将终端输入、事件流和控制动作映射到稳定端口，而不是让 UI 拥有模型循环。
工程借鉴：CLI/TUI 适配器可共享 request、event、approval 和 cancel contract，同时允许显示层有不同投影密度。
边界保留：终端体验不能成为 durable state；重连和恢复必须回到 Harness/Event Store。
### grok-build
本地架构启发：构建/编码工作流需要把长任务、进度、diff、artifact 和失败交付给宿主；IDE/CLI 适配器应优先提供可追踪的 artifact reference。
工程借鉴：批处理与交互工作流共享 run/correlation，但 Batch 使用 item-level idempotency 和 manifest。
边界保留：workspace 能见性不等于 Sandbox 写权限，adapter 只展示或提交命令。
### opencode
本地架构启发：工具、模型、会话和 UI 通过事件驱动连接；Host Adapter 应保持事件投影可重放并可恢复。
工程借鉴：将工具请求、审批、输出、错误和终态都暴露为显式事件，避免 UI 通过轮询内部状态猜测。
边界保留：不同 provider、工具和终端协议不应泄漏到 HostPort canonical contract。
### claude-code
本地架构启发：编码宿主需要审批、工具执行反馈、文件变更和终端交互的紧密协作；这些应通过 control command 和 artifact/diff 交付表达。
工程借鉴：Approval、steering、cancel 需要清晰的用户可见状态与不可抵赖的 correlation。
边界保留：用户同意不是 Sandbox 授权本身，Policy/Sandbox 仍在真实执行面强制。
### openclaw
本地架构启发：多渠道、多客户端和远程连接要求统一会话、身份、消息路由和能力协商；Channel Adapter 不能把消息线程当作完整 session truth。
工程借鉴：webhook 重复、连接恢复、消息长度和多端一致性必须由 adapter/HostPort 共同定义。
边界保留：渠道身份需映射到 AuthContext/TenantContext，不能由文本中的 user id 自称。
### 综合结论
五个项目共同指向：宿主入口可以多样，Harness、事件和状态事实必须统一；流式交付必须可重放；控制命令必须可审计；大结果必须引用化；真实权限必须留在 Policy/Sandbox。
## 自检表
- 文档包含目录、目标与非目标、职责边界、数据模型、TypeScript 接口、生命周期、决策流程、集成、恢复、安全、可观测性、测试、反模式、实施清单和五个参考项目启发来源。
- 覆盖 CLI、TUI、IDE、RPC、HTTP、Batch、Channel、HostPort、capability negotiation、event projection、framing、stream/resume/backpressure、correlation、approval、steering、cancel、auth/tenant、artifact、session browsing、idempotency、disconnect/reconnect、多客户端一致性、安全/redaction 和测试。
- 明确 Host Adapter 负责协议/交付，不负责推断 durable truth；Routing、Policy、Sandbox、Harness 的边界未被混淆。
