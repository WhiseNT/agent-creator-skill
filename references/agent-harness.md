# Agent Harness 设计指南

> Harness 不是系统提示词的同义词。它是让模型在特定环境中可靠工作的完整控制系统。

## 目录

1. [定义](#定义)
2. [Harness 的十一层](#harness-的十一层)
3. [Harness 输入与输出](#harness-输入与输出)
4. [装配流程](#装配流程)
5. [Prompt Harness](#prompt-harness)
6. [Tool Harness](#tool-harness)
7. [State Harness](#state-harness)
8. [Execution Harness](#execution-harness)
9. [Feedback Harness](#feedback-harness)
10. [Subagent Harness](#subagent-harness)
11. [Extension Harness](#extension-harness)
12. [Harness 配置模型](#harness-配置模型)
13. [Harness 质量清单](#harness-质量清单)
14. [按产品类型裁剪](#按产品类型裁剪)

## 定义

一个有效 Harness 应明确回答：

```text
模型是谁？
它当前在做什么？
它能看到什么？
它能调用什么？
谁允许它调用？
工具在哪里执行？
执行结果如何反馈？
上下文不够时如何压缩？
失败时如何重试或恢复？
状态如何保存？
事件如何展示和审计？
扩展如何加载与隔离？
```

可将 Harness 看成 Agent Kernel 的依赖注入容器、策略层、资源编译器和运行监督器。

## Harness 的十一层

### 1. Identity Harness

定义：

- system policy；
- persona；
- 任务目标；
- 行为边界；
- 输出契约；
- 当前日期、平台、工作目录等运行事实。

避免把不可信检索内容拼入同一权威 system block。

### 2. Context Harness

负责发现、排序、筛选和预算：

- global/project rules；
- AGENTS.md / CLAUDE.md；
- skills；
- memory；
- prompt templates；
-文件和附件；
- 检索结果；
- session history；
- compaction summary。

输出应是结构化 `ContextPlan`，而不是直接返回巨型字符串。

### 3. Model Harness

负责：

- provider/model 解析；
- credential；
- API family；
- capability detection；
- stream 归一化；
- retry；
- fallback；
- usage/cost。

Pi、Grok Build、OpenClaw 都把 provider 原始协议转换为内部事件后再交给 loop。

### 4. Tool Harness

负责：

- 工具发现；
- schema；
- 动态可见性；
- 参数校验；
- policy；
- approval；
- 调度；
- output truncation；
- artifact offload；
- 结果标准化。

### 5. Execution Harness

定义工具执行环境：

- host；
- sandbox；
- container；
- VM；
- remote worker；
- browser；
- code interpreter；
- network policy；
- filesystem mapping。

工具名称相同不代表执行环境相同。

### 6. State Harness

保存：

- transcript；
- semantic entries；
- branch；
- checkpoint；
- pending approval；
- tool idempotency；
- active model/tools；
- compaction；
- retry/fallback；
- delivery state。

### 7. Control Harness

限制自主运行：

- max turns；
- max tool calls；
- wall-clock timeout；
- token/cost budget；
- recursion/subagent depth；
- duplicate/doom-loop detection；
- cancellation；
- human intervention。

### 8. Extension Harness

加载：

- skills；
- hooks；
- plugins；
- MCP；
- LSP；
- custom provider；
- custom tools；
- host/channel adapter。

扩展来源必须带 trust 和 provenance。

### 9. Feedback Harness

把内部事件变成模型、用户和系统可消费的反馈：

- 模型看到 tool result；
- 用户看到进度、diff、审批和结果；
- UI 看到流式 delta；
- 运维看到 trace、usage 和错误；
- 恢复器看到 checkpoint。

### 10. Evaluation Harness

提供：

- fake provider；
- scripted tool；
- event assertions；
- replay；
- fault injection；
-安全案例；
- benchmark；
- regression fixtures。

### 11. Delivery Harness

负责结果交付：

- terminal output；
- IDE patch；
- HTTP response；
- chat message；
- PR/commit；
- artifact；
- background notification。

OpenClaw 的 channel/gateway 架构说明：交付不是简单 `print(finalText)`，而是独立产品层。

## Harness 输入与输出

### HarnessSpec

```typescript
interface HarnessSpec {
  identity: IdentitySpec;
  model: ModelSelection;
  context: ContextPolicy;
  tools: ToolPolicy;
  execution: ExecutionPolicy;
  session: SessionPolicy;
  control: ControlBudget;
  extensions: ExtensionPolicy;
  observability: ObservabilityPolicy;
  delivery: DeliveryPolicy;
}
```

### HarnessRun

```typescript
interface HarnessRun {
  runId: string;
  sessionId: string;
  input: AgentInput;
  environment: ExecutionEnvironment;
  signal: AbortSignal;
}
```

### HarnessResult

```typescript
interface HarnessResult {
  status: "completed" | "failed" | "cancelled" | "waiting_for_approval";
  output?: AgentOutput;
  checkpoint?: Checkpoint;
  usage: Usage;
  artifacts: ArtifactRef[];
  diagnostics: Diagnostic[];
}
```

事件流与最终结果应同时存在：

```typescript
interface RunningHarness {
  events: AsyncIterable<HarnessEvent>;
  result: Promise<HarnessResult>;
  cancel(reason?: string): void;
}
```

这与 Pi/OpenClaw 的 `EventStream + final result` 思路一致。

## 装配流程

```text
1. Parse host request
2. Resolve workspace and trust
3. Load global resources
4. Conditionally load trusted project resources
5. Resolve model and credentials
6. Build tool catalog
7. Apply visibility policy
8. Resolve execution backends
9. Restore/create session
10. Build context plan
11. Create run scope and event bus
12. Start kernel
13. Supervise retries, approvals and compaction
14. Deliver result
15. Persist settlement and close resources
```

### 两阶段资源加载

学习 Pi/Grok Build 的 project trust：

```text
Phase A: safe bootstrap
  only user/global built-ins

Phase B: trusted workspace
  project hooks/plugins/MCP/LSP/config
```

在信任判断前不要执行项目代码。

## Prompt Harness

Prompt Harness 应动态编译，而不是维护一个不断膨胀的固定 prompt。

### 推荐组成

```text
System policy
Role and objective
Environment facts
Active tools and constraints
Project instructions
Relevant skills
Retrieved context
Current task state
Output contract
```

### 动态工具提示

只描述当前可见工具。若 read-only 模式不提供 edit/bash，就不要在 prompt 中解释它们。

### 来源标记

每个资源保存：

```text
source
scope
trust level
priority
estimated tokens
loaded timestamp/version
```

### Prompt 与代码策略分离

例如“删除操作必须确认”应由 policy engine 强制，prompt 只负责向模型解释原因。不能只靠文字约束。

## Tool Harness

### ToolSpec

```typescript
interface ToolSpec<I, O> {
  name: string;
  description: string;
  inputSchema: JsonSchema;
  outputSchema?: JsonSchema;
  effect: "read" | "write" | "external" | "destructive";
  concurrency: "parallel" | "serial" | "resource-locked";
  timeoutMs: number;
  outputBudget: OutputBudget;
  approval: ApprovalPolicy;
  executor: ToolExecutor<I, O>;
}
```

### 执行管线

```text
model ToolCall
  -> normalize arguments
  -> schema validation
  -> business validation
  -> before-tool hooks
  -> re-validation if changed
  -> policy decision
  -> optional approval
  -> acquire resource lock
  -> execute in selected backend
  -> stream progress
  -> redact/truncate/offload
  -> after-tool hooks
  -> normalize ToolResult
  -> append durable result
```

### ToolResult

```typescript
interface ToolResult {
  callId: string;
  status: "success" | "error" | "denied" | "cancelled";
  content: ContentPart[];
  artifacts?: ArtifactRef[];
  error?: {
    code: string;
    message: string;
    retryable: boolean;
  };
  metadata?: Record<string, unknown>;
}
```

不要向模型暴露完整内部异常、密钥或宿主路径。

## State Harness

### Session 与 Run

- Session：长期对话/任务容器；
- Run：一次可取消、可恢复的执行；
- Turn：一次模型采样和后续工具批次；
- Attempt：某 provider/model 下的一次尝试。

不要混用 ID。

### 推荐层级

```text
Session
  Branch
    Run
      Attempt
        Turn
          Message/Tool entries
```

### Projector

从 durable entries 投影：

- 模型上下文；
- TUI transcript；
- usage report；
- pending approvals；
- active model/toolset；
- recovery state。

OpenCode 的 durable event/projector 方向适合需要 server、多客户端同步和 replay 的产品。

### Compaction Entry

```typescript
interface CompactionEntry {
  coveredFrom: EntryId;
  coveredTo: EntryId;
  summary: ContentPart[];
  structuredState?: Record<string, unknown>;
  modelRef: ModelRef;
  usage: Usage;
  sourceHash: string;
}
```

`sourceHash` 可防止复用已失效的后台摘要。

## Execution Harness

### Backend

```typescript
interface ExecutionBackend {
  capabilities(): ExecutionCapabilities;
  run(request: ExecutionRequest, signal: AbortSignal): AsyncIterable<ExecutionEvent>;
  dispose(): Promise<void>;
}
```

后端示例：

- LocalHostBackend；
- SandboxBackend；
- ContainerBackend；
- VmBackend；
- RemoteWorkerBackend；
- BrowserBackend。

### 三个不同开关

```text
tool visible?
action authorized?
execution isolated?
```

不能合成一个 `dangerousMode`。

### Elevated 通道

高权限执行应是显式 backend 或 capability，不能通过给普通 shell 临时添加参数实现。

## Feedback Harness

### 标准事件

```text
RunStarted
ContextCompiled
ModelRequestStarted
TextDelta
ReasoningDelta
ToolCallStarted
ToolArgumentsDelta
ToolCallReady
ApprovalRequested
ApprovalResolved
ToolExecutionStarted
ToolProgress
ToolExecutionCompleted
UsageUpdated
CompactionStarted
CompactionCompleted
AttemptFailed
FallbackSelected
RunCompleted
RunFailed
RunCancelled
```

### 多消费者

同一事件总线可连接：

- TUI/IDE；
- RPC/SSE/WebSocket；
- transcript projector；
- tracing exporter；
- audit log；
- testing recorder。

消费者错误不应默认杀死 Kernel，但 durable state consumer 的失败必须被监督。

### Backpressure

工具和模型可能快速产生事件。明确：

- bounded queue；
- drop/coalesce policy；
- durable event 不可丢；
- text delta 可合并；
- slow UI 不应阻塞模型网络读取到超时。

## Subagent Harness

Subagent 不是简单递归调用。

### SubagentSpec

```typescript
interface SubagentSpec {
  objective: string;
  inputArtifacts: ArtifactRef[];
  allowedTools: string[];
  modelPolicy: ModelSelection;
  contextPolicy: ContextPolicy;
  budget: ControlBudget;
  executionIsolation: ExecutionPolicy;
  resultSchema: JsonSchema;
}
```

### 必要机制

- 父子 run 关联；
- 独立预算；
- 工具和文件边界；
- 取消传播；
- 输出结构；
- 并发上限；
- 结果去重与合并；
- 子 agent trace 不污染主对话；
- 失败是否局部可恢复。

Grok Build 的独立 harness trace、Claude Code 的 subagent 产品能力、Pi 的 steering/follow-up 都表明：并行自主工作需要独立上下文和结果契约。

### 适合委派

- 大型代码库分区调查；
- 可独立实现的模块；
- 并行测试；
- 多来源研究；
- reviewer/critic；
- 长时间后台任务。

不适合：

- 共享同一未加锁文件的并行编辑；
- 强顺序依赖的小步骤；
- 需要持续共享隐式上下文的任务。

## Extension Harness

### Skills

Skill 主要提供工作流知识和资源导航。它不等于强制安全策略。

### Hooks

Hook 应声明能力：

```text
observe only
transform
block
execute side effect
```

默认限制 hook 的执行时间，记录来源。

### MCP

MCP server 属于外部工具提供者。需要：

- server provenance；
- 启动命令信任；
- auth refresh；
- tool snapshot；
- output budget；
- connection lifecycle；
- server crash/reconnect；
- schema/version drift；
- per-tool policy。

### Plugin

插件注册使用事务：

```text
begin
register
validate
commit
or rollback in reverse order
```

插件 unload 时撤销全部全局副作用。

## Harness 配置模型

推荐分层配置：

```text
built-in defaults
  < organization policy
  < user global settings
  < trusted workspace settings
  < session settings
  < run overrides
```

安全上限不能被低层覆盖。例如组织禁止宿主 shell 时，workspace 不能重新开启。

### 配置快照

每次 run 保存解析后的配置摘要和版本：

```text
model ref
visible tools
policy version
sandbox profile
resource hashes
extension versions
context compiler version
```

恢复时才能解释行为差异。

## Harness 质量清单

### 架构

- [ ] Kernel 无 UI、磁盘和具体 provider 依赖
- [ ] transcript 与 provider messages 分离
- [ ] provider 原始事件被归一化但未丢失 metadata
- [ ] host adapter 可替换
- [ ] 扩展点有明确生命周期

### 工具

- [ ] 参数在最终执行边界校验
- [ ] hook 修改后重新校验
- [ ] 有副作用工具有幂等策略
- [ ] 工具输出有预算
- [ ] 并行工具有资源锁
- [ ] tool result 关联 call ID

### 安全

- [ ] project trust、policy、approval、sandbox 分离
- [ ] 未信任 workspace 不加载可执行配置
- [ ] 沙箱失败策略明确
- [ ] 插件来源可追溯
- [ ] 敏感日志脱敏
- [ ] 高风险动作有人工确认

### 状态

- [ ] append-only 或等价的可审计持久化
- [ ] 支持 crash recovery
- [ ] pending approval 可恢复
- [ ] compaction 可审计
- [ ] branch/checkpoint 语义明确
- [ ] 并发写入有版本控制

### 控制

- [ ] max turns/tool calls/time/token/cost
- [ ] abort 传播到模型和工具
- [ ] doom-loop/duplicate 检测
- [ ] retry 与 fallback 分离
- [ ] 未知执行结果的写操作不盲目重放

### 反馈与测试

- [ ] 结构化事件而非字符串流
- [ ] usage 包括 retry、fallback、compaction、subagent
- [ ] 有 fake provider 和 event recorder
- [ ] 测试截断 tool call
- [ ] 测试取消、审批和恢复
- [ ] 测试插件注册失败回滚
- [ ] 测试 sandbox deny

## 按产品类型裁剪

### 简单业务 Agent

需要：

- Kernel；
- provider adapter；
-少量工具；
- schema/policy；
- session；
- event stream；
- tests。

通常不需要插件、MCP、分支、subagent 或复杂 sandbox。

### Coding Agent CLI

增加：

- project trust；
- 文件/shell 工具；
- diff/snapshot/revert；
- compaction；
- skills/project rules；
- TUI/RPC；
- sandbox；
- LSP/MCP；
- branch/session tree。

### Multi-channel Personal Agent

增加：

- Gateway；
- channel adapters；
- identity routing；
- session key policy；
- delivery retries；
- long-term memory；
- scheduler/background jobs；
- plugin lifecycle；
- channel-specific capabilities。

OpenClaw 是该类型的典型参考。

### Enterprise Agent Platform

增加：

- durable event log/projector；
- distributed worker；
- tenancy；
- IAM/OBO；
- policy service；
- secrets service；
- artifact storage；
- evaluation；
- tracing；
- deployment/versioning；
- data residency；
- admin governance。
