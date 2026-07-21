# Workflow Orchestration Engineering 细粒度工程设计
> 本文定义面向 Agent Harness 的 Workflow Orchestration：把用户目标、可版本化定义、durable execution、工具与 subagent 协作、人工控制、恢复和交付组织成可审计的工作流系统。
>
> 设计依据仅来自当前目录已有的参考架构、`agent-harness.md`、Prompt、Context、Tool、State/Memory、Permission/Sandbox、Subagent、Event/Observability、Evaluation、Coding Agent、Provider Runtime、Provider Routing、Artifact、Multi-tenant、Host Adapter、Workspace Isolation、Production Operations、Session Replay、Privacy、Agent Product、Durable Queue 文档及五个参考项目的本地源码调研结论；不依赖 README，不发起新网络搜索。
>
> Workflow Orchestration 不是把多步 prompt 串起来，也不是把工具调用放进一个队列。它是围绕 Definition、Version、Task、Workflow、Run、Step、Attempt、Job、Checkpoint、Event、Artifact、Approval、Signal、Policy、Lease 和 Settlement 建立的 durable 状态系统。
## 目录
1. [设计目标与非目标](#设计目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [职责边界](#职责边界)
4. [总体架构与包布局](#总体架构与包布局)
5. [Workflow Definition 与 Version](#workflow-definition-与-version)
6. [Task、Workflow、Run、Step、Attempt 与 Job](#taskworkflowrunstepattempt-与-job)
7. [核心数据模型](#核心数据模型)
8. [TypeScript 接口](#typescript-接口)
9. [输入输出 Schema 与契约](#输入输出-schema-与契约)
10. [DAG、依赖与拓扑执行](#dag依赖与拓扑执行)
11. [条件、分支与表达式](#条件分支与表达式)
12. [循环、Map 与动态 Fan-out](#循环map-与动态-fan-out)
13. [并行、Join 与资源协调](#并行join-与资源协调)
14. [补偿、Saga 与部分成功](#补偿saga-与部分成功)
15. [Durable Queue、Lease 与 Worker](#durable-queuelease-与-worker)
16. [Step Attempt、Timeout、Retry 与 Idempotency](#step-attempttimeoutretry-与-idempotency)
17. [Checkpoint、Replay 与恢复](#checkpointreplay-与恢复)
18. [Pause、Resume、Cancel 与 Signal](#pauseresumecancel-与-signal)
19. [Human Approval 与 Steering](#human-approval-与-steering)
20. [Subagent 编排](#subagent-编排)
21. [Tool、Artifact 与 Context 集成](#toolartifact-与-context-集成)
22. [Model、Prompt、State、Policy 与 Harness 集成](#modelpromptstatepolicy-与-harness-集成)
23. [租户、权限、Workspace 与 Sandbox](#租户权限workspace-与-sandbox)
24. [生命周期与状态机](#生命周期与状态机)
25. [端到端决策流程](#端到端决策流程)
26. [故障恢复、失败、未知结果与降级](#故障恢复失败未知结果与降级)
27. [版本发布、迁移与兼容](#版本发布迁移与兼容)
28. [可观测性、指标与 SLO](#可观测性指标与-slo)
29. [安全、隐私与数据治理](#安全隐私与数据治理)
30. [测试策略与 Evaluation](#测试策略与-evaluation)
31. [反模式与审查规则](#反模式与审查规则)
32. [实施清单](#实施清单)
33. [五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
Workflow Orchestration 必须能够：；将用户目标规范化为可验证的 `TaskSpec` 和 `WorkflowInput`。；以不可变的 workflow definition/version 描述节点、依赖、条件、循环、并行和补偿。；区分 Task、Workflow、Run、Step、Attempt、Job 和 Event 的业务语义。；让每一次 step 执行拥有 durable 状态、lease、timeout、retry、idempotency 和结果引用。；支持 DAG、条件分支、循环、Map、动态 fan-out、parallel、join、barrier 和依赖失败传播。；支持 human approval、steering、pause、resume、cancel、signal 和 external callback。；支持 subagent、model、prompt、context、tool、artifact、state、policy 和 sandbox 的显式绑定。；通过 checkpoint、replay、outbox、inbox 和 execution record 支持崩溃恢复。；区分 failed、cancelled、partial success、blocked、expired 和 unknown outcome。；对真实副作用使用幂等键、状态查询、receipt、补偿或人工处理，避免重复执行。；在多租户环境中实施 scope、permission、workspace、egress、quota 和 worker 隔离。；让 workflow definition 发布、迁移、回滚和长期运行兼容可验证。；提供从步骤到运行、租户、provider、tool、artifact 和成本的可观测性。；通过 deterministic testkit、fault injection、replay 和 side-effect oracle 验证行为。
### 非目标
Workflow Orchestration 不负责：；代替 Agent Kernel 的模型—工具 while loop。；用 prompt 文本定义真正的权限、审批、沙箱和数据外发边界。；让 workflow definition 直接执行任意 shell、SQL、HTTP 或生产 API。；把 DAG 图形界面当作 durable source of truth。；把 queue 可见、worker 已领取或模型回复成功当作业务动作成功。；用 exactly-once 作为传输层承诺。；在 worker 内读取最新全局配置覆盖已经冻结的 run snapshot。；让 workflow 版本升级静默改写已完成的历史事实。；把失败后的自动重试当作所有副作用的通用恢复策略。；让子工作流自动继承父工作流全部 tenant、secret、workspace 和 artifact 权限。；以单一总分掩盖安全失败、未知结果、预算超限和部分成功。；把 UI spinner、HTTP 断开或 host ack 当作 workflow terminal truth。
### 核心公式
```text
Workflow Reliability
  = Definition Correctness
  × State Durability
  × Dependency Semantics
  × Lease Ownership
  × Retry Safety
  × Side-effect Evidence
  × Policy Compliance
  × Recovery Quality
```
## 核心判断与术语
### 编排的三种 truth
```text
Task Truth      用户目标、约束、验收标准、优先级和交付选择
Workflow Truth  definition/version、节点、依赖、schema、策略和版本
Run Truth       实际执行的 step、attempt、job、event、artifact、receipt 和错误
```
三者不能混为一张“任务状态”表。
### 术语；`Task`：面向用户的目标，可能由一个或多个 workflow run 完成。；`WorkflowDefinition`：声明可执行结构、节点、边、schema、策略和兼容信息。；`WorkflowVersion`：不可变、可寻址、可发布的 definition 版本。；`Workflow`：产品层可复用的逻辑工作流身份，拥有多个版本。；`Run`：某一版本在具体 tenant、workspace、输入和预算下的一次执行。；`Step`：run 中一个逻辑节点的状态和输出容器。；`Attempt`：step 在某 worker、provider、tool 或 subagent 上的一次执行尝试。；`Job`：交给 durable queue 的可调度工作单元，不等于业务成功。；`Dependency`：决定 step 是否可运行的显式边或 join 条件。；`Condition`：基于受限输入和已完成结果的分支表达式。；`Loop`：有限、可预算、可 checkpoint 的重复执行结构。；`Compensation`：对已完成动作执行的反向或补救步骤，不保证物理回滚。；`Checkpoint`：某个 run/step cursor 上可加载的恢复视图。；`Signal`：外部或人工向运行发送的结构化事实或控制信息。；`Approval`：对具体动作、参数、范围和有效期的授权事实。；`Steering`：用户改变当前 run 下一步策略的控制命令。；`Settlement`：结果、usage、cost、artifact、receipt 和终态的 durable 结算。；`Unknown Outcome`：可能已执行但无法确认结果的状态。
### Queue 与 Event 的差别
```text
Command -> Job -> Lease -> Attempt -> Event + Result/Receipt
```；Command 是意图。；Job 是待处理工作。；Lease 是临时所有权。；Attempt 是一次执行。；Event 是已发生事实。；Receipt 是可查询证明。
Event 不能无条件重新入队为同一副作用 Job。
## 职责边界
| 模块 | 负责 | 不负责 |
|---|---|---|
| `TaskService` | 目标、验收、交付、任务视图 | 直接执行节点 |
| `WorkflowRegistry` | definition、version、发布和兼容 | 运行时调度 |
| `Compiler` | 校验图、schema、policy 和执行计划 | 修改业务状态 |
| `RunCoordinator` | 创建 run、冻结 snapshot、控制生命周期 | 具体工具协议 |
| `DAGScheduler` | 可运行节点、依赖、条件、循环和 join | 业务副作用授权 |
| `DurableQueue` | enqueue、lease、heartbeat、retry、DLQ | 判断业务结果 |
| `Worker` | 验证 lease、执行 job、写 checkpoint 和 result | 越权扩大 scope |
| `StepExecutor` | 节点类型的执行适配 | 自行更改 workflow definition |
| `ApprovalService` | 请求、展示、解决和过期审批 | 自动扩大审批范围 |
| `SignalRouter` | 关联外部 signal 与 run/step | 伪造外部事实 |
| `CompensationManager` | 补偿计划、顺序和结果 | 承诺所有副作用可回滚 |
| `SubagentSupervisor` | child run、能力交集、结果合并 | 默认共享可变工作区 |
| `ArtifactStore` | 日志、输出、快照和交付引用 | 决定节点逻辑 |
| `ContextCompiler` | 选择模型可见资源 | 改写 durable step 状态 |
| `PolicyEngine` | visibility、call、approval、execution、egress | 生成 workflow graph |
| `SandboxBackend` | 文件、进程、网络和资源边界 | 代替业务审批 |
| `State/Event Store` | append-only facts、CAS、replay、projection | 产生模型行为 |
| `Harness` | 装配、监督、预算、取消、恢复和交付 | 变成 God Object |
| `HostAdapter` | 协议、事件投影、控制命令和 artifact 交付 | 推断 durable truth |
强制关系：
```text
Definition explains structure.
Compiler validates executable contract.
Policy authorizes action.
Sandbox enforces effect boundary.
Queue owns work delivery.
Worker owns temporary execution.
State records facts.
Harness supervises lifecycle and recovery.
Host projects facts and submits controls.
```
## 总体架构与包布局
```text
Host Request / API / Batch
  -> Auth + TenantContext
  -> Task Intake + Workflow Resolver
  -> Definition Registry + Version Compiler
  -> Run Coordinator
  -> Policy / Budget / Quota Admission
  -> Durable Queue + Scheduler
  -> Worker Lease
  -> Workflow Runtime
      ├─ DAG / Condition / Loop / Parallel Engine
      ├─ Model / Prompt / Context Runtime
      ├─ Tool Runtime / Approval / Sandbox
      ├─ Subagent Supervisor
      ├─ Artifact / State / Checkpoint
      └─ Compensation / Recovery
  -> Event Store / Result Store / Usage Ledger
  -> Projector / Host Delivery / Audit / Evaluation
```
推荐包布局：
```text
packages/workflow/
  contracts.ts
  definition.ts
  versioning.ts
  compiler.ts
  graph.ts
  expressions.ts
  loop.ts
  parallel.ts
  compensation.ts
  run.ts
  step.ts
  attempt.ts
  checkpoint.ts
  replay.ts
  migration.ts
  testkit/
packages/workflow-runtime/
  coordinator.ts
  scheduler.ts
  queue.ts
  worker.ts
  executor.ts
  approvals.ts
  steering.ts
  signals.ts
  recovery.ts
packages/workflow-adapters/
  model-step.ts
  tool-step.ts
  subagent-step.ts
  human-step.ts
  artifact-step.ts
```
依赖方向：
```text
Host -> Workflow Product Port -> RunCoordinator
Coordinator -> Registry/Compiler/Policy/Queue/State
Runtime -> Model/Prompt/Context/Tool/State/Artifact ports
Worker -> Lease + Harness + Sandbox ports
Infrastructure -> Queue/Event/Store/Provider adapters
```
Workflow 核心不得导入具体 CLI、数据库 ORM、provider SDK 或 shell 实现。
## Workflow Definition 与 Version
### Definition 组成
一个 definition 至少包含：；workflow identity、display name 和 owner。；schemaVersion 与 definitionVersion。；inputSchema、outputSchema 和 errorSchema。；nodes、edges、join、condition、loop 和 compensation。；step type、capability requirements 和 side-effect class。；timeout、retry、idempotency、budget 和 concurrency policy。；approval、steering、signal 和 cancellation policy。；tenant、workspace、egress、retention 和 artifact policy。；migration hints 和 backward compatibility。；provenance、review、publishedBy 和 contentHash。
### 不可变版本；发布后的 `WorkflowVersion` 不可修改。；修改节点、schema、条件、权限、超时、retry 或 tool binding 必须生成新版本。；run 永远引用具体 version，不只引用 workflow name。；draft 可以编辑，但不可被生产 run 引用。；version hash 覆盖规范化 definition、schema、policy references 和 compiler version。；同一个 version 在不同 worker 上必须得到同一执行计划。
### 发布状态
```text
draft -> validating -> reviewed -> published -> deprecated -> retired
```；draft 只允许测试和 preview。；validating 检查 schema、图、表达式、能力和 policy。；reviewed 需要人或治理规则确认高风险动作。；published 可被新 run 选择。；deprecated 不接收新 run，但允许旧 run 继续或迁移。；retired 只能被 replay、audit 或显式恢复使用。
### Definition 版本选择
版本选择必须记录：；requested workflow ID/version constraint。；resolved version。；tenant/workspace default。；rollout、canary 或 pinned rule。；registry version。；selection reason。；compile version。
运行中不能因 registry 更新自动切换版本。
## Task、Workflow、Run、Step、Attempt 与 Job
### Task
Task 是产品层对象，包含：；objective、constraints 和 acceptance criteria。；requested workflow 或 mode。；workspace、input artifacts 和 privacy choices。；priority、deadline 和 delivery preference。；user steering、approval 和 feedback。；一个或多个 run 引用。
Task 可以在一次 run 失败后创建新的 resume run，但不能覆盖历史 run。
### Workflow
Workflow 是逻辑身份和版本集合：；workflowId。；owner 和 tenant scope。；current published version。；allowed version range。；default policy。；usage、quality 和 deprecation metadata。
### Run
Run 是执行边界，冻结：；task、workflow、version。；tenant、workspace、principal 和 branch。；input snapshot 和 output contract。；model/provider/toolset/context/policy/sandbox snapshot。；budget、quota、deadline 和 cancellation token。；route、artifact、checkpoint 和 delivery refs。
### Step
Step 是逻辑节点，不等于一次 worker 执行：；stepId 和 nodeId。；dependency status。；current state。；input/output refs。；attempt history。；child jobs、approval 和 signal refs。；compensation status。；checkpoint cursor。
### Attempt
Attempt 记录一次尝试：；attemptId、stepId、jobId 和 worker lease。；provider/model/tool/subagent identity。；start/end、timeout 和 cancellation。；retry ordinal、idempotency key。；request/result/receipt refs。；usage、cost 和 diagnostics。；side-effect status。；outcomeKnown 和 recovery status。
### Job
Job 是 durable queue 工作单元：；jobId、runId、stepId、attemptId。；frozen snapshots。；capability requirements。；priority、partition、deadline。；retry、lease 和 checkpoint refs。；idempotency/dedup keys。；status、attemptCount 和 last error。
## 核心数据模型
### 标识与状态
```typescript
type TaskId = string; type WorkflowId = string; type WorkflowVersionId = string; type RunId = string; type StepId = string; type AttemptId = string; type JobId = string; type CheckpointId = string; type SignalId = string; type ApprovalId = string; type CompensationId = string;
type RunStatus = "created" | "admitted" | "queued" | "running" | "waiting" | "paused" | "cancelling" | "cancelled" | "completed" | "failed" | "partial" | "unknown" | "expired" | "blocked";
type StepStatus = "pending" | "ready" | "queued" | "leased" | "running" | "waiting" | "paused" | "succeeded" | "failed" | "skipped" | "cancelled" | "compensating" | "compensated" | "partial" | "unknown" | "blocked";
type AttemptStatus = "created" | "started" | "streaming" | "waiting" | "succeeded" | "failed" | "timed_out" | "cancelled" | "unknown" | "recovered";
```
### WorkflowDefinition
```typescript
interface WorkflowDefinition {
  workflowId: WorkflowId;
  versionId: WorkflowVersionId;
  schemaVersion: string;
  name: string;
  description?: string;
  owner: WorkflowOwner;
  inputSchema: JsonSchema;
  outputSchema: JsonSchema;
  errorSchema?: JsonSchema;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  policies: WorkflowPolicies;
  compensation?: CompensationPlan;
  migration?: MigrationHints;
  provenance: DefinitionProvenance;
  contentHash: string;
  status: "draft" | "validating" | "reviewed" | "published" | "deprecated" | "retired";
}
```
### WorkflowNode 与 Edge
```typescript
interface WorkflowNode {
  nodeId: string;
  key: string;
  type: "model" | "tool" | "subagent" | "human" | "condition"
    | "parallel" | "map" | "loop" | "join" | "artifact" | "transform" | "wait";
  inputSchema?: JsonSchema;
  outputSchema?: JsonSchema;
  config: unknown;
  capabilities: CapabilityRequirement[];
  sideEffect: "none" | "read" | "write_reversible" | "write_external" | "high_risk";
  timeout: TimeoutPolicy;
  retry: RetryPolicy;
  idempotency: IdempotencyPolicy;
  compensationRef?: string;
}
interface WorkflowEdge {
  from: string;
  to: string;
  kind: "success" | "failure" | "always" | "condition" | "loop_back" | "join";
  condition?: Expression;
  priority?: number;
}
```
### Run、Step 与 Attempt
```typescript
interface WorkflowRun {
  runId: RunId;
  taskId: TaskId;
  workflowId: WorkflowId;
  workflowVersionId: WorkflowVersionId;
  tenant: TenantContext;
  workspace?: WorkspaceContext;
  status: RunStatus;
  input: InputRef;
  output?: OutputRef;
  contextSnapshotId: string;
  policySnapshotId: string;
  toolsetSnapshotId: string;
  sandboxSnapshotId: string;
  budgetReservationId: string;
  deadlineAt?: string;
  currentCursor: WorkflowCursor;
  checkpointId?: CheckpointId;
  childRunIds: RunId[];
  createdAt: string;
  updatedAt: string;
}
interface WorkflowStep {
  runId: RunId;
  stepId: StepId;
  nodeId: string;
  status: StepStatus;
  dependencyState: DependencyState;
  input?: InputRef;
  output?: OutputRef;
  attempts: AttemptRef[];
  activeAttemptId?: AttemptId;
  compensation?: CompensationState;
  checkpointId?: CheckpointId;
  startedAt?: string;
  completedAt?: string;
}
interface StepAttempt {
  attemptId: AttemptId;
  runId: RunId;
  stepId: StepId;
  jobId: JobId;
  status: AttemptStatus;
  ordinal: number;
  idempotencyKey: string;
  leaseId?: string;
  workerId?: string;
  executionRef?: string;
  requestRef?: ArtifactRef;
  resultRef?: ArtifactRef;
  receiptRefs: ArtifactRef[];
  outcomeKnown: boolean;
  error?: NormalizedError;
  usage?: Usage;
  cost?: CostBreakdown;
  startedAt: string;
  endedAt?: string;
}
```
### Job、Lease、Checkpoint
```typescript
interface WorkflowJob {
  jobId: JobId;
  runId: RunId;
  stepId: StepId;
  attemptId: AttemptId;
  tenantId: string;
  scope: ScopeRef;
  payloadHash: string;
  configSnapshotId: string;
  policySnapshotId: string;
  capabilityRequirements: CapabilityRequirement[];
  queueId: string;
  partitionKey: string;
  priority: number;
  availableAt: string;
  deadlineAt?: string;
  retryPolicy: RetryPolicy;
  idempotencyKey: string;
  status: "created" | "queued" | "leased" | "running" | "waiting" | "completed" | "failed" | "unknown" | "dead_lettered";
}
interface WorkflowLease {
  leaseId: string;
  jobId: JobId;
  workerId: string;
  leaseVersion: number;
  fencingToken: string;
  issuedAt: string;
  heartbeatAt: string;
  visibilityUntil: string;
  expiresAt?: string;
  status: "active" | "renewing" | "expired" | "released" | "recovered";
}
interface WorkflowCheckpoint {
  checkpointId: CheckpointId;
  runId: RunId;
  cursor: WorkflowCursor;
  stateHash: string;
  stepStates: StepCheckpoint[];
  pendingJobs: JobRef[];
  pendingApprovals: ApprovalRef[];
  pendingSignals: SignalRef[];
  artifactRefs: ArtifactRef[];
  snapshotRefs: SnapshotRef[];
  schemaVersion: string;
  createdAt: string;
}
```
## TypeScript 接口
### Registry 与 Compiler
```typescript
interface WorkflowRegistry { get(workflowId: WorkflowId, version?: VersionConstraint): Promise<WorkflowDefinition>; publish(input: PublishWorkflowInput): Promise<PublishReceipt>; deprecate(workflowVersionId: WorkflowVersionId, reason: string): Promise<void>; list(scope: ScopeRef, filter?: WorkflowFilter): Promise<WorkflowSummary[]>; }
interface WorkflowCompiler { validate(definition: WorkflowDefinition): Promise<CompileReport>; compile(definition: WorkflowDefinition, context: CompileContext): Promise<ExecutionPlan>; explain(planId: string): Promise<ExecutionPlanExplanation>; }
```
### Coordinator 与 Runtime
```typescript
interface WorkflowCoordinator { start(input: StartWorkflowRequest): Promise<RunAdmissionReceipt>; resume(input: ResumeWorkflowRequest): Promise<RunAdmissionReceipt>; pause(input: PauseWorkflowRequest): Promise<ControlReceipt>; cancel(input: CancelWorkflowRequest): Promise<ControlReceipt>; signal(input: SignalRequest): Promise<SignalReceipt>; steer(input: SteeringRequest): Promise<ControlReceipt>; inspect(runId: RunId, scope: ScopeRef): Promise<WorkflowRunView>; }
interface WorkflowRuntime { schedule(runId: RunId): Promise<void>; execute(job: WorkflowLease): Promise<JobResult>; recover(input: RecoveryRequest): Promise<RecoveryDecision>; replay(input: ReplayRequest): Promise<ReplayReport>; }
```
### Queue 与 Worker
```typescript
interface WorkflowQueue { enqueue(job: WorkflowJob, idempotencyKey: string): Promise<JobReceipt>; lease(filter: LeaseFilter, worker: WorkerIdentity): Promise<WorkflowLease | undefined>; heartbeat(lease: WorkflowLease, progress?: ProgressSnapshot): Promise<LeaseReceipt>; ack(lease: WorkflowLease, result: JobResult): Promise<void>; nack(lease: WorkflowLease, error: NormalizedError): Promise<NackReceipt>; cancel(jobId: JobId, scope: ScopeRef): Promise<CancelReceipt>; recoverExpired(leaseId: string): Promise<RecoveryDecision>; }
interface WorkflowWorker { start(lease: WorkflowLease): Promise<RunningJob>; stop(input: StopWorkerRequest): Promise<void>; capabilities(): WorkerCapabilities; }
```
### Control 与 Signals
```typescript
interface ApprovalService { request(input: ApprovalRequest): Promise<ApprovalRef>; resolve(input: ApprovalResolution): Promise<ApprovalReceipt>; expire(approvalId: ApprovalId, reason: string): Promise<void>; }
interface SignalRouter { append(input: SignalInput): Promise<SignalReceipt>; route(signalId: SignalId): Promise<SignalRoutingResult>; listPending(runId: RunId): Promise<SignalRef[]>; }
```
## 输入输出 Schema 与契约
### Input Schema
每个 workflow、node、tool 和 subagent 都应有明确 input schema：；字段类型、必填、默认值和枚举。；sensitivity、provenance 和 source mapping。；最大字节、数组长度和递归深度。；是否允许 artifact reference。；是否允许模型生成。；是否允许用户 steering 覆盖。；是否需要业务系统二次校验。
schema 校验必须在 admission、step enqueue、worker start 和 external signal 入口重复执行必要部分。
### Output Schema
Output schema 需要区分：；成功业务输出。；警告、诊断和 partial output。；artifact references。；side-effect receipts。；unknown outcome。；compensation result。；user-visible summary。
模型生成 JSON 不等于通过 output schema；必须执行解析、schema、业务约束和 provenance 校验。
### Error Schema
```typescript
interface WorkflowErrorEnvelope {
  code: string;
  category: "validation" | "policy" | "capacity" | "timeout" | "dependency"
    | "provider" | "tool" | "workspace" | "conflict" | "unknown" | "system";
  retryable: boolean;
  outcomeKnown: boolean;
  safeMessage: string;
  diagnosticRef?: ArtifactRef;
  causeRefs?: string[];
  recoveryHint?: string;
}
```
### Contract 不变量；下游输入来自上游已 settlement 的 output ref。；schema version 必须可解析。；未知字段按 definition policy 保留或拒绝，不能静默丢弃关键字段。；artifact ref 必须经过 scope 和 egress 检查。；error 不能覆盖已经确认的 side-effect receipt。；partial output 必须标识 incomplete 和 source step。
## DAG、依赖与拓扑执行
### 图模型
Workflow graph 是有向图，节点可以是普通 step、condition、parallel、map、loop、join 或 compensation node。
编译期必须检查：；node ID 唯一。；edge 指向存在的节点。；必需输入存在可达来源。；success/failure/always 边语义不冲突。；非 loop_back 图不存在意外环。；join 的入边和完成策略明确。；terminal node 可达。；compensation 引用存在。；capability、schema 和 policy 可解析。；图大小、深度、fan-out 和 loop 上限不超预算。
### 拓扑调度
```text
load current cursor
  -> find pending nodes
  -> evaluate dependency states
  -> mark ready nodes
  -> apply condition and policy
  -> reserve budget/capacity
  -> create step attempt and job
  -> enqueue durable job
```
调度器不得依据 UI 视图或 worker 内存状态判断依赖完成。
### 依赖状态；`satisfied`：前置 step 成功且输出可用。；`failed`：前置 step 明确失败。；`skipped`：条件未选择或被策略跳过。；`unknown`：前置结果未确认。；`waiting`：等待 signal、approval、时间或外部状态。；`partial`：前置只有部分结果可用。
### 失败传播
Definition 必须声明：；fail-fast。；continue-on-error。；best-effort join。；partial output allowed。；compensation required。；manual intervention。
默认不把 `unknown` 当作 `failed`，也不把 `partial` 当作 `succeeded`。
## 条件、分支与表达式
### 表达式边界
Condition 只能读取受限、版本化、已 settlement 的数据：；workflow input。；task metadata。；step output summary。；signal payload。；policy snapshot 中允许的字段。；当前时间和预算剩余量。
Condition 不得直接读取：；任意文件系统。；secret 原文。；未授权 session 或 memory。；provider raw payload。；worker 环境变量。；未完成 attempt 的流式 delta。
### Expression 规则；解析器采用 allowlist AST。；禁止任意代码执行。；限制计算深度、字符串长度和集合大小。；对 null、unknown、missing 做显式三值逻辑。；记录表达式版本和输入 hash。；条件结果成为 durable decision entry。
### 三值逻辑
```text
true -> true 分支；false -> false 分支；unknown -> 等待、人工决定或安全失败，取决于 definition
```
涉及外部副作用的 unknown 不得自动走“继续发送”。
### Branch
分支步骤必须记录：；evaluated expression。；sanitized input snapshot。；result。；selected edges。；non-selected edges。；policy and budget decision。
不应在 host 断线后重新评估条件而改变历史路径。
## 循环、Map 与动态 Fan-out
### Loop
循环必须声明：；最大迭代次数。；最大 wall-clock。；每轮 input/output schema。；退出条件。；是否允许人工 steering。；每轮 checkpoint 间隔。；单轮和总预算。；失败和 unknown 策略。
```text
loop_start -> iteration_ready -> iteration_running -> iteration_settled
     ^                                             |
     +------------- continue condition ------------+
```
### Map
Map 对输入集合创建有限的 child step：；集合来源必须是已验证 output。；最大 fan-out 在 compile/admission/runtime 都检查。；每个 item 有稳定 item key。；item job 的 idempotency key 包含 run、node、item key 和 version。；支持 all、any、quorum、best-effort join。；失败 item 不得丢失其 result/receipt。
### 动态 Fan-out
动态生成节点必须写入 `ExpansionEntry`：
```typescript
interface ExpansionEntry {
  expansionId: string;
  runId: RunId;
  parentStepId: StepId;
  itemKeys: string[];
  childStepIds: StepId[];
  sourceHash: string;
  maxChildren: number;
  createdAt: string;
}
```
扩展一旦 durable commit，不因重复 worker 执行而再次创建同一 child。
### 循环安全；不允许由模型自行修改 loop bound。；steering 只能收紧或在 policy 允许范围内改变下一轮。；loop 状态必须可从 checkpoint 重建。；循环中的外部写操作必须有幂等或补偿。；超过预算进入 `expired`、`partial` 或 `blocked`，不能无限运行。
## 并行、Join 与资源协调
### Parallel
并行节点应先创建 durable group：；groupId、parent step、child set。；concurrency limit。；resource locks。；budget reservation。；cancellation mode。；join policy。
### Join 策略；`all_success`：全部成功才成功。；`all_settled`：全部进入终态后给出聚合结果。；`any_success`：一个成功即可结束，其余 cancel 或继续 cleanup。；`quorum`：达到阈值即可结束。；`best_effort`：收集成功、失败和 unknown。；`manual`：等待用户选择如何处理剩余 child。
### 并发与锁
资源锁 key 必须使用 canonical resource ID：；workspace/path。；branch/worktree。；provider/deployment。；artifact/version。；external business key。；tenant quota bucket。
锁只保护协调，不证明业务动作可回滚。
### 取消传播；parent cancel 默认向 child 发送 cancel requested。；child 已进入 unknown 不应盲目重试。；`any_success` 的 loser child 需要保留取消和清理事件。；detached background child 必须有独立 scope、预算和通知策略。；child 不能因 parent host disconnect 自动假定取消。
## 补偿、Saga 与部分成功
### 补偿不是回滚保证
外部动作可能不可逆；compensation 只能尝试减少影响。
```text
forward step success
  -> durable side-effect receipt
  -> later failure
  -> compensation plan
  -> compensation attempt
  -> compensated | compensation_failed | manual
```
### CompensationPlan
```typescript
interface CompensationPlan {
  entries: CompensationEntry[];
  order: "reverse_completion" | "definition_order" | "dependency_order";
  maxAttempts: number;
  requireApproval: boolean;
  unknownPolicy: "pause" | "manual" | "continue";
}
interface CompensationEntry {
  compensationId: CompensationId;
  forwardNodeId: string;
  compensationNodeId: string;
  trigger: "failure" | "cancel" | "timeout" | "manual";
  idempotencyTemplate: string;
}
```
### Partial Success
partial 结果必须包含：；已成功 step。；已失败 step。；unknown step。；skipped step。；compensation 状态。；可交付 artifacts。；未满足 acceptance criteria。；下一步建议。
产品不能只显示“工作流失败”而隐藏已经产生的外部变化。
### Unknown Outcome
以下情况应进入 unknown：；worker 在外部写请求后崩溃。；provider remote job 已提交但状态不可查。；HTTP 连接断开且无 request receipt。；lease 过期但 execution record 不完整。；tool 返回 timeout，无法确认是否执行。；artifact upload 收到部分响应。
unknown 的默认动作：；停止同一副作用的自动重试。；查询外部状态或 receipt。；将 run 标记为 waiting、unknown 或 manual。；允许只读诊断和安全补偿。；需要新 idempotency key 时显式创建新 attempt。
## Durable Queue、Lease 与 Worker
### Admission
```text
authenticate
  -> resolve tenant/workspace/session/run
  -> validate command and definition
  -> evaluate policy and capability
  -> reserve budget/quota/capacity
  -> freeze snapshots
  -> create run/step/job records
  -> append accepted events and outbox
  -> enqueue durable job
  -> return receipt
```
没有 scope、policy snapshot、budget reservation、idempotency key 和 payload hash，不得入队。
### Lease
Worker 领取 job 时原子检查：；job status 可领取。；availableAt 和 deadline 有效。；partition barrier 满足。；worker capability 满足。；tenant quota 允许。；lease/CAS 成功。；policy/config snapshot 仍可验证。
### Heartbeat
Heartbeat 只能延长临时所有权，不得改变：；tenant。；workflow version。；policy。；budget。；input payload。；side-effect authorization。
Heartbeat 失败时：；transient store error 只在 lease margin 内重试。；lease conflict 立即停止提交结果。；worker clock skew 使用 store time。；policy revoke 停止新的高风险动作。；lease expired 进入 recovery probe。
### Queue 分层
建议区分：
```text
interactive-run
approval-resume
background-run
subagent
compensation
recovery
artifact
notification
migration
```
每类队列应有独立 capacity、retry、SLO、retention 和 fairness。
### Worker 隔离
Worker 使用：；`RunScopeContext`。；config/policy/toolset/model snapshot。；sandbox profile。；fencing token。；budget lease。；artifact namespace。；event cursor。
Worker 不得从 job payload 的普通字符串自行选择 tenant、region、credential 或 workspace。
## Step Attempt、Timeout、Retry 与 Idempotency
### Timeout 分层
必须分开：；admission timeout。；queue wait timeout。；lease visibility timeout。；step wall-clock timeout。；attempt execution timeout。；provider first-event/total timeout。；tool timeout。；approval timeout。；external status-query timeout。；compensation timeout。
visibility timeout 不是业务 wall-clock timeout。
### Retry 层级
```text
transport retry  同一安全请求内的连接重试
agent retry      改变 context 或生成参数的新 attempt
provider fallback 新 provider/model/deployment attempt
 tool retry      tool runtime 内的受控重试
queue retry      同一 job 重新调度
recovery retry   查询状态、补写结果或加载 checkpoint
compensation     对已发生动作执行补救
```
### RetryPolicy
```typescript
interface RetryPolicy {
  maxAttempts: number;
  maxElapsedMs: number;
  backoff: "none" | "fixed" | "exponential_jitter";
  baseDelayMs: number;
  maxDelayMs: number;
  retryableCategories: string[];
  requireStatusQueryForSideEffects: boolean;
  retryUnknown: "never" | "status_query" | "manual";
  deadLetterAfterExhaustion: boolean;
}
```
### Idempotency
稳定键应包含：
```text
tenant + workflowVersion + run + step + logical item + operation
```
幂等记录至少包含：；idempotency key。；payload hash。；first attempt。；current outcome。；result/receipt refs。；expiry。；scope。
同 key 同 payload 返回原 receipt；同 key 不同 payload 返回 conflict；unknown 不得直接当作未执行。
### Dedup 与并发；dedup 只能合并明确相同的逻辑工作。；不同 step attempt 不应共享可变 result。；queue duplicate delivery 由 execution record 和 idempotency 防护。；fence 失效的 worker 不得写 terminal result。；provider request 可能成功时先查询状态，再决定新 attempt。
## Checkpoint、Replay 与恢复
### Checkpoint 内容
checkpoint 至少保存：；run cursor。；definition/version hash。；node/edge evaluation facts。；step 状态和 output refs。；pending jobs、approval、signal 和 timer。；loop iteration、map expansion 和 join state。；budget、usage、cost 和 retry counters。；toolset、model、context、policy、sandbox snapshots。；artifact、receipt 和 side-effect ledger refs。；schema/reducer version。
### Checkpoint 时机；run admission 后。；每个 step durable settlement 后。；branch/condition 决策后。；loop iteration 后。；map expansion 后。；approval/signal 等待前后。；pause/cancel 请求处理后。；compensation phase 切换后。；关键 artifact 和 external receipt 保存后。
### Replay 模式；`semantic`：只重建状态和事件。；`recorded`：使用已记录 provider/tool result。；`deterministic`：使用 scripted model、fake tool、固定 clock/id。；`simulated`：运行隔离模拟，不触发真实副作用。；`live_quarantined`：新 run、新 scope、新 policy 下的受控执行。
Replay 默认不重放真实副作用。
### 恢复流程
```text
load run and latest checkpoint
  -> verify tenant/scope/version/hash
  -> read events after checkpoint
  -> reconcile jobs/leases/attempts
  -> inspect side-effect receipts
  -> classify unknowns
  -> rebuild ready queue
  -> resume or pause for manual decision
```
历史 event immutable；恢复通过新 event 和新 attempt 表达。
## Pause、Resume、Cancel 与 Signal
### Pause
pause 是协调状态，不等于杀死所有进程：；停止创建新的高风险 step job。；允许当前安全边界内的步骤完成或进入 checkpoint。；等待中的 approval、signal 和 timer 保留。；background child 按 policy 决定暂停或独立运行。；写入 pause requested 与 paused durable event。
### Resume
resume 必须重新验证：；principal、membership 和 tenant scope。；workflow version 是否仍可恢复。；policy、egress、sandbox 和 budget。；pending approval 是否过期。；unknown side effect 是否已解决。；workspace/baseline 是否变化。
resume 可继续原 run，也可创建新 run；两者必须显式记录。
### Cancel
cancel 状态至少区分：；cancel requested。；cancelling。；cancelled。；cancel blocked。；unknown。；partial after cancel。
取消不撤销已经发生的外部动作；必要时触发 compensation。
### Signal
Signal 需要：；signalId、type、source、scope、schemaVersion。；causation/correlation。；payload hash 和敏感度。；target run/step/wait handle。；receivedAt、verifiedAt 和 expiry。
外部 webhook 不能因为带有 runId 就自动被信任；必须认证、验签、去重和 scope check。
### Timer 与等待
wait step 记录：；wait reason。；resume condition。；deadline。；external correlation key。；status query policy。；checkpoint。
不可只把睡眠线程当作 durable timer。
## Human Approval 与 Steering
### Approval
审批请求必须展示：；具体 step、tool 或 external action。；material parameters。；影响的 workspace、文件、资源或数据。；provider、region、模型和 egress。；side-effect class、可逆性和预计成本。；sandbox、network 和 secret binding。；expiry、approver scope 和 approval version。；deny、edit、approve、approve_once 和 approve_scope。
审批是动作授权，不是通用 consent，也不是永久 policy。
### Approval 不变量；approval token 绑定 payload hash、definition version、step、scope 和 expiry。；参数变化后旧 approval 失效。；parent approval 不自动覆盖 child run。；host ack 不等于 approval resolved。；过期 approval 不可恢复执行。；approval event durable 后才允许 enqueue 高风险 job。
### Steering
steering 可以：；修改未开始 step 的输入。；改变下一个 branch 的用户选择。；收紧预算、范围或工具。；要求暂停、复核或人工处理。；请求重新规划但创建新的 plan/attempt。
steering 不可以：；修改已完成历史。；直接改变 tenant、owner、policy safety floor。；将 unknown 伪造为 success。；无审批升级高风险动作。；改写已发出的 provider/tool request。
## Subagent 编排
### Child Run
subagent 应建模为 child run，而不是普通文本调用：；parentRunId、childRunId。；child workflow/version 或 subagent spec。；capability intersection。；workspace view、artifact scope 和 context package。；budget reservation 和 deadline。；parent cancellation policy。；result schema 和 evidence requirements。
### Capability 交集
```text
child capabilities
  = requested capabilities
  ∩ parent assignment
  ∩ tenant policy
  ∩ workspace view
  ∩ toolset/policy
  ∩ sandbox
  ∩ budget
```
### Child 结果
ChildResult 必须包含：；status、summary、structured output。；artifact refs、evidence refs 和 test results。；usage、cost 和 child run receipt。；failed、partial、unknown 的区分。；允许父级消费的字段。；provenance 和 scope。
父级不得仅凭 child 的自然语言声称完成任务。
### Fan-out；child 数量受 maxFanout、预算、租户 quota 和 worker capacity 限制。；child creation 具备稳定 idempotency key。；parent join 按显式策略聚合。；child memory、artifact、workspace 和 provider cache 默认隔离。；child 的 high-risk action 仍需独立 policy/approval。
## Tool、Artifact 与 Context 集成
### Tool Step
Tool step 必须记录：；ToolSpec/version。；输入 schema 和 canonical arguments hash。；visibility、call、approval、execution、egress decision。；sandbox profile、workspace view 和 secret binding。；timeout、retry 和 idempotency。；ToolExecution receipt、artifact refs 和 side effects。
Tool result 分为：；model-facing summary。；user-facing result。；durable structured result。；diagnostic artifact。；side-effect receipt。
### Artifact Step
Artifact 用于：；大型输入输出。；日志、diff、测试报告和截图。；workflow input/output package。；checkpoint、replay 和 forensics。；provider raw payload 的受控保存。
ArtifactRef 必须带 tenant、scope、owner、sensitivity、version、hash、retention 和 scan status。
### Context Step
ContextPlan 记录：；task、run、step purpose。；selected resource、memory、artifact 和 workspace slice。；source、authority、trust、freshness、sensitivity。；token/byte budget。；redaction、summary、offload、drop 原因。；provider target、egress snapshot 和 plan hash。
workflow 不应把整个前置步骤输出原文注入后续模型；应使用 schema、summary、artifact ref 或 range。
### Model Step
Model step 冻结：；`ResolvedModel`、route snapshot 和 catalog version。；Prompt template/compiler version。；ContextPlan。；Toolset snapshot。；output contract。；retry/fallback policy。；usage/cost ledger。
fallback 产生新 Attempt，并重新执行 capability、egress、budget 和 output contract 检查。
## Model、Prompt、State、Policy 与 Harness 集成
### Model
Workflow Runtime 只消费 provider-neutral `ModelPort`：；adapter 差异在 Provider Runtime 内封装。；stream 是事件流，不是字符串。；tool call 完成后才执行。；unknown provider outcome 进入恢复协议。；usage、cost、retry、fallback 归因到 step/attempt。
### Prompt
Prompt 负责解释 workflow context：；当前目标、步骤和完成标准。；上游结果是事实、摘要、artifact 还是推断。；当前可用工具和审批边界。；失败、unknown、partial 和等待状态。；模型不能自行修改 workflow graph 或 policy。
Prompt 不负责调度、租户授权、幂等和恢复。
### State/Event
Durable state 保存：；Task、Workflow、Run、Step、Attempt、Job 状态。；definition/version、schema、policy 和 snapshot refs。；condition、loop、map、join 和 compensation facts。；approval、steering、signal、pause、resume 和 cancel facts。；output、artifact、receipt、usage、cost 和 error。
Event log append-only；projector 生成 host、task、run、audit、evaluation 和 replay view。
### Policy
每个 step 执行前依次检查：
```text
visibility -> call -> approval -> execution -> egress
```
workflow definition 只能声明需要的 capability，不得授予自己权限。
### Harness
Harness 负责：；bootstrap 和 snapshot freeze。；structured concurrency。；cancel propagation。；budgets、quotas、deadlines。；checkpoint 和 recovery。；event routing、artifact settlement 和 delivery。；provider/tool/subagent 端口装配。；Host control 的幂等和版本检查。
Harness 不应把所有 DAG 规则、provider 适配和业务授权写进一个类。
## 租户、权限、Workspace 与 Sandbox
### Scope 层级
```text
Tenant -> User -> Workspace -> Project -> Session -> Run
       -> Workflow -> Step -> Attempt -> Job -> Tool/Subagent
```
不变量：；run tenant 必须等于 task、workflow owner、session、artifact、event 和 job tenant。；child run 默认继承 tenant，但不继承全部权限。；workflow version 的 owner 不能覆盖调用者 policy。；queue partition key 不是授权证明。；cache、checkpoint、artifact、trace 和 provider request 都带 scope。
### Permission
权限至少区分：；谁可以执行 workflow。；谁可以启动特定 version。；谁可以查看 run/step/artifact。；谁可以 approve、steer、pause、resume 或 cancel。；谁可以重放、fork、迁移和补偿。；谁可以查看敏感 diagnostics。
### Workspace；Workflow run 使用冻结的 `WorkspaceView`。；路径必须 canonicalize 和 containment check。；用户已有修改不可被 workflow step 静默覆盖。；branch/worktree/baseline 变化使相关 step approval 和 context 失效。；subagent 只能拿到显式授予的 roots 和 locks。
### Sandbox
Sandbox profile 由 policy 选择并由 backend 强制：；filesystem mounts。；network allowlist。；process、CPU、memory 和 wall-clock。；secret bindings。；temp/artifact/cache namespaces。；native host 或 remote worker attestation。
sandbox 不可用时：；低风险只读 step 可按 policy 降级。；写文件、外部网络、高风险工具默认 fail-closed。；不得静默回退到宿主 shell。
### Provider Egress
workflow 的每个 model/tool/artifact step 都重新检查：；data sensitivity。；purpose。；provider/model/region。；retention/training/remote object semantics。；redaction/summary view。；tenant/workspace policy。
fallback、hedging、shadow 和 replay 都不能绕过 egress。
## 生命周期与状态机
### Task 生命周期
```text
created -> normalized -> planned -> admitted -> running -> verifying
       -> delivered -> settled
created -> rejected | cancelled
running -> paused | waiting | partial | failed | unknown
```
### Run 生命周期
```text
created -> compiled -> admitted -> queued -> running
running -> waiting | paused | cancelling | completed | failed | partial | unknown
paused -> resuming | cancelled | expired
waiting -> running | expired | blocked | cancelled
cancelling -> cancelled | partial | unknown
```
### Step 生命周期
```text
pending -> ready -> queued -> leased -> running
running -> waiting | paused | succeeded | failed | partial | unknown | cancelled
failed -> retrying | compensating | blocked
succeeded -> compensating
compensating -> compensated | compensation_failed | manual
```
### Job 生命周期
```text
created -> admitted -> queued -> leased -> running
running -> checkpointed | waiting | completed | failed | unknown
failed -> retry_scheduled | dead_lettered
leased -> expired -> recovery_pending
```
### Attempt 生命周期
```text
created -> started -> streaming -> succeeded
started/streaming -> timed_out | failed | cancelled | unknown
unknown -> status_query | recovered | manual
```
### Approval 生命周期
```text
requested -> displayed -> approved | denied | edited | expired
approved -> consumed | invalidated
```
### Signal 生命周期
```text
received -> authenticated -> schema_validated -> matched -> consumed
received -> rejected | expired | duplicate
```
## 端到端决策流程
### Start
```text
HostRequest
  -> authenticate principal
  -> resolve tenant/workspace/session
  -> normalize TaskSpec
  -> resolve WorkflowVersion
  -> compile definition
  -> evaluate capability/policy/egress
  -> reserve quota/budget
  -> create Run and initial checkpoint
  -> enqueue root jobs
  -> return acceptance receipt
```
### Schedule
```text
event/step settlement
  -> load workflow cursor
  -> evaluate dependencies
  -> resolve conditions
  -> expand loop/map if allowed
  -> acquire locks and capacity
  -> request approval if needed
  -> create attempt/job
  -> durable enqueue
```
### Execute
```text
lease job
  -> verify fence and snapshots
  -> create execution context
  -> compile prompt/context or tool input
  -> policy/approval/sandbox check
  -> execute model/tool/subagent/human wait
  -> capture result/artifact/receipt
  -> validate output schema
  -> append attempt/step events
  -> checkpoint
  -> schedule downstream or compensation
```
### Deliver
```text
terminal event
  -> settle output/usage/cost/artifact
  -> build task/run projection
  -> notify host
  -> expose recovery or next action
```
### Resume
```text
resume command
  -> idempotency/version check
  -> load checkpoint and unresolved states
  -> revalidate tenant/policy/sandbox/egress/budget
  -> resolve approval/signal/unknown
  -> create new job or attempt
  -> continue from durable cursor
```
## 故障恢复、失败、未知结果与降级
### 错误分类；definition invalid：发布前拒绝。；input invalid：run 不入队。；policy denied：不可重试，需替代路径或用户决策。；capability mismatch：换兼容 step/version，不盲重试。；transient provider/tool：有限 retry 或 fallback。；dependency failed：按 graph failure policy 传播。；timeout：根据 side-effect 状态决定 retry、status query 或 unknown。；lease lost：停止提交，进入 recovery。；schema mismatch：暂停并迁移或人工处理。；budget exhausted：pause、partial 或 terminal。；external unknown：status query、compensation 或 manual。
### Recovery Coordinator
```typescript
interface WorkflowRecoveryCoordinator {
  inspect(runId: RunId): Promise<RecoveryInspection>;
  classify(runId: RunId): Promise<RecoveryClassification>;
  resume(input: RecoveryResumeRequest): Promise<ControlReceipt>;
  retryStep(input: RetryStepRequest): Promise<ControlReceipt>;
  compensate(input: CompensationRequest): Promise<ControlReceipt>;
  markManual(input: ManualResolutionRequest): Promise<ControlReceipt>;
}
```
### 安全降级
允许的降级：；从 streaming 降为 snapshot，若 host 支持。；从 rich artifact 预览降为安全摘要。；从 parallel 降为 bounded sequential。；从模型步骤降为人工审批或用户输入。；暂停非关键 background child。；使用已记录的 provider/tool result 做 semantic replay。
禁止的降级：；关闭 policy、sandbox 或 audit。；跨 region/provider 发送不允许数据。；用旧 approval 继续新参数。；将 unknown 写操作直接重放。；用模型自述覆盖 side-effect ledger。
## 版本发布、迁移与兼容
### 兼容轴
必须分别管理：；workflow definition version。；input/output schema version。；event schema version。；checkpoint/reducer version。；provider/tool adapter version。；policy/config snapshot version。；artifact schema version。
### 发布策略；draft validation。；deterministic testkit。；scenario/evaluation。；reviewed approval。；canary tenant/workspace。；gradual rollout。；deprecation window。；rollback 或 pin old version。
### Long-running Run
运行中的 run 默认继续使用原 version。
若必须迁移：；读取旧 checkpoint。；验证 migration plan 和 cursor mapping。；显式生成 `RunMigrated` event。；保留 old/new definition hash。；只迁移未开始或可安全重建的 step。；已完成 step 不重新执行。；unknown step 先解决，再迁移。；migration 失败回到旧 checkpoint 或 manual。
### Schema Migration
```typescript
interface WorkflowMigrationPlan {
  migrationId: string;
  fromVersion: WorkflowVersionId;
  toVersion: WorkflowVersionId;
  compatibility: "backward" | "forward" | "none";
  cursorMappings: CursorMapping[];
  inputUpcasters: string[];
  outputDowncasters?: string[];
  dryRunRequired: boolean;
  rollbackPlan: string;
}
```
历史事件不修改；projector 用 schema version 读取。
## 可观测性、指标与 SLO
### Durable Events
建议事件：；`task.created`、`task.accepted`、`task.delivered`。；`workflow.version_resolved`、`workflow.compiled`。；`run.created`、`run.admitted`、`run.started`、`run.completed`。；`step.ready`、`step.started`、`step.succeeded`、`step.failed`。；`attempt.started`、`attempt.completed`、`attempt.unknown`。；`job.enqueued`、`job.leased`、`job.retried`、`job.dead_lettered`。；`condition.evaluated`、`loop.iteration`、`map.expanded`、`join.settled`。；`approval.requested`、`approval.resolved`。；`signal.received`、`signal.consumed`。；`checkpoint.created`、`run.paused`、`run.resumed`、`run.cancelled`。；`compensation.started`、`compensation.completed`。；`artifact.created`、`usage.settled`、`cost.reconciled`。
### Ephemeral Events；model/tool progress。；heartbeat。；queue position。；streaming delta。；host delivery ack。；UI phase update。
### Trace 维度
```text
tenant_id
workspace_id
session_id
task_id
workflow_id
workflow_version_id
run_id
step_id
attempt_id
job_id
lease_id
provider/model/tool/subagent
artifact_id
policy_version
sandbox_profile
checkpoint_id
```
敏感内容使用 hash、分类、大小和 ArtifactRef，不把 secret、完整 prompt 或原始 tool args 直接写入 trace。
### 指标
队列与执行：；admission latency。；queue wait P50/P95/P99。；lease expiry rate。；heartbeat failure rate。；step success/failure/unknown rate。；retry amplification。；dead-letter rate。；checkpoint lag。；replay divergence。
图执行：；dependency resolution latency。；condition evaluation failure。；loop iterations。；map fan-out。；join partial rate。；compensation success rate。；orphan child rate。
用户与成本：；task completion rate。；acceptance criteria pass rate。；partial delivery rate。；approval wait time。；pause/resume success。；cancel settlement time。；model/tool/provider cost。；cost per successful task。；artifact bytes。
安全与隔离：；policy deny。；sandbox failure。；cross-tenant attempt。；egress denied。；approval bypass。；scope mismatch。；unknown side-effect count。
### SLO
SLO 必须分别定义：；request acceptance。；first durable event。；first user-visible progress。；step settlement。；complete run。；final delivery。；unknown resolution。；approval resume。；deletion/retention cleanup。；replay reconstruction。
不能以 HTTP 200 或模型最终文本成功率代替 workflow SLO。
## 安全、隐私与数据治理
### Data Inventory
Workflow 会产生：；task input、workflow definition 和 schema。；prompt/context/model request。；tool args/results、approval 和 signals。；step output、artifact、checkpoint 和 replay bundle。；provider request/response、usage 和 cost。；workspace snapshot、patch、logs 和 side-effect receipt。
每类数据都需要 source、owner、tenant、scope、sensitivity、purpose、retention、egress 和 deletion dependency。
### 最小化；step 之间优先传递结构化字段和 artifact ref。；不把完整历史 transcript 自动传给每个节点。；高敏感输入优先使用 redacted view、summary 或 artifact_only。；workflow graph 不把 secret 写入 definition。；approval 卡片只显示必要 material parameters。；audit 保存 decision evidence，不复制完整 payload。
### Retention
不同对象分开保留：；definition/version。；run/step/attempt event。；artifact/log。；provider remote object。；checkpoint/replay。；approval/audit。；queue job/dead-letter。
删除 workflow 不应误删已完成 run 的业务事实；删除 run 也不应绕过 legal hold、audit 或 external receipt。
### DSAR 与导出
导出和删除必须覆盖：；task、run、step、attempt。；artifacts、logs、checkpoints。；model/provider request references。；queue history、notifications 和 projections。；child run 和 compensation。；backup、export package 和 provider remote binding。
## 测试策略与 Evaluation
### Unit；definition schema。；graph cycle detection。；topological ordering。；condition tri-state evaluation。；loop bound。；map expansion。；join policy。；compensation order。；retry/backoff。；idempotency key。；timeout classification。；cursor migration。；state transition guards。
### Component；fake registry。；deterministic compiler。；in-memory and durable queue。；scripted worker。；fake approval provider。；deterministic clock/ID/random。；fake model/tool/subagent。；side-effect recorder。；fake artifact store。；replay runner。
### Integration；coordinator + queue + worker + event store。；ModelStep + ContextPlan + Provider Runtime。；ToolStep + Policy + Sandbox + Artifact。；Subagent fan-out + parent join。；approval resume + host delivery。；checkpoint crash recovery。；schema migration。；multi-tenant partition。；provider fallback and egress。
### Scenario Fixtures
至少覆盖：；线性 DAG。；条件分支。；bounded loop。；map fan-out。；parallel quorum。；dependency failure with compensation。；approval pause/resume。；steering before unstarted step。；cancel during tool execution。；provider unknown outcome。；lease expiry and duplicate delivery。；partial success。；dead-letter recovery。；version migration。；cross-tenant denial。；sandbox unavailable。；artifact scan pending。
### Deterministic Assertions
必须检查：；event sequence。；status transition。；step execution count。；idempotency receipts。；provider/tool request。；side-effect ledger。；checkpoint contents。；output schema。；approval payload hash。；scope and policy snapshot。；budget/cost settlement。
### LLM Judge 边界
LLM judge 只能评估：；任务语义完成度。；workflow 最终解释质量。；用户可读性。；计划是否合理。
LLM judge 不得判断：；是否实际运行。；是否满足权限。；是否真的写文件或发送外部请求。；是否发生重复副作用。；是否已完成 compensation。；是否满足 SLO、TTL、lease 和幂等。
### Fault Injection
注入：；queue store timeout。；worker crash before/after side effect。；lease heartbeat loss。；provider 429/5xx/EOF。；tool partial side effect。；approval stale。；signal duplicate/out-of-order。；event append conflict。；artifact upload partial。；sandbox mount failure。；budget reservation failure。；policy revoke during run。
### Online Evaluation
生产反馈只在脱敏、去重、最小化和审核后进入 regression dataset：；任务成功/失败。；用户纠正和 steering。；人工接管。；unknown 和 partial outcome。；cost、latency、approval wait。；安全 deny 和恢复质量。
## 反模式与审查规则
1. 只有一个 `isRunning` 字段，没有 Run、Step、Attempt 和 Job 分层。
2. 把 workflow definition 和 run state 存在同一份可变 JSON 中。
3. 运行中自动读取 latest workflow version。
4. 用 prompt 描述 DAG，而不保存可执行 definition。
5. 只按拓扑顺序循环扫描，不保存 cursor 和 checkpoint。
6. 将 condition 表达式当作任意 JavaScript 执行。
7. 模型可以自行修改 loop bound 或 fan-out 数量。
8. 并行 step 没有 join policy 和资源锁。
9. 把 queue visible 当作旧 worker 未执行。
10. 任何 timeout 都自动 retry。
11. unknown 外部写操作自动重新发送。
12. 没有 idempotency receipt 和 payload hash。
13. approval 只记录按钮点击，不绑定参数和版本。
14. parent approval 自动覆盖 child。
15. pause 只停止 UI，不停止调度器。
16. cancel 只关闭 host socket，不记录 durable control。
17. host ack 被当作 run complete。
18. subagent 共享父级全部 workspace、artifact 和 secret。
19. child result 只返回自然语言，不返回 evidence/ref。
20. step 输出全文无界注入后续 context。
21. compensation 被宣传为任意副作用回滚。
22. partial success 被显示为 failed 或 success 的单一状态。
23. unknown 被隐藏为 failed。
24. dead-letter 自动无限重放。
25. migration 修改历史 event。
26. replay 直接触发真实支付、删除、部署或消息发送。
27. queue 没有 tenant fairness 和 noisy-neighbor 防护。
28. worker lease 过期后仍可提交结果。
29. sandbox 失败静默回退到宿主进程。
30. policy deny 通过 fallback 或 subagent 绕过。
31. route、provider、tool、artifact 和 checkpoint 没有关联 ID。
32. 日志保存完整 prompt、secret 和原始工具参数。
33. 用平均成功率掩盖高风险动作失败。
34. workflow 图可以无限递归或无限 fan-out。
35. 将 durable event、trace span 和 UI projection 混为事实源。
36. 没有 Definition of Done，只以“模型说完成”收尾。
## 实施清单
### 第一阶段：核心契约；[ ] 定义 Task、Workflow、WorkflowVersion、Run、Step、Attempt、Job。；[ ] 定义状态枚举和合法迁移。；[ ] 定义 input/output/error schema。；[ ] 定义 WorkflowDefinition、Node、Edge 和 policy contract。；[ ] 实现 Registry、Compiler 和 content hash。；[ ] 实现 append-only event、CAS 和 projector。；[ ] 实现最小线性 DAG runtime。
### 第二阶段：Durable Execution；[ ] 接入 DurableQueue、lease、heartbeat 和 fencing token。；[ ] 实现 attempt、timeout、retry、backoff 和 idempotency。；[ ] 实现 checkpoint、recovery 和 unknown 状态。；[ ] 实现 artifact、result、receipt 和 usage settlement。；[ ] 实现 pause、resume、cancel、signal。；[ ] 实现 approval 和 host delivery。；[ ] 实现 deterministic testkit 和 side-effect oracle。
### 第三阶段：图能力；[ ] 实现条件、三值逻辑和 branch event。；[ ] 实现 bounded loop 和 iteration checkpoint。；[ ] 实现 map、dynamic fan-out 和 expansion entry。；[ ] 实现 parallel、join、quorum 和 barrier。；[ ] 实现 dependency failure propagation。；[ ] 实现 compensation/Saga 和 partial result。；[ ] 实现 workflow visualization projector。
### 第四阶段：Agent 集成；[ ] 接入 ModelStep、PromptCompiler 和 ContextPlan。；[ ] 接入 ToolRuntime、Policy、Approval 和 Sandbox。；[ ] 接入 ArtifactRef、workspace view 和 file lock。；[ ] 接入 SubagentSupervisor 和 child run。；[ ] 接入 Provider Routing/Runtime 和 usage/cost ledger。；[ ] 接入 Session Replay、fork/resume 和 evaluation。；[ ] 接入 memory、privacy、egress 和 retention。
### 第五阶段：生产治理；[ ] 多租户 queue partition、quota、fairness 和 noisy-neighbor。；[ ] SLO、dashboard、alert、runbook 和 incident response。；[ ] version rollout、canary、migration 和 rollback。；[ ] DLQ、operator recovery 和 break-glass audit。；[ ] backup、restore、DR 和 replay drill。；[ ] schema compatibility 和长期运行迁移。；[ ] DSAR、删除、导出和 provider remote cleanup。
### 发布门禁；[ ] Definition 校验拒绝环、无出口节点和未满足 schema。；[ ] 任一 step 都可定位到 run、attempt、job、worker 和 event。；[ ] 重复投递不会重复已保护的副作用。；[ ] unknown 不会自动重放高风险写操作。；[ ] lease 失效 worker 不能提交结果。；[ ] approval 绑定 payload hash、scope、version 和 expiry。；[ ] pause/resume/cancel/signal 都有 durable receipt。；[ ] subagent capability 是父级和租户边界的交集。；[ ] checkpoint 可从事件和状态恢复。；[ ] workflow version 发布后不可变。；[ ] migration 不修改历史事实。；[ ] cross-tenant、egress、sandbox 和 secret 测试通过。；[ ] partial、failed、cancelled、blocked、expired、unknown 可被用户区分。；[ ] SLO、成本、审计和安全指标可查询。
## 五个参考项目的启发来源
### Pi；headless agent loop 与 harness 分离，说明 workflow runtime 应复用 Kernel，而不是复制模型循环。；session、branch、compaction 和 checkpoint 经验支持 run cursor、replay 和长期恢复。；多 host 共享核心执行路径，说明 workflow event 必须 canonical、host-specific projection。；工具调用与结果反馈的明确边界适用于 ModelStep、ToolStep 和 Attempt。；较弱的默认安全边界提醒 workflow 必须独立接入 Policy、Sandbox 和审批。
### Grok Build；actor/stage 与消息协调模式启发 DAG scheduler、并行 actor 和 join 状态设计。；资源锁、folder trust、sandbox 和 permission decision 说明 step 调度不能只看图依赖。；background task、parallel tool 和 structured state 适用于 worker lease 与 checkpoint。；对外部副作用的边界提醒补偿不等于物理回滚。；明确状态和错误路径支持 partial、unknown 和 recovery 分层。
### OpenCode；session/message/part 和 server/client 分离说明 Workflow Run View 是 projector，不是事实源。；permission、snapshot、patch/revert 和 persistent state 支持 approval、artifact、checkpoint 和审计模型。；数据库 schema 与迁移经验说明 workflow version、event schema 和长期 run 需要兼容窗口。；可观察的客户端事件流启发 Host Adapter 的 pause、resume、steering 和 delivery。；工具执行事实与 UI 展示分离，避免 host ack 冒充 step success。
### Claude Code；coding workflow 的 plan、implementation、review 和用户 steering 说明 workflow 需要明确阶段与验收。；hooks、skills、subagents 与权限边界说明 node type 必须带 provenance、trust 和 capability。；workspace、diff、测试和 artifact 经验支持 Coding Agent 场景的可验证 step output。；用户对 approval、取消、继续和结果审查的控制可转化为 human step 与 product control。；公开能力不等同于内部安全授权，仍需 Harness/Policy/Sandbox 强制。
### OpenClaw；AgentHarness、registry 和 gateway/channel 分离启发 workflow capability 的可装配与版本化。；agent-core 与多个 channel 的边界支持 workflow event canonicalization 和多端投影。；tool、sandbox、elevated 和 plugin registration 经验适用于 tool step、subagent step 和 approval。；事务化注册与失败回滚启发 workflow version publish、migration 和 compensation。；多渠道、多 provider 和后台任务组合强化 queue、tenant、artifact、notification 和 retention 的治理需求。
### 综合结论
```text
Workflow Orchestration
  = immutable definition/version
  + typed DAG/condition/loop/parallel
  + durable Run/Step/Attempt/Job state
  + queue lease worker execution
  + approval/steering/signal control
  + checkpoint/replay/recovery
  + idempotency/receipt/compensation
  + tenant/policy/sandbox/egress
  + artifact/context/model/tool/subagent integration
  + observable SLO and evaluation
```
它不是“把多个 prompt 串起来”，而是让复杂 Agent 任务拥有可验证的结构、执行事实、恢复路径和用户控制。
