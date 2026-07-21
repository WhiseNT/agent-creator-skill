# Workflow Scheduling Engineering 细粒度工程设计
> 本文定义 Agent Harness 中 Workflow Scheduling 的调度控制面：它负责 readiness、依赖、优先级、公平性、租户配额、容量预留、并发/组限制、分区、背压、deadline/timer、lease/fencing、抢占/取消、approval/wait/signal、DAG/loop/map/parallel join、retry/unknown、reconciliation、恢复、仿真、负载/故障测试和 SLO。
>
> 设计依据仅来自当前目录已有的参考架构、`agent-harness.md`、Workflow Orchestration、Workflow Versioning、Durable Queue、Harness、State/Memory、Event/Observability、Evaluation、Tool、Permission/Sandbox、Subagent、Agent Product、Data Governance、Privacy、Provider Runtime 文档以及五个参考项目的本地源码调研结论；不依赖 README，不进行网络搜索。
>
> 核心判断：**Workflow Scheduling 不是“把 `queue.poll()` 放进 `while` 循环**”。调度器必须在 durable workflow truth、依赖图、冻结 run snapshot、policy/quota、资源能力、租约所有权、预算、deadline、取消和副作用证据之间做可审计的决策。
## 目录
1. [设计目标与非目标](#设计目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [Scheduler 与 Orchestrator、Queue、Worker 的边界](#scheduler-与-orchestratorqueueworker-的边界)
4. [总体架构与包布局](#总体架构与包布局)
5. [核心数据模型与 TypeScript 接口](#核心数据模型与-typescript-接口)
6. [Readiness 与依赖语义](#readiness-与依赖语义)
7. [DAG、Loop、Map、Parallel 与 Join](#dagloopmapparallel-与-join)
8. [Priority、Fairness 与 Queue Ordering](#priorityfairness-与-queue-ordering)
9. [Tenant Quota、Capacity Reservation 与 Admission](#tenant-quotacapacity-reservation-与-admission)
10. [Concurrency、Group Limit 与 Resource Lock](#concurrencygroup-limit-与-resource-lock)
11. [Partitioning、Affinity 与 Noisy Neighbor](#partitioningaffinity-与-noisy-neighbor)
12. [Backpressure 与过载控制](#backpressure-与过载控制)
13. [Deadline、Timer、Delay 与 Expiry](#deadlinetimerdelay-与-expiry)
14. [Lease、Heartbeat 与 Fencing](#leaseheartbeat-与-fencing)
15. [Preemption、Cancellation 与 Graceful Stop](#preemptioncancellation-与-graceful-stop)
16. [Approval、Wait、Signal 与 External Callback](#approvalwaitsignal-与-external-callback)
17. [Retry、Unknown Outcome 与 Recovery](#retryunknown-outcome-与-recovery)
18. [Scheduler Decision 与 Reason Code](#scheduler-decision-与-reason-code)
19. [调度生命周期与状态机](#调度生命周期与状态机)
20. [Reconciliation、Checkpoint 与恢复](#reconciliationcheckpoint-与恢复)
21. [与 Model、Prompt、Context、Tool、State、Policy、Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
22. [安全、隐私、租户与 Workspace 边界](#安全隐私租户与-workspace-边界)
23. [可观测性、SLO 与 Capacity Planning](#可观测性slo-与-capacity-planning)
24. [仿真、负载与故障测试](#仿真负载与故障测试)
25. [测试策略与 Evaluation](#测试策略与-evaluation)
26. [故障分类与运行手册](#故障分类与运行手册)
27. [反模式与审查规则](#反模式与审查规则)
28. [实施清单](#实施清单)
29. [五个参考项目的启发来源](#五个参考项目的启发来源)
30. [Definition of Done](#definition-of-done)
## 设计目标与非目标
### 目标
Workflow Scheduler 必须能够：
- 根据 durable workflow/run/step truth 计算可运行节点，而不是扫描瞬时内存对象。
- 区分 `pending`、`blocked`、`ready`、`queued`、`leased`、`running`、`waiting`、`preempting`、`retrying`、`unknown`、`completed` 和 `failed`。
- 只在所有 required dependency、condition、approval、signal、resource 和 policy 条件满足时把 step 置为 ready。
- 以不可变 RunSnapshot、WorkflowVersion、PolicySnapshot、BudgetSnapshot 和 CapabilitySnapshot 做 admission 和执行。
- 在 tenant、workspace、session、run、subagent、provider、tool、region 和 resource class 之间实施配额、公平、并发和容量控制。
- 支持 priority、weighted fairness、aging、deadline、reserved capacity、burst、rate limit 和 noisy-neighbor protection。
- 支持 DAG、条件、loop、map、dynamic fan-out、parallel join、barrier 和 compensation 的调度语义。
- 支持 durable queue、lease、heartbeat、fencing、checkpoint、retry、backoff、cancel 和 recovery。
- 对 provider/tool/subagent 可能产生外部副作用的执行区分 `failed` 与 `unknown outcome`。
- 支持 approval、wait、signal、external callback、timer 和人类 steering，不把 HTTP 连接或 UI 状态当作 workflow truth。
- 记录每次调度决策、候选、被拒原因、资源账本、租约版本和后续结果。
- 提供仿真、负载、故障、恢复、SLO 和容量规划能力。
### 非目标
Scheduler 不负责：
- 代替 Workflow Definition Compiler 校验任意 graph/schema/policy。
- 代替 Orchestrator 决定业务步骤输出、补偿语义和最终 Task settlement。
- 代替 Durable Queue 负责持久化 job、lease storage、ack/nack 和 dead-letter 实现。
- 代替 Worker 执行 Model—Tool loop、shell、数据库、HTTP 或 subagent。
- 用 prompt 文本定义依赖、租户配额、审批、权限、lease 或 fencing。
- 通过读取最新全局配置改变已经冻结的 RunSnapshot。
- 把 queue visible、worker lease、model response 或 UI ack 当作业务成功。
- 承诺 transport exactly-once；调度层必须假定至少一次、重复投递和 unknown。
- 让高优先级永远压过其他 tenant，或用一个全局 FIFO 伪装公平性。
- 以平均吞吐抵消 deadline miss、scope violation、duplicate side effect 或 starvation。
### 核心公式
```text
Scheduling Correctness
  = Readiness Correctness
  × Dependency Semantics
  × Admission Safety
  × Ownership/Fencing
  × Fairness
  × Retry Safety
  × Recovery Quality
```
任何一个因子为零，系统都可能在高负载下产生不可解释或不可恢复的执行。
## 核心判断与术语
### 三种 truth
```text
Task Truth      用户目标、约束、验收、优先级、deadline、交付选择
Workflow Truth  definition/version、节点、依赖、条件、循环和资源契约
Run Truth       step/attempt/job/event/lease/checkpoint/receipt 的实际执行事实
```
Scheduler 只读取 Workflow Truth 与 Run Truth，不能用 UI、模型文本或缓存状态覆盖它们。
### 对象区分
- `Task`：产品层用户目标，可关联多个 run。
- `WorkflowDefinition`：声明节点、边、schema、policy、timeout、retry、resource 和 compensation。
- `WorkflowVersion`：不可变、可寻址、可发布的 definition 版本。
- `Run`：一次具体执行，冻结输入、版本、scope、policy、budget、capability、provider 和 sandbox。
- `Step`：run 中的逻辑节点状态和输出容器。
- `Attempt`：某 step 的一次执行尝试。
- `Job`：交给 durable queue 的可调度工作单元。
- `Dependency`：决定 step readiness 的显式前置关系。
- `Lease`：worker 在有限时间内拥有 job 的临时权利。
- `FencingToken`：旧 lease 失效后阻止其继续写入的单调所有权凭证。
- `Approval`：具体 action、参数、范围和有效期的授权事实。
- `Signal`：外部系统或用户发来的结构化事实。
- `Wait`：run 保持 durable 状态，等待 timer、approval、signal、callback 或资源。
- `Settlement`：step/run 的结果、usage、cost、artifact、receipt 和终态结算。
- `UnknownOutcome`：可能已经发生副作用但当前无法确认的状态。
### Queue 与 Scheduler
```text
Scheduler: 哪个工作现在允许且值得运行？
Queue:     如何持久保存、交付、租约和重试已决定的工作？
Worker:    如何在租约和能力边界内执行工作？
Orchestrator: 业务结果如何推进 graph、补偿和最终结算？
```
Scheduler 可以产生 `ScheduleDecision`，但不能直接假设 job 执行成功。
## Scheduler 与 Orchestrator、Queue、Worker 的边界
| 组件 | 负责 | 不负责 |
|---|---|---|
| `WorkflowRegistry` | definition/version、发布、兼容和 provenance | runtime 调度 |
| `Compiler` | graph、schema、condition、policy、resource contract 校验 | 修改 run 状态 |
| `RunCoordinator` | 创建 run、冻结 snapshot、生命周期控制 | 选择每个 worker |
| `DAGScheduler` | readiness、依赖、优先级、公平、配额、资源和决策 | 执行业务节点 |
| `DurableQueue` | enqueue、lease、heartbeat、ack/nack、retry、DLQ | 判断业务成功 |
| `Worker` | 验证 lease/capability、执行 job、checkpoint、result | 改租户或 policy |
| `StepExecutor` | model/tool/subagent/human/artifact 节点执行适配 | 计算全局公平 |
| `ApprovalService` | 请求、展示、解决、过期和撤销审批 | 自动扩大范围 |
| `SignalRouter` | 将外部 signal 关联到 run/step | 伪造 signal |
| `QuotaManager` | 预算、配额、reservation、usage 和 release | 执行 step |
| `PolicyEngine` | visibility、call、approval、execution、egress | 修改 workflow graph |
| `Harness` | 装配、监督、取消、恢复、delivery、settlement | 成为调度器 God Object |
| `HostAdapter` | 展示状态、提交控制、订阅和 ack | 推断 durable truth |
### 强制关系
```text
Definition declares possible work.
Compiler validates executable graph.
Policy authorizes action.
Scheduler selects admissible work.
Queue owns durable delivery.
Worker owns temporary execution.
State/Event records facts.
Orchestrator advances business truth.
Harness supervises lifecycle and recovery.
Host projects facts and submits control commands.
```
## 总体架构与包布局
```text
Host/API/Batch
  -> Auth + TenantContext
  -> Task Intake + Workflow Resolver
  -> Definition Registry + Compiler
  -> RunCoordinator + RunSnapshot
  -> Policy/Quota/Budget Admission
  -> Readiness Engine
  -> Candidate Planner
  -> Fairness/Priority/Capacity Selector
  -> Durable Queue
  -> Lease Manager
  -> Worker Runtime
       ├─ Workflow Step Executor
       ├─ Agent Kernel / Model Runtime
       ├─ Tool / Sandbox / Approval
       ├─ Subagent Supervisor
       └─ Checkpoint / Result / Receipt
  -> Event Store / State Store / Usage Ledger
  -> Reconciliation / Projector / Audit / Evaluation
```
### 包布局
```text
packages/scheduling/
  contracts.ts
  readiness.ts
  dependency.ts
  graph-cursor.ts
  priority.ts
  fairness.ts
  quota.ts
  reservation.ts
  capacity.ts
  concurrency.ts
  partition.ts
  backpressure.ts
  deadline.ts
  timer.ts
  lease.ts
  fencing.ts
  preemption.ts
  cancellation.ts
  decision.ts
  reconciliation.ts
  simulation.ts
  metrics.ts
  testkit/
packages/workflow-runtime/
  coordinator.ts
  scheduler-loop.ts
  step-dispatcher.ts
  worker-adapter.ts
  approvals.ts
  signals.ts
  recovery.ts
```
### 调度循环的正确形态
```text
load durable cursor
  -> apply new events/checkpoint
  -> reconcile stale state
  -> compute readiness
  -> evaluate policy/quota/deadline/capacity
  -> produce ranked candidates
  -> reserve resources atomically
  -> issue ScheduleDecision
  -> enqueue jobs with idempotency
  -> observe lease/result events
  -> advance graph after verified outcome
```
`while` 只是实现细节，不能代替上述语义、快照、资源账本和恢复边界。
## 核心数据模型与 TypeScript 接口
### 标识与状态
```typescript
type TaskId = string;
type WorkflowId = string;
type WorkflowVersionId = string;
type RunId = string;
type StepId = string;
type AttemptId = string;
type JobId = string;
type LeaseId = string;
type PartitionId = string;
type ReservationId = string;
type ApprovalId = string;
type SignalId = string;
type DecisionId = string;
type RunStatus =
  | "created" | "admitted" | "queued" | "running" | "waiting"
  | "paused" | "cancelling" | "cancelled" | "completed"
  | "failed" | "partial" | "unknown" | "expired" | "blocked";
type StepStatus =
  | "pending" | "blocked" | "ready" | "queued" | "leased"
  | "running" | "waiting" | "preempting" | "retrying"
  | "succeeded" | "failed" | "skipped" | "cancelled"
  | "partial" | "unknown" | "compensating" | "compensated";
type AttemptStatus =
  | "created" | "admitted" | "leased" | "started" | "streaming"
  | "waiting" | "succeeded" | "failed" | "timed_out"
  | "cancelled" | "preempted" | "unknown" | "recovered";
type ReadinessState =
  | "not_evaluated" | "blocked_dependency" | "blocked_condition"
  | "blocked_approval" | "blocked_signal" | "blocked_quota"
  | "blocked_capacity" | "blocked_policy" | "blocked_deadline"
  | "ready" | "expired" | "terminal";
```
### RunSnapshot
```typescript
interface RunSnapshot {
  runId: RunId;
  taskId: TaskId;
  workflowId: WorkflowId;
  workflowVersionId: WorkflowVersionId;
  definitionHash: string;
  tenantId: string;
  workspaceId?: string;
  sessionId?: string;
  branchId?: string;
  principal: PrincipalRef;
  inputRefs: ResourceRef[];
  policySnapshotId: string;
  permissionSnapshotId: string;
  modelSnapshotId?: string;
  promptSnapshotId?: string;
  contextSnapshotId?: string;
  toolRegistrySnapshotId?: string;
  sandboxSnapshotId?: string;
  budgetSnapshot: BudgetSnapshot;
  quotaSnapshot: QuotaSnapshot;
  capabilitySnapshot: CapabilitySnapshot;
  featureFlags: Record<string, boolean>;
  deadlineAt?: string;
  createdAt: string;
  snapshotHash: string;
}
```
### StepNode 与 Edge
```typescript
interface WorkflowStepNode {
  nodeId: string;
  type: "model" | "tool" | "subagent" | "human" | "artifact"
    | "condition" | "loop" | "map" | "parallel" | "join" | "wait";
  inputSchema: JsonSchema;
  outputSchema?: JsonSchema;
  dependencies: WorkflowEdge[];
  condition?: ConditionExpression;
  retryPolicy: RetryPolicy;
  timeoutPolicy: TimeoutPolicy;
  resourceClass: string;
  requiredCapabilities: string[];
  concurrencyGroup?: string;
  sideEffectClass: "none" | "read" | "reversible" | "external_write" | "irreversible";
  approvalPolicy?: ApprovalPolicy;
  cancellationPolicy: CancellationPolicy;
  priorityPolicy?: PriorityPolicy;
}
interface WorkflowEdge {
  fromNodeId: string;
  toNodeId: string;
  kind: "data" | "ordering" | "condition" | "barrier" | "approval" | "signal" | "compensation";
  required: boolean;
  joinKey?: string;
  predicate?: ConditionExpression;
}
```
### StepState
```typescript
interface StepState {
  runId: RunId;
  stepId: StepId;
  nodeId: string;
  status: StepStatus;
  readiness: ReadinessState;
  dependencySnapshot: DependencySnapshot;
  inputRefs: ResourceRef[];
  outputRefs: ResourceRef[];
  attemptIds: AttemptId[];
  currentAttemptId?: AttemptId;
  approvalIds: ApprovalId[];
  signalIds: SignalId[];
  reservationIds: ReservationId[];
  checkpointRef?: CheckpointRef;
  nextEligibleAt?: string;
  deadlineAt?: string;
  lastDecisionId?: DecisionId;
  outcomeKnown: boolean;
  updatedAt: string;
  version: number;
}
```
### Job、Lease 与 Reservation
```typescript
interface ScheduleJob {
  jobId: JobId;
  runId: RunId;
  stepId: StepId;
  attemptId: AttemptId;
  tenantId: string;
  partitionId: PartitionId;
  priority: number;
  fairnessClass: string;
  deadlineAt?: string;
  availableAt: string;
  requiredCapabilities: string[];
  resourceRequest: ResourceRequest;
  configSnapshotHash: string;
  policySnapshotId: string;
  idempotencyKey: string;
  deduplicationKey?: string;
  retryOrdinal: number;
  status: "created" | "queued" | "leased" | "running" | "waiting" | "completed" | "failed" | "cancelled" | "unknown";
}
interface LeaseRef {
  leaseId: LeaseId;
  jobId: JobId;
  workerId: string;
  leaseVersion: number;
  fencingToken: string;
  issuedAt: string;
  visibilityUntil: string;
  heartbeatAt: string;
  state: "active" | "renewing" | "expired" | "released" | "fenced";
}
interface ResourceReservation {
  reservationId: ReservationId;
  scope: ScopeRef;
  resourceClass: string;
  units: number;
  tokens?: number;
  bytes?: number;
  expiresAt: string;
  source: "quota" | "capacity" | "burst" | "deadline_reserve";
  status: "held" | "committed" | "released" | "expired";
}
```
### ScheduleDecision
```typescript
interface ScheduleDecision {
  decisionId: DecisionId;
  schedulerVersion: string;
  observedCursor: EventCursor;
  runId: RunId;
  stepId: StepId;
  action: "enqueue" | "delay" | "hold" | "preempt" | "cancel" | "reconcile" | "skip" | "fail";
  rank: number;
  scoreBreakdown: ScoreBreakdown;
  reasons: DecisionReason[];
  candidateSnapshot: CandidateSnapshot;
  reservations: ReservationId[];
  policySnapshotId: string;
  createdAt: string;
  expiresAt?: string;
  idempotencyKey: string;
}
interface DecisionReason {
  code: string;
  category: "readiness" | "priority" | "fairness" | "quota" | "capacity" | "deadline" | "policy" | "dependency" | "recovery";
  message?: string;
  evidenceRefs: ResourceRef[];
}
```
## Readiness 与依赖语义
### Readiness 不是 queue presence
step 只有在以下条件全部满足时才是 `ready`：
```text
run admitted and not terminal
  ∧ step not terminal
  ∧ all required dependencies settled successfully or explicitly tolerated
  ∧ condition evaluates true
  ∧ required inputs exist and schema-valid
  ∧ approval valid
  ∧ required signal/callback present
  ∧ policy allows visibility/call/execution/egress
  ∧ quota reservation possible
  ∧ capacity class available or reservable
  ∧ deadline not expired
  ∧ concurrency/group/lock constraints satisfied
  ∧ cancellation not preventing start
```
### Dependency 状态
```typescript
type DependencyOutcome =
  | "success" | "failed" | "skipped" | "cancelled"
  | "partial" | "unknown" | "not_settled";
interface DependencySnapshot {
  required: DependencyObservation[];
  optional: DependencyObservation[];
  joinGroups: JoinGroupState[];
  evaluatedAt: string;
  sourceCursor: EventCursor;
}
```
- required dependency failed：默认 downstream blocked/failed，取决于 error policy。
- optional dependency failed：允许 condition 或 default branch 继续，但必须有 reason。
- unknown dependency：不得假装 success；只能走 explicit unknown branch、manual review 或 hold。
- skipped dependency：只有 definition 明确允许 `skip_as_success` 才可满足 join。
- cancelled dependency：默认不满足；补偿或 alternate path 必须显式声明。
- partial dependency：只能被接受到声明支持 partial 的节点。
### 条件求值
- condition 只能读取已结算、schema-valid、scope-checked 的输入。
- condition 不得调用模型、任意 shell、外部网络或非确定性隐式函数。
- condition 版本和 compiler 版本进入 RunSnapshot。
- condition error 不等于 false，应进入 `condition_error` 并按 policy 处理。
- condition 结果必须产生 expression hash、input hash、evaluation result 和 reason。
### 动态依赖
动态 fan-out 产生的新 step 必须：
- 继承父 run snapshot 的 policy、tenant、workspace、budget 和 deadline 上限。
- 具有稳定 `mapItemKey`、parentStepId、attemptId 和 idempotency key。
- 经过最大 fan-out、per-tenant quota、group limit 和 resource admission。
- 在 graph cursor 中持久化，不能仅存于 worker 内存。
- 能在 crash/replay 后重建且不重复创建。
## DAG、Loop、Map、Parallel 与 Join
### DAG 拓扑
编译阶段检查：
- node ID、edge ID、schema 引用唯一。
- required edge 不形成非法 cycle。
- condition/loop/map 的出口明确。
- join 对 required/optional/unknown/timeout 有策略。
- compensation graph 独立且可验证。
- 节点 capability、resource class、side-effect class 有效。
- 图的最大节点数、边数、fan-out、loop iterations 在 budget 内。
### Loop
loop 必须声明：
```typescript
interface LoopPolicy {
  maxIterations: number;
  maxWallClockMs: number;
  breakCondition: ConditionExpression;
  checkpointEvery: number;
  onUnknown: "hold" | "fail" | "manual" | "compensate";
  onIterationFailure: "retry" | "break" | "fail" | "continue";
}
```
规则：
- 每次 iteration 产生 durable cursor、input hash、output ref 和 decision。
- break condition 必须单调收敛或有最大次数，不允许无限 while。
- iteration 的 priority/fairness 不能绕过 parent run 的 deadline 和 quota。
- crash 后从最后 checkpoint 恢复，不能重复不可逆 side effect。
- loop 中的 child/subagent 受递归深度和 fan-out 上限。
### Map
map 调度关注：
- item enumeration 的版本和 hash。
- map item 的稳定 key、排序和去重。
- max concurrency、per-group limit、per-tenant quota。
- partial success、failed item、unknown item 和 retry。
- join 是否等待 all、quorum、best-effort 或 explicit threshold。
- item 输出的 artifact、receipt 和 error schema。
### Parallel 与 Join
```text
parallel opened
  -> child branches ready/queued/running
  -> branch settle
  -> join barrier evaluates
  -> all/quorum/any/conditional result
  -> downstream readiness
```
Join 必须保存：
- 已到达 branch IDs。
- 缺失 branch IDs 和原因。
- unknown branch IDs。
- quorum/threshold。
- duplicate branch event 去重结果。
- join evaluation hash。
`all` join 不应把 `unknown` 当成功；`any` join 必须取消或隔离未选分支；`quorum` 必须明确失败和 unknown 的计数规则。
## Priority、Fairness 与 Queue Ordering
### Priority
priority 是候选排序信号，不是越权授权。计算输入可包括：
- 用户交互模式。
- deadline slack。
- workflow critical path。
- retry ordinal。
- tenant plan 或 service class。
- operator emergency flag。
- aging。
禁止：
- 让模型任意声明 critical。
- 让单 tenant 持续提升 priority 绕过公平。
- 用 priority 覆盖 policy deny、quota hard limit 或 safety hold。
### Score 分解
```text
priority score
  = base priority
  + deadline urgency
  + aging bonus
  + critical-path bonus
  + retry fairness adjustment
  - quota debt
  - noisy-neighbor penalty
  - resource scarcity penalty
```
每一项都应进入 `scoreBreakdown`，禁止只有一个不可解释总数。
### Fairness
支持：
- weighted fair queue。
- deficit round robin。
- tenant round robin。
- workflow-class fairness。
- per-user/session fairness。
- reserved interactive lane。
- aging 防止 starvation。
公平性目标：
- 有限资源下同级 tenant 获得可预测的服务份额。
- background 不饿死 interactive，interactive 也不永久挤压 background。
- 单一 fan-out run 不占满所有 partition。
- worker capability 不匹配的 job 不应阻塞其他可运行 job。
### Queue ordering
ordering key 可能是：
```text
tenant + queue class
session
run
workflow critical path
partition + sequence
```
ordering 必须与并发、reordering、retry 和 deadline 语义同时定义：
- 强顺序队列中前一 job 未 settle，后续 job 不得越过。
- 允许乱序的队列必须有 per-step idempotency 和 dependency guard。
- retry 产生新 availableAt 和 reason，不静默插到队首。
- priority aging 不得破坏 required ordering barrier。
## Tenant Quota、Capacity Reservation 与 Admission
### Quota 维度
至少包括：
- concurrent runs/steps/attempts。
- model requests、tool calls、subagents。
- CPU、memory、GPU、sandbox processes。
- network egress、artifact bytes、queue backlog。
- provider tokens、cost micros、embedding/index operations。
- per-minute、per-hour、daily budget。
- high-risk action 和 approval pending 数量。
### Admission 顺序
```text
authenticate
  -> resolve tenant/workspace/run scope
  -> validate workflow snapshot
  -> evaluate policy and capability
  -> check deadline and priority class
  -> reserve quota/budget/capacity
  -> create durable job and decision
  -> enqueue with idempotency
  -> return receipt
```
reservation 失败应返回稳定 reason：
```text
quota_exhausted
capacity_unavailable
budget_exhausted
policy_denied
deadline_impossible
missing_capability
concurrency_limit
partition_paused
```
### Reservation 语义
- reservation 是暂时锁定，不是实际 usage。
- execution start commit 后转为 committed usage。
- cancel、expiry、failure、lease recovery 必须释放或 reconcile reservation。
- reservation 有 owner、scope、resource class、amount、expiry、version 和 reason。
- crash 后由 reconciler 对 reservation 与 attempt/lease 对账。
- 不允许 worker 自行增加 reservation。
### Reserved capacity
为交互、审批恢复、reconciliation、recovery 和 incident 提供保留容量：
- reserved lane 不能被普通 background 消耗。
- emergency 使用需审计，并设定最大时间和恢复策略。
- reserved capacity 不意味着跳过 policy、scope、fencing 或 side-effect checks。
- capacity planner 需要计算 reserved、burst、steady-state 和 failure headroom。
## Concurrency、Group Limit 与 Resource Lock
### 并发层级
```text
global
  -> region
  -> tenant
  -> workspace
  -> session
  -> run
  -> workflow node
  -> concurrency group
  -> provider/model/tool
  -> external resource key
```
有效并发是所有层级剩余容量的最小值：
```text
allowed = min(global, region, tenant, workspace, run, group, provider, resource)
```
### Group limit
`concurrencyGroup` 用于限制互斥或有限共享资源：
- 同一 deployment。
- 同一 workspace 写锁。
- 同一 session state projector。
- 同一 external account。
- 同一 provider rate class。
- 同一文件、数据库 row 或 artifact destination。
Group 状态必须 durable 或可从 lease/event 重建。
### Resource lock
锁只是调度协调，不是业务成功证明：
- 使用 scope-aware key，不能把用户可控字符串直接当全局锁名。
- lock lease 必须有 expiry、owner、fencing token 和诊断。
- lock conflict 进入 `blocked_resource`，不应无限 busy loop。
- 真实副作用仍需 idempotency、receipt 和 reconciliation。
- deadlock 通过固定锁顺序、短 lease、超时检测和回退策略避免。
## Partitioning、Affinity 与 Noisy Neighbor
### Partition 维度
```text
tenant + queue class
workspace + resource class
session actor
run
provider + region + deployment
workflow version
```
### Affinity
适合保持：
- 同一 session 的顺序和 cache locality。
- 同一 workspace 的 sandbox/worktree 状态。
- 同一 provider region 的网络和认证。
- 同一 run 的 checkpoint locality。
- 同一 resource lock 的 owner。
affinity 不是授权证明；worker 每次仍检查 tenant、scope、capability、policy snapshot 和 fencing。
### Noisy neighbor
必须防止：
- 一个 tenant 的 map fan-out 占满全局 worker。
- 一个 provider outage 产生 retry storm。
- 一个长 compaction job 阻塞 interactive queue。
- 一个 session 的高频 delta 淹没 control plane。
- 一个 stuck lease 阻塞整个 partition。
控制手段：
- tenant weighted fairness。
- per-tenant concurrency and backlog caps。
- queue class isolation。
- circuit breaker 和 retry budget。
- partition split/rehash。
- aging 但有上限。
- background shedding。
- reserved recovery lane。
## Backpressure 与过载控制
### Backpressure 层级
```text
Host intake
  -> Task admission
  -> Run admission
  -> Step readiness
  -> Queue enqueue
  -> Lease issuance
  -> Worker execution
  -> Provider/tool backend
  -> Event/projector/delivery
```
每一层可拒绝、延迟、降级、采样或取消，但必须有 durable reason。
### 策略
- 先拒绝不可完成的 deadline，再排队浪费资源。
- 对 background 任务延迟或暂停，对 interactive 保留容量。
- 对 map 限制 fan-out，使用 bounded window。
- 对 provider 429 使用 retry-after、token bucket 和 retry budget。
- 对 event/delivery 慢消费者使用 coalescing，不阻塞 durable control events。
- 对 artifact/diagnostic 大输出使用 artifact ref，不把 blob 塞入 job payload。
- 对负载持续超限触发 admission deny，而不是无限积压。
### 过载 reason
```text
queue_depth_limit
partition_lag
worker_capacity_exhausted
provider_rate_limited
event_sink_backpressure
artifact_capacity_low
quota_debt
retry_budget_exhausted
```
## Deadline、Timer、Delay 与 Expiry
### 时间字段
```typescript
interface TimeBudget {
  createdAt: string;
  notBeforeAt?: string;
  softDeadlineAt?: string;
  hardDeadlineAt?: string;
  leaseUntil?: string;
  retryAvailableAt?: string;
  approvalExpiresAt?: string;
  retentionExpiresAt?: string;
}
```
必须区分：
- queue delay。
- worker start timeout。
- provider first-event/total timeout。
- tool timeout。
- step deadline。
- run deadline。
- lease visibility timeout。
- approval expiry。
- retention TTL。
### Deadline 调度
- 计算 slack：`deadline - now - estimated_remaining`。
- deadline 不应授权 policy deny 或超出 tenant budget 的动作。
- impossible deadline 应在 admission 阶段拒绝或要求用户重新选择。
- soft deadline 可触发降级、减少 fan-out、切换 provider 或通知用户。
- hard deadline 触发 cancel/timeout/partial/expired，保留已发生事实。
- timer job 必须 durable、幂等、可取消、可重放。
### 时钟
- scheduler 使用 store/server time 或单调时钟处理 lease。
- wall-clock 用于用户可见 deadline 和 retention。
- clock skew 进入 diagnostic，不能让 worker 伪造 lease 延长。
- 仿真使用 deterministic clock，并测试跳时、回拨、DST 和 leap boundary。
## Lease、Heartbeat 与 Fencing
### Lease 获取
原子检查：
```text
job status is schedulable
  ∧ availableAt <= now
  ∧ deadline not expired
  ∧ required capability matched
  ∧ tenant/quota/capacity reservation valid
  ∧ ordering barrier satisfied
  ∧ no active lease
  ∧ CAS/version succeeds
```
### Heartbeat
heartbeat 只延长 ownership，不改变：
- tenant、scope、policy、snapshot。
- budget、quota、resource request。
- approval、egress、side-effect class。
- workflow definition/version。
```typescript
interface HeartbeatRequest {
  leaseId: LeaseId;
  jobId: JobId;
  workerId: string;
  leaseVersion: number;
  fencingToken: string;
  progress?: ProgressSnapshot;
  checkpointRef?: CheckpointRef;
  observedAt: string;
}
```
### Fencing
- 每次 lease renewal/ownership change 产生单调 lease version 和 fencing token。
- State/Event/Result/Receipt 写入必须携带 fencing token。
- token 过期、版本冲突或 worker scope 不匹配时拒绝写入。
- provider/tool 端若支持幂等或 external fencing，应传播 attempt identity。
- lease expired 不证明旧 worker 未执行，必须进入 recovery probe。
### Lease recovery
```text
lease expired
  -> inspect execution record
  -> inspect checkpoint/event cursor
  -> query provider/tool status if side effect possible
  -> classify succeeded/failed/unknown/not_started
  -> fence old owner
  -> reconcile reservation
  -> resume, retry, manual or terminal
```
## Preemption、Cancellation 与 Graceful Stop
### Preemption
抢占只适用于 definition、resource class 和 policy 明确允许的工作：
- 优先抢占可 checkpoint、无不可逆 side effect 的 step。
- 不在 external_write 正在 commit 时强杀，先进入 safe point。
- 保存 checkpoint、partial output、usage、reservation 和 reason。
- 被抢占的 attempt 状态为 `preempted`，不能伪装为 failed。
- 恢复时使用同一 step 的新 attempt 和新的 idempotency handling。
### Cancellation 层次
```text
user cancel request
  -> run cancellation intent
  -> scheduler stops new dispatch
  -> queued jobs cancel
  -> workers receive abort
  -> tool/provider cancellation
  -> safe-point checkpoint
  -> settlement
```
必须区分：
- cancel requested。
- cancellation propagating。
- cancelled before start。
- cancelled at safe point。
- cancellation failed。
- unknown outcome。
- partial success。
### Cancel 规则
- 断开 Host 不自动 cancel。
- cancel 不删除已经发生的外部副作用。
- approval、wait、timer 和 signal 必须有取消语义。
- child/subagent 取消传播遵守 structured concurrency 和 detach policy。
- cancellation command 幂等，重复 cancel 返回同一 receipt。
## Approval、Wait、Signal 与 External Callback
### Approval
Approval 绑定：
```text
action type
material parameters
resource scope
tenant/workspace
risk and reversibility
policy snapshot
requested by
expiresAt
approval id
```
调度器只在 approval receipt 有效、未过期、参数 hash 匹配、scope 未变化时将 step ready。
审批拒绝、过期、撤回或 policy 变化不得被模型文本覆盖。
### Wait
wait node 必须写入：
- wait reason。
- expected signal/approval/timer/callback key。
- not-before、expiry、run deadline。
- resume condition。
- cancellation and timeout policy。
- current checkpoint。
wait 不占用 worker lease，但可能占用 run slot、reservation 或 approval capacity，必须明确是否释放。
### Signal
```typescript
interface WorkflowSignal {
  signalId: SignalId;
  signalType: string;
  source: "user" | "tool" | "provider" | "external_system" | "timer" | "operator";
  targetRunId: RunId;
  targetStepId?: StepId;
  idempotencyKey: string;
  payload: unknown;
  payloadHash: string;
  receivedAt: string;
  authorization: AuthorizationSnapshot;
}
```
- signal 先认证、scope check、schema validate、dedupe，再 append durable event。
- late signal 不自动复活 terminal run，除非显式 resume policy。
- 过早 signal 暂存或拒绝，必须有 reason。
- 重复 signal 不重复推进节点。
## Retry、Unknown Outcome 与 Recovery
### Retry 层次
区分：
- transport retry。
- provider attempt retry。
- tool retry。
- step retry。
- workflow compensation/retry。
- scheduler requeue。
任何 retry 都需要 error taxonomy、budget、backoff、jitter、attempt identity 和 side-effect classification。
### Retry policy
```typescript
interface RetryPolicy {
  maxAttempts: number;
  retryableErrors: string[];
  backoff: "fixed" | "exponential" | "decorrelated_jitter";
  initialDelayMs: number;
  maxDelayMs: number;
  retryBudgetMicros?: number;
  onUnknown: "query" | "hold" | "manual" | "compensate" | "fail";
  idempotencyMode: "required" | "best_effort" | "never_retry";
}
```
### Unknown outcome
可能发生：
- provider connection 在 request accepted 后断开。
- tool 在 side effect commit 后 worker crash。
- external callback 已发送但 receipt 丢失。
- lease expiry 后旧 worker 仍在执行。
- event store ack 与业务提交边界不一致。
处理顺序：
```text
fence old attempt
  -> query external status
  -> inspect receipt/idempotency record
  -> inspect event/checkpoint
  -> reconcile reservation
  -> known success / known failure / still unknown
```
unknown 状态下：
- 不自动重复不可逆动作。
- 不把 job visible 当作未执行。
- 可继续无副作用的诊断或等待。
- 向用户展示准确的 uncertain 状态。
- 达到 escalation deadline 后进入 manual/terminal policy。
## Scheduler Decision 与 Reason Code
### 决策输入
```typescript
interface SchedulingInput {
  run: RunSnapshot;
  step: StepState;
  dependencies: DependencySnapshot;
  policy: PolicySnapshot;
  quota: QuotaSnapshot;
  capacity: CapacitySnapshot;
  activeLeases: LeaseRef[];
  queueState: QueueState;
  clocks: SchedulerClock;
  recentFailures: FailureWindow;
}
```
### 决策阶段
```text
load candidate steps
  -> filter terminal/invalid
  -> evaluate dependencies
  -> evaluate condition/approval/signal
  -> evaluate policy and scope
  -> estimate resource/deadline feasibility
  -> apply quota and reservation
  -> score priority/fairness/aging
  -> apply partition/order/group constraints
  -> choose bounded batch
  -> commit reservations and decision
  -> enqueue idempotently
```
### Reason code 示例
```text
READY_DEPENDENCIES_SATISFIED
BLOCKED_REQUIRED_DEPENDENCY
BLOCKED_UNKNOWN_DEPENDENCY
BLOCKED_CONDITION_FALSE
BLOCKED_APPROVAL_MISSING
BLOCKED_SIGNAL_MISSING
BLOCKED_POLICY_DENIED
BLOCKED_QUOTA_EXHAUSTED
BLOCKED_CAPACITY_UNAVAILABLE
BLOCKED_CONCURRENCY_GROUP
BLOCKED_ORDERING_BARRIER
DELAYED_NOT_BEFORE
DELAYED_BACKOFF
DELAYED_DEADLINE_POLICY
PREEMPTED_FOR_RESERVED_CAPACITY
CANCELLED_BY_RUN
RECONCILE_LEASE_EXPIRED
HOLD_UNKNOWN_OUTCOME
```
### 可解释性要求
每个 candidate 即使没有被选中，也应能回答：
- 观察到哪个 durable cursor。
- 哪些 dependency/condition 已满足或缺失。
- 哪个 policy/quota/capacity 阻止它。
- 与被选 candidate 的 priority/fairness 差异。
- 是否存在 deadline、reservation、partition、lock 或 recovery 影响。
- 下一次重新评估的时间或触发事件。
## 调度生命周期与状态机
### Run 状态机
```text
created
  -> admitted
  -> queued
  -> running
  -> waiting
  -> paused
  -> cancelling
  -> completed | failed | partial | cancelled | unknown | expired | blocked
```
### Step 状态机
```text
pending
  -> blocked
  -> ready
  -> queued
  -> leased
  -> running
  -> waiting | preempting | retrying
  -> succeeded | failed | skipped | cancelled | partial | unknown
```
### Job 状态机
```text
created -> queued -> leased -> running
running -> checkpointed | waiting | completed | failed | cancelled | unknown
leased -> expired -> recovered | requeued | unknown
failed -> retry_scheduled -> queued
unknown -> probing -> known_success | known_failure | manual | terminal
```
### 状态转换不变量
- 状态变化必须有 actor、reason、expected version、event ID 和 timestamp。
- terminal state 不因旧 event 回退。
- job completed 不自动等于 step succeeded，必须由 Orchestrator 验证 result/schema/receipt。
- step succeeded 不自动等于 run completed，必须重新计算 graph。
- queue ack 丢失时可恢复，不重复提交 side effect。
- projector 落后不改变 canonical scheduling truth。
## Reconciliation、Checkpoint 与恢复
### Reconciliation 触发
- scheduler 启动。
- worker heartbeat 超时。
- queue lease expiry。
- event/projector lag 超阈值。
- reservation expiry。
- provider/tool unknown。
- workflow migration/resume。
- operator 请求。
- periodic scan。
### Reconciliation 检查
```text
run snapshot vs workflow version
step state vs events
job state vs lease
lease vs worker heartbeat
attempt vs execution record
reservation vs actual usage
checkpoint vs cursor
artifact vs result ref
provider/tool status vs receipt
queue visibility vs side-effect ledger
```
### Checkpoint
checkpoint 至少保存：
- graph cursor、completed/skipped/blocked nodes。
- loop iteration、map item manifest、parallel join arrivals。
- active approvals、waits、signals、timers。
- step/attempt last durable boundary。
- input/output refs、artifact refs、receipt refs。
- budget/quota usage、reservation、deadline slack。
- pending recovery probes。
checkpoint 必须版本化、hash、scope-aware、可加载并能与 event replay 互相验证。
### 恢复流程
```text
load latest valid checkpoint
  -> replay events after checkpoint
  -> validate snapshot and policy
  -> fence stale leases
  -> reconcile jobs/attempts/reservations
  -> classify unknown outcomes
  -> recompute readiness
  -> schedule safe work
  -> write recovery receipt
```
## 与 Model、Prompt、Context、Tool、State、Policy、Harness 集成
### Model
调度器不选择 prompt 内容，但需要看到：
- model/provider capability。
- context window、rate class、concurrency、cost and region capacity。
- retry/fallback health 和 circuit state。
- model request 的 estimated tokens/cost。
provider fallback 必须产生新 Attempt、新 decision、新 usage 归因和新 egress evaluation。
### Prompt
Prompt 不能决定 step readiness、approval 或 priority。
- workflow model step 只在 scheduler 判定 ready 后进入 Kernel。
- model 输出的 tool call、memory intent、subagent request 和 completion claim 都是不可信事件。
- prompt/compiler version 在 RunSnapshot 中冻结。
### Context
ContextPlan 是 step 输入的一部分：
- scheduler 只调度拥有完整、合规 ContextPlan 的 model step。
- context compile failure 可 retry、degrade、wait 或 fail，但不能用空 context 假装成功。
- ContextPlan 的 resource refs、token budget、sensitivity 和 egress 都进入 decision evidence。
- compaction、memory recall 和 artifact range 可能产生 background jobs，需要独立 queue class 和 quota。
### Tool
调度器只负责工具工作单元的 admission、priority、quota、lease、timeout、cancel 和 recovery。
Tool Runtime 负责：
- schema/business validation。
- capability、approval、sandbox、network 和 side-effect。
- receipt、unknown outcome、idempotency 和 normalized error。
一个 tool job 可被调度不等于工具可以执行；Policy 和 Sandbox 仍是硬边界。
### State/Event
- canonical events 是 readiness、lease、attempt、approval、signal、checkpoint、settlement 的输入。
- state store 提供 CAS、版本、append-only facts 和 replay。
- projector 只生成 UI/ops views，不作为 scheduler truth。
- event backpressure 不能丢 control-plane events。
- scheduler decision、candidate ranking、reason code、reservation 和 recovery 都应 durable 或可重建。
### Policy
执行前分别检查：
```text
visibility: step/resource 是否对当前 run 可见
call: 是否允许提交该类型工作
approval: 是否需要具体用户授权
execution: worker/sandbox/provider/tool 是否可执行
egress: 输入/结果是否可进入目标外部边界
```
policy 变化：
- queued job 默认使用 frozen snapshot。
- 对尚未开始的高风险 job 可按显式 policy revalidate。
- 已开始 attempt 不应静默扩大权限。
- deny/unknown/expired 进入 hold、cancel、manual 或 recovery。
### Harness
Harness 负责：
- 创建 RunScope、TaskGroup、AbortController 和 Budget。
- 装配 Scheduler、Queue、Worker、Kernel、Tool、State、Artifact、Policy 和 Host。
- 传播取消、deadline、approval、signal 和 steering。
- 监督 checkpoint、recovery、delivery、usage、cost、audit 和 settlement。
- 维持 parent/child run 的 scope、capability、budget 和 trace 隔离。
Scheduler 不应吸收所有 Harness 责任。
## 安全、隐私、租户与 Workspace 边界
### Scope 交集
```text
requested resource
  ∩ tenant
  ∩ principal
  ∩ workspace/project
  ∩ session/branch/run
  ∩ workflow snapshot
  ∩ policy snapshot
  ∩ worker capability
  ∩ sandbox profile
  ∩ provider egress
```
partition key、priority class、job payload 和 worker location 都不是授权证明。
### 关键不变量
- queue、job、lease、event、artifact、usage、audit 的 tenant scope 一致。
- child/subagent 不默认继承父全部资源、secret、workspace 或 provider capability。
- untrusted workspace、MCP、plugin、文件和 tool output 不能提升 priority、quota、policy 或 approval。
- provider/region 选择来自冻结 routing/egress snapshot，不由 worker 或 adapter 私自 fallback。
- scheduler decision 不保存不必要的 raw prompt、secret 或完整 tool output。
- metric、log、diagnostic 和 artifact 使用 redaction、retention 和访问审计。
### 安全降级
分类未知、policy unavailable、scope mismatch、DLP failure、sandbox attestation missing、provider region unavailable 时：
- 对高风险 action fail closed。
- 对只读、低敏感度 action 可降级到 metadata-only、summary 或 manual。
- 记录 diagnostic、audit 和 recovery candidate。
- 不把可用性压力作为跳过权限和隐私检查的理由。
## 可观测性、SLO 与 Capacity Planning
### 事件与 trace
调度事件至少包括：
```text
RunAdmissionEvaluated
StepReadinessEvaluated
DependencyResolved
ConditionEvaluated
QuotaReserved
CapacityReserved
ScheduleCandidateRanked
ScheduleDecisionCreated
JobEnqueued
JobLeaseAcquired
JobHeartbeat
JobPreempted
JobCancelled
ApprovalRequested
WorkflowWaiting
SignalReceived
RetryScheduled
UnknownOutcomeDetected
ReconciliationStarted
ReconciliationCompleted
StepSettled
RunSettled
```
事件字段：
- tenant/workspace/session/run/step/attempt/job。
- workflow version、snapshot hash、scheduler version。
- partition、worker、resource class、decision ID、reason codes。
- queue time、lease time、run time、deadline slack。
- quota/capacity reservation、usage、cost、artifact/receipt refs。
- sensitivity、retention、redaction 和 audit class。
### 核心指标
```text
readiness_evaluation_latency
queue_wait_latency
schedule_to_lease_latency
lease_to_start_latency
step_runtime
workflow_critical_path_latency
ready_but_unqueued_age
blocked_by_dependency_count
blocked_by_quota_count
blocked_by_capacity_count
starvation_age_p95
fairness_share_by_tenant
noisy_neighbor_violations
reservation_leak_rate
lease_expiry_rate
fencing_rejection_rate
preemption_rate
cancellation_latency
unknown_outcome_rate
reconciliation_age
retry_storm_rate
deadline_miss_rate
```
### SLO
按 queue class 和 tenant tier 分别定义：
- interactive admission latency。
- approval resume latency。
- background queue wait P95/P99。
- schedule-to-lease latency。
- deadline miss rate。
- cancellation propagation P95。
- reconciliation completion window。
- unknown resolution window。
- fairness skew、starvation 上限。
- reservation leak 和 duplicate job 率。
- scheduler decision durable coverage。
安全与正确性 SLO 是 zero-tolerance 或 release-blocking，不允许被吞吐平均值抵消。
### Capacity planning
容量模型至少包括：
```text
steady-state concurrency
+ peak burst
+ retry amplification
+ provider outage backlog
+ map fan-out
+ recovery/reconciliation reserve
+ approval/wait metadata
+ artifact/event/projector load
```
规划步骤：
1. 按 workflow node/resource class 统计 arrival rate、service time 和 fan-out。
2. 计算每 tenant、partition、provider 和 queue class 的峰值。
3. 预留 interactive、approval、recovery、operator 和 reconciliation 容量。
4. 模拟 worker、provider、event store、queue partition 和 region 故障。
5. 设置 backlog、deadline slack、retry budget 和 autoscaling 触发。
6. 以 cost、latency、fairness 和 capacity headroom 共同评审。
## 仿真、负载与故障测试
### Scheduler Simulator
Simulator 输入：
```typescript
interface SimulationScenario {
  durationMs: number;
  tenants: TenantLoadProfile[];
  workflowMix: WorkflowArrivalProfile[];
  workerPools: WorkerPoolProfile[];
  providerProfiles: ProviderCapacityProfile[];
  faults: SimulatedFault[];
  clock: "deterministic" | "trace_replay";
  seed: number;
}
```
输出：
- 每次 decision、rank、reason、reservation 和 lease。
- queue depth、ready age、fairness share、capacity utilization。
- deadline miss、starvation、retry amplification 和 unknown。
- worker crash、partition outage、provider 429/5xx、event lag 和 recovery 时间。
- cost、reserved capacity 使用和 admission deny。
### 负载模型
覆盖：
- interactive burst。
- long-running background run。
- map fan-out burst。
- approval resume wave。
- provider outage retry storm。
- tenant skew：一个大 tenant、很多小 tenant。
- capability skew：少数 GPU/region/provider worker。
- hot session/workspace。
- deadline synchronized batch。
### Fault injection
- scheduler process crash。
- queue store timeout/partial commit。
- worker crash before/after side effect。
- lease heartbeat loss and clock skew。
- fencing token conflict。
- event store lag、duplicate、out-of-order、unknown event。
- provider rate limit、stream disconnect、accepted-but-no-receipt。
- tool timeout、sandbox crash、artifact upload partial。
- quota/reservation store inconsistency。
- approval late/duplicate/expired。
- signal early/late/duplicate。
- partition split/merge。
### 正确性不变量
- required dependency 未 settle 不会 dispatch。
- 同一 idempotency key 不产生不可逆重复副作用。
- 过期 lease 的 worker 不能提交 result。
- terminal run 不被 late signal 复活，除非显式 policy。
- unknown 不被自动转成 failed 或 success。
- quota/reservation 不泄漏。
- fair scheduler 不让 tenant 永久 starvation。
- cancellation 停止新的 dispatch，已有副作用有 receipt/unknown 处理。
- replay/reconciliation 后 state 与 event truth 一致。
## 测试策略与 Evaluation
### Unit
- graph validation、topological readiness、condition evaluator。
- loop/map/parallel/join 状态转移。
- priority、aging、weighted fair、deficit round robin。
- quota、reservation、capacity、group limit、partition。
- deadline/slack/timer/expiry。
- lease/CAS/heartbeat/fencing。
- cancellation/preemption/retry/unknown。
- decision reason、score breakdown 和 evidence。
### Component
- `ReadinessEngine` 与 state/event store。
- `CandidateSelector` 与 fairness/quota/capacity。
- `DurableQueue` contract、lease manager 和 retry scheduler。
- `ReservationLedger`、usage ledger 和 reconciliation。
- approval、signal、timer、external callback。
- worker adapter、checkpoint、result/receipt settlement。
- scheduler metrics、trace、audit 和 Host projection。
### Integration
- Workflow Orchestration 的 RunCoordinator、Compiler、StepExecutor。
- Workflow Versioning 的 RunSnapshot、migration 和 rollback。
- Model/Prompt/Context/Tool/State/Policy/Harness 真实装配。
- Subagent child run、structured concurrency 和 parent cancel。
- provider routing、rate limit、fallback、cost 和 egress。
- event projector、session replay、artifact、usage 和 audit。
- multi-tenant、workspace isolation、sandbox、approval 和 DSAR。
### Evaluation 断言
调度评测不只看吞吐，还要验证：
- ready node 是否及时且只被调度一次。
- blocked node 是否有正确 reason。
- queue order、fairness、deadline 和 capacity 是否符合 contract。
- reservation、lease、fencing、retry、unknown 和 reconciliation 是否正确。
- graph completion、partial、compensation 和 run settlement 是否正确。
- 用户取消、审批、signal 和 Host disconnect 的语义是否准确。
- scheduler 版本、policy snapshot、decision artifact 可复现。
## 故障分类与运行手册
### 故障分类
```text
invalid_definition
snapshot_mismatch
readiness_bug
condition_error
dependency_cycle
quota_exhausted
capacity_exhausted
partition_hotspot
fairness_skew
starvation
queue_store_error
lease_expired
fencing_conflict
worker_lost
provider_rate_limit
provider_unknown
tool_unknown
approval_expired
signal_missing
deadline_missed
retry_budget_exhausted
reservation_leak
projector_lag
reconciliation_stuck
```
### On-call 诊断顺序
```text
identify tenant/workspace/run/step/job
  -> read canonical run/step state
  -> read latest decision and reasons
  -> inspect dependency/condition/approval/signal
  -> inspect quota/capacity/reservation
  -> inspect queue partition and lease
  -> inspect worker heartbeat/fencing
  -> inspect provider/tool receipt and unknown
  -> inspect checkpoint/event cursor
  -> choose resume/retry/hold/cancel/manual
  -> record operator action and receipt
```
### 安全操作
- 不直接改 UI projection 伪造状态。
- 不删除 job/event/lease 以“清理卡住任务”。
- 不在 unknown side effect 上盲目 retry。
- 不临时关闭 tenant scope、approval、sandbox 或 egress。
- 不通过提高 priority 绕过 quota 或公平。
- operator override 需要短时、最小 scope、双人或高强度审计策略。
## 反模式与审查规则
1. `queue.poll()` 放进 while，未定义 readiness、依赖、租约、配额和恢复。
2. 用内存中的 ready list 作为 durable truth。
3. queue visible 就认为前一个副作用没有发生。
4. worker lease 没有 fencing token。
5. heartbeat 能改变权限、tenant、预算或 payload。
6. retry 不区分 transport、attempt、tool、step 和 side effect。
7. 把 unknown 当 failed，然后自动重试不可逆动作。
8. 用全局 FIFO 处理多 tenant、多优先级和多资源能力。
9. 高 priority 永久压制 background 和其他 tenant。
10. 没有 aging、fairness share 或 starvation 指标。
11. map fan-out 无上限。
12. loop 没有 max iterations、deadline 和 checkpoint。
13. join 把 failed、skipped、unknown 混成 success。
14. approval 只看 boolean，不绑定参数、scope、expiry 和 policy snapshot。
15. late signal 直接复活 terminal run。
16. timer 存在 worker 内存，进程重启后丢失。
17. cancellation 只改 UI，不停止 queue、worker、provider 和 child run。
18. preemption 在 external side effect commit 中间强杀。
19. reservation 没有 expiry、release 和对账。
20. capacity 不保留 recovery、approval、interactive 和 operator lane。
21. scheduler 读取 latest policy 覆盖 RunSnapshot。
22. partition key 被当作授权证明。
23. 把 Host ack、model response 或 queue ack 当作业务成功。
24. 不记录未选 candidate 的 reason code。
25. 只报平均吞吐，不报 deadline、fairness、unknown、lease 和 recovery。
26. 只测试 happy path，不做 simulation、load、fault 和 chaos。
27. 将 scheduler 变成执行所有 Model/Tool/Artifact 业务逻辑的 God Object。
28. 不保存 decision、score、reservation、cursor 和 snapshot hash，导致无法重放。
29. 让子 Agent 继承父全部 quota、secret、workspace 和 worker capability。
30. 把 Workflow Scheduling 误实现为一个有线程的队列消费者。
## 实施清单
### P0：契约与状态
- [ ] 定义 RunSnapshot、StepState、ScheduleJob、Lease、Reservation、ScheduleDecision 和 reason code。
- [ ] 定义 readiness、dependency、condition、approval、wait、signal、timer 和 terminal 状态。
- [ ] 建立 scheduler 与 Orchestrator/Queue/Worker 的 port 边界。
- [ ] 在 durable store 中保存 graph cursor、event cursor、decision、lease 和 reservation。
### P1：基础调度
- [ ] 实现 DAG readiness、required/optional/unknown dependency 和 deterministic condition。
- [ ] 实现 priority、aging、weighted fairness、queue ordering、partition 和 group limit。
- [ ] 实现 tenant quota、capacity reservation、budget admission 和 release/reconciliation。
- [ ] 实现 durable enqueue、lease、heartbeat、fencing、retry、cancel 和 deadline。
### P2：复杂工作流
- [ ] 实现 loop、map、dynamic fan-out、parallel join、barrier 和 partial success。
- [ ] 实现 approval、wait、signal、external callback、timer 和 steering。
- [ ] 实现 preemption、safe point、checkpoint、unknown probe 和 compensation handoff。
- [ ] 接入 Model/Prompt/Context/Tool/State/Policy/Harness/Subagent。
### P3：可靠性与运营
- [ ] 实现 reconciliation、recovery runbook、simulation、load、fault 和 chaos suite。
- [ ] 建立 queue wait、fairness、starvation、deadline、lease、unknown、reservation 和 retry 指标。
- [ ] 按 queue class、tenant tier、region、provider 和 resource class 定义 SLO。
- [ ] 建立容量模型、reserved lane、autoscaling、backlog shedding 和 outage playbook。
### P4：发布与治理
- [ ] scheduler decision、workflow version、policy snapshot 和 result artifact 可重放。
- [ ] 接入 Evaluation release gate、workflow version migration 和 canary。
- [ ] 完成 cross-tenant、scope、secret、sandbox、approval、DSAR 和 retention 测试。
- [ ] 建立 operator override、审计、双人审批和安全降级流程。
## 五个参考项目的启发来源
### Pi
- session/branch/turn 的 durable 结构启发 run、step、attempt、checkpoint 和 readiness cursor 分离。
- event stream 与 host delivery 分层启发 scheduler decision、control event、ephemeral progress 和 replay 分离。
- compaction、background task、subagent 和 queue 语义启发 structured concurrency、cancel propagation、bounded fan-out 和恢复 lane。
### Grok Build
- actor/sampler/工具执行边界启发 worker lease、resource lock、tool side-effect 和 attempt 归因。
- 路径级锁、预算和输出限制启发 concurrency group、capacity admission、artifact ref 和 backpressure。
- trust、permission 和 sandbox 分层启发 readiness 不能越过 policy、approval、workspace 与 execution isolation。
### OpenCode
- session/message/part、server/client、tool/permission 分层启发 canonical event、projector、Host ack 与 scheduler truth 分离。
- snapshot/patch/revert 启发 workflow snapshot、checkpoint、replay、version locking 和 rollback 不改历史。
- 多 provider、MCP/LSP 和状态迁移边界启发 capability matching、provider partition、unknown 和 conformance。
### Claude Code
- plan、task、approval、memory、hooks、skills 和 subagents 启发 human steering、wait/signal、child scope 和用户可见的控制状态。
- permission modes 与 project trust 启发 priority 不能提升权限，scheduler 只能调度已获准的 execution。
- background work 与通知路径启发 foreground/background queue class、delivery disconnect 与 durable run truth 分离。
### OpenClaw
- session key、gateway/channel 和 cron/background 结构启发 tenant/session partition、timer jobs、notification delivery 和重连恢复。
- compaction memory flush、hybrid retrieval 与长任务启发 memory/index queue 的独立容量、checkpoint 和 backpressure。
- tool、sandbox、elevated 与插件注册启发 capability snapshot、egress、approval、lease 和 operator audit。
## Definition of Done
Workflow Scheduling 只有同时满足以下条件才算完成：
- scheduler 与 Orchestrator、Queue、Worker 的职责边界在接口和代码依赖中清晰存在。
- readiness、dependency、priority、fairness、quota、capacity、concurrency、partition、backpressure、deadline、lease 和 fencing 有可执行契约。
- DAG、loop、map、parallel join、approval、wait、signal、retry、unknown、cancel、preemption 和 recovery 有状态机和测试。
- 每次调度 decision 有 candidate snapshot、score breakdown、reason code、reservation、cursor、snapshot hash 和可重放 artifact。
- 多 tenant、noisy neighbor、starvation、deadline miss、retry storm、lease expiry 和 provider outage 可仿真、压测和故障注入。
- worker crash、event lag、queue duplicate、provider accepted-but-no-receipt 和 external unknown 都不会造成盲目重复副作用。
- cancellation、approval、signal、timer 和 Host disconnect 的 durable 语义与 UI 投影一致。
- Model、Prompt、Context、Tool、State、Policy、Harness、Subagent、Artifact、Provider 和 Evaluation 的集成不绕过既有边界。
- SLO、capacity planning、reserved recovery lane、backpressure、autoscaling 和运行手册已落地。
- 安全、隐私、租户、workspace、sandbox、egress、DSAR、retention 和 operator override 有 hard gate 与审计。
- 决策流程必须记录 candidate、readiness、dependency、policy、quota、capacity、fairness、reservation、lease、reason code 和最终 enqueue/deny 结果。
- 故障恢复必须先 reconciliation queue、lease、checkpoint、reservation、worker 和 side-effect receipt，再决定 retry、resume、quarantine、preempt 或 manual。
- “Workflow Scheduling 不是把 queue.poll() 放进 while loop”在 readiness、decision、resource、lease、recovery 和运营层均被落实。
