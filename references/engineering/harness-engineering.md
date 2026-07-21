# Agent Harness Engineering 详细设计

> 本文关注 Harness 的工程实现：如何把 Agent Kernel、Context Compiler、Prompt Compiler、Model Runtime、Tool Runtime、Policy、Sandbox、Session、Extensions 和 Host 装配成可运行、可取消、可恢复、可测试的系统。

## 目录

1. [设计目标](#设计目标)
2. [Kernel 与 Harness 契约](#kernel-与-harness-契约)
3. [组件图](#组件图)
4. [Harness Bootstrap](#harness-bootstrap)
5. [Run Supervisor](#run-supervisor)
6. [事件骨干](#事件骨干)
7. [Model Runtime 装配](#model-runtime-装配)
8. [Tool Runtime 装配](#tool-runtime-装配)
9. [Policy、Approval 与 Sandbox](#policyapproval-与-sandbox)
10. [Session 与 Durability](#session-与-durability)
11. [Retry、Fallback 与 Recovery](#retryfallback-与-recovery)
12. [Extensions、Hooks、Skills 与 MCP](#extensionshooksskills-与-mcp)
13. [Subagent 与 Background Run](#subagent-与-background-run)
14. [Host Adapter](#host-adapter)
15. [配置与依赖注入](#配置与依赖注入)
16. [资源生命周期](#资源生命周期)
17. [测试 Harness](#测试-harness)
18. [运维与诊断](#运维与诊断)
19. [反模式](#反模式)
20. [实施蓝图](#实施蓝图)

## 设计目标

Harness 应提供：

- 确定性装配；
- 明确能力边界；
- 统一事件；
- 结构化并发；
- 取消传播；
- 崩溃恢复；
- 安全执行；
- 可插拔 provider/tool/state/host；
- 可观测性；
- 可测试性。

Harness 不应成为包含全部业务逻辑的 God Object。它负责装配、监督和路由，实际能力由组件实现。

## Kernel 与 Harness 契约

### Kernel 只依赖端口

```typescript
interface KernelEnvironment {
  model: ModelPort;
  tools: ToolPort;
  context: ContextPort;
  state: KernelStatePort;
  events: KernelEventSink;
  clock: Clock;
  ids: IdGenerator;
}
```

Kernel 不应知道：

- OpenAI/Anthropic SDK；
- SQLite/JSONL；
- TUI/HTTP；
- Docker/bwrap；
- MCP transport；
- 用户确认 UI。

### Harness 控制 Kernel 生命周期

```typescript
interface AgentHarness {
  start(request: HarnessRequest): Promise<RunningHarness>;
  resume(checkpoint: CheckpointRef): Promise<RunningHarness>;
  inspect(sessionId: string): Promise<SessionView>;
  dispose(): Promise<void>;
}
```

```typescript
interface RunningHarness {
  runId: string;
  events: AsyncIterable<HarnessEvent>;
  result: Promise<HarnessResult>;
  cancel(reason?: string): void;
  submitApproval(decision: ApprovalDecision): Promise<void>;
  steer(message: AgentInput): Promise<void>;
}
```

## 组件图

```text
Host Adapter
  │
  ▼
Harness Facade
  ├─ Bootstrapper
  ├─ Run Supervisor
  ├─ Event Router
  ├─ Session Coordinator
  ├─ Context/Prompt Compiler
  ├─ Model Runtime
  ├─ Tool Runtime
  ├─ Policy/Approval
  ├─ Execution Backends
  ├─ Extension Runtime
  └─ Delivery Adapter
          │
          ▼
      Agent Kernel
```

### 控制面与数据面

控制面：

- 配置；
- session；
- 权限；
- 插件；
- 模型选择；
- 取消；
- 审批；
- 恢复。

数据面：

- 模型 stream；
- tool execution；
- content parts；
- artifacts；
- event delivery。

两者分开，避免流量路径被复杂管理逻辑阻塞。

## Harness Bootstrap

### 启动阶段

```text
1. Parse host request
2. Resolve user/workspace/tenant
3. Load safe global configuration
4. Resolve project trust
5. Load trusted project resources
6. Build extension registry transaction
7. Resolve model/provider credentials
8. Build tool catalog and policies
9. Resolve execution backends
10. Open session repository
11. Create event router
12. Validate assembled capabilities
13. Freeze run configuration snapshot
```

### BootstrapResult

```typescript
interface BootstrapResult {
  config: ResolvedHarnessConfig;
  registries: HarnessRegistries;
  sessionRepository: SessionRepository;
  runtimeFactories: RuntimeFactories;
  diagnostics: Diagnostic[];
  configSnapshot: ConfigSnapshot;
}
```

### 两阶段信任加载

```text
Safe phase:
  built-ins, user config, non-executable metadata

Trusted phase:
  workspace plugins, hooks, MCP/LSP commands, env loaders
```

### 能力一致性校验

启动前检查：

- prompt 宣称的工具确实存在；
- policy 引用的工具名存在；
- sandbox backend 支持要求的文件/网络能力；
- provider 支持所需模态和 tool calling；
- session schema 可迁移；
- plugin contribution 无冲突；
- host 支持 approval/event 类型。

## Run Supervisor

Run Supervisor 是 Harness 的核心，而不是 Agent Kernel。

### 职责

- 创建 run scope；
- 恢复 checkpoint；
- 启动 Kernel；
- 监督模型、工具、审批和事件任务；
- 执行 retry/fallback；
- 触发 compaction；
- 维护预算；
- 处理 steering/follow-up；
- 完成 settlement。

### RunScope

```typescript
interface RunScope {
  runId: string;
  sessionId: string;
  branchId: string;
  abortController: AbortController;
  budget: BudgetTracker;
  taskGroup: TaskGroup;
  config: FrozenRunConfig;
  checkpoint: CheckpointWriter;
}
```

### Structured Concurrency

所有子任务属于 RunScope：

```text
model stream
parallel tools
approval wait
background compaction
subagents
event consumers
delivery
```

父 run 取消时：

1. 设置 abort signal；
2.停止新任务；
3.等待子任务 settle；
4.记录未知执行状态；
5.写 cancellation entry；
6.释放资源。

### BudgetTracker

跟踪：

```text
turn count
tool count
subagent count
wall-clock
input/output tokens
cached tokens
cost
retry count
artifact bytes
```

每次动作前预检，每次事件后更新。

## 事件骨干

### 三类事件

```text
KernelEvent     模型和工具循环
HarnessEvent    审批、fallback、compaction、session、sandbox
HostEvent       UI/协议特定表示
```

转换方向：

```text
Provider Event
  -> Kernel Event
  -> Harness Event
  -> Host Event
```

不要让 Provider Event 直接进入 UI。

### Durable 与 Ephemeral

Durable：

- message completed；
- tool requested/result；
- approval；
- 模型切换；
- compaction；
- checkpoint；
- final status。

Ephemeral：

- text delta；
- spinner；
- 局部 tool progress；
- heartbeat。

### EventRouter

```typescript
interface EventRouter {
  publish(event: HarnessEvent): Promise<void>;
  subscribe(filter: EventFilter): AsyncIterable<HarnessEvent>;
  flush(): Promise<void>;
}
```

关键 durable consumer 失败时 Run Supervisor 必须知道；普通 UI consumer 失败可隔离。

### Backpressure

策略：

- durable queue bounded but never silently drop；
- text delta 可合并；
- progress 可只保留最新；
- error/completion 不可丢；
- 慢客户端可断开并从 durable state 重建。

## Model Runtime 装配

### 分层

```text
Credential Provider
  -> Model Catalog
  -> Provider Adapter
  -> Transport/Retry
  -> Stream Normalizer
  -> ModelPort
```

与 Grok Build 的 HTTP、纯协议转换、actor 管理三层思路一致。

### Provider Registry

```typescript
interface ProviderRegistry {
  register(provider: ModelProvider): RegistrationHandle;
  resolve(model: ModelRef): Promise<ModelProvider>;
  snapshot(): ProviderRegistrySnapshot;
}
```

### Fallback

Fallback 是 Harness 逻辑：

```text
attempt primary
  -> classify failure
  -> verify fallback policy
  -> ensure capability compatibility
  -> snapshot model change
  -> attempt fallback
  -> restore or commit selection
```

不要在 provider adapter 内偷偷切模型。

### Retry

Transport retry 与 Agent retry 分开：

- Transport retry：同请求的安全网络重试；
- Agent retry：重新生成或修改上下文；
- Fallback：换模型/provider；
- Tool retry：工具自身策略。

## Tool Runtime 装配

### Registry 组成

```text
built-in tools
+ trusted workspace tools
+ plugin tools
+ MCP tools
+ session-scoped tools
- policy hidden tools
- host unsupported tools
= active toolset
```

生成 toolset hash 保存到 run snapshot。

### Tool Execution Scheduler

```typescript
interface ToolScheduler {
  schedule(calls: PreparedToolCall[], scope: RunScope): AsyncIterable<ToolEvent>;
}
```

调度策略：

- `parallel`；
- `serial`；
- `resource-locked`；
- `exclusive`；
- `background`。

### Resource Lock

锁 key 由工具解析：

```text
file:D:/repo/src/a.ts
repo:D:/repo
account:customer-123
service:production-deploy
```

Grok Build 对同一路径写入串行化是这一模式的具体实例。

### Artifact Store

大输出、diff、图片、日志等进入 ArtifactStore：

```typescript
interface ArtifactStore {
  put(input: ArtifactInput): Promise<ArtifactRef>;
  get(ref: ArtifactRef, range?: ByteRange): Promise<Artifact>;
}
```

## Policy、Approval 与 Sandbox

### 决策管线

```text
Tool visibility policy
  -> call policy
  -> approval policy
  -> execution sandbox policy
  -> result egress policy
```

### PolicyDecision

区分：

```text
allow
ask
deny_recoverable
deny_terminal
transform
cancel
```

Grok Build 区分用户 Reject 和 PolicyDeny 很有价值：策略拒绝后模型可能选择其他安全动作。

### Approval

Approval 是可持久化状态：

```typescript
interface ApprovalRequest {
  id: string;
  runId: string;
  actionSummary: string;
  toolCall: ToolCall;
  risk: RiskAssessment;
  expiresAt?: string;
}
```

Agent 进程重启后仍能恢复等待状态。

### Sandbox Backend

```typescript
interface SandboxBackend extends ExecutionBackend {
  profile: SandboxProfile;
  attest(): Promise<SandboxAttestation>;
}
```

Attestation 包括：

- sandbox 是否真正应用；
- 文件读写边界；
- 网络边界；
- 进程权限；
- 已知降级。

安全敏感 profile 要求 fail-closed。

## Session 与 Durability

### SessionCoordinator

负责：

- load/create；
- 版本检查；
- append；
- branch；
- checkpoint；
- compaction；
- projection；
- retention。

### 写入时机

```text
user input accepted          durable
assistant complete           durable
tool call ready              durable
tool result                  durable
approval requested/resolved  durable
text delta                   ephemeral
```

### 乐观并发

```typescript
append(sessionId, entries, expectedVersion)
```

冲突时重新加载和协调，不能覆盖其他客户端写入。

### Checkpoint

包含：

```text
last durable entry
active branch
current model/toolset
budget counters
pending approvals
in-flight tools and idempotency
compaction state
extension/config snapshot
```

## Retry、Fallback 与 Recovery

### Error Taxonomy

```text
provider_transport
provider_rate_limit
provider_context_overflow
provider_capability
model_output_invalid
tool_validation
tool_permission
tool_execution
sandbox
session_conflict
extension
host_delivery
cancelled
```

### RetryDecision

```typescript
interface RetryDecision {
  action: "retry_same" | "retry_modified" | "fallback" | "wait" | "stop";
  delayMs?: number;
  reason: string;
  maxAttempts: number;
}
```

### Crash Recovery

启动恢复：

1. 加载 checkpoint；
2.识别 in-flight 操作；
3.查询幂等状态；
4.标记 unknown outcome；
5.恢复 pending approval；
6.重新构建 context；
7.继续或要求人工处理。

不要重新执行状态未知的付款、发送、删除、部署等动作。

## Extensions、Hooks、Skills 与 MCP

### Contribution Registry

```typescript
interface HarnessRegistries {
  providers: ProviderRegistry;
  tools: ToolRegistry;
  hooks: HookRegistry;
  skills: SkillRegistry;
  hosts: HostRegistry;
  memory: MemoryRegistry;
  sandboxes: SandboxRegistry;
}
```

### RegistrationHandle

每个注册返回可撤销句柄：

```typescript
interface RegistrationHandle {
  dispose(): Promise<void>;
}
```

加载失败按逆序 dispose，学习 OpenClaw 的事务化回滚。

### Hook Runner

```typescript
interface HookRunner {
  run<T>(phase: HookPhase, payload: T, policy: HookPolicy): Promise<HookResult<T>>;
}
```

HookPolicy 定义：

- timeout；
- 顺序；
- 可否修改；
- 可否阻断；
- 错误是否隔离；
- 修改后是否重新校验。

### Skills

Skill loader 只负责提供工作流指令和资源，不直接扩大权限。Skill 要求的工具必须再经过 active toolset 和 policy。

### MCP

MCP lifecycle：

```text
discover config
  -> trust check
  -> start/connect
  -> authenticate
  -> snapshot tools/resources
  -> wrap with local policy/output budgets
  -> health/reconnect
  -> dispose
```

## Subagent 与 Background Run

### SubagentSupervisor

```typescript
interface SubagentSupervisor {
  spawn(spec: SubagentSpec, parent: RunScope): Promise<ChildRunHandle>;
}
```

### 隔离

- 独立 run ID；
- 独立 context plan；
- 独立预算；
- 受限 toolset；
- 可选独立 sandbox；
- 独立 event namespace；
- 父取消传播；
- 结果 schema。

### Background Run

后台任务需要：

- durable queue；
- lease/heartbeat；
- retry ownership；
- checkpoint；
- 结果通知；
- 过期和取消；
- 不依赖前台连接存活。

### 结果合并

父 Agent 接收结构化 ChildResult，不直接拼接全部 child transcript。

## Host Adapter

### 统一 HostPort

```typescript
interface HostPort {
  capabilities(): HostCapabilities;
  deliver(event: HostEvent): Promise<void>;
  requestApproval(request: ApprovalRequest): Promise<ApprovalDecision>;
  receiveControl(): AsyncIterable<HostControlEvent>;
}
```

### CLI/TUI

- 增量渲染；
- 工具进度；
- 审批；
- 取消；
- session 切换；
- artifact 路径。

### RPC/HTTP

- 稳定 framing；
- idempotent request ID；
- SSE/WebSocket resume；
- 慢消费者；
- auth/tenant；
- durable result query。

Pi 的严格 JSONL framing、OpenCode 的 server/event、OpenClaw 的 Gateway/channel 都说明 Host 应是独立适配层。

### Channel

消息渠道还需要：

- 入站身份归一化；
- session key；
- message split；
- media conversion；
- delivery retry；
- platform rate limit；
- edit/delete capability；
- typing/progress indicators。

## 配置与依赖注入

### Resolved Config

不要让组件到处读取环境变量。Bootstrap 统一解析：

```typescript
interface ResolvedHarnessConfig {
  model: ResolvedModelConfig;
  context: ResolvedContextConfig;
  tools: ResolvedToolConfig;
  policy: ResolvedPolicyConfig;
  execution: ResolvedExecutionConfig;
  session: ResolvedSessionConfig;
  extensions: ResolvedExtensionConfig;
  host: ResolvedHostConfig;
}
```

### Factory 注入

```typescript
interface RuntimeFactories {
  createModelRuntime(config): ModelRuntime;
  createToolRuntime(config): ToolRuntime;
  createExecutionBackend(config): ExecutionBackend;
  createSessionRepository(config): SessionRepository;
}
```

测试替换 factory，不使用全局 singleton。

### 配置快照

每个 run 保存不可变 snapshot。运行中配置变化仅影响新 run，除非通过显式 model/toolset change entry。

## 资源生命周期

### Scope

```text
process scope: provider registry, plugin catalog
workspace scope: trust, LSP/MCP, repo index
session scope: transcript, memory view
run scope: abort, budget, model stream, tool tasks
turn scope: request, tool batch
```

### Dispose 顺序

通常逆序：

```text
stop accepting work
cancel runs
flush durable events
close tool processes
close MCP/LSP
close session/database
unregister plugins
close host server
```

### Leak 检测

监控：

- 未结束 model stream；
- 孤儿子进程；
- 未释放文件锁；
- 悬挂 approval；
- 未完成 event consumer；
- 未关闭 MCP connection；
- background task 无 owner。

## 测试 Harness

### In-memory Harness

```typescript
createTestHarness({
  model: new ScriptedModel([...]),
  tools: [fakeRead, fakeWrite],
  session: new InMemorySessionRepository(),
  clock: new FakeClock(),
  ids: new DeterministicIds(),
})
```

### Fault Injection

注入：

- stream 中断；
- 429/5xx；
- 参数 delta 损坏；
- tool timeout；
- session conflict；
- sandbox unavailable；
- plugin registration failure；
- host disconnect；
- crash after side effect before durable commit。

### Event Assertions

验证完整序列：

```text
RunStarted
ModelStarted
ToolCallReady
ApprovalRequested
ApprovalResolved
ToolStarted
ToolCompleted
ModelStarted
RunCompleted
```

### Recovery Test

在每个 durable boundary 后模拟崩溃，确认恢复不会重复副作用或丢失状态。

### Conformance Suite

所有 provider、tool backend、session store、host adapter 都应运行契约测试。

## 运维与诊断

### Diagnostic Snapshot

提供安全脱敏的运行快照：

```text
config versions
provider/model
active tools
policy/sandbox
session version
pending tasks
budget usage
extension list
event queue depth
last errors
```

### Health

区分：

- liveness；
- readiness；
- provider reachability；
- session store；
- execution backend；
- MCP/LSP；
- event delivery。

### Trace

层级：

```text
session span
  run span
    attempt span
      model span
      tool span
      approval span
      compaction span
      subagent span
```

### Cost Attribution

包含：

- 主模型；
- retry；
- fallback；
- compaction；
- memory extraction；
- subagent；
- embedding/rerank。

Pi 对 compaction usage 的持续完善说明隐式模型调用也必须计费归因。

## 反模式

1. Harness 是单个几千行类。
2. Kernel 直接 import provider SDK 和数据库。
3. 所有组件读取全局环境变量。
4. 事件总线没有 durable/ephemeral 区分。
5. UI 消费速度阻塞模型流。
6. 插件注册没有回滚。
7. Tool policy、approval 和 sandbox 合为一个布尔值。
8. Fallback 偷偷发生且不写 session。
9. Retry 层次混乱，导致重复副作用。
10. Cancel 只停止 UI，不停止工具子进程。
11. Session 只在最终成功时写入。
12. Background run 依赖客户端连接。
13. Subagent 与父 Agent 共用全部 mutable state。
14. Sandbox 初始化失败后静默执行宿主 shell。
15. 测试只 mock 最终文本，不验证事件和恢复。

## 实施蓝图

### V1：Headless Harness

```text
Kernel
ModelPort
ToolPort
EventRecorder
InMemorySession
CLI host
```

### V2：Durable Harness

```text
Semantic entries
SessionRepository
Checkpoint
Compaction
Retry taxonomy
Artifacts
```

### V3：Secure Harness

```text
Project trust
Policy engine
Approval
Sandbox backend
Resource locks
Audit trace
```

### V4：Extensible Harness

```text
Skills
Hooks
MCP/LSP
Plugin transactions
Custom providers
Host adapters
```

### V5：Distributed Harness

```text
Durable queue
Worker leases
Event projector
Multi-client sync
Subagent scheduler
Tenant isolation
Operations dashboard
```

## 项目启发来源

- Pi：headless loop、EventStream、AgentSession、通用 AgentHarness、resource loader、session tree、RPC/TUI 适配。
- Grok Build：Session/ChatState/Sampler actor、分层 sampler、permission decisions、folder trust、sandbox、路径级工具锁。
- OpenCode：server/client、message/part、event bus、durable projector、snapshot/patch/revert、permission、MCP/LSP。
- Claude Code：permission modes、hooks、skills、subagents、memory、MCP 和计划任务的完整产品 harness。
- OpenClaw：Harness registry、agent-core、Gateway/channel、provider runtime、tool/sandbox/elevated、事务化插件、后台运行与 memory。
