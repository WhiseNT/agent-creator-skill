# Agent Tool Engineering 详细设计
> Tool Engineering 负责把模型提出的工具调用转换为可发现、可校验、可授权、可调度、可执行、可恢复、可审计的工程动作。工具调用是协议，不是自动执行许可。
>
> 核心边界：Prompt 只解释工具用途与策略；Harness、Policy、Scheduler、Execution Backend 与 Sandbox 才负责强制执行。
## 目录
1. [设计目标](#设计目标)；2. [职责边界](#职责边界)；3. [模块架构](#模块架构)；4. [核心数据模型](#核心数据模型)；5. [工具定义与 Schema](#工具定义与-schema)；6. [Registry 与注册事务](#registry-与注册事务)；7. [Discovery、Visibility 与 Toolset Snapshot](#discoveryvisibility-与-toolset-snapshot)；8. [Tool Call 增量组装](#tool-call-增量组装)。
9. [Normalization 与 Validation](#normalization-与-validation)；10. [准备阶段与决策边界](#准备阶段与决策边界)；11. [Scheduler](#scheduler)；12. [串行、并行与资源锁](#串行并行与资源锁)；13. [幂等、去重与未知结果](#幂等去重与未知结果)；14. [执行生命周期](#执行生命周期)；15. [Progress 与事件协议](#progress-与事件协议)；16. [Result、Artifact 与输出预算](#resultartifact-与输出预算)。
17. [Remote 与 MCP Tools](#remote-与-mcp-tools)；18. [Provider、Host 与 Harness 集成](#providerhost-与-harness-集成)；19. [版本与兼容](#版本与兼容)；20. [错误分类、重试与恢复](#错误分类重试与恢复)；21. [安全边界](#安全边界)；22. [可观测性](#可观测性)；23. [测试与 Conformance](#测试与-conformance)；24. [反模式](#反模式)。
25. [实施清单](#实施清单)；26. [五个参考项目的启发来源](#五个参考项目的启发来源)。
## 设计目标
Tool Runtime 应满足：
- **协议正确**：完整处理多调用、流式参数、call ID 和 provider finish 语义；**定义稳定**：工具名称、schema、效果声明和版本可追踪；**默认不信任**：模型生成的名称、参数、路径、URL、命令和资源 ID 都是不可信输入；**职责分层**：发现、可见性、校验、授权、审批、调度、执行和结果转换互不替代；**并发可控**：只读独立调用可并行，副作用和共享资源调用受锁与顺序约束；**副作用可恢复**：幂等键、执行记录和 unknown outcome 可用于崩溃恢复；**输出有界**：工具结果可摘要、截断、脱敏并卸载到 artifact；**扩展可撤销**：插件、workspace 与 MCP 工具使用注册事务和来源记录。
- **Provider-neutral**：Kernel 只处理内部 ToolCall/ToolResult，不依赖某家 SDK；**可审查**：每个决策和状态变化都能由事件、快照和 trace 解释；**可测试**：registry、assembler、validator、scheduler、backend 均有契约测试。
质量目标可表达为：
```text
Tool Reliability
  = Protocol Correctness
  × Validation Strength
  × Policy Enforcement
  × Execution Isolation
  × Recovery Safety
  × Result Quality
```
任一乘项接近零，工具越多只会扩大故障面。
## 职责边界
### Tool Engineering 负责
- 工具定义和 schema 契约；registry、命名冲突与版本选择；工具发现、来源和动态可见性；provider tool-call 事件的增量组装；参数规范化、schema 校验和业务校验；调度、并发、资源锁、超时和取消；幂等、重复调用检测和执行状态查询；progress、result、artifact 与错误标准化。
- local、remote、MCP 工具统一适配；工具运行 trace、指标和 conformance suite。
### Tool Engineering 不独自负责
- 模型如何选择工具：Prompt 可引导，但不能保证；某次动作是否获准：由 Policy/Approval 决定；OS 级文件、网络、进程隔离：由 Sandbox/Execution Backend 强制；session durable commit：由 State Harness 协调；provider 原始流读取：由 Model Runtime 完成；用户界面与审批交互：由 Host Adapter 完成；整个 Agent turn loop：由 Kernel 和 Run Supervisor 控制。
### 强制原则
```text
Prompt explains when and why to use a tool.
Schema constrains structural shape.
Validator constrains semantic validity.
Policy decides whether the action is allowed.
Approval records human consent when required.
Sandbox limits what execution can affect.
Harness supervises lifecycle and recovery.
```
不能用更详细的工具描述替代任何代码边界。
## 模块架构
```text
Provider Stream
  -> ToolCallAssembler
  -> ToolCallNormalizer
  -> ToolRegistry.resolve
  -> ToolValidator
  -> HookRunner.beforeTool
  -> ToolValidator.revalidate
  -> Policy/Approval
  -> ToolScheduler
  -> ResourceLockManager
  -> ExecutionBackend / RemoteTransport
  -> ToolResultNormalizer
  -> Redaction / Budget / ArtifactStore
  -> Session commit
  -> Provider result adapter
```
### 推荐模块
```text
tool-runtime/
  contracts.ts
  definition.ts
  registry.ts
  discovery.ts
  visibility.ts
  assembler.ts
  normalization.ts
  validation.ts
  preparation.ts
  scheduler.ts
  locks.ts
  idempotency.ts
  executor.ts
  progress.ts
  result.ts
  artifacts.ts
  errors.ts
  versioning.ts
  remote/
  mcp/
  testkit/
```
### 依赖方向
```text
Kernel -> ToolPort -> ToolRuntime contracts
ToolRuntime -> PolicyPort / ExecutionPort / StatePort
Adapters implement provider, host, MCP and backend contracts
```
Tool Runtime 不应导入具体 TUI、数据库 schema 或 provider SDK 类型。
## 核心数据模型
### ToolSpec
```typescript
interface ToolSpec<I = unknown, O = unknown> {
  identity: ToolIdentity; description: string; inputSchema: JsonSchema; outputSchema?: JsonSchema; semantics: ToolSemantics; execution: ToolExecutionSpec; result: ToolResultSpec;
  compatibility: ToolCompatibility; provenance: ToolProvenance; executor: ToolExecutor<I, O>;
}
```
### ToolIdentity
```typescript
interface ToolIdentity {
  name: string; version: string; namespace?: string; aliases?: string[]; stableId: string;
}
```
`name` 是暴露给模型的稳定协议名；`stableId` 是内部身份，不应随展示别名变化。
### ToolSemantics
```typescript
interface ToolSemantics {
  effect: "read" | "write" | "external" | "destructive"; repeatability: "repeatable" | "idempotent" | "non_repeatable"; determinism: "deterministic" | "environment_dependent" | "nondeterministic"; confidentiality: "public" | "internal" | "confidential" | "secret"; riskTags: string[];
}
```
### ToolExecutionSpec
```typescript
interface ToolExecutionSpec {
  mode: "parallel" | "serial" | "resource_locked" | "exclusive" | "background"; timeoutMs: number; cancellation: "cooperative" | "process" | "unsupported"; backendSelector: BackendSelector; retryPolicy: ToolRetryPolicy; idempotencyPolicy: IdempotencyPolicy; resourceKeys?: ResourceKeyResolver;
}
```
### ToolResultSpec
```typescript
interface ToolResultSpec {
  outputBudget: OutputBudget; redactionPolicy: RedactionPolicy; artifactPolicy: ArtifactPolicy; modelProjection: "full" | "summary" | "structured" | "artifact_ref";
}
```
### ToolCall
```typescript
interface ToolCall {
  callId: string; name: string; rawArguments: string | unknown; source: ToolCallSource; providerMetadata?: Record<string, unknown>;
}
```
### PreparedToolCall
```typescript
interface PreparedToolCall {
  call: ToolCall; spec: ToolSpec; normalizedArguments: unknown; validatedArguments: unknown; fingerprint: string; businessIdempotencyKey?: string; resourceKeys: string[];
  risk: RiskAssessment; backend: ResolvedExecutionBackend; preparationVersion: string;
}
```
### AuthorizedToolCall
```typescript
interface AuthorizedToolCall extends PreparedToolCall {
  policyDecisionId: string; approvalId?: string; authorizationSnapshot: AuthorizationSnapshot;
}
```
### ToolResult
```typescript
interface ToolResult {
  callId: string; toolStableId: string; status: "success" | "error" | "denied" | "cancelled" | "unknown"; content: ContentPart[]; structured?: unknown; artifacts: ArtifactRef[]; error?: ToolErrorView;
  metadata: ToolResultMetadata;
}
```
## 工具定义与 Schema
### 定义必须包含的事实
每个工具至少声明：
- 稳定名称与内部 stable ID；面向模型的简洁描述；输入 JSON Schema；可选输出 schema；副作用等级；并发模式；超时与取消能力；幂等和重试策略。
- backend 要求；输出预算、脱敏和 artifact 策略；来源、版本和信任等级。
### 名称规则
工具名称应：
- 动词开头；语义单一；在同一 toolset 内唯一；不包含用户 ID、文件路径等动态值；不把版本号放进日常名称；避免 `search`、`find_text`、`lookup` 等近义重复；兼容目标 provider 的名称字符限制。
Provider 对名称有限制时，由 adapter 生成可逆映射，而不是改变内部身份。
### Description 规则
Description 回答：
1. 工具做什么；2. 何时使用；3. 何时不要使用；4. 关键副作用和限制是什么。
类型、required、enum 放入 schema；权限、路径边界和金额上限必须由代码校验。
### Schema 规则
- 使用明确 `type`；对象字段声明 `required`；默认拒绝未知字段，除非兼容策略允许；enum 应稳定且有语义；数值声明范围；字符串声明长度、格式或 pattern；嵌套深度和数组长度设上限；不依赖 provider 未支持的 JSON Schema 关键字。
- schema 编译失败应在注册期暴露，而不是调用期才发现。
### Provider Schema Projection
```typescript
interface ToolSchemaProjector {
  project(spec: ToolSpec, capabilities: ModelCapabilities): ProjectedToolDefinition;
}
```
投影器负责：
- 转换到 provider 支持的 schema 子集；保留内部 canonical schema；记录被降级或删除的约束；对不可安全降级的 schema 拒绝暴露；生成 projection hash。
本地最终校验永远使用 canonical schema，不能只信 provider strict 模式。
## Registry 与注册事务
### ToolRegistry
```typescript
interface ToolRegistry {
  register(spec: ToolSpec): RegistrationHandle;
  resolve(ref: ToolRef, context: ToolResolutionContext): Promise<ResolvedTool>;
  list(query: ToolRegistryQuery): Promise<ToolRecord[]>;
  snapshot(): ToolRegistrySnapshot;
}
```
### 注册来源
```text
built-in
user-global
trusted-workspace
plugin
MCP
session-scoped
host-contributed
```
每个来源都要保存 provenance、trust、scope 和 registration owner。
### 冲突策略
同名冲突不得静默后者覆盖前者。可选策略：
- stable ID 相同且兼容：升级为新版本；namespace 不同：通过显式别名解析；同名不同语义：拒绝注册；workspace 尝试覆盖 built-in：按组织策略拒绝或隔离 namespace；provider 名称投影冲突：生成 diagnostic 并隐藏冲突项。
### 注册事务
```text
begin snapshot
  -> register candidate definitions
  -> compile schemas
  -> validate names and aliases
  -> resolve conflicts
  -> validate backend availability
  -> validate policy references
  -> commit snapshot
failure
  -> dispose handles in reverse order
  -> restore previous snapshot
```
插件和 MCP 部分注册成功后失败，不能留下半个 active toolset。
### Registry Snapshot
```typescript
interface ToolRegistrySnapshot {
  version: string; records: ToolRecordSnapshot[]; hash: string; createdAt: string;
}
```
Run 使用不可变 snapshot；运行中的动态变化通过显式 ToolsetChangeEntry 生效。
## Discovery、Visibility 与 Toolset Snapshot
### Discovery 与 Visibility 分开
- Discovery：系统知道某工具存在；Visibility：模型当前是否看到该工具；Call policy：即使可见，某个参数化动作是否允许；Execution capability：即使允许，backend 是否真正能执行。
### Discovery Pipeline
```text
load built-ins
  -> inspect trusted extension contributions
  -> connect approved MCP servers
  -> collect host/session tools
  -> normalize metadata
  -> registry transaction
```
未信任 workspace 只能发现非执行元数据，不得启动项目 MCP、加载插件或运行 discovery command。
### VisibilityContext
```typescript
interface ToolVisibilityContext {
  tenantId?: string; userId?: string; workspaceId?: string; projectTrust: ProjectTrustState; mode: AgentMode; hostCapabilities: HostCapabilities; modelCapabilities: ModelCapabilities;
  sandboxCapabilities: ExecutionCapabilities; sessionState: SessionProjection; policyVersion: string;
}
```
### Visibility 决策
按顺序过滤：
```text
registry candidates
  -> source trust
  -> organization allowlist/denylist
  -> project trust
  -> agent mode
  -> host capability
  -> provider schema/tool capability
  -> sandbox/backend availability
  -> session/run overrides
  -> tool count/token budget
```
### Toolset Snapshot
```typescript
interface ActiveToolset {
  tools: ProjectedToolDefinition[]; bindings: Map<string, ToolBinding>; registryVersion: string; visibilityDecisionIds: string[]; hash: string;
}
```
Prompt Compiler 只描述 `ActiveToolset` 中的工具。
如果工具被隐藏，Prompt 不应继续声称它可用。
## Tool Call 增量组装
### 原则
流式输出是事件流，不是字符串 token 流。只有 provider 明确完成某个调用后，才能解析和执行参数。
### 输入事件
```typescript
type NormalizedModelEvent =
  | { type: "tool_call_start"; responseId: string; itemKey: string; callId?: string; name?: string }
  | { type: "tool_call_name_delta"; itemKey: string; delta: string }
  | { type: "tool_call_arguments_delta"; itemKey: string; delta: string }
  | { type: "tool_call_complete"; itemKey: string; callId?: string }
  | { type: "response_complete"; finishReason: string }
  | { type: "provider_error"; error: unknown };
```
### AssemblyState
```typescript
interface ToolCallAssemblyState {
  responseId: string; itemKey: string; callId?: string; nameBuffer: string; argumentsBuffer: string; phase: "started" | "streaming" | "complete" | "invalid"; byteCount: number;
  eventCount: number; providerMetadata: Record<string, unknown>;
}
```
### 组装算法
```text
on start:
  create state keyed by responseId + itemKey
on name delta:
  require state not complete
  append within name byte limit
on arguments delta:
  require state not complete
  append exact bytes/string fragments
  enforce total byte and event limits
on complete:
  freeze state
  resolve call ID and name
  parse JSON once
  emit ToolCallReady or ToolCallInvalid
on response complete:
  verify no unfinished call
  reject calls when finish reason means length/safety/cancel truncation
```
### 必须处理的边界
- 一个响应包含多个并行调用；delta 交错到达；call ID 在 start 或 complete 才出现；name 也可能增量到达；JSON 字符串在转义字符中间切分；Unicode 字符跨传输片段；参数重复片段或 provider retry 重放；complete 后继续收到 delta。
- response 因长度、安全或取消结束；provider 返回未知事件。
未知事件应保留为 provider metadata 或 diagnostic，不能静默丢弃。
### 安全限制
Assembler 必须限制：
- 单调用参数字节数；单响应调用数量；嵌套深度的后续解析上限；delta 事件数量；未完成状态存活时间；同一 call ID 冲突。
不完整调用不得进入 policy 或 executor。
## Normalization 与 Validation
### 分层管线
```text
raw assembled call
  -> syntax parse
  -> canonical name resolution
  -> shape normalization
  -> canonical schema validation
  -> business validation
  -> hook transform
  -> full re-validation
  -> policy evaluation
```
### Normalization
可允许的规范化必须显式且可审计，例如：
- provider 把整数表示为无小数数值；enum 大小写按声明规则归一；路径分隔符转换为宿主 canonical 形式；URL 主机名做 IDNA/case 规范化；缺省值由可信应用填充；租户 ID、用户 ID 从执行上下文注入，而不是从模型参数信任。
禁止模糊修复：
- 猜测不存在的工具名；自动补全高风险目标；把自由文本转换成 shell 命令；删除未知字段后继续执行而不记录；对付款、删除、发送目标做近似匹配。
### ToolValidator
```typescript
interface ToolValidator {
  validateSchema(spec: ToolSpec, input: unknown): ValidationResult;
  validateBusiness(spec: ToolSpec, input: unknown, context: ValidationContext): Promise<ValidationResult>;
}
```
### ValidationResult
```typescript
interface ValidationResult<T = unknown> {
  ok: boolean; value?: T; issues: ValidationIssue[]; normalized: boolean; validationVersion: string;
}
```
### 业务校验示例
- 路径是否位于允许根目录且解析符号链接后仍在边界内；URL scheme、host、port、解析后 IP 是否允许；资源是否属于当前 tenant/user；数据库操作是否满足只读或受限语句策略；金额、数量、收件人和环境是否符合上限；Git、部署或发布状态机是否允许当前动作；命令是否通过结构化 argv 传递而非字符串拼接。
Hook、Policy transform 或 Approval 修改参数后，必须重新执行 schema 与业务校验。
## 准备阶段与决策边界
### prepare 不执行副作用
```typescript
interface ToolRuntime {
  list(context: ToolVisibilityContext): Promise<ToolDefinition[]>;
  prepare(call: ToolCall, context: ToolPrepareContext): Promise<PreparedToolCall>;
  execute(call: AuthorizedToolCall, signal: AbortSignal): AsyncIterable<ToolEvent>;
}
```
`prepare` 可以解析、校验、计算风险、资源键和 backend，但不得执行实际业务动作。
### Prepare 顺序
```text
resolve active binding
  -> verify call belongs to current toolset snapshot
  -> normalize arguments
  -> validate schema
  -> validate business rules
  -> run allowed transform hooks
  -> revalidate
  -> derive effect/risk
  -> derive resource keys
  -> derive idempotency key
  -> resolve backend requirements
  -> produce PreparedToolCall
```
### Policy 交接
PreparedToolCall 交给 Policy/Approval：
```text
visibility policy
  -> call policy
  -> approval policy
  -> execution policy
  -> egress policy
```
Tool Runtime 不得把“可见”解释为“已授权”。
## Scheduler
### 接口
```typescript
interface ToolScheduler {
  schedule(batch: AuthorizedToolCall[], scope: ToolScheduleScope): AsyncIterable<ToolEvent>;
}
```
### 调度输入
```typescript
interface ToolScheduleScope {
  runId: string; turnId: string; signal: AbortSignal; concurrencyLimit: number; lockManager: ResourceLockManager; budget: BudgetTracker; clock: Clock;
}
```
### 调度目标
- 保证授权快照与执行一致；控制全局和每工具并发；避免共享资源竞态；保持模型结果顺序稳定；快速传播取消；避免一个慢工具阻塞独立工具；对 durable boundary 产生明确事件。
### Batch 计划
```typescript
interface ToolExecutionPlan {
  batchId: string; nodes: ToolPlanNode[]; resultOrder: string[]; concurrencyLimit: number;
}
```
`resultOrder` 默认保持模型提出调用的顺序；执行完成事件可按真实时间发布。
### 决策流程
```text
for each call:
  verify budget
  classify execution mode
  expand resource keys
  build conflict edges
  apply exclusive barriers
  cap concurrency
  create deterministic plan
```
### Background 工具
后台工具不能伪装为普通同步工具。必须返回 durable job reference，并由独立 worker lease、heartbeat、取消和结果查询机制管理。
## 串行、并行与资源锁
### 默认策略
- `read + read` 且资源独立：可并行；任一调用声明 `serial`：在对应序列域串行；写同一文件、repo、账户或部署目标：资源锁；`destructive` 或全局状态动作：默认 exclusive；未声明并发语义的第三方工具：默认 serial；MCP 工具未提供可靠声明时：本地策略保守降级。
### ResourceLockManager
```typescript
interface ResourceLockManager {
  acquire(request: LockRequest, signal: AbortSignal): Promise<LockLease>;
}
interface LockRequest {
  ownerId: string; keys: string[]; mode: "shared" | "exclusive"; timeoutMs: number;
}
```
### 资源键
示例：
```text
file:D:/repo/src/a.ts
repo:D:/repo
branch:D:/repo#main
account:customer-123
mailbox:user@example.com
service:production-deploy
mcp:server-id/session-id
```
键必须 canonicalize，避免大小写、符号链接、相对路径或 URL 别名绕过冲突检测。
### 多锁规则
- 先排序后获取，防止死锁；获取失败时释放已得锁；lock lease 绑定 run/call owner；取消时释放；进程崩溃后依靠 lease 过期；锁等待时间计入工具预算；不在持锁期间等待人工审批。
### 顺序语义
```text
execution completion order != model result order
```
Scheduler 保存 call-order buffer，全部或可提交子集完成后按 provider 协议投影。
## 幂等、去重与未知结果
### 三个不同标识
- `callId`：模型/provider 协议关联；`fingerprint`：检测相同语义调用；`businessIdempotencyKey`：业务系统防止重复副作用。
三者不能混用。
### Fingerprint
```text
hash(
  tool stable ID
  + canonical validated arguments
  + relevant workspace/tenant scope
  + semantic version
)
```
不应包含无关时间戳或随机字段。
### IdempotencyPolicy
```typescript
interface IdempotencyPolicy {
  mode: "none" | "runtime_key" | "caller_key" | "query_before_retry"; scope: "run" | "session" | "tenant" | "global"; retentionMs?: number;
}
```
### 去重决策
```text
same callId replayed:
  return committed result if available
same fingerprint + non_repeatable:
  deny duplicate or require explicit new approval
same business key + completed:
  return prior business result
same business key + in_flight:
  wait/query status
unknown outcome:
  never blindly replay side effect
```
### ExecutionRecord
```typescript
interface ToolExecutionRecord {
  executionId: string; callId: string; fingerprint: string; idempotencyKey?: string; state: "prepared" | "authorized" | "started" | "committed" | "failed" | "unknown"; backendRef?: string; resultRef?: string;
  version: number;
}
```
### 崩溃窗口
最危险窗口是“副作用已发生，但 durable result 尚未提交”。恢复时：
1. 读取 ExecutionRecord；2. 查询 backend 或业务系统状态；3. 若能证明成功，补写结果；4. 若能证明失败，按策略重试；5. 无法确认时标记 `unknown`；6. 高风险动作要求人工处理。
## 执行生命周期
### 状态机
```text
Discovered
  -> Visible
  -> Assembling
  -> Ready
  -> Validating
  -> Prepared
  -> WaitingForApproval | Authorized | Denied
  -> Queued
  -> WaitingForLock
  -> Running
  -> Succeeded | Failed | Cancelled | Unknown
  -> ResultNormalized
  -> Committed
  -> Delivered
```
不要仅使用 `isExecuting: boolean`。
### ToolExecutor
```typescript
interface ToolExecutor<I, O> {
  execute(input: ToolExecutionInput<I>): AsyncIterable<RawToolEvent<O>>;
  queryStatus?(query: ToolStatusQuery): Promise<ToolExecutionStatus>;
}
```
### ToolExecutionInput
```typescript
interface ToolExecutionInput<I> {
  executionId: string; arguments: I; context: TrustedExecutionContext; idempotencyKey?: string; backend: ExecutionBackend; signal: AbortSignal;
}
```
`TrustedExecutionContext` 由 Harness 注入 tenant、workspace、cwd、凭据引用和授权快照；模型不能覆盖。
### 执行前 durable boundary
有副作用工具建议先持久化：
- PreparedToolCall hash；policy/approval decision；idempotency key；backend/profile；resource keys；execution ID。
### 取消
取消语义分级：
- cooperative：executor 观察 AbortSignal；process：backend 终止进程树；remote：发送 cancel 并继续查询最终状态；unsupported：标记取消请求，但结果可能 unknown。
UI 显示“已请求取消”不能等同“副作用未发生”。
## Progress 与事件协议
### ToolEvent
```typescript
type ToolEvent =
  | { type: "tool_prepared"; callId: string }
  | { type: "tool_queued"; callId: string; position?: number }
  | { type: "tool_lock_wait"; callId: string; keys: string[] }
  | { type: "tool_started"; callId: string; executionId: string }
  | { type: "tool_progress"; callId: string; progress: ToolProgress }
  | { type: "tool_artifact"; callId: string; artifact: ArtifactRef }
  | { type: "tool_completed"; callId: string; result: ToolResult }
  | { type: "tool_failed"; callId: string; error: ToolRuntimeError }
  | { type: "tool_cancelled"; callId: string; outcomeKnown: boolean };
```
### ToolProgress
```typescript
interface ToolProgress {
  message?: string; current?: number; total?: number; unit?: string; phase?: string; ephemeral: boolean;
}
```
### 事件规则
- started/completed/error 不可丢；高频 progress 可 coalesce；durable state 与 UI progress 分开；慢 Host 不得阻塞工具 stdout/stderr 读取到死锁；progress 不得包含未脱敏密钥；事件携带 runId、turnId、callId、executionId；同一 call 的状态必须单调前进。
### Backpressure
- durable queue bounded 且满时显式失败；ephemeral progress 可只保留最新；stdout/stderr 使用独立有界缓冲；大数据直接流向 ArtifactStore；Host 重连后从 durable entries 重建，不重放全部 delta。
## Result、Artifact 与输出预算
### 四种输出视图
```text
raw backend output
structured tool output
model-facing projection
user-facing artifact
```
它们不能默认是同一份数据。
### OutputBudget
```typescript
interface OutputBudget {
  maxBytes: number; maxLines?: number; maxItems?: number; maxModelTokens?: number; truncation: "head" | "tail" | "head_tail" | "semantic"; offloadThresholdBytes: number;
}
```
### Result Normalization
```text
collect raw events
  -> detect exit/business status
  -> validate optional output schema
  -> redact sensitive fields
  -> summarize or select salient portions
  -> truncate with explicit metadata
  -> offload full output to artifact
  -> build ToolResult
```
### ArtifactRef
```typescript
interface ArtifactRef {
  id: string; uri: string; mediaType: string; size: number; hash: string; summary?: string; sensitivity: Sensitivity;
  expiresAt?: string;
}
```
### 截断元数据
```typescript
interface TruncationMetadata {
  truncated: true; originalBytes: number; retainedBytes: number; retainedRange: string; artifactRef?: ArtifactRef;
}
```
不得让模型误以为它看到了完整结果。
### 错误输出
模型可见错误只包含：
- 稳定 code；安全 message；retryable；recoverable hint；必要的字段级 validation issues。
不要返回完整堆栈、宿主绝对路径、环境变量或原始凭据。
## Remote 与 MCP Tools
### RemoteToolTransport
```typescript
interface RemoteToolTransport {
  connect(signal: AbortSignal): Promise<void>;
  listTools(): Promise<RemoteToolSnapshot>;
  invoke(request: RemoteInvokeRequest, signal: AbortSignal): AsyncIterable<RemoteToolEvent>;
  queryStatus?(executionRef: string): Promise<RemoteExecutionStatus>;
  close(): Promise<void>;
}
```
### Remote 边界
Remote 工具额外需要：
- server provenance 和身份；transport 安全；auth refresh；tenant 绑定；request/response 大小限制；deadline 与网络重试；远端幂等能力声明；连接断开后的 unknown outcome。
- 服务端 schema/version drift；输出 egress 和本地再脱敏。
### MCP 生命周期
```text
discover config
  -> project trust check
  -> approve/start or connect
  -> authenticate
  -> initialize capabilities
  -> snapshot tool definitions
  -> wrap with local identity/policy/budget
  -> expose through active toolset
  -> health/reconnect
  -> refresh snapshot explicitly
  -> dispose
```
### MCP Tool Wrapper
本地 wrapper 必须补充：
- stable local ID；server ID 与 transport provenance；本地 canonical schema；effect/risk 分类；visibility 和 per-tool policy；timeout、output budget 和 artifact policy；本地错误分类；schema snapshot hash。
MCP server 声称“只读”不能自动成为安全事实；本地 policy 仍需验证。
### Schema Drift
```text
connection snapshot A active for current run
server advertises snapshot B
  -> record drift
  -> new runs may adopt B after validation
  -> current run keeps A unless explicit toolset change
```
调用响应显示方法不存在或 schema 不兼容时，不应无限重连重试。
### MCP 进程信任
项目配置中的 MCP 启动命令属于可执行代码。未信任 workspace 不启动；启动后仍应通过 sandbox、最小环境变量和受限凭据运行。
## Provider、Host 与 Harness 集成
### Provider Adapter
Provider adapter 负责：
- 把 ActiveToolset 投影为原生 tool definitions；把原生流转换为 ToolCallStart/Delta/Complete；保留 provider metadata；把 ToolResult 转换回原生消息/part；遵守 call ID 和消息顺序协议；识别长度、安全、取消导致的不完整调用。
Provider adapter 不执行工具，也不做业务授权。
### Kernel 集成
Kernel 流程：
```text
sample model
  -> commit complete assistant item
  -> collect all ready tool calls
  -> ask ToolPort.prepare/execute
  -> commit every result paired by call ID
  -> project results in stable order
  -> continue sampling or stop
```
### Harness 集成
Harness 负责：
- 构造 registry snapshot 和 active toolset；注入 Policy、Approval、Backend、ArtifactStore；创建 run/turn execution scope；监督 scheduler、预算、取消和恢复；将 durable tool entries 写入 session；将事件路由给 Host、trace 和测试 recorder。
### Host 集成
Host 能力可能包括：
```typescript
interface HostToolCapabilities {
  supportsProgress: boolean; supportsApproval: boolean; supportsArtifacts: boolean; supportsBackgroundJobs: boolean; supportsResultResume: boolean;
}
```
Host 不支持审批时，高风险调用必须 fail-closed，而不是自动 allow。
### Prompt 集成
Prompt Compiler 只消费 active tool definitions，并解释：
- 工具用途；使用时机；重要限制；当前模式下的审批预期。
Prompt 不决定可见性、权限、执行 backend 或网络边界。
## 版本与兼容
### 版本维度
分别记录：
- tool semantic version；input schema version/hash；output schema version/hash；executor implementation version；provider projection version；policy classification version；MCP server snapshot version；result projection version。
### 兼容分类
```text
backward compatible:
  add optional field
  broaden safe output metadata
potentially breaking:
  add required input
  narrow enum
  change effect classification
  change idempotency semantics
  change result meaning
  rename tool
```
### Run Freeze
每个 run 保存：
```text
toolset hash
registry version
per-tool stable ID/version
schema hashes
projection hashes
policy version
backend/profile version
```
恢复时优先使用兼容实现；不兼容时停止并产生 migration diagnostic。
### Alias 与迁移
Alias 只用于解析旧 transcript 或 provider 映射，不应同时向模型暴露多个近义名称。
旧 call 恢复必须映射到同一语义 stable ID；无法证明时不得执行。
## 错误分类、重试与恢复
### Error Taxonomy
```typescript
type ToolErrorKind =
  | "assembly"
  | "unknown_tool"
  | "schema_validation"
  | "business_validation"
  | "permission"
  | "approval_rejected"
  | "approval_expired"
  | "scheduling"
  | "lock_timeout"
  | "backend_unavailable"
  | "sandbox"
  | "execution_timeout"
  | "execution_failed"
  | "remote_transport"
  | "remote_protocol"
  | "output_validation"
  | "artifact_store"
  | "cancelled"
  | "unknown_outcome";
```
### Retry 决策
- assembly/schema/business validation：不重试原调用；模型可修正后提出新调用；permission/approval rejected：不自动重试；可向模型返回安全替代提示；lock timeout：可在总预算内有限重排或等待；backend unavailable：仅可切换到策略允许且能力等价的 backend；safe remote transport failure：指数退避并尊重服务端提示；已可能发生副作用：先 queryStatus，不能盲目重放；output projection failure：保留原执行状态，尝试从 artifact 重建结果；cancellation：根据 backend attestation 判断结果已知或 unknown。
### ToolRetryPolicy
```typescript
interface ToolRetryPolicy {
  maxAttempts: number; maxElapsedMs: number; backoff: "none" | "fixed" | "exponential_jitter"; retryableKinds: ToolErrorKind[]; requireStatusQueryForSideEffects: boolean;
}
```
### Recovery
启动恢复时：
1. 加载 pending/in-flight execution records；2. 恢复对应 toolset、policy 和 backend snapshot；3. 检查 committed result；4. 对可查询执行询问状态；5. 对纯只读、未开始调用可安全重启；6. 对副作用 unknown 标记人工处置；7. 补写 durable result 或 recovery entry；8. 释放过期 lock lease 和孤儿进程。
## 安全边界
### 不可信输入
以下全部视为不可信：
- 工具名和参数；检索内容建议的调用；文件内嵌指令；URL、重定向和 DNS 结果；shell、SQL 和代码片段；MCP server schema 与描述；remote tool result；模型声称“用户已批准”的文本。
### 强制层次
```text
Visibility
  -> Call Policy
  -> Approval
  -> Execution Policy
  -> Sandbox
  -> Result Egress
```
详细权限和沙箱设计见 `permission-sandbox-engineering.md`。
### Secrets
工具只能接收凭据引用或受限 capability，不把明文 secret 放入模型参数、prompt、progress 或普通日志。
### Prompt Injection
工具结果和外部资源只能作为数据进入上下文。它们不能：
- 注册新工具；提高权限；自动批准动作；改变 sandbox profile；要求把 secret 发送到外部；覆盖组织 policy。
### 最小能力
工具 executor 只获得完成动作所需的：
- 文件映射；网络目的地；进程能力；secret handle；tenant scope；时间和资源预算。
## 可观测性
### Trace 属性
每次调用记录：
```text
trace_id
run_id
turn_id
call_id
execution_id
tool stable ID/name/version
toolset hash
schema/projection hash
provider/model/api_family
source/provenance
visibility decision
validation version/result
policy/approval IDs
risk/effect
scheduler mode
resource keys hash
queue/lock/execution latency
backend/sandbox profile
idempotency/fingerprint hash
retry count
result status/size/truncation/artifacts
error kind
```
敏感参数、结果和路径按 policy 脱敏或只记录 hash。
### 指标
- tool call success rate；unknown tool rate；schema/business validation failure rate；approval rate/rejection rate；queue 与 lock wait latency；execution latency p50/p95/p99；timeout/cancel/unknown outcome rate；duplicate suppression rate。
- retry success rate；output truncation/artifact offload rate；MCP reconnect/schema drift rate；orphan process/lock count。
### Diagnostic Snapshot
应能安全查看：
- active toolset 与 hash；registry sources 和版本；backend readiness；MCP connection state；in-flight calls；lock owners；pending/unknown executions；output queue depth。
- 最近错误分类。
## 测试与 Conformance
### 单元测试
覆盖：
- 名称和 schema 注册校验；registry 冲突与事务回滚；visibility 过滤；provider schema projection；交错 tool-call delta 组装；Unicode、转义、截断和重复 delta；canonical normalization；schema 与业务校验。
- hook transform 后重新校验；fingerprint 与 idempotency key；resource key canonicalization；result truncation、redaction 和 artifact offload。
### Scheduler 测试
矩阵至少包括：
```text
parallel read/read
serial write/write
shared read locks
exclusive write lock
multi-key deadlock prevention
exclusive barrier
concurrency limit
lock timeout
cancel while queued
cancel while holding lock
stable result ordering
```
### 执行测试
- 正常成功；业务失败；timeout；cooperative cancel；强制终止进程树；side effect 后 commit 前崩溃；queryStatus 成功恢复；unknown outcome。
- artifact store 暂时失败；backend attestation 不满足要求。
### Provider Contract Tests
每个 provider adapter 使用脱敏 fixture 验证：
- 单调用和多调用；参数分片；call ID 映射；不同 finish reason；incomplete call 不执行；ToolResult 回传形状；未知事件保留；usage/provider metadata 不丢失。
### Tool Conformance Suite
```typescript
interface ToolConformanceCase {
  name: string; arrange: ToolFixture; expectedEvents: EventExpectation[]; expectedResult: ResultExpectation;
}
```
所有工具至少通过：
- canonical valid input；missing required；unknown field；boundary values；oversized input；cancellation；timeout；output budget。
- redaction；effect/idempotency declaration；deterministic cleanup。
### MCP Conformance
- 初始化和能力协商；tool snapshot；server crash/reconnect；schema drift；auth refresh；transport timeout；oversized output；malformed result。
- server description 注入；project trust deny；per-tool policy deny。
### 安全测试
包含：
- 非法工具名；路径穿越与符号链接逃逸；SSRF、重定向和 DNS rebinding；shell/SQL 注入；tenant/resource ID 越权；巨型参数和调用洪泛；prompt injection 诱导调用；secret 出现在参数/progress/result。
- sandbox unavailable 时 fail-closed；Host 不支持审批时拒绝高风险调用。
### Replay 与回归
保存脱敏的：
- model event fixtures；registry snapshots；prepared call snapshots；scheduler plans；tool event sequences；recovery checkpoints。
升级 SDK、schema validator、MCP transport 或 scheduler 后运行 replay。
## 反模式
1. 模型输出工具名后直接反射调用函数；2. 只验证 JSON 能解析，不做 schema 和业务校验；3. 只处理响应中的第一个工具调用；4. 在 ToolCallComplete 前解析和执行参数；5. provider finish reason 为 length/cancel 时仍执行半个调用；6. 把工具可见性等同于授权；7. Hook 或 policy 修改参数后不重新校验；8. 所有工具无差别并行。
9. 用原始文件路径作为未规范化锁键；10. 使用 call ID 作为业务幂等键；11. 非幂等写操作网络失败后盲目重试；12. 工具输出无限进入模型上下文；13. 截断结果但不告诉模型；14. 把完整异常、宿主路径和 secret 返回模型；15. MCP server 描述和 schema 被无条件信任；16. 项目未信任时启动项目 MCP 或插件工具。
17. Registry 同名工具静默覆盖；18. Run 中途静默切换工具版本；19. UI 断开导致工具执行任务失去 owner；20. Cancel 只停止进度显示，不终止子进程；21. Prompt 说“不要删除”但 policy 允许 destructive tool；22. 只测试最终文本，不测试事件、锁、崩溃和恢复。
## 实施清单
### 契约与 Registry
- [ ] 定义 ToolSpec、ToolIdentity、ToolSemantics；- [ ] 定义 canonical input/output schema；- [ ] 建立 ToolRegistry 和不可变 snapshot；- [ ] 实现命名、别名和冲突规则；- [ ] 注册使用可撤销 handle 与事务回滚；- [ ] 保存 provenance、trust、scope 和版本
### Discovery 与 Provider
- [ ] 两阶段发现 built-in 与 trusted workspace 工具；- [ ] 建立 VisibilityContext 和 active toolset；- [ ] 生成 toolset hash；- [ ] Prompt 只描述可见工具；- [ ] 实现 provider schema projection；- [ ] 建立可逆 provider 名称映射
### 流式与校验
- [ ] 建立 per-call ToolCallAssembler；- [ ] 支持多调用和交错 delta；- [ ] 不完整/截断调用不执行；- [ ] 限制参数大小、事件数和存活时间；- [ ] 建立 normalization policy；- [ ] 实现 schema 与业务双重校验
- [ ] 所有 transform 后重新校验
### 调度与执行
- [ ] 定义 parallel/serial/resource_locked/exclusive/background；- [ ] 实现 deterministic execution plan；- [ ] 实现 canonical resource keys；- [ ] 多锁排序并绑定 lease；- [ ] 保持 result order 与 call order 一致；- [ ] 取消传播到 queue、lock、backend 和 remote
- [ ] 有副作用调用执行前写 durable record
### 幂等与恢复
- [ ] 区分 call ID、fingerprint、business idempotency key；- [ ] 定义 per-tool IdempotencyPolicy；- [ ] 持久化 ExecutionRecord 状态机；- [ ] 实现 committed result replay；- [ ] 实现 remote/backend queryStatus；- [ ] unknown outcome 禁止盲目重放
- [ ] crash recovery 覆盖副作用提交窗口
### Result 与 Artifact
- [ ] 定义 ToolResult 和稳定错误 code；- [ ] 原始、结构化、模型、用户输出分层；- [ ] 设置 bytes/lines/items/token 预算；- [ ] 显式 truncation metadata；- [ ] 大输出卸载 ArtifactStore；- [ ] progress/result/log 执行脱敏
- [ ] optional output schema 本地再校验
### Remote 与 MCP
- [ ] 定义 RemoteToolTransport；- [ ] MCP 启动经过 project trust；- [ ] 保存 server provenance 和 snapshot hash；- [ ] 本地补充 effect/risk/policy/budget；- [ ] 处理 auth refresh、reconnect 和 schema drift；- [ ] transport 中断区分安全重试与 unknown outcome
- [ ] dispose 连接和子进程
### 可观测性与测试
- [ ] 全链路传播 run/turn/call/execution ID；- [ ] 记录 toolset、schema、policy、backend 版本；- [ ] 指标覆盖校验、排队、锁、执行、结果和恢复；- [ ] 建立 FakeTool、FakeBackend、FakeLockManager；- [ ] 建立 provider/tool/backend/MCP conformance suite；- [ ] 故障注入 timeout、cancel、crash、drift、artifact failure
- [ ] 安全矩阵覆盖 traversal、SSRF、注入、越权和 secret
## 五个参考项目的启发来源
- **Pi**：极小 headless tool loop、统一事件流、执行并发但结果顺序稳定、工具定义与 AgentSession/Harness 分层，为 ToolPort 与 Kernel 边界提供了直接启发；**Grok Build**：分层 sampler、独立工具 crate、permission decision、并行工具与路径级锁、工具/MCP 输出上限，启发了 assembler、scheduler、resource key 和 output budget 设计；**OpenCode**：独立 tool/permission 模块、server/client 事件、message/part、durable event/projector、MCP/LSP 与 snapshot/patch/revert，启发了 registry snapshot、durable execution record 和 Host 投影；**Claude Code**：官方公开的权限模式、hooks、skills、subagents 与 MCP 产品语义，启发了工具可见性、模式裁剪、审批体验和扩展生命周期；实现判断不依赖非官方镜像作为权威规范；**OpenClaw**：AgentHarness registry、agent-core、tool/sandbox/elevated 分层、Gateway/channel、事务化插件注册和 remote capability 组合，启发了注册回滚、Host 能力协商和执行边界分离。
