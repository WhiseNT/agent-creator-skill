# Subagent Engineering 细粒度工程设计
> Subagent 不是“再开一个聊天”，而是由 Harness Supervisor 监督的隔离 `child run`：它拥有明确目标、受限能力、独立上下文、独立预算、独立 trace、结构化结果和可传播的取消信号。
>
> 本文沿用现有 `Agent Kernel`/`Harness`、`RunScope`、`SubagentSpec`、`ContextPlan`、`ControlBudget`、`ChildResult`、`ArtifactRef`、`PolicyDecision`、`structured concurrency` 和 durable/ephemeral event 术语。架构依据仅来自本地已调研的五个参考项目源码归纳与现有工程文档，不依赖 README，不发起新的网络搜索。
## 目录
1. [设计目标与边界](#设计目标与边界)
2. [Subagent 的定义](#subagent-的定义)
3. [何时委派与何时不委派](#何时委派与何时不委派)
4. [任务分解模型](#任务分解模型)
5. [SubagentSpec 数据模型](#subagentspec-数据模型)
6. [Capability、Context、Budget 隔离](#capabilitycontextbudget-隔离)
7. [Child Run 生命周期](#child-run-生命周期)
8. [Structured Concurrency](#structured-concurrency)
9. [前台、后台与队列运行](#前台后台与队列运行)
10. [上下文编译与委派包](#上下文编译与委派包)
11. [工具、Sandbox 与 Permission 委派](#工具sandbox-与-permission-委派)
12. [结果 Schema 与证据](#结果-schema-与证据)
13. [Fan-out/Fan-in](#fan-outfan-in)
14. [冲突检测与合并](#冲突检测与合并)
15. [取消、重试与恢复](#取消重试与恢复)
16. [递归深度与成本控制](#递归深度与成本控制)
17. [状态、事件与持久化](#状态事件与持久化)
18. [安全边界与隐私](#安全边界与隐私)
19. [可观测性与运维](#可观测性与运维)
20. [测试策略](#测试策略)
21. [反模式与审查规则](#反模式与审查规则)
22. [实施清单与分阶段交付](#实施清单与分阶段交付)
23. [五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与边界
### 目标
Subagent Harness 必须保证：
- 委派目标可执行、可验收、可取消；
- child run 不默认继承父 transcript；
- child 只能访问声明并获准的工具、资源和 sandbox；
- 父 run 能知道 child 的状态、预算、证据和副作用；
- 多个 child 可以并发，但共享资源不会无序覆盖；
- child 失败可以局部重试、恢复或降级，不拖垮父 run；
- 结果可以被机器校验、去重、引用和审计；
- 子调用的 token、时间、工具、artifact 和 provider cost 可归因；
- 递归深度和 fan-out 有硬上限；
- 父取消可以传播到模型、工具、后台队列和子进程。
### 非目标
本模块不把以下职责塞进 `SubagentSupervisor`：
- 代替 Agent Kernel 实现模型—工具循环；
- 代替 Policy Engine 决定高风险动作；
- 代替 Context Compiler 选择所有上下文；
- 代替 ArtifactStore 保存任意大输出；
- 代替业务层做最终 merge；
- 以 prompt 文本保证隔离；
- 自动把 child transcript 拼进父对话。
核心关系：
```text
Parent Run -> creates assignment and child scope Harness Supervisor -> enforces capability/context/budget/isolation Child Run -> executes Kernel under
its own lifecycle ChildResult -> validated evidence returned to parent Parent -> decides accept, merge, retry, reject or ask user
```
## Subagent 的定义
### Child run 而非聊天副本
`Subagent` 是由父 `RunScope` 创建、由 `SubagentSupervisor` 监督、使用独立 `runId` 执行的隔离运行单元。
它必须有：
- `parentRunId`、`parentSessionId` 和 `childRunId` 关联；
- 独立 branch 或隔离 state namespace；
- 独立 `ContextPlan` 和 context budget；
- 独立 tool visibility、policy 和 execution backend；
- 独立 abort controller、task group 和 deadline；
- 独立 event namespace 和 trace span；
- 固定结果 schema、证据要求和 artifact 引用；
- 明确共享资源、写权限和合并策略。
### 父子关系
```text
Session └─ Parent Branch └─ Parent Run ├─ Child Run A │   ├─ Child Turn(s) │   └─ Child artifacts └─ Child Run B
```
child 可以读取父 assignment 摘要和明确传入的 artifact，但不能通过共享可变对象偷偷读写父状态。
### 三个独立问题
委派审查必须分别回答：
```text
child 看得到什么？       capability/context visibility child 能做什么？         policy/permission child 在哪里做？         sandbox/execution isolation
```
不能用一个 `allowSubagent: boolean` 代替三者。
## 何时委派与何时不委派
### 适合委派
| 场景 | 委派理由 | 推荐模式 |
|---|---|---|
| 大型代码库分区调查 | 分区互不依赖 | fan-out read-only |
| 独立模块实现 | 接口已冻结 | foreground child |
| 并行测试 | 测试命令互不冲突 | bounded parallel |
| 多来源研究 | 证据源可分组 | background/read-only |
| reviewer/critic | 需要独立视角 | read-only child |
| 长时间索引或扫描 | 不应阻塞前台 | durable background |
| 方案对比 | 结果可结构化 | fan-out/fan-in |
### 不适合委派
- 强顺序依赖的两个小步骤；
- 需要持续共享隐式上下文的任务；
- 多个 child 同时编辑同一未加锁文件；
- 父必须每一步即时指导的交互任务；
- 目标没有验收标准；
- 只为“让系统更像多 Agent”；
- child 成本高于本地一次工具调用；
- 需要用户审批但子系统无法持久化审批；
- 需要跨 child 共享 secret 而没有安全传递机制。
### 委派决策函数
```text
delegate if independent work value - coordination overhead - context packaging cost - child model/tool cost - merge/conflict risk > parent-local
execution value
```
实现上采用保守门槛：
1. 先估算本地执行步骤、时长和工具调用；
2. 判断任务能否拆成独立验收单元；
3. 判断结果能否用 schema 和证据表达；
4. 检查父 budget、depth、fan-out、sandbox capability；
5. 若任一硬约束不满足，留在父 run。
### 委派前检查清单
```text
objective 非空 acceptance criteria 可观察 依赖资源已列出 写入目标有 owner/lock allowedTools 是 capability 的子集 budget 足以完成最小工作 resultSchema 可校验 privacy/egress 允许传递
cancel/retry policy 已指定
```
## 任务分解模型
### TaskGraph
```typescript
interface TaskGraph { id: string; parentRunId: RunId; rootObjective: string; nodes: TaskNode[]; edges: TaskEdge[]; createdAt: string; version: number;
} interface TaskNode { id: string; objective: string; type: "research" | "implementation" | "test" | "review" | "background"; dependencies: string[];
acceptanceCriteria: string[]; assignedChildRunId?: RunId; status: "pending" | "ready" | "running" | "blocked" | "completed" | "failed"; } interface
TaskEdge { from: string; to: string; kind: "data" | "ordering" | "resource" | "approval"; }
```
### 分解规则
每个 node 应满足：
- 单一主要目标；
- 输入和输出边界明确；
- 可在一个 child lifecycle 内结束或 checkpoint；
- 不依赖父的未声明隐式状态；
- 能列出成功、失败和不确定三种结果；
- 能判断是否写文件、产生 artifact 或触发副作用。
### 分解流程
```text
normalize parent TaskSpec -> list required outcomes -> identify independent work units -> classify dependencies -> assign resource ownership -> choose
foreground/background -> create ChildSpec candidates -> validate budget and capabilities -> schedule ready nodes
```
### 顺序与并行
默认：
- 只读且资源独立的 nodes 可并行；
- 同一文件、数据库记录或部署环境写入必须串行或 exclusive；
- 结果合并前必须等待所有 required dependencies；
- optional child 失败不应阻塞 required child；
- 子 child 的 completion 不等于父任务完成，仍需 fan-in 验证。
## SubagentSpec 数据模型
### 基本接口
```typescript
interface SubagentSpec { objective: string; taskType: "research" | "implementation" | "test" | "review" | "background"; acceptanceCriteria:
AcceptanceCriterion[]; inputArtifacts: ArtifactRef[]; inputResources: ResourceRef[]; parentStateSummary?: ParentStateSummary; allowedTools: string[];
toolPolicy: ToolPolicy; modelPolicy: ModelSelection; contextPolicy: ChildContextPolicy; budget: ControlBudget; executionIsolation: ExecutionPolicy;
resultSchema: JsonSchema; evidencePolicy: EvidencePolicy; lifecycle: ChildLifecyclePolicy; mergePolicy: MergePolicy; privacy: ChildPrivacyPolicy; }
```
### AcceptanceCriterion
```typescript
interface AcceptanceCriterion { id: string; description: string; kind: "file" | "test" | "finding" | "artifact" | "state" | "review"; required:
boolean; verifier: "parent" | "harness" | "child_report" | "automated_test"; }
```
criterion 必须能转成断言、命令结果、文件 hash、结构化 finding 或人工确认；“尽力完成”不能作为唯一 criterion。
### ChildContextPolicy
```typescript
interface ChildContextPolicy { inherit: { objective: boolean; constraints: boolean; recentTurns: "none" | "summary" | "selected"; workingState: "none"
| "summary" | "selected"; parentRules: "system_only" | "system_and_workspace"; }; resources: ResourceSelector[]; maxTokens: number; includeMemory:
boolean; includeUntrustedContent: boolean; redactionProfile: string; }
```
### ControlBudget
```typescript
interface ControlBudget { maxTurns: number; maxToolCalls: number; maxSubagents: number; maxRecursionDepth: number; wallClockMs: number; inputTokens:
number; outputTokens: number; costMicros: number; artifactBytes: number; retryAttempts: number; }
```
Child budget 必须是 parent 剩余预算的子集：
```text
child budget <= parent remaining budget child depth = parent depth + 1 child deadline <= parent deadline
```
## Capability、Context、Budget 隔离
### Capability 隔离
父提交 `allowedTools` 只是请求，不是授权结果。Harness 计算：
```text
child visible tools = requested tools ∩ parent active toolset ∩ host capabilities ∩ policy allowlist ∩ execution backend capabilities
```
child 不能通过 prompt、skill、retrieval 或工具结果注册新权限。
### Context 隔离
父 transcript 不等于 child transcript：
```text
parent transcript != child transcript != child model context
```
父只传递最小必要委派包：
- objective；
- acceptance criteria；
- 必要约束；
- 相关文件/ArtifactRef；
- 已验证的 working state 摘要；
- 允许工具、预算和结果 schema。
不得默认传整个历史、全部 memory、完整 tool output 或 secret。
### State 隔离
child 有自己的：
- `runId`、`turnId`、attempt；
- branch/state namespace；
- event queue；
- checkpoint；
- memory candidate scope；
- artifact owner；
- working directory 或 workspace view。
共享只通过显式端口：
```typescript
interface ChildSharedPort { readArtifact(ref: ArtifactRef): Promise<ArtifactChunk>; publishFinding(finding: ChildFinding): Promise<void>;
requestApproval(request: ApprovalRequest): Promise<ApprovalDecision>; acquireResource(lock: ResourceLockRequest): Promise<ResourceLease>; }
```
### Budget 隔离
预算在动作前预检、事件后扣减：
```text
before model call -> reserve token/cost before tool call -> reserve tool/time/artifact before spawn child -> reserve subagent/depth budget after
completion -> settle actual usage
```
child 超预算只影响 child，父收到 `budget_exhausted`，不能绕过父硬上限继续生成。
## Child Run 生命周期
### 状态机
```text
created -> validating -> queued -> preparing -> running -> waiting_for_approval -> waiting_for_parent -> finalizing -> completed
created/queued/preparing/running/waiting -> cancelling -> cancelled 任意非终态 -> failed failed -> retrying -> queued paused -> resuming -> preparing
```
### 生命周期步骤
```text
1. Parent builds SubagentSpec 2. Supervisor validates capability/context/budget 3. Durable ChildAssigned entry 4. Create isolated ChildRunScope 5.
Build child ContextPlan 6. Freeze child config snapshot 7. Start Kernel and event namespace 8. Execute turns/tools under policy 9. Check acceptance
criteria 10. Persist checkpoint/result/artifacts 11. Validate ChildResult schema and evidence 12. Publish ChildCompleted/Failed 13. Release locks and
resources
```
### 生命周期接口
```typescript
interface SubagentSupervisor { spawn(spec: SubagentSpec, parent: RunScope): Promise<ChildRunHandle>; inspect(childRunId: RunId):
Promise<ChildRunView>; cancel(childRunId: RunId, reason: string): Promise<void>; retry(childRunId: RunId, policy?: RetryPolicy):
Promise<ChildRunHandle>; resume(checkpoint: CheckpointRef): Promise<ChildRunHandle>; } interface ChildRunHandle { childRunId: RunId; parentRunId:
RunId; events: AsyncIterable<ChildEvent>; result: Promise<ChildResult>; cancel(reason?: string): Promise<void>; pause(reason: string): Promise<void>;
resume(): Promise<void>; }
```
## Structured Concurrency
### RunScope 树
```typescript
interface RunScope { runId: RunId; parent?: RunScope; abortController: AbortController; deadline: number; budget: BudgetTracker; taskGroup: TaskGroup;
locks: ResourceLease[]; checkpoint: CheckpointWriter; }
```
所有 child 任务属于父 task group：
```text
parent RunScope ├─ child supervisor task ├─ child model stream task ├─ child tool tasks ├─ child approval wait ├─ child event consumers └─ child
delivery task
```
### 取消传播
父取消时：
1. 设置父 abort signal；
2. 停止接收新的 child assignment；
3. 向所有 child 传播相同 cancellation cause；
4. 等待模型流、工具进程、approval wait、event consumer settle；
5. 为未完成副作用写 unknown state；
6. 写 child cancellation entry 和 parent cancellation entry；
7. 释放 lease、文件锁、队列 ownership；
8. 父 run 等待 child settlement 后才进入终态。
UI 断开不等于父 run 取消；后台运行需要独立 owner 和 durable queue。
### 取消竞态
如果 child 在取消信号到达前已完成副作用，结果必须保留；如果 result commit 与取消并发，按 durable sequence 决定最终事实，不能仅看 UI 状态。
## 前台、后台与队列运行
### Foreground child
适用于父需要尽快 fan-in 的短任务：
- child 生命周期绑定父 task group；
- 父等待 child result；
- 共享父 deadline 的更小子 deadline；
- child event 可实时显示但不污染父 transcript；
- child 失败通常让父重新规划。
### Background child
适用于长时间、低交互任务：
```typescript
interface BackgroundJob { id: string; childRunId: RunId; owner: string; leaseUntil: string; heartbeatAt: string; retryCount: number; checkpointRef?:
CheckpointRef; notify: NotificationPolicy; expiresAt?: string; }
```
必须有：
- durable queue；
- lease/heartbeat；
- worker 重启后的 ownership recovery；
- checkpoint；
- cancel/expire；
- 结果通知；
- 不依赖前台连接存活。
### Background 状态
```text
queued -> leased -> running -> checkpointed -> completed queued/leased/running -> expired | cancelled | failed leased heartbeat timeout -> recoverable
```
lease 超时后只能由新 worker 在幂等/锁协议下接管，不得并行执行同一不可逆任务。
## 上下文编译与委派包
### Assignment Artifact
父将委派内容编译成结构化 assignment，而非复制 prompt：
```typescript
interface AssignmentPacket { assignmentId: string; parentRunId: RunId; childRunId?: RunId; objective: string; acceptanceCriteria:
AcceptanceCriterion[]; constraints: string[]; inputResources: ResourceRef[]; inputArtifacts: ArtifactRef[]; stateSummary?: ParentStateSummary;
allowedTools: string[]; resultSchema: JsonSchema; evidencePolicy: EvidencePolicy; sensitivity: Sensitivity; packetHash: string; }
```
### ContextPlan
child 编译器输出自己的 plan：
```typescript
interface ChildContextPlan extends ContextPlan { assignmentId: string; inheritedSections: string[]; redactedSections: string[];
excludedParentResources: string[]; capabilityHash: string; budget: TokenBudgetAllocation; }
```
### 传递优先级
```text
system/product policy > organization policy > child harness policy > assignment objective/constraints > trusted workspace rules > selected
artifacts/resources > retrieved/tool content
```
父传入的自然语言 summary 仍然是数据，不能覆盖 child system policy 或扩展权限。
### 上下文选择算法
```text
collect assignment resources -> verify tenant/scope and hashes -> redact by sensitivity -> filter by child context policy -> preserve required
artifacts -> score relevance/freshness/authority -> deduplicate -> fit child token budget -> compile and hash
```
超预算按以下顺序降级：
```text
remove duplicates -> trim metadata -> summarize selected history -> offload large output to artifact -> narrow file/resource slices -> reject
assignment with diagnostic
```
不从字符串尾部机械截断，也不切断 tool call/result 对。
## 工具、Sandbox 与 Permission 委派
### 能力解析
```typescript
interface ChildCapabilities { visibleTools: string[]; allowedActions: string[]; filesystem: FilesystemCapability; network: NetworkCapability;
processes: ProcessCapability; artifacts: ArtifactCapability; canSpawnChildren: boolean; }
```
能力必须在 child config snapshot 中冻结；运行中增加能力只能通过显式 policy/approval 和新 capability entry。
### 工具委派规则
- 父可缩小 child toolset，不能扩大组织安全上限；
- child tool schema 必须在最终执行边界再次校验；
- hook/child transform 后重新做 schema、业务、policy 校验；
- 有副作用工具要求幂等键；
- 同一资源写入必须 acquire lock；
- tool output 有 bytes/lines/time/token 预算；
- 大输出 offload 到 child-owned artifact，再返回 summary + ref。
### Permission 与 Approval
policy 管线：
```text
visibility -> call validation -> action policy -> approval policy -> sandbox policy -> result egress
```
父已批准不必然等于 child 可执行：
- approval 必须绑定 child call ID、参数 hash、resource scope 和 expiresAt；
- child 修改参数或目标后必须重新审批；
- child 不能把父对另一资源的 approval 复用；
- host 无法展示 child 风险摘要时拒绝高风险动作。
### Sandbox
sandbox backend 要返回 attestation：
```typescript
interface SandboxAttestation { backend: string; profile: string; filesystemBoundary: string; networkBoundary: string; processBoundary: string;
applied: boolean; capabilities: string[]; createdAt: string; }
```
安全敏感配置下 sandbox 不可用必须 fail-closed，不能静默回退宿主 shell。
## 结果 Schema 与证据
### ChildResult
```typescript
interface ChildResult<T = unknown> { childRunId: RunId; assignmentId: string; status: "completed" | "partial" | "failed" | "cancelled" | "blocked";
summary: string; output: T; findings: ChildFinding[]; confidence: number; evidence: EvidenceRef[]; artifacts: ArtifactRef[]; changes: ChangeRef[];
verification: VerificationReport; openRisks: RiskItem[]; usage: Usage; diagnostics: Diagnostic[]; provenance: Provenance; }
```
### ChildFinding
```typescript
interface ChildFinding { id: string; claim: string; severity?: "info" | "low" | "medium" | "high" | "critical"; confidence: number; sourceRefs:
ResourceRef[]; evidenceRefs: EvidenceRef[]; assumptions?: string[]; status: "verified" | "inferred" | "unverified" | "contradicted"; }
```
### EvidenceRef
```typescript
interface EvidenceRef { id: string; kind: "file_range" | "test_run" | "command" | "artifact" | "event" | "source"; ref: string; hash?: string;
excerpt?: string; capturedAt: string; sensitivity: Sensitivity; }
```
父不应只收到一段无来源自然语言。每个 required acceptance criterion 必须映射到至少一个 evidence 或明确失败理由。
### VerificationReport
```typescript
interface VerificationReport { criteria: CriterionResult[]; commands: CommandResult[]; changedFiles: FileVerification[]; reproducible: boolean;
performedBy: "child" | "parent" | "harness"; }
```
child 报告“测试通过”时，必须提供命令、退出码、工作目录、关键输出摘要和 artifact 引用，不能伪造。
## Fan-out/Fan-in
### Fan-out 调度
```typescript
interface FanOutPlan { parentRunId: RunId; childSpecs: SubagentSpec[]; maxConcurrency: number; failurePolicy: "fail_fast" | "collect_all" |
"required_only"; mergePolicy: MergePolicy; }
```
调度器：
1. 为每个 child 预留 budget；
2. 按 dependency graph 选 ready nodes；
3. 使用 semaphore 限制并发；
4. 为共享资源取得 lease；
5. 启动 child；
6. 收集状态和心跳；
7. 进入 fan-in 前等待 required children settle。
### Fan-in
```text
collect ChildResults -> validate schema and signatures/hashes -> map criteria to evidence -> deduplicate findings -> detect contradictory claims ->
classify file/resource conflicts -> produce MergePlan -> parent verification -> accept/partial/retry/reject
```
fan-in 不是把 summaries 直接拼成 prompt；父应读取结构化结果和必要 artifact 片段。
### 失败策略
- `fail_fast`：任一 required child 失败即取消同组未开始任务；
- `collect_all`：尽量收集独立结果，再由父判断；
- `required_only`：required child 失败阻塞，optional child 失败记录 warning。
## 冲突检测与合并
### 冲突类型
```text
finding conflict       同一事实结论不同 resource conflict      同一文件/记录同时修改 policy conflict        child 声称允许但 harness 拒绝 state conflict         parent branch
已变化 artifact conflict      相同路径/hash 不同 budget conflict        合并超出父剩余预算
```
### Finding 合并
```text
same claim + same evidence -> deduplicate same claim + stronger evidence -> prefer stronger, retain both refs same claim + contradictory evidence ->
conflict review inference vs direct evidence -> direct evidence wins unverified -> never promote to verified
```
### 文件变更合并
实现 child 默认使用：
- 独立 worktree/snapshot；或
- 明确目录所有权；或
- exclusive resource lock。
合并前：
1. 校验 parent base snapshot hash；
2. 生成 patch 和 affected paths；
3. 做三方合并；
4. 检测同一行/符号冲突；
5. 运行针对性测试；
6. 由 parent 或用户决定应用；
7. 追加 merge/change entry。
不得把 child 在共享目录里的“最后写入”当作合并。
### MergePlan
```typescript
interface MergePlan { childResults: RunId[]; acceptedFindings: string[]; rejectedFindings: string[]; conflicts: MergeConflict[]; patches:
PatchRecord[]; requiredVerification: AcceptanceCriterion[]; requiresApproval: boolean; }
```
## 取消、重试与恢复
### Child cancellation
取消原因分类：
```text
parent_cancelled user_cancelled budget_exhausted deadline_exceeded policy_denied resource_conflict superseded worker_lost
```
每次取消写 durable lifecycle entry，child 结果为 `cancelled`，未完成工具标记 `unknown` 或 `cancelled`，不伪造成功。
### RetryDecision
```typescript
interface ChildRetryDecision { action: "retry_same" | "retry_modified" | "resume_checkpoint" | "fallback_model" | "stop"; reason: string; maxAttempts:
number; delayMs?: number; preserveArtifacts: boolean; preserveFindings: boolean; }
```
重试分类：
- transport/容量错误：可有限 retry；
- context overflow：修改 context 后 retry；
- tool validation：修正 assignment/schema 后 retry；
- policy deny：不得盲目 retry 原调用；
- side effect unknown：先 probe，不重放；
- deterministic failure：停止或换策略；
- child model failure：按 capability compatibility 选择 fallback。
### Resume
resume 使用 child checkpoint：
```typescript
interface ChildCheckpoint { childRunId: RunId; lastDurableEntry: EntryId; taskNodeId: string; workingState: WorkingState; inFlightTools:
InFlightToolState[]; budgetUsed: BudgetCounters; contextPlanHash: string; configSnapshotId: string; }
```
resume 必须重新验证：
- parent assignment 是否仍有效；
- workspace/base snapshot 是否变化；
- policy、toolset、sandbox 是否仍兼容；
- budget/deadline 是否足够；
- 未知副作用是否已查明。
### Worker crash
```text
lease timeout -> mark worker_lost -> load last checkpoint -> probe in-flight side effects -> acquire recovery lease -> resume or terminal-fail
```
不得因为 worker 崩溃就创建并行副本执行同一不可逆动作。
## 递归深度与成本控制
### Depth
```typescript
interface DepthPolicy { current: number; max: number; allowRecursiveTypes: string[]; denyAtRemainingBudgetBelow: number; }
```
默认 child 不可继续 spawn；允许递归时：
```text
child.depth = parent.depth + 1 child.maxSubagents <= parent.remaining child.deadline <= parent.deadline
```
到达 max depth 必须返回结构化 `recursion_limit`，不能通过 background queue 绕过。
### Doom-loop 检测
检测：
- 相同 assignment hash 重复 spawn；
- 相同 tool call/参数 hash 重复；
- child 反复失败于同一 criterion；
- fan-out 产生相同资源 owner；
- parent 只转发 child summary 而没有推进状态。
触发后：
```text
stop spawn -> emit diagnostic -> preserve existing evidence -> ask parent to re-plan or finish
```
### 成本归因
usage 至少分解：
```text
parent model child model by runId child retry/fallback child compaction child memory extraction/recall child tool execution child artifact bytes
embedding/rerank if used
```
预算报告既要有 actual，也要有 reserved，避免并发 child 超卖父预算。
## 状态、事件与持久化
### Child durable entries
```typescript
type ChildEntry = | ChildAssignedEntry | ChildStartedEntry | ChildCheckpointEntry | ChildApprovalEntry | ChildArtifactEntry | ChildResultEntry |
ChildFailedEntry | ChildCancelledEntry | ChildLeaseEntry | ChildMergeEntry;
```
父 session 保存 assignment、child reference、状态摘要和 ChildResult 引用；child session 保存自己的 semantic transcript。
### 事件命名空间
```text
parent.run.child.<childRunId>.started parent.run.child.<childRunId>.progress parent.run.child.<childRunId>.checkpointed
parent.run.child.<childRunId>.completed parent.run.child.<childRunId>.failed
```
child 的 text delta、tool progress 默认 ephemeral；assignment、tool call/result、approval、checkpoint、result、failure 是 durable。
### Projector
至少提供：
- `ChildStatusProjector`：父侧状态；
- `ChildResultProjector`：结果引用；
- `ChildBudgetProjector`：预算；
- `ChildResourceProjector`：lock/lease；
- `ChildTraceProjector`：诊断索引。
父侧 projection 落后时，UI 可显示 stale；Supervisor 不能据此宣称 child 已完成。
## 安全边界与隐私
### Trust 与 authority
父 state summary、memory、tool result、检索文档都不自动拥有 child 指令 authority。child 的真实能力由 Harness policy、tool registry 和 execution backend 强制。
### Sensitive data 传递
```text
public      可按 provider policy 传递 internal    需 tenant/model policy confidential 默认 redaction 或 artifact-only secret      不进入 child model context
regulated   需要专门 egress/审计策略
```
secret 只能通过 capability-based secure handle 传给受信工具，不把值写入 assignment、prompt、event 或 ChildResult。
### Artifact 访问
child 只能访问：
- `inputArtifacts`；
- task 所需且 policy 允许的资源；
- 自己创建的 artifact；
- 明确授予的父 artifact range。
父不能为了方便给 child 整个 artifact bucket；artifact URI 需要租户、owner、expiry 和 sensitivity 校验。
### 插件和 MCP
child 请求的 plugin/MCP tool 必须经过：
```text
trust check -> active toolset -> child policy -> sandbox capability -> output budget -> health/auth
```
未信任 workspace 的可执行配置不能因 child 委派而自动加载。
### Prompt injection
外部文档、测试输出、issue、tool result 进入 child Context 时包装为不可信数据。child 不得因其内容：
- 改变 system policy；
- 注册新工具；
- 扩大 parent assignment；
- 发送数据到外部地址；
- 代替 approval。
## 可观测性与运维
### Trace 层级
```text
session span -> parent run span -> assignment span -> child run span -> child turn/attempt -> model/tool/approval -> child compaction -> fan-in/merge
```
### 字段
```text
trace_id parent_run_id child_run_id assignment_id task_node_id session/branch config snapshot hash context plan hash capability/toolset hash sandbox
attestation budget reserved/actual queue/lease/heartbeat model/provider/api_family retry/fallback artifact ids/hashes criterion/evidence status
conflict ids cancellation cause
```
### 指标
- delegate decision rate；
- child success/partial/failure/cancel rate；
- acceptance criterion coverage；
- evidence completeness；
- parent wait latency；
- queue delay、lease loss、resume success；
- fan-out concurrency utilization；
- conflict and merge rejection rate；
- retry amplification；
- child token/cost/artifact consumption；
- duplicate assignment/doom-loop rate；
- sandbox/policy deny rate；
- context packaging latency；
- stale result adoption rate。
### Diagnostic Snapshot
```text
parent/child IDs assignment objective hash state and last durable entry active model/toolset budget remaining pending approvals in-flight tools
lock/lease owner checkpoint age last event sequence result validation errors open conflicts
```
输出必须脱敏；不把完整 child transcript 默认暴露给父 UI 或运维日志。
## 测试策略
### 单元测试
- `SubagentSpec` schema 和默认值；
- budget 子集计算和 reservation/settlement；
- capability intersection；
- context inheritance 和 redaction；
- depth/fan-out limit；
- result/evidence schema 校验；
- finding dedup/contradiction；
- cancellation cause 传播；
- retry classification；
- merge conflict detection。
### Harness 集成测试
使用：
```typescript
createTestHarness({ model: new ScriptedModel([...]), tools: [fakeRead, fakeWrite], session: new InMemorySessionRepository(), clock: new FakeClock(),
ids: new DeterministicIds(), })
```
场景至少包括：
1. 一个只读 foreground child；
2. 两个独立 read-only child 并行；
3. optional child 失败而 required child 成功；
4. parent cancellation 传播到 model/tool；
5. child 超时和 budget exhaustion；
6. child context 不包含父 secret；
7. child 请求未授权工具被拒绝；
8. sandbox unavailable 时 fail-closed；
9. child 写入同一文件发生 lock/merge conflict；
10. fan-in 发现相互矛盾的 findings；
11. schema 不完整的 ChildResult 被拒绝；
12. child checkpoint 后 worker crash 并 resume；
13. side effect 后 result commit 前 crash；
14. recursive spawn 到达 depth limit；
15. 相同 assignment 触发 doom-loop；
16. background worker lease 过期后安全接管；
17. host 断开但 background child 继续；
18. retry 不重复未知副作用；
19. context plan hash 变化导致 resume 重新验证；
20. 所有 child usage 正确归因给 parent。
### 事件序列断言
测试不只看最终 summary，应验证：
```text
ParentRunStarted -> ChildAssigned -> ChildStarted -> ContextCompiled -> ModelStarted -> ToolCallReady -> ToolCompleted -> ChildCheckpointed ->
ChildResultValidated -> ChildCompleted -> FanInStarted -> MergePlanProduced
```
取消、失败和恢复路径同样必须有完整事件序列。
### 属性测试
```text
child budget never exceeds parent remaining budget child visible tools ⊆ parent active tools cancel(parent) eventually settles every descendant same
result replay does not duplicate merge same assignment hash is bounded by doom-loop policy fan-in does not accept finding without required evidence
resource lock prevents overlapping exclusive writes
```
### Provider/Backend Conformance
所有 Model Runtime、Tool Runtime、Sandbox Backend、Queue Worker 和 Host Adapter 运行共同契约：
- abort 可观察；
- usage 可归因；
- 错误分类稳定；
- durable result 可恢复；
- 未知副作用可标记；
- capability 宣称与实际执行一致。
## 反模式与审查规则
1. child 只是用同一 prompt 递归调用模型。
2. parent 和 child 共用完整 transcript 或 mutable working state。
3. 通过 prompt 声称隔离，却没有 tool/sandbox enforcement。
4. `allowedTools` 直接等于授权工具。
5. child 没有独立 budget、deadline、trace 或 run ID。
6. 子任务没有 acceptance criteria。
7. 父只收一段无来源自然语言 summary。
8. child 返回“已验证”但没有 evidence。
9. 多 child 同时写同一文件而没有 lock/snapshot/merge。
10. fan-out 无并发上限，fan-in 无失败策略。
11. parent cancel 只停止 UI，不停止 child process。
12. background run 依赖前台连接。
13. worker 丢失后并行重跑不可逆工具。
14. retry 复制同一 side effect 而没有幂等键。
15. child 可无限递归 spawn。
16. child context 包含所有父 memory 和 secret。
17. result schema 允许任意字符串、没有版本。
18. fallback 偷偷换模型，父 session 没有记录。
19. child failure 直接杀死所有无关 child。
20. merge 以最后写入文件覆盖冲突。
21. 把子任务数量当作质量指标。
22. 用模型“遵守规则”代替 Harness policy。
23. child 生成的 artifact 没有 owner、hash、expiry。
24. 子调用 cost 没有归因到父任务。
25. 只测试 happy path，不测试 lease、crash、cancel、resume。
审查最低标准：
```text
隔离可证明 预算可计算 取消可传播 结果可校验 证据可追溯 副作用可恢复 冲突可呈现 递归有上限
```
## 实施清单与分阶段交付
### V1：单 child foreground
- [ ] 定义 `SubagentSpec`、`ChildRunHandle`、`ChildResult`；
- [ ] 建立独立 run/trace/event namespace；
- [ ] 实现 capability intersection；
- [ ] 实现最小 context packet；
- [ ] 实现 child budget 和 max depth；
- [ ] 实现 schema/evidence 验证；
- [ ] 实现 parent wait 与取消传播。
### V2：并发与隔离
- [ ] structured task group；
- [ ] bounded fan-out；
- [ ] resource lock；
- [ ] 独立 artifact ownership；
- [ ] sandbox profile/attestation；
- [ ] finding dedup 和冲突报告；
- [ ] parent-child durable entries。
### V3：后台与恢复
- [ ] durable queue；
- [ ] lease/heartbeat；
- [ ] child checkpoint；
- [ ] worker crash recovery；
- [ ] retry/fallback 分类；
- [ ] unknown side-effect probe；
- [ ] background notification 和 expiry。
### V4：实现 child 与合并
- [ ] snapshot/patch base hash；
- [ ] worktree/目录 ownership；
- [ ] MergePlan；
- [ ] 三方合并和 targeted tests；
- [ ] approval 绑定 call/args/resource；
- [ ] parent verification gate。
### V5：规模化治理
- [ ] 多租户 quota 和 cost attribution；
- [ ] recursive task graph；
- [ ] priority/fair scheduling；
- [ ] capability registry；
- [ ] conformance suite；
- [ ] evaluation benchmark、ablation 和 chaos tests；
- [ ] admin diagnostic snapshot。
## 五个参考项目的启发来源
### Pi
- headless agent loop、EventStream 和 AgentSession 启发 child 使用相同 Kernel、由外部 Harness 管理生命周期；
- session tree 启发独立 branch、steering/follow-up 和 parent/child 状态引用；
- CLI/TUI/RPC 共用 runtime 启发 child event 不应绑定单一 host；
- 依据：现有 `references/agent-reference-architecture.md`、`agent-harness.md` 和 `harness-engineering.md` 中列出的 Pi 源码范围。
### Grok Build
- actor 化 Session/ChatState/Sampler 启发 child scope 的串行状态所有权；
- sampler 三层分离启发 child model attempt、retry/fallback 和 usage 归因；
- permission decision、folder trust、sandbox 启发 visibility/policy/approval/sandbox 分离；
- 路径级工具锁启发 fan-out 中的资源 lease 和写冲突处理；
- 依据：现有参考文档列出的 session、sampler、tools、sandbox 源码目录。
### OpenCode
- client/server 分离启发 child event namespace、durable result 和背景 worker；
- session/message/part 启发 assignment、child transcript 与 model context 分离；
- durable event/projector 启发 parent status projector 和 replay；
- snapshot/patch/revert 启发 child 实现结果的基线 hash、冲突和可审计合并；
- 依据：现有参考文档列出的 `session`、`tool`、`permission`、`server` 源码范围。
### Claude Code
- subagents、skills、hooks、memory、permission modes 启发“能力声明不等于能力授权”和最小必要上下文；
- 计划与任务工作流启发 acceptance criteria、parent verification 和 background child；
- 项目规则与 auto memory 启发 scope、provenance 和 context isolation；
- 公开安全语义以现有文档中标注的 Anthropic 官方资料为准，辅助源码不作为规范；
- 依据：本地 `references/engineering/context-engineering.md`、`harness-engineering.md` 和参考架构的已调研归纳。
### OpenClaw
- AgentHarness registry 启发 Supervisor 通过注册表组合 model/tool/sandbox/host 能力；
- agent-core 与 Gateway/channel 分层启发 foreground/background 和 delivery 解耦；
- tool/sandbox/elevated 分离启发 child execution profile；
- 后台运行、memory flush 和事务化插件启发 queue ownership、checkpoint、结果治理和失败回滚；
- 依据：现有参考文档列出的 `agent-core`、`harness/registry`、`openclaw-tools`、`plugins` 源码范围。
本设计的实现审查应使用现有本地文档和其已记录的一手源码范围作为依据。若引入新的调度器、分布式队列、provider 或跨租户策略，应在单独设计中补充对应一手证据、迁移方案和测试契约。
