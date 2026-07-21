# 优秀 Agent 参考架构

> 调研日期：2026-07-20。
>
> 本文交叉研究了 `earendil-works/pi`、`xai-org/grok-build`、`anomalyco/opencode`、`claude-code-best/claude-code`、`openclaw/openclaw`。重点不是复制任一项目，而是提炼反复出现、可被源码验证的架构模式。

## 目录

1. [核心结论](#核心结论)
2. [五个项目的架构侧重点](#五个项目的架构侧重点)
3. [Agent Kernel 与 Harness](#agent-kernel-与-harness)
4. [参考分层架构](#参考分层架构)
5. [一次 Turn 的标准生命周期](#一次-turn-的标准生命周期)
6. [核心模块契约](#核心模块契约)
7. [状态与持久化](#状态与持久化)
8. [工具执行架构](#工具执行架构)
9. [上下文工程](#上下文工程)
10. [安全架构](#安全架构)
11. [扩展架构](#扩展架构)
12. [并发、取消与恢复](#并发取消与恢复)
13. [测试与可观测性](#测试与可观测性)
14. [常见反模式](#常见反模式)
15. [实施顺序](#实施顺序)
16. [源码依据](#源码依据)

## 核心结论

优秀 Agent 不是“一个 while 循环加几个 function”。其质量主要由模型外部的工程系统决定：

```text
Agent Quality
  = Model Capability
  × Context Quality
  × Tool Reliability
  × Policy Safety
  × State Durability
  × Harness Feedback
```

五个项目虽然产品形态不同，但反复出现以下共同点：

1. **模型协议先归一化。** Agent loop 不直接识别每家 API 的原始事件。
2. **核心 loop 保持 headless。** TUI、CLI、RPC、HTTP、聊天渠道只是适配器。
3. **Transcript 与 provider message 分离。** 应用状态比模型消息更丰富。
4. **工具执行是独立 runtime。** 定义、校验、授权、调度、执行和结果转换分层。
5. **事件是主接口，不是附加日志。** 文本、推理、工具、权限、usage 和完成状态都通过事件传播。
6. **长会话依赖显式 compaction。** 摘要、切点和 usage 应可恢复、可审计。
7. **项目可信、工具权限和 OS 隔离是三个不同问题。** 不能互相替代。
8. **Harness 决定 Agent 的实际能力边界。** Prompt 只是 harness 的一个组成部分。
9. **扩展代码通常等同可信宿主代码。** 若没有进程隔离，不应宣称插件安全。
10. **恢复能力必须从一开始设计。** 长任务不能只保存最终聊天文本。

## 五个项目的架构侧重点

| 项目 | 最值得学习的部分 | 主要取舍或风险 |
|---|---|---|
| Pi | 极小 headless agent loop、统一 provider event、session tree、可恢复 compaction、CLI/TUI/RPC 共用 runtime | 默认执行隔离较弱；扩展是宿主内可信代码；通用 harness 与产品实现存在双路线 |
| Grok Build | Rust actor 架构、采样器三层分离、明确 permission decision、并行工具与路径锁、folder trust、sandbox | 模块数量和状态机复杂；部分沙箱路径可能 fail-open；上下文修剪会丢失旧工具结果 |
| OpenCode | client/server 分离、session/message/part 数据模型、事件总线、durable event/projector、权限、snapshot/patch/revert、MCP/LSP | 新旧状态模型并行时迁移复杂；事件投影和分布式状态增加调试成本 |
| Claude Code | 权限模式、hooks、subagents、skills、memory、MCP、计划与任务工作流形成完整产品 harness | `claude-code-best/claude-code` 不是应被视为权威规范的官方源码；实现判断需与 Anthropic 官方文档交叉核对 |
| OpenClaw | AgentHarness registry、独立 agent-core、多渠道 Gateway、provider runtime、tool/sandbox/elevated 分层、事务化插件注册 | 单 Gateway 故障域较大；插件拥有进程权限；跨 channel/provider 的组合复杂度高 |

### 共同趋势

这些项目的演进方向不是继续扩大单个 `Agent` 类，而是把系统拆为：

```text
Protocol
Runtime
State
Policy
Tools
Context
Extensions
Host adapters
Operations
```

## Agent Kernel 与 Harness

### Agent Kernel

Agent Kernel 是最小可复用运行内核：

```text
input messages
  -> model stream
  -> normalized events
  -> tool calls
  -> tool results
  -> next model turn
  -> final result
```

Kernel 应负责：

- turn loop；
- provider-neutral message；
- tool-call/result 顺序；
- 最大步数；
- abort；
- stop reason；
- 核心生命周期事件。

Kernel 不应直接负责：

- TUI；
- 项目配置扫描；
- 密钥存储；
- Git 操作；
- SQLite/JSONL 具体格式；
- 用户确认 UI；
- 插件发现；
- 长期 memory；
- 云部署。

### Harness

Harness 是围绕 Kernel 的完整执行环境：

```text
Harness
  ├─ Bootstrap / configuration
  ├─ Prompt and context compiler
  ├─ Model/provider runtime
  ├─ Tool registry and executor
  ├─ Permission and approval
  ├─ Sandbox / execution environment
  ├─ Session / checkpoints / compaction
  ├─ Skills / hooks / plugins / MCP
  ├─ Event routing and UI adapters
  ├─ Retry / fallback / budgets
  └─ Tracing / testing / operations
```

**简化判断：**

- Kernel 回答“模型下一步做什么”；
- Harness 回答“它能看到什么、能做什么、在哪里做、谁批准、失败后如何恢复、结果如何交付”。

详细 harness 设计见 [agent-harness.md](agent-harness.md)。

## 参考分层架构

```text
┌─────────────────────────────────────────────────────────────┐
│  Host Adapters                                              │
│  CLI / TUI / IDE / HTTP / RPC / Gateway / Channel / Batch  │
├─────────────────────────────────────────────────────────────┤
│  Application Orchestrator                                   │
│  request routing / queue / fallback / subagent / delivery   │
├─────────────────────────────────────────────────────────────┤
│  Agent Kernel                                               │
│  turn loop / normalized events / tool loop / stop / abort   │
├───────────────────────┬─────────────────────────────────────┤
│  Context Runtime      │  Tool Runtime                       │
│  prompt/resources     │  registry/schema/dispatch/output    │
│  compaction/memory    │  timeout/idempotency/concurrency    │
├───────────────────────┼─────────────────────────────────────┤
│  Model Runtime        │  Policy & Execution Security        │
│  provider adapters    │  permission/approval/trust/sandbox  │
│  auth/retry/stream    │  path/network/process boundaries    │
├───────────────────────┴─────────────────────────────────────┤
│  Durable State & Event Backbone                             │
│  transcript / semantic entries / checkpoint / event log     │
│  projector / usage / trace / replay                         │
├─────────────────────────────────────────────────────────────┤
│  Extension Runtime                                          │
│  skills / hooks / plugins / MCP / LSP / custom providers    │
└─────────────────────────────────────────────────────────────┘
```

### 依赖方向

依赖应向内：

```text
Host -> Orchestrator -> Kernel -> Contracts
Infrastructure implements Contracts
```

Kernel 不导入 TUI、SQLite、AWS SDK 或具体 shell 实现。

### 推荐包边界

```text
packages/
  protocol/        # Message, Part, Event, ToolCall, Usage
  model-runtime/   # provider registry and adapters
  agent-core/      # headless loop
  tool-runtime/    # registry, policy, execution
  context-runtime/ # prompt, resource loading, compaction
  session/         # durable semantic transcript
  harness/         # assembly and lifecycle
  hosts/           # cli, tui, server, rpc, channels
  extensions/      # plugin SDK, MCP, skills, hooks
  testkit/         # fake provider, fixtures, replay
```

小项目可以合包，但保留逻辑边界。

## 一次 Turn 的标准生命周期

```text
1. Receive
2. Normalize
3. Restore/check session
4. Compile context
5. Build model request
6. Stream model events
7. Commit assistant item
8. Validate tool calls
9. Authorize/approve
10. Schedule and execute tools
11. Commit tool results
12. Continue or stop
13. Compact/checkpoint
14. Emit final delivery event
15. Settle listeners and resources
```

### 推荐状态机

```text
Idle
  -> Preparing
  -> Sampling
  -> WaitingForApproval | ExecutingTools | Finalizing
  -> Sampling                # tool result 后继续
  -> Compacting | Completed
  -> Failed | Cancelled
```

不要仅使用 `isRunning: boolean`。状态机使取消、恢复和 UI 更可靠。

### Commit 顺序

模型输出包含工具调用时：

1. 先提交完整 assistant 输出；
2. 再执行工具；
3. 每个结果关联原 call ID；
4. 再开始下一次采样。

不能只保存工具结果而丢弃提出调用的 assistant item。

## 核心模块契约

### Model Runtime

```typescript
interface ModelRuntime {
  stream(request: ModelRequest, signal: AbortSignal): AsyncIterable<ModelEvent>;
  resolveModel(ref: ModelRef): Promise<ResolvedModel>;
  capabilities(ref: ModelRef): Promise<ModelCapabilities>;
}
```

职责：

- provider registry；
- 认证；
- 模型解析；
- 原生事件归一化；
- 网络重试；
- usage 和 provider metadata。

### Agent Kernel

```typescript
interface AgentKernel {
  run(input: AgentInput, env: KernelEnvironment): AsyncIterable<AgentEvent>;
  continue(runId: string, env: KernelEnvironment): AsyncIterable<AgentEvent>;
  cancel(runId: string, reason?: string): Promise<void>;
}
```

### Tool Runtime

```typescript
interface ToolRuntime {
  list(context: ToolVisibilityContext): Promise<ToolDefinition[]>;
  prepare(call: ToolCall): Promise<PreparedToolCall>;
  execute(call: AuthorizedToolCall, signal: AbortSignal): AsyncIterable<ToolEvent>;
}
```

### Session Repository

```typescript
interface SessionRepository {
  load(id: string): Promise<SessionProjection>;
  append(id: string, entries: SessionEntry[], expectedVersion: number): Promise<number>;
  branch(id: string, fromEntry: string): Promise<SessionId>;
  checkpoint(id: string): Promise<Checkpoint>;
}
```

使用版本或 compare-and-swap，避免多进程静默覆盖。

### Policy Engine

```typescript
interface PolicyEngine {
  evaluate(request: ActionRequest): Promise<PolicyDecision>;
}

type PolicyDecision =
  | { type: "allow" }
  | { type: "ask"; prompt: ApprovalPrompt }
  | { type: "deny"; reason: string; recoverable: boolean }
  | { type: "transform"; action: ActionRequest };
```

若 policy 或 hook 修改参数，必须重新执行 schema 与业务校验。

## 状态与持久化

### 不要把 Provider Message 当数据库模型

Provider message 只表达模型调用需要的信息。Agent transcript 还需保存：

- session metadata；
- model/provider 变化；
- active tools；
- approval；
- compaction；
- branch summary；
- checkpoint；
- usage/cost；
- error/retry；
- attachment/resource reference；
- hook/plugin 结果；
- delivery status。

### 推荐 append-only semantic entries

```text
UserMessageEntry
AssistantMessageEntry
ToolResultEntry
ApprovalEntry
ModelChangeEntry
ToolsetChangeEntry
CompactionEntry
BranchSummaryEntry
CheckpointEntry
ErrorEntry
CustomEntry
```

优点：

- 审计；
- replay；
- branch；
- 崩溃恢复；
- projector 可重建不同视图；
- 不必反复覆盖完整 session。

Pi 的 session tree、OpenCode 的 durable event/projector 方向都说明：复杂 Agent 最终会从“聊天数组”演化为事件化状态。

### Durable Event 与 UI Event 分开

不是每个 token delta 都需要永久保存。

```text
Durable events: message completed, tool requested, approval, result, checkpoint
Ephemeral events: text delta, spinner, partial progress, heartbeat
```

## 工具执行架构

### 六段管线

```text
Discover
  -> Normalize
  -> Validate
  -> Authorize
  -> Execute
  -> Normalize Result
```

### 工具并发

默认规则：

- 只读、互不依赖工具可并行；
- 有副作用工具默认串行；
- 写同一文件或资源必须使用资源锁；
- 返回给模型的结果顺序保持原 tool-call 顺序；
- UI 完成事件可以按真实完成时间发出。

Pi 和 Grok Build 都体现了“执行并发、上下文顺序稳定”的价值；Grok Build 进一步对同一路径写入序列化。

### 输出预算

每个工具都应定义：

```text
max bytes
max lines/items
timeout
stream policy
redaction policy
artifact offload policy
```

大输出写入 artifact/file，只把摘要和引用回传模型。Grok Build 对工具和 MCP 输出设置上限，是防止上下文雪崩的重要实践。

## 上下文工程

### Context Compiler

上下文不应由字符串拼接散落在入口函数中。建立独立编译阶段：

```text
ContextPlan
  system policy
  persona
  project rules
  skills
  active tool descriptions
  memory retrieval
  recent conversation
  compaction summary
  attachments
  runtime facts
  token budget
```

### 资源优先级

推荐：

```text
system/product policy
  > organization policy
  > user global config
  > trusted workspace config
  > task-local resources
  > retrieved untrusted content
```

同时保存来源和 trust level。

### Compaction

优秀 compaction 需要：

- 预留输出和工具 token；
- 保留最近对话；
- 使用语义切点，避免切断 tool call/result；
- 摘要旧历史；
- 保存摘要、切点、模型、usage 和来源；
- 支持模型窗口变小后的重新压缩；
- 支持失败回退；
- 对关键事实保留结构化 state，而非只靠自然语言摘要。

Pi 把 compaction 写为可恢复 entry；Grok Build 使用预计算与同步压缩双通道；OpenClaw 在压缩前执行 memory flush。可组合为：

```text
structured checkpoint
  + background summary candidate
  + synchronous final compaction
  + durable compaction entry
```

## 安全架构

### 四层安全边界

```text
1. Visibility: 模型是否看得到工具
2. Policy: 当前调用是否允许
3. Approval: 是否需要用户确认
4. Sandbox: 即使允许，操作能影响什么
```

OpenClaw 明确区分 tool policy、sandbox、elevated；Grok Build 区分 folder trust、permission decision、sandbox。这比单一 `allowTools` 更可靠。

### Project Trust

仓库中的配置、hooks、MCP、插件、`.envrc` 都可能执行代码。未信任项目应：

- 不加载项目插件；
- 不启动项目 MCP/LSP；
- 不执行 hooks；
- 不读取会改变行为的本地配置；
- 在非交互环境默认拒绝，而不是自动信任。

### Sandbox

生产安全敏感场景应 fail-closed：

```text
sandbox unavailable
  -> refuse dangerous execution
```

不要像部分示例实现那样静默回退到宿主 shell。

### 插件信任

进程内 TypeScript/Python/Rust 动态插件拥有宿主能力。若要加载第三方不可信插件，需要：

- 独立进程或容器；
- capability-based RPC；
- 签名和来源记录；
- 超时、资源限制；
- 崩溃隔离；
- 注册事务和回滚。

OpenClaw 的事务化插件注册适合解决失败污染，但不能阻止恶意插件。

## 扩展架构

### 扩展点应按阶段定义

```text
bootstrap
resource_discovery
context_compile
before_model
model_event
before_tool
approval
before_execute
tool_event
after_tool
turn_complete
session_compact
session_close
```

每个 hook 明确：

- 是否可修改输入；
- 是否可阻断；
- 顺序；
- 超时；
- 错误策略；
- 是否需要重新校验；
- 是否 durable。

### 扩展贡献类型

```text
tool
provider
skill
prompt/resource
hook
host adapter
channel
memory source
context engine
sandbox backend
observability exporter
agent harness
```

### 注册事务

插件加载：

```text
snapshot
  -> register contributions
  -> validate conflicts
  -> commit
failure
  -> reverse rollback
```

这是 OpenClaw 很有价值的模式。

## 并发、取消与恢复

### Structured Concurrency

每次 run 创建生命周期作用域：

```text
RunScope
  model stream task
  tool tasks
  approval wait
  background compaction
  event consumers
```

取消 run 时，所有子任务都接收同一个取消信号，并等待 settle。

### Actor 适用场景

像 Grok Build 一样，当系统存在高并发状态写入时，可把以下组件建成 actor：

- SessionActor；
- ChatStateActor；
- SamplerActor；
- ToolExecutionActor。

Actor 适合串行化状态所有权，但跨 actor 事务仍需显式协议和补偿。

### 恢复所需信息

```text
last durable entry
pending approval
in-flight tool with idempotency key
completed tool results
current model/toolset
compaction checkpoint
retry/fallback state
```

启动时不要盲目重放状态未知的写操作。

## 测试与可观测性

### 测试重点

优秀项目反复测试的是边界，不只是最终答案：

- provider stream 转换；
- 事件顺序；
- tool arguments 被拆分；
- `length` 截断时不执行不完整调用；
- 串行/并行调度；
- abort；
- hook block/transform；
- compaction 切点；
- branch/replay；
- permission decision；
- sandbox deny；
- plugin rollback；
- RPC/SSE framing；
- fallback 和 usage 归因。

### Testkit

提供：

```text
FakeModelProvider
ScriptedModelStream
FakeToolRuntime
InMemorySessionRepository
DeterministicClock
DeterministicIdGenerator
EventRecorder
CrashInjector
ReplayRunner
```

### Observability

每个 run 应有：

```text
trace_id
run_id
session_id
turn_id
model_request_id
tool_call_id
approval_id
provider/model/api_family
latency and queue time
usage/cost/cache
retry/fallback
compaction usage
sandbox/policy decision
extension contribution
```

## 常见反模式

1. 一个巨型 `Agent` 类同时处理 API、工具、UI、磁盘和权限。
2. 把 provider messages 直接保存为唯一 session 数据。
3. 流式接口只返回字符串。
4. 工具 hook 修改参数后不重新校验。
5. 所有工具无差别并行。
6. 工具输出不设上限。
7. 项目信任被误认为执行沙箱。
8. 沙箱失败时静默回退到宿主执行。
9. 插件加载失败后留下半注册状态。
10. compaction 静默删除历史，无法审计或恢复。
11. 只测试最终文本，不测试事件和失败状态。
12. 为适配所有 provider 构建“最低公分母”，导致特有能力全部丢失。
13. 复杂产品长期维护两套 session/harness 而没有迁移边界。
14. Subagent 只是递归调用同一 prompt，没有预算、隔离、结果契约和取消传播。

## 实施顺序

### 第一阶段：可验证内核

1. protocol；
2. scripted fake provider；
3. headless loop；
4. tool schema 与执行；
5. event recorder；
6. 单元测试。

### 第二阶段：可恢复 Harness

1. semantic transcript；
2. session repository；
3. checkpoint；
4. compaction；
5. retry/fallback；
6. CLI/RPC adapter。

### 第三阶段：安全执行

1. policy engine；
2. approvals；
3. project trust；
4. sandbox backend；
5. output budgets；
6. audit trace。

### 第四阶段：扩展与规模化

1. skills/hooks；
2. MCP/LSP；
3. plugin transaction；
4. subagents；
5. server/channels；
6. durable event/projector；
7. distributed workers。

## 源码依据

### Pi

- https://github.com/earendil-works/pi/blob/main/packages/agent/src/agent-loop.ts
- https://github.com/earendil-works/pi/blob/main/packages/agent/src/harness/agent-harness.ts
- https://github.com/earendil-works/pi/blob/main/packages/agent/src/harness/session/session.ts
- https://github.com/earendil-works/pi/blob/main/packages/agent/src/harness/compaction/compaction.ts
- https://github.com/earendil-works/pi/blob/main/packages/ai/src/utils/event-stream.ts
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/agent-session.ts

### Grok Build

- https://github.com/xai-org/grok-build/tree/main/crates/codegen/xai-grok-shell/src/session
- https://github.com/xai-org/grok-build/tree/main/crates/codegen/xai-grok-sampler/src
- https://github.com/xai-org/grok-build/tree/main/crates/codegen/xai-grok-tools/src
- https://github.com/xai-org/grok-build/tree/main/crates/codegen/xai-grok-sandbox/src

### OpenCode

- https://github.com/anomalyco/opencode/tree/dev/packages/opencode/src/session
- https://github.com/anomalyco/opencode/tree/dev/packages/opencode/src/tool
- https://github.com/anomalyco/opencode/tree/dev/packages/opencode/src/permission
- https://github.com/anomalyco/opencode/tree/dev/packages/opencode/src/provider
- https://github.com/anomalyco/opencode/tree/dev/packages/opencode/src/server

### Claude Code

- https://github.com/claude-code-best/claude-code
- https://docs.anthropic.com/en/docs/claude-code/overview

`claude-code-best/claude-code` 仅作为结构研究的辅助材料。Claude Code 的公开能力和安全语义应以 Anthropic 官方文档为准。

### OpenClaw

- https://github.com/openclaw/openclaw/blob/main/packages/agent-core/src/agent-loop.ts
- https://github.com/openclaw/openclaw/blob/main/src/agents/harness/registry.ts
- https://github.com/openclaw/openclaw/blob/main/src/agents/openclaw-tools.ts
- https://github.com/openclaw/openclaw/blob/main/packages/llm-core/src/types.ts
- https://github.com/openclaw/openclaw/blob/main/src/plugins/api-builder.ts
- https://github.com/openclaw/openclaw/blob/main/src/plugins/loader-runtime-load.ts
- https://github.com/openclaw/openclaw/blob/main/docs/gateway/sandbox-vs-tool-policy-vs-elevated.md
