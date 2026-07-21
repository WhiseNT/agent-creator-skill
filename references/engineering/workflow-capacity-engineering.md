# Workflow Capacity Engineering 细粒度工程设计

> Workflow Capacity 是 Agent Harness 中回答“在什么边界、以什么节奏、为谁保留多少可执行能力”的控制面。
> **Workflow Capacity 不是“CPU 利用率 dashboard”**：CPU 只是某一种资源的滞后信号；容量还包括队列、依赖、worker、pool、provider、model、tool、sandbox、artifact、storage、egress、预算、区域、租户公平、deadline 和恢复余量。
> 本设计与 Workflow Scheduling、Workflow Orchestration、Durable Queue、Production Operations、Cost Governance、Multi-tenant、Provider Routing、Agent Reference Architecture 和 Agent Harness 的契约对齐。标题映射约定：`ResourceClass` 即“资源类别”，`Demand/Reservation/Usage` 即“需求/预留/使用量”，`Deadline risk` 即“截止期限风险”，`Release gate` 即“发布门禁”，代码类型名保留英文以便实现对齐。

## 目录

1. [目标与非目标](#目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [职责边界](#职责边界)
4. [总体架构与包布局](#总体架构与包布局)
5. [容量域与核心数据模型](#容量域与核心数据模型)
6. [TypeScript 接口](#typescript-接口)
7. [生命周期与状态机](#生命周期与状态机)
8. [中文决策流程](#中文决策流程)
9. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
10. [容量模型与 Little 定律](#容量模型与-little-定律)
11. [Resource Class 与资源账本](#resource-class-与资源账本)
12. [Worker、Pool、Provider、Model、Tool](#workerpoolprovidermodeltool)
13. [Sandbox、Artifact、Queue 与存储容量](#sandboxartifactqueue-与存储容量)
14. [Tenant/Workspace Quota](#tenantworkspace-quota)
15. [Reserved、Burst、Concurrency 与 Fairness](#reservedburstconcurrency-与-fairness)
16. [Backlog、Admission、Backpressure 与 Shedding](#backlogadmissionbackpressure-与-shedding)
17. [Deadline、SLO 与容量余量](#deadlineslo-与容量余量)
18. [Cost、Budget 与容量权衡](#costbudget-与容量权衡)
19. [Regional Capacity、DR 与 Failover](#regional-capacitydr-与-failover)
20. [Autoscaling 与容量控制器](#autoscaling-与容量控制器)
21. [Forecast 与容量计划](#forecast-与容量计划)
22. [Load/Soak/Stress/Chaos 测试](#loadsoakstresschaos-测试)
23. [Capacity Incident 与 Runbook](#capacity-incident-与-runbook)
24. [Capacity Evidence 与 Release Gate](#capacity-evidence-与-release-gate)
25. [反模式](#反模式)
26. [实施清单](#实施清单)
27. [五个参考项目的启发来源](#五个参考项目的启发来源)

## 目标与非目标

### 目标

Workflow Capacity Engineering 必须：

- 为 workflow、run、step、attempt、job、queue、worker、pool、provider、model、tool、sandbox、artifact、storage、region 和 tenant 建立容量事实。
- 把 arrival rate、service rate、并发、排队、资源 reservation、burst、fairness、deadline、budget 和 recovery headroom 放在同一决策模型中。
- 在工作进入 durable queue 前完成 admission；在 lease、执行、settlement 和 recovery 期间维护可追踪资源账本。
- 支持 resource class、capability、region、provider deployment 和 sandbox profile 的硬约束匹配。
- 防止单一 tenant、workspace、session、subagent fan-out、provider retry 或 artifact upload 消耗全局容量。
- 让 reserved capacity 与 burst capacity 可解释、可回收、可计费，并为关键 SLO 留出 headroom。
- 将 backlog、deadline risk、unknown outcome、cost cap、quota、circuit、DR 和跨区域复制纳入 autoscaling、backpressure 和 shedding。
- 提供容量预测、发布门禁、负载/浸泡/压力/混沌测试、事件响应和复盘证据。
- 以 durable facts 证明“能否接收”和“是否完成”，不以 dashboard 的单一指标声称容量充足。

### 非目标

- 不替代 Workflow Definition Compiler、DAGScheduler 或 Orchestrator 判断业务依赖和最终 settlement。
- 不把 CPU、内存、Pod 数或 QPS 单项当作 workflow capacity。
- 不承诺无限 autoscaling、无限 burst、transport exactly-once 或无成本 failover。
- 不以低利用率为目标牺牲 deadline、tenant fairness、privacy、policy、budget 或副作用安全。
- 不让 worker、provider adapter、tool 或模型自行增加 quota、改变 region 或绕过 admission。
- 不把 queue visible、worker lease、model response 或 UI ack 当作 workflow 成功。
- 不在没有 receipt、side-effect status 或 fencing 的情况下重放未知副作用工作。

### 核心判断

```text
Workflow Capacity
 = admissible work
 + resource reservations
 + fair scheduling
 + bounded execution
 + backlog control
 + deadline protection
 + cost/budget control
 + regional resilience
 + recovery headroom
```

```text
Workflow Capacity != CPU 利用率 dashboard
Capacity Truth = durable demand + available supply + reservations
                + queue delay + service rate + constraints + evidence
```

容量决策必须能够回答“拒绝或延迟谁、释放什么、何时恢复、依据哪个快照”。

## 核心判断与术语

### 三种 truth

```text
Workflow Truth definition/version、节点、依赖、resource contract
Run Truth      step/attempt/job/lease/checkpoint/result/unknown
Capacity Truth demand、supply、reservation、quota、backlog、headroom、decision
```

- capacity truth 不能从 UI 进度、内存对象或 worker 自报状态推断。
- Scheduler 选择可运行工作；Queue 负责 durable delivery；Worker 执行租约内工作；Capacity Controller 控制资源供给和 admission。
- reservation 是将来可用权利；usage 是已消耗事实；capacity evidence 是供给可验证证明。

### 容量维度

- **需求**：arrival rate、fan-out、step weight、expected duration、deadline、retry、unknown recovery。
- **供给**：worker 数、pool slots、provider quota、model TPM/RPM、tool permits、sandbox cores、artifact I/O、queue storage。
- **约束**：tenant/workspace quota、policy、region、capability、cost、privacy、approval、circuit、maintenance。
- **质量**：queue delay、start latency、service latency、deadline miss、fairness、error budget、SLO。
- **证据**：reservation receipt、lease、usage meter、provider receipt、queue depth、capacity snapshot 和 reconciliation。

### 术语

- `ResourceClass`：可独立配额、计量、调度和扩容的一类资源。
- `CapacityPool`：具有同一 resource class、region、capability、sandbox 或 provider 边界的供给池。
- `Reservation`：对未来工作占用 capacity 的可过期承诺。
- `Headroom`：为波动、故障、恢复、部署和关键 SLO 预留的未分配容量。
- `Backlog`：已接受但未完成的可执行工作及其年龄、权重和 deadline 风险。
- `ServiceRate`：在特定 resource class 和状态下完成有效 work unit 的速率。
- `ArrivalRate`：进入 admission 的 work unit 速率，不等于 HTTP 请求数。
- `FairnessDebt`：一个 scope 因长期少得资源而积累的调度债务。
- `CapacityEvidence`：支持 supply、demand、usage、decision 或 forecast 的可验证记录。
- `Shedding`：在安全边界内拒绝、降级、取消、合并或延迟工作。

## 职责边界

| 组件 | 负责 | 不负责 |
|---|---|---|
| `WorkflowRegistry/Compiler` | resource contract、能力、上限和图校验 | runtime admission |
| `Orchestrator` | 创建 run、冻结 snapshot、推进业务 graph | 计算全局 pool capacity |
| `DAGScheduler` | readiness、依赖、priority、fairness、候选选择 | 增加真实供给 |
| `CapacityController` | supply、reservation、quota、headroom、autoscale、admission | 执行 step |
| `DurableQueue` | durable enqueue、lease、retry、DLQ、delivery | 判断资源能否无限扩张 |
| `Worker/PoolManager` | 报告能力、领取 lease、heartbeat、drain、执行 | 改 tenant quota 或 policy |
| `ProviderRouting` | 解析 capability、health、region、quota、cost、route | 绕过容量 admission |
| `ModelRuntime` | provider request、stream、usage、error、receipt | 全局公平和 pool 扩容 |
| `Tool/Sandbox` | schema、approval、执行边界、CPU/memory/network meter | 自行重试占满 pool |
| `Artifact/Storage` | bytes、I/O、retention、replication 和吞吐 | 隐式丢弃 workflow output |
| `Quota/Budget` | quota、reservation、cost cap、settlement | 执行工作 |
| `Policy` | visibility、call、approval、execution、egress | 用 prompt 替代 capacity contract |
| `Production Operations` | SLO、告警、部署、DR、事件和 runbook | 手工绕过 admission |
| `Harness` | 装配 snapshot、监督、取消、恢复、delivery | 成为容量 God Object |

强制关系：

```text
Definition declares possible resource demand.
Compiler validates bounded contract.
Policy authorizes work and destination.
CapacityController admits and reserves supply.
Scheduler selects fairly among admitted candidates.
Queue owns durable delivery and lease.
Worker executes within reservation and fencing.
UsageLedger settles actual usage and cost.
Harness supervises cancellation, recovery and delivery.
```

## 总体架构与包布局

### 逻辑拓扑

```text
Host/API
 -> Auth + TenantContext + Task Intake
 -> Workflow Registry/Compiler
 -> RunSnapshot + PolicySnapshot + BudgetSnapshot
 -> Capacity Profile Resolver
 -> Demand Estimator
 -> Quota/Budget/Headroom Admission
 -> Readiness + Fair Scheduler
 -> Durable Queue + Reservation Lease
 -> Worker Pool / Sandbox Pool
 -> Model Runtime / Tool Runtime / Subagent Supervisor
 -> Artifact/State/Event/Usage Ledger
 -> Capacity Metrics + Reconciliation + Forecast
 -> Autoscaler / Shedding / Incident Control
```

### 控制面与数据面

- 控制面维护 resource catalog、pool capacity、quota、reservation policy、forecast、region、provider contract 和 rollout。
- 数据面读取冻结的 `CapacitySnapshot`，执行 assignment、lease、heartbeat、usage 和 checkpoint。
- 已 admitted run 不因普通配置刷新静默改变资源合同；安全 revoke、region outage 或 budget stop 可产生 durable control event。
- Capacity Controller 不读取完整 prompt；只读需求摘要、tokens、tool count、artifact bytes、capability 和 policy classification。
- 高风险任务在容量证据缺失时 fail-closed；低风险后台任务可以排队或降级，但要记录 degraded reason。

### 包布局

```text
packages/workflow-capacity/
  contracts.ts resource-class.ts catalog.ts demand.ts supply.ts snapshot.ts
  quota.ts reservation.ts budget.ts fairness.ts backlog.ts deadline.ts admission.ts
  backpressure.ts shedding.ts scheduler-bridge.ts autoscaling.ts forecast.ts
  regional.ts failover.ts reconciliation.ts evidence.ts metrics.ts runbooks.ts testkit/
packages/workflow-runtime/
  coordinator.ts scheduler.ts queue.ts worker.ts lease.ts recovery.ts
packages/operations/
  slo.ts alerts.ts capacity-dashboard.ts incidents.ts chaos.ts
```

依赖方向：

```text
Host -> Orchestrator -> Capacity Port -> Scheduler/Queue
Capacity -> Quota/Budget/Policy/Provider Catalog/Usage
Worker -> Lease/Reservation/Harness/Sandbox ports
Infrastructure -> Capacity/Queue/Pool/Provider/Storage adapters
```

## 容量域与核心数据模型

### ResourceClass

```typescript
type ResourceClass =
  | "workflow_slot" | "step_slot" | "worker_cpu" | "worker_memory" | "worker_disk"
  | "model_rpm" | "model_tpm" | "model_concurrency" | "provider_quota"
  | "tool_concurrency" | "tool_rate" | "sandbox_cpu" | "sandbox_memory"
  | "artifact_ingress" | "artifact_egress" | "artifact_storage" | "queue_depth"
  | "event_write" | "state_read" | "state_write" | "embedding" | "rerank"
  | "subagent_depth" | "network_egress" | "budget_currency";
type CapacityUnit = "slot" | "request" | "token" | "byte" | "byte_second" | "cpu_ms" | "memory_mb" | "item" | "currency";
interface ResourceKey {
  class: ResourceClass;
  poolId: string;
  region?: string;
  provider?: string;
  model?: string;
  tool?: string;
  sandboxProfile?: string;
}
```

### CapacityPool 与 Supply

```typescript
interface CapacityPool {
  poolId: string;
  resourceClass: ResourceClass;
  unit: CapacityUnit;
  region: string;
  capabilities: string[];
  provider?: string;
  model?: string;
  tool?: string;
  sandboxProfile?: string;
  total: number;
  allocatable: number;
  reserved: number;
  used: number;
  draining: number;
  unavailable: number;
  headroomTarget: number;
  version: string;
  observedAt: string;
}
interface CapacitySupply {
  pool: ResourceKey;
  total: number;
  healthy: number;
  allocatable: number;
  reserved: number;
  used: number;
  pendingScale: number;
  failureRate: number;
  observedAt: string;
  evidenceRefs: string[];
}
```

### Demand、Reservation、Usage

```typescript
interface WorkDemand {
  demandId: string;
  tenantId: string;
  workspaceId?: string;
  runId: string;
  stepId?: string;
  jobId?: string;
  resource: ResourceKey;
  estimatedUnits: number;
  maxUnits: number;
  expectedDurationMs: number;
  deadlineAt?: string;
  priority: number;
  fairnessClass: string;
  retryMultiplier: number;
  fanout: number;
  confidence: number;
  source: "definition" | "history" | "provider" | "user" | "forecast";
  snapshotId: string;
}
interface CapacityReservation {
  reservationId: string;
  scope: { tenantId: string; workspaceId?: string; runId?: string; jobId?: string };
  demands: WorkDemand[];
  reservedUnits: Record<string, number>;
  expiresAt: string;
  priority: number;
  fairnessClass: string;
  status: "requested" | "held" | "partially_held" | "committed" | "released" | "expired" | "revoked";
  fencingToken: string;
  idempotencyKey: string;
  evidenceRefs: string[];
}
interface CapacityUsage {
  usageId: string;
  reservationId?: string;
  runId: string;
  jobId?: string;
  resource: ResourceKey;
  requestedUnits: number;
  actualUnits: number;
  startAt?: string;
  endAt?: string;
  outcome: "completed" | "failed" | "cancelled" | "unknown";
  meterSource: string;
  receiptRef?: string;
  costEntryRef?: string;
}
```

### CapacitySnapshot 与 Decision

```typescript
interface CapacitySnapshot {
  snapshotId: string;
  tenantScope: string;
  policyVersion: string;
  quotaVersion: string;
  budgetVersion: string;
  catalogVersion: string;
  pools: CapacitySupply[];
  reservations: string[];
  backlogVersion: string;
  forecastVersion?: string;
  regionVersion: string;
  createdAt: string;
  expiresAt: string;
  hash: string;
}
type CapacityDecisionKind = "admit" | "queue" | "reserve" | "partial" | "degrade" | "shed" | "deny" | "failover" | "scale";
interface CapacityDecision {
  decisionId: string;
  kind: CapacityDecisionKind;
  runId: string;
  jobId?: string;
  candidates: string[];
  selectedPools: ResourceKey[];
  reservationId?: string;
  reasonCodes: string[];
  queueDelayEstimateMs?: number;
  deadlineRisk?: number;
  costEstimate?: number;
  snapshotId: string;
  createdAt: string;
  evidenceRefs: string[];
}
```

## TypeScript 接口

### CapacityPort

```typescript
interface CapacityPort {
  snapshot(input: CapacitySnapshotInput): Promise<CapacitySnapshot>;
  estimate(input: DemandInput): Promise<WorkDemand[]>;
  admit(input: AdmissionRequest): Promise<CapacityDecision>;
  reserve(input: ReservationRequest): Promise<CapacityReservation>;
  commit(reservationId: string, fencingToken: string): Promise<void>;
  release(input: ReleaseReservation): Promise<void>;
  recordUsage(input: CapacityUsage): Promise<void>;
  reconcile(input: ReconciliationRequest): Promise<CapacityReport>;
}
interface AdmissionRequest {
  runId: string;
  workflowVersionId: string;
  demands: WorkDemand[];
  tenantQuotaRef: string;
  workspaceQuotaRef?: string;
  policySnapshotId: string;
  budgetSnapshotId: string;
  deadlineAt?: string;
  priority: number;
  fairnessClass: string;
  preferredRegions?: string[];
  failoverAllowed: boolean;
  idempotencyKey: string;
}
interface ReservationRequest {
  runId: string;
  jobId?: string;
  demands: WorkDemand[];
  ttlMs: number;
  allowPartial: boolean;
  preemptionClass: "never" | "cooperative" | "allowed";
  idempotencyKey: string;
}
```

### Pool 与 Worker

```typescript
interface WorkerCapacityReport {
  workerId: string;
  poolId: string;
  region: string;
  capabilities: string[];
  resourceTotals: Record<ResourceClass, number>;
  resourceFree: Record<ResourceClass, number>;
  activeLeases: number;
  sandboxProfiles: string[];
  drainState: "active" | "draining" | "drained" | "failed";
  observedAt: string;
  attestationRef?: string;
}
interface PoolScaler {
  plan(input: ScaleInput): Promise<ScalePlan>;
  apply(plan: ScalePlan): Promise<ScaleReceipt>;
  drain(poolId: string, reason: string): Promise<void>;
}
interface ScalePlan {
  poolId: string;
  from: number;
  to: number;
  reasonCodes: string[];
  expectedCost: number;
  expectedReadyAt: string;
  safetyChecks: string[];
  expiresAt: string;
}
```

### Quota、Fairness、Forecast

```typescript
interface QuotaPolicy {
  scope: { tenantId: string; workspaceId?: string };
  resourceLimits: Record<ResourceClass, number>;
  rateLimits: Record<ResourceClass, number>;
  concurrentRuns: number;
  concurrentSteps: number;
  reservedShare: number;
  burstLimit: number;
  fairnessWeight: number;
  deadlineClasses: string[];
  version: string;
}
interface FairnessState {
  scopeKey: string;
  virtualFinish: number;
  consumedUnits: Record<ResourceClass, number>;
  reservedUnits: Record<ResourceClass, number>;
  debt: number;
  lastServedAt?: string;
  starvationMs: number;
}
interface CapacityForecast {
  forecastId: string;
  horizon: string;
  granularityMs: number;
  demandSeries: Array<{ time: string; resource: ResourceKey; p50: number; p95: number; p99: number }>;
  supplySeries: Array<{ time: string; resource: ResourceKey; expected: number; lower: number; upper: number }>;
  assumptions: string[];
  headroomTarget: number;
  confidence: number;
  createdAt: string;
}
```

## 生命周期与状态机

### Capacity request

```text
Created
 -> Normalized
 -> Estimated
 -> PolicyChecked
 -> QuotaChecked
 -> BudgetChecked
 -> SupplyChecked
 -> Reserved
 -> Admitted
 -> Queued
 -> Leased
 -> Running
 -> Settling
 -> Released
 -> Completed
```

分支：`QueuedByCapacity`、`PartiallyReserved`、`Degraded`、`Shed`、`Denied`、`Expired`、`Unknown`、`FailedOver`。

### Reservation

```text
Requested -> Holding -> Held -> Committed -> Used -> Settling -> Released
```

分支：`PartiallyHeld`、`Expired`、`Revoked`、`Conflict`、`Unknown`。

### Pool

```text
Discovered -> Attested -> Warmup -> Ready -> Serving -> Draining -> Drained
```

分支：`Degraded`、`Quarantined`、`Failed`、`Recovering`。

### 状态不变量

- `Admitted` 必须有有效 reservation、quota、budget、policy 和 capacity snapshot。
- reservation 过期后不能由旧 worker 写入 usage；fencing token 使旧写入无效。
- `Running` 不等于业务成功；必须等待 result/receipt/settlement。
- `Shed` 不得与 `Completed` 混淆；用户通知要说明原因和重试选择。
- scale desired 不等于 ready supply；只有 attested worker 才进入 allocatable。
- failover 会产生新的 region/pool decision，不覆盖原 run 的历史 capacity evidence。
- release 必须幂等；unknown usage 不能直接释放为零。

## 中文决策流程

### 端到端决策流程

```text
收到 workflow/run 请求
 -> 解析 definition/version 和 resource contract
 -> 冻结 tenant、workspace、policy、budget、region、provider、model、tool、sandbox snapshot
 -> 将 graph readiness 转成可执行 step demand
 -> 根据历史、definition、fan-out 和 deadline 估算 arrival、duration、tokens、bytes 与 retry multiplier
 -> 检查 tenant/workspace quota、reserved share、burst、budget、privacy 和 policy
 -> 读取各 region/pool/provider/model/tool/sandbox/artifact 的 supply 与 health evidence
 -> 计算 queue delay、service rate、headroom、deadline risk 和 cost
 -> 先保留关键路径和恢复余量，再按 fairness/priority/aging 选择候选
 -> 原子创建 reservation，返回 admit、queue、degrade、shed 或 deny
 -> 只有 reservation 有效才 enqueue 和发放 lease
 -> worker heartbeat、meter usage、checkpoint，异常时释放或恢复 reservation
 -> 结算实际 usage/cost，更新 backlog、fairness debt 和 forecast
 -> reconciliation 比较 reservation、lease、usage、queue、provider receipt 和账本
 -> 触发 scale、backpressure、shedding、failover 或 incident
```

### 解释语句模板

- “本次 run 被排队，因为 `model_tpm` 的 p95 需求超过当前 region 的可用供给；预计等待 18 秒，reservation 在 60 秒后过期。”
- “本次 step 被降级为 summary/artifact-only，因为 artifact egress pool 没有满足原始 payload 的容量和 privacy contract。”
- “本次工作被拒绝，因为 tenant quota、预算上限和可用 burst 均不足；不是因为 CPU 利用率过高。”
- “本次 failover 选择 region B，因为 region A 的 provider capacity evidence 过期且 deadline risk 超过阈值。”
- “本次资源已保留但尚未 ready；desired scale 不等于可执行 supply，系统继续保护关键路径 headroom。”

### Reason codes

```text
DEMAND_UNBOUNDED / FANOUT_LIMIT / DEPENDENCY_NOT_READY
TENANT_QUOTA_EXCEEDED / WORKSPACE_QUOTA_EXCEEDED / RESERVED_SHARE_EXHAUSTED
BURST_EXHAUSTED / BUDGET_CAP / COST_ESTIMATE_UNKNOWN
POOL_UNAVAILABLE / CAPABILITY_MISMATCH / PROVIDER_QUOTA / MODEL_TPM / MODEL_RPM
TOOL_CONCURRENCY / SANDBOX_CAPACITY / ARTIFACT_IO / QUEUE_STORAGE
HEADROOM_PROTECTED / DEADLINE_RISK / BACKLOG_AGE / FAIRNESS_AGING
POLICY_DENY / PRIVACY_RESIDENCY / APPROVAL_REQUIRED / CIRCUIT_OPEN
BACKPRESSURE / LOAD_SHEDDING / REGION_DEGRADED / FAILOVER_REQUIRED
RESERVATION_CONFLICT / LEASE_EXPIRED / USAGE_UNKNOWN / EVIDENCE_STALE
```

## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成

### Model

Model routing 提供 provider、API family、model、deployment、region、capability、TPM/RPM、concurrency、latency、cost 和 health demand/supply 输入。

- input/output token、reasoning、cache、stream 和 batch 都进入 demand。
- fallback、retry、hedge 和 provider unknown 产生新的 demand 与 reservation，不复用 primary 余量。
- route snapshot 冻结可用 region、provider quota、budget 和 capacity evidence。
- Capacity Controller 不因“模型返回了文本”直接释放整个 step reservation；等待 usage 和 settlement。
- provider 429/容量错误更新 service rate 和 circuit，但不把错误无限 retry 成 arrival storm。

### Prompt

- Prompt 负责语义要求和输出契约；容量系统只读取 token estimate、priority、deadline、sensitivity、tool hints 和 context class。
- Prompt 不能通过文字提升 priority、quota、reserved share 或 bypass admission。
- prompt size、system rules、memory summary、tool schema 和 output budget 分项计量。
- prompt compaction 是降低 demand 的策略，必须记录质量风险和新 ContextPlan snapshot。

### Context

- ContextCompiler 输出资源清单、token/byte 预算、候选 memory、artifact range、embedding/rerank demand。
- context overflow 先走可解释的 summarize、artifact-only、defer 或 deny，不直接发送超限请求。
- recall、embedding、rerank 和 compaction 是独立 work unit，拥有独立 resource class、quota、SLO 和 retry budget。
- ContextPlan 变更可能改变 model demand，必须重新估算和 reservation delta。

### Tool

- tool schema、参数大小、执行时长、CPU、memory、网络、外部 API rate 和并发都是 demand。
- tool approval、sandbox profile、filesystem scope、egress policy 是硬约束，不可因 pool 空闲而放宽。
- 并行 tool fan-out 先计算最大并发和 join barrier，再分配 reservation。
- side-effect tool 的 unknown outcome 需要保留 query/recovery capacity，不能把 slot 当成功释放。

### State

- State/Event Store 记录 capacity request、snapshot、reservation、lease、usage、decision、scale、shedding 和 reconciliation facts。
- queue、checkpoint、event write、projection backlog 和 state read/write 是独立容量域。
- replay 只重建 capacity state，不重新扩容、发送 provider、执行 tool 或重复 reservation。
- usage ledger 以 reservation id、attempt id 和 idempotency key 去重；adjustment 追加，不覆盖历史。

### Policy

Policy 提供 priority floor、deadline class、allowed region/provider/model/tool/sandbox、retention、privacy、approval、quota 和 cost cap。

- `visibility -> call -> approval -> execution -> egress` 每层都可能减少可用候选。
- Capacity 不得把低优先级 policy 解释成安全许可，也不得因为供给不足放宽 privacy、residency 或 approval。
- emergency policy revoke 可以撤销 reservation、drain pool、停止新 egress，但必须有 durable control event。

### Harness

Harness 负责：

- 创建 RunScope、CapacitySnapshot、PolicySnapshot、BudgetSnapshot、ContextPlan、AbortController 和 child scope。
- 将 reservation、lease、heartbeat、checkpoint、usage、cost、cancel、retry、recovery、delivery 与 workflow truth 关联。
- 传播 parent cancel、budget stop、deadline、incident、region drain 和 provider revoke 到 subagent、queue、worker、tool 和 model。
- 不把 capacity dashboard、worker 自报或 Host ack 当作 terminal truth。

## 容量模型（capacity model）与 Little 定律

### Work unit

不同 workflow 的 work unit 不能只用请求数表示。建议按 resource class 记录：

```text
model = request + input_tokens + output_tokens + reasoning_tokens + stream_ms
worker = active_ms + cpu_ms + memory_mb_ms + disk_bytes
queue = enqueued_job + lease_ms + retry_attempt + dead_letter
tool = invocation + duration_ms + external_rate_unit + network_bytes
sandbox = process + cpu_ms + memory_mb_ms + filesystem_bytes + network_bytes
artifact = ingress_bytes + egress_bytes + storage_byte_seconds + scan_items
state = read/write operations + event bytes + projection lag
subagent = child_run + depth + fanout + delegated tokens
```

### Arrival 与 service rate

- `λ` 是进入某个 capacity domain 的有效 work unit/秒。
- `μ` 是一个可用服务槽在当前失败、重试、延迟和 capability 下的有效 work unit/秒。
- `c` 是可同时服务的独立槽数；基础稳定条件是 `ρ = λ / (c × μ) < 1`。
- 对 burst workload 使用窗口、p95/p99 和 fan-out，而不是只看长周期平均。
- retry、fallback、hedge、unknown recovery 和 replay 产生额外 arrival；必须进入 effective λ。

### Little's law

```text
L = λ × W
```

- `L` 是系统中平均 work 数，`W` 是从 accepted 到 completed 的平均时间。
- 对 queue 使用 `Lq = λ × Wq`，不要把 backlog 深度直接等同于服务能力。
- 估算时分别计算 ready backlog、leased backlog、running、waiting、unknown 和 recovery backlog。
- 如果 arrival 增加而 service rate 不变，queue delay 和 deadline risk 会先于 CPU 告警上升。
- Little 定律是稳态近似，不能替代 burst、故障域、依赖阻塞、容量异质性和 SLO 分位数分析。

### Headroom

```text
headroom = allocatable - reserved - safety_floor - failure_reserve - recovery_reserve
```

- `safety_floor` 防止单一 tenant 或关键路径耗尽共享池。
- `failure_reserve` 用于 provider、worker、AZ、region 或 deployment 故障。
- `recovery_reserve` 用于 lease recovery、reconciliation、replay、delete、notification 和 DR。
- headroom 不是“闲置浪费”；它是满足 SLO 和恢复的可用能力。
- 关键 interactive pool 的 headroom 目标可高于 background pool；具体值写入 versioned policy。

### Deadline risk

```text
deadline_risk
 = P(queue_delay + service_time + retry_time + recovery_time > deadline)
```

至少用 backlog age、candidate queue delay、p95 service、retry budget、provider health 和 reservation confidence 估算，不用单一平均值。

## Resource Class 与资源账本

### 分类原则

- 每一类资源有 owner、unit、meter、quota、reservation、usage、SLO、failure mode 和扩容方式。
- 可替代资源必须显式记录 substitution；不同 provider/model/region 不能隐式混算。
- resource class 之间存在约束图，例如 model token 需要 worker slot，tool 需要 sandbox，artifact upload 需要 egress 和 storage。
- 关键路径使用 `AND` reservation；可选 fallback 使用 `OR` candidate capacity。
- reservation graph 要能在 partial failure 后释放未使用边。

### Reservation ledger

```text
requested -> held -> committed -> consumed -> settled -> released
```

每条 ledger entry 记录 reservation id、scope、resource key、requested/held/used/released、expiry、fencing、source、receipt 和 cost ref。

- 并发 reservation 使用 CAS/version 或等价原子操作。
- 相同 idempotency key 返回同一 reservation；payload 不同返回 conflict。
- release 和 settlement 必须幂等，不能让重复 worker 释放两次。
- usage unknown 时保持 reserved/unknown，直到 status query、manual review 或 reconciliation。
- quota、budget 和 resource 账本必须能按 tenant、workspace、run、attempt、provider、region 聚合。

## Worker、Pool、Provider、Model、Tool

### Worker capacity

Worker 报告 capability、CPU、memory、disk、network、sandbox profile、region、active lease、drain state 和 attestation。

- 只有 ready 且 attested worker 进入 allocatable。
- liveness 成功不等于 readiness；连接 provider、queue、state、sandbox 和 artifact 失败应标记 degraded。
- heartbeat 延迟、lease age、checkpoint lag 和 orphan process 是容量信号。
- drain 先停止新 lease，再等待可取消边界、checkpoint、receipt 和 reservation release。
- worker crash 后恢复器需要 recovery capacity，不能把全部池容量继续发给新工作。

### Pool

建议按 interactive-critical、interactive-standard、background、recovery、artifact、embedding、rerank、subagent、sandbox profile 和 region 分池。

- 每池有独立 capacity、worker、priority range、retry、SLO、quota、headroom 和 incident policy。
- recovery pool 不能被普通 background backlog 抢占。
- pool merge/split 保留 reservation、job、attempt、fencing 和 usage lineage。
- noisy-neighbor protection 既在 pool 层也在 tenant 层实施。

### Provider/Model

- provider capacity 维度至少包括 API family、model、deployment、region、credential、RPM、TPM、concurrency、latency 和 cost。
- catalog freshness、health、circuit、quota receipt 和 rate-limit header 是 evidence，不是模型回答。
- provider 429、capacity exhausted、context overflow、tool mismatch 和 policy deny 分开计量。
- fallback 只在 policy、residency、budget、capability、capacity 和 privacy 交集非空时执行。
- provider capacity unknown 时可 queue 或本地 degrade，不应无界 hedge。

### Tool capacity

- 每个 tool 记录 max concurrency、rate、duration distribution、CPU/memory、network、external quota、approval latency 和 side-effect class。
- 队列 slot、sandbox slot 和外部 API rate 必须同时 reservation。
- tool 返回大结果时，把 artifact I/O 和 storage capacity 纳入 demand。
- tool retry 使用独立 retry budget；业务副作用 unknown 需要 status query capacity。

## Sandbox、Artifact、Queue 与存储容量

### Sandbox

- sandbox profile 按 CPU、memory、disk、process、network、GPU、timeout、workspace 和 egress 分配 capacity。
- filesystem snapshot、path lock、container/VM warmup、image pull 和 orphan cleanup 都有容量项。
- image cache 命中降低启动 demand，但 cache storage、tenant scope 和 eviction 也需计量。
- sandbox 资源超限应进入 bounded cancellation 或 deny，不以宿主机超卖解决。

### Artifact

- artifact capacity 分为 ingress、egress、storage byte-second、scan、range read、replication 和 CDN delivery。
- raw、sanitized、summary、diff、snapshot、export、forensic class 使用不同 retention 和 quota。
- 大文件采用 `ArtifactRef`；queue payload 只保存引用、hash、size、range 和 privacy snapshot。
- artifact upload 的 provider、region、egress、storage 和 DLP 需求必须一起 reservation。
- storage pool full 时可压缩、延期、artifact-only、拒绝或清理到期对象，不能静默丢结果。

### Queue 与 Event

- queue capacity 包括 depth、partition、enqueue rate、lease rate、visibility、DLQ、storage bytes、index、event write 和 projector lag。
- backlog 必须按 tenant、queue class、priority、deadline、age、resource class、region 和 retry ordinal 分层。
- queue visible 不等于资源可执行；依赖 waiting、quota、approval 和 provider circuit 仍可能阻塞。
- durable queue 的 lease、heartbeat、ack/nack、recovery 和 fencing 自身需要 capacity。
- event/projector backlog 会扩大 state read、delivery 和 reconciliation demand，不能只扩 worker。

## Tenant/Workspace Quota

### 层级

```text
organization
 -> tenant
   -> user
     -> workspace
       -> project
         -> session
           -> run
             -> step/attempt/subagent
```

### Quota 设计

- quota 维度包括 concurrent runs/steps、model tokens、provider requests、tool calls、sandbox CPU/memory、artifact bytes、queue rate、storage、egress、subagent depth 和 budget。
- 父级 quota 是 safety floor；子级只能收紧或在明确的 reserved share 内细化。
- reservation 在动作前扣除；实际 usage 在 settlement 后调整；并发运行不能超卖。
- quota key 绑定 tenant、workspace、resource class、region、provider/model/tool、priority class 和 policy version。
- quota 变更不静默改变已冻结 run；新 run 使用新 snapshot。

### Noisy neighbor

- 单 tenant burst 不得让其他 tenant 没有 reserved share、worker、provider quota、event capacity 或 recovery capacity。
- weighted fair queue、per-tenant concurrency、token bucket、aging 和 admission debt 共同使用。
- tenant fan-out 按 parent budget、depth、child count、resource multiplier 限制。
- workspace 内部也需隔离 interactive、background、maintenance 和 recovery 工作。
- quota exceeded 的用户通知包含当前使用、预计恢复时间、可用降级和管理员路径，不泄露其他 tenant 数据。

## Reserved、Burst、Concurrency 与 Fairness

### Reserved 与 Burst

- `reserved` 是长期或关键业务保证；`burst` 是在未使用 headroom 内的临时借用。
- burst 必须有上限、TTL、回收顺序、成本规则、fairness debt 和拒绝原因。
- reserved capacity 不可被普通 burst 永久侵占；关键 SLO pool 预留 recovery floor。
- burst 使用后产生 debt，后续调度按 aging 或 rate 限制偿还。
- provider 的 reserved throughput、模型套餐和 worker warm pool 分开计量。

### Concurrency

- workflow、run、step、attempt、tool、subagent、provider、model、sandbox、artifact 和 storage 各有并发上限。
- parallel DAG 的并发由依赖、join、resource contract、tenant quota 和 deadline 共同裁剪。
- concurrency limit 不是 rate limit；二者都要进入 admission。
- lease count 不等于 active execution；waiting approval、provider stream、blocked dependency 要分别统计。
- cancellation 要释放可释放资源；side-effect unknown 仍保留 query/recovery slot。

### Fairness

推荐使用 weighted fair queue + deficit/virtual finish + aging：

```text
effective_priority
 = base_priority
 + deadline_urgency
 + aging_bonus
 + fairness_debt_bonus
 - noisy_neighbor_penalty
 - cost/risk_penalty
```

- 高 priority 不能永久饿死低 priority tenant。
- fairness 是 tenant/workspace/resource class/region 维度，不能只做全局 FIFO。
- 记录每个 scope 的 virtual finish、reserved share、consumed units、debt、starvation 和 last served。
- 关键任务可以抢占 cooperative work，但必须 checkpoint、release reservation、fence old lease 并记录 reason。
- fairness trade-off 以 SLO、deadline、policy 和 tenant contract 解释，不能隐藏在一个总分中。

## Backlog、Admission、Backpressure 与 Shedding

### Backlog

backlog view 至少包含 ready、queued、leased、running、waiting、retrying、unknown、recovery、dead-letter、年龄、deadline、priority、fairness debt 和 estimated units。

- backlog age 比深度更能预测 deadline miss；两者都需要 p50/p95/p99。
- backlog 按 dependency blocked、quota blocked、capacity blocked、approval waiting、provider circuit 和 artifact blocked 分解。
- backlog growth 的根因可能是 arrival storm、service slowdown、retry storm、projection lag 或 reservation leak。
- backlog reconciliation 对比 queue、run truth、lease、reservation 和 worker active state。

### Admission 顺序

```text
身份/tenant scope
 -> workflow contract/依赖 readiness
 -> policy/privacy/approval
 -> demand upper bound
 -> quota/reserved/burst
 -> budget/cost cap
 -> region/provider/model/tool/sandbox capability
 -> supply/headroom/deadline
 -> reservation CAS
 -> queue enqueue
```

- admission 失败不得产生无界 retry 或重复 job。
- partial reservation 只有在 workflow contract 支持 partial 时返回；否则原子失败。
- enqueue 成功但 reservation commit 失败进入 reconciliation，不直接执行。
- admission decision、reason、snapshot、reservation 和 notification 都写 durable event。

### Backpressure

- queue producer 根据 backlog、arrival rate、service rate、headroom、quota 和 deadline risk 调整 token bucket。
- 上游返回 `accepted/queued/deferred/degraded/rejected`，不是统一 200。
- Model/Tool/Provider API 的 retry-after 进入 capacity controller，不让每个 worker自行睡眠重试。
- backpressure 传播到 Host、Orchestrator、Subagent fan-out、Prompt/Context compiler、artifact ingest 和 notifications。
- backpressure 是策略化控制，不能仅靠连接超时。

### Shedding

按安全顺序选择：

```text
合并/去重 -> 延迟低优先级 -> 降低 fan-out -> summary/artifact-only
-> 禁止 hedge/shadow -> 暂停 background -> 拒绝新低优先级
-> 取消可重试且无副作用工作 -> 保留 recovery/interactive critical
```

- 不得 shed 正在未知副作用中的查询、audit、deletion、incident、reconciliation 和 hold 工作。
- shedding 需要 reason、scope、estimated recovery、用户通知和可重放证据。
- 绝不能通过 shed policy、privacy、approval、tenant isolation 或 settlement 来恢复容量。

## Deadline、SLO 与容量余量

### SLO 分层

分别测量：

- admission acknowledgement、queue start、first event、model turn、tool completion、artifact upload、完整 run、terminal settlement、后台 deletion 和 recovery。
- p50/p95/p99 latency、deadline miss、queue age、unknown resolution、fairness、cost 和 error budget。
- interactive、standard、background、recovery、tenant tier、region、provider/model/tool 单独统计。

### Deadline admission

- `deadlineAt` 冻结在 RunSnapshot；子 step 的 deadline 不得晚于 parent contract。
- admission 使用 queue delay + service p95 + retry/recovery allowance + delivery margin。
- deadline risk 超阈值时选择更快合规 route、降低 fan-out、预留 capacity、degrade 或 deny。
- 不能用高 priority 无限绕过 tenant quota、budget、privacy、residency 或 tool approval。
- 已无法满足 deadline 的工作应尽早解释和重新计划，而不是继续消耗关键池。

### Headroom policy

- interactive-critical、provider failover、recovery、audit、deletion 和 incident pool 设置显式 safety floor。
- 维护、deploy、AZ 故障、provider outage 和 replay 使用 failure/recovery reserve。
- headroom burn rate 触发 warning/critical；不等同于利用率过低。
- 发布、迁移和大租户开通必须验证 headroom 在最坏情形仍满足 SLO。

## Cost、Budget 与容量权衡

### 成本维度

```text
model tokens/reasoning/cache
provider request/region/reserved throughput/failure retry
worker CPU/memory/disk/idle reservation
sandbox process/image/network
queue storage/lease/retry/DLQ
artifact storage/scan/egress/replication
embedding/rerank/subagent/backup
```

- estimate before action、reserve before concurrency、settle after usage、reconcile against receipt。
- 每次 retry/fallback/hedge/subagent 都有新的 usage/cost entry。
- reservation 不是实际扣费；未使用部分在 settlement release，并保留 adjustment 事实。
- 预算硬上限可以触发 queue、degrade、pause、approval 或 deny，但不能放宽安全和隐私。
- 成本选择必须同时满足 quality floor、deadline、residency、provider contract、fairness 和 capacity headroom。

### Capacity-cost decision

```text
候选 route
 -> 检查 capability/policy/residency
 -> 估算 latency、tokens、worker、egress 和 currency
 -> 计算 backlog/deadline/headroom
 -> 在 budget cap 内排序
 -> reservation + cost estimate
 -> settle actual usage
```

- cheapest route 不是默认最优；它可能有更低 service rate、更高 retry 或更少 headroom。
- 预留高峰吞吐可以增加固定成本，但应与 deadline miss、fallback 和 incident 成本比较。
- capacity controller 与 Cost Governance 共用 snapshot version，避免价格/配额漂移造成超卖。

## Regional Capacity、DR 与 Failover

### Regional model

每个 region 记录：

- worker/pool 总量、healthy/allocatable、provider/model/tool quota、artifact/storage、queue/event、network egress。
- data residency、tenant allowlist、provider deployment、latency、failure rate、cost、headroom 和 forecast。
- region health、capacity evidence freshness、maintenance/drain 和 replication lag。

### Failover

```text
region degraded
 -> freeze new high-risk admission
 -> classify in-flight/unknown/queued work
 -> preserve snapshot, reservation and idempotency
 -> select compliant target region
 -> check quota/capacity/residency/cost/deadline
 -> reserve target capacity
 -> fence old worker/lease
 -> enqueue recovery/failover job
 -> query provider/tool side effect
 -> reconcile and notify
```

- failover 不是把队列字符串复制到另一 region；必须重做 policy、capacity、residency、budget 和 capability evaluation。
- primary region reservation 不自动等于 secondary reservation；DR 要有预留或明确 RTO/RPO。
- 未知 provider side effect 先查询状态，再决定 fallback，避免双重副作用。
- region 复旧时先 drain、reconcile、replay tombstone/checkpoint，再逐步恢复 admission。

### DR 指标

- RTO/RPO、capacity warmup time、queue replication lag、state/event recovery、artifact restore、provider route readiness、reconciliation completion。
- DR drill 必须测 interactive、background、unknown、deletion、audit、budget 和 tenant isolation。
- 备份容量、restore I/O、rebuild vector/index、replay event 和 recovery worker 都需要 capacity reservation。

## Autoscaling 与容量控制器

### Signals

autoscaling 使用多信号：

- queue age/depth、arrival/service rate、deadline risk、lease wait、reservation rejection。
- worker active/free、CPU/memory/disk、sandbox startup、artifact I/O、event lag。
- provider RPM/TPM/concurrency、429、circuit、latency、capacity error。
- tenant quota pressure、fairness debt、headroom burn、cost budget 和 forecast。

CPU 只能作为 worker resource signal，不能作为 workflow autoscaling 的唯一触发器。

### 控制循环

```text
observe durable metrics
 -> validate evidence freshness
 -> estimate demand/supply/headroom
 -> simulate scale and cost
 -> check quota/region/DR/policy
 -> create versioned ScalePlan
 -> warm/attest/drain pool
 -> observe ready supply
 -> reconcile desired vs actual
```

- scale up 有 warmup、image pull、credential、provider quota、artifact、network 和 budget 延迟。
- scale down 先停止新 lease，再等待 checkpoint、receipt、cancel safe boundary 和 reservation release。
- oscillation 用 cooldown、hysteresis、minimum pool size、forecast smoothing 和 rate limit 防止。
- provider quota、sandbox license、storage 和 region capacity 可能无法 autoscale，控制器必须返回 queue/degrade/failover。
- ScalePlan、ScaleReceipt、actual ready time、cost 和失败原因进入 evidence。

## Forecast 与容量计划

### 输入

- workflow/run/step arrival、seasonality、tenant growth、fan-out、priority、deadline、retry、provider outage、deploy、maintenance、DR drill。
- service time p50/p95/p99、token/byte distributions、artifact size、tool external rate、subagent depth。
- quota contract、reserved share、price、region、provider catalog、headroom policy 和 reliability target。

### 输出

- 每个 region/resource class 的 p50/p95/p99 demand、supply lower/upper、headroom burn、capacity gap、扩容提前量和成本区间。
- baseline、expected、stress、failure scenario 分开；不把高峰平均值掩盖成单一 forecast。
- forecast 记录数据窗口、版本、假设、confidence、模型变更和人工 override。

### 计划节奏

- 每日短期 backlog/deadline forecast。
- 每周 worker、provider、tool、artifact、storage 和 tenant quota review。
- 每月 region、reserved throughput、DR、成本、headroom 和增长计划。
- 重大 workflow/version、模型切换、subagent fan-out、价格或租户上线前做 capacity review。
- forecast 偏差进入 capacity incident 或模型校准，不静默覆盖历史 evidence。

## Load/Soak/Stress/Chaos 测试

### 测试模型

使用 deterministic provider、scripted tool、fake queue、fake pool、fixed clock、synthetic tenant、artifact generator、fault injector 和 side-effect oracle。

- 记录 arrival、service、fan-out、tokens、bytes、cost、deadline、retry、unknown、region 和 fairness ground truth。
- 测试 interactive、background、recovery、embedding、rerank、artifact、notification 和 deletion workload 的混合比例。
- 验证 capacity decision 可解释、reservation 无超卖、fairness 不饿死、headroom 受保护。

### Load test

- 逐步增加 arrival rate，测 admission、queue、lease、worker、provider、tool、artifact、state 和 settlement。
- 以 p95/p99 queue age、deadline miss、reservation rejection 和 effective service rate 判断拐点。
- 注入 tenant burst、workspace fan-out、large prompt、large artifact、parallel tools 和 provider rate limit。

### Soak test

- 连续 24/48/72 小时混合负载，观察 reservation leak、lease leak、fairness debt、memory、queue storage、index、cost 和 TTL drift。
- 周期性加入 deploy、worker drain、provider route change、quota update、reconciliation 和 compaction。
- 断言长时间运行不会让 last_accessed 无限延长、未知 job 无限积累或低优先级永久饥饿。

### Stress test

- 超过稳定容量持续推压，验证 backpressure、queue boundedness、shedding、degrade、budget cap、notification 和恢复。
- 记录从 accepted 到 rejected 的转折点、recovery time、headroom burn 和数据面副作用。
- 压力测试不使用真实高权限生产 credential，不执行未审批 side effect。

### Chaos test

注入：

- worker crash、AZ/region outage、provider 429/5xx/stream EOF、model capacity error。
- queue partition、lease expiry、duplicate delivery、event lag、state CAS conflict、artifact backend down。
- tool timeout、sandbox orphan、image pull failure、storage full、network partition、clock skew。
- budget/quota service down、capacity evidence stale、autoscaler failure、forecast error、DR restore。

必须断言：不跨 tenant、不绕过 policy/residency、reservation 不超卖、旧 lease 不能写入、unknown 不重复副作用、recovery pool 保留、audit/usage/receipt 可重放。

## Capacity Incident 与 Runbook

### 事件触发

- p99 queue age、deadline miss、reservation rejection、headroom burn、backlog growth 或 fairness starvation 超过 SLO。
- provider/model/tool/sandbox/artifact/queue/state capacity evidence stale 或 supply 突降。
- retry storm、fan-out storm、lease leak、reservation leak、storage full、event lag 或 cost spike。
- DR failover capacity 不足、recovery backlog 无法下降、shed 规则误伤关键工作。

### 事件分级

```text
SEV1 cross-tenant/safety/settlement 或关键 workflow 全面无法执行
SEV2 critical SLO、region、provider 或 recovery capacity 大范围受损
SEV3 单 tenant/resource class/backlog 超阈值但有安全降级
SEV4 forecast、metric、evidence 或 dashboard 偏差，无即时用户影响
```

### 通用 Runbook

1. 固定 incident scope、region、tenant、resource class、时间窗和影响的 run/step/job。
2. 读取 CapacitySnapshot、Quota/Budget/Policy snapshot、reservation ledger、queue backlog、lease、usage、provider receipt 和 forecast。
3. 区分 arrival storm、service slowdown、resource outage、reservation leak、retry storm、dependency block、evidence stale 和 autoscaler failure。
4. 保护 interactive-critical、recovery、audit、deletion、incident、hold 和 reconciliation pool。
5. 停止无界 retry、hedge、shadow、subagent fan-out、低优先级 background 和非必要 artifact copy。
6. 检查 quota、budget、privacy、region、provider route 和 failover capacity；不得用 fail-open 恢复。
7. 启动 bounded scale、drain、degrade、queue、shed 或 compliant failover。
8. 对 leased/running/unknown 工作查询 side effect，不能盲目重放。
9. 监控 backlog age、service rate、headroom、fairness、deadline、cost、reservation release 和 evidence freshness。
10. 恢复后做 queue/run/lease/reservation/usage/provider/ledger reconciliation。
11. 通知受影响用户/tenant，说明 queued、degraded、shed、partial、unknown 和预计恢复。
12. 生成时间线、根因、容量缺口、永久修复、测试 fixture 和 release gate。

### Backlog Runbook

- 先按 queue class、tenant、priority、deadline、resource class、retry 和 age 分片。
- 对比过去窗口 arrival/service，识别 λ 上升还是 μ 下降。
- 查 readiness/approval/provider circuit/region/queue partition 是否造成虚假 capacity shortage。
- 扩容前检查 provider quota、artifact/storage、event、budget 和 headroom；只扩 worker 可能无效。
- 应用 fairness/aging、reserved share、bounded shedding 和用户通知。
- backlog 下降后保持 cooldown，验证 recovery、reconciliation 和低优先级公平恢复。

### Reservation Leak Runbook

- 对比 reservation ledger、lease、job、worker active、usage 和 settlement。
- 找出无 job reservation、有 job 无 lease、过期未 release、重复 idempotency 和 fencing mismatch。
- 暂停自动释放高风险 unknown；由 recovery worker query side effect。
- 对确定无执行的 reservation 做幂等 release；对已执行但未结算的写 usage/adjustment。
- 修复 CAS、outbox、lease recovery 或 shutdown hook，增加 crash fixture。

### Provider/Region Runbook

- 区分 provider quota、deployment capacity、region outage、network、credential、policy 和 model capability mismatch。
- 停止无界 fallback/hedge，读取 route/capacity evidence freshness。
- 选择符合 residency、privacy、budget、deadline、tool capability 的 region/provider。
- 预留 target capacity 后再 failover；旧 lease fence，unknown request 先查状态。
- 对恢复流量做 canary、rate ramp、headroom 和 cost 监控。

## Capacity Evidence 与 Release Gate

### Evidence 类型

```text
CapacitySnapshot / DemandEstimate / SupplyAttestation / ReservationReceipt
LeaseReceipt / WorkerHeartbeat / UsageMeter / ProviderReceipt / QueueWatermark
QuotaDecision / BudgetReservation / ScalePlan / ScaleReceipt / Forecast
FairnessState / BacklogReport / ReconciliationReport / IncidentTimeline
```

每条 evidence 记录 source、scope、resource key、版本、时间、expiry、hash、owner 和 integrity reference。

### Reconciliation

周期性比较：

```text
capacity catalog vs worker/provider/pool attestation
reservation ledger vs queue/job/lease
lease vs worker active execution
usage meter vs provider/tool/artifact receipt
quota/budget reservation vs settlement
backlog projection vs durable queue/run truth
desired scale vs ready/allocatable supply
region failover plan vs actual DR capacity
forecast vs observed demand/service rate
fairness state vs served work
```

finding 必须有 severity、owner、safe repair、deadline、status 和 evidence；dashboard 数字本身不是 repair。

### Release gate

Hard gate：

- reservation 超卖、跨 tenant/workspace、旧 lease 写入、unknown 被重复执行。
- critical SLO 无 headroom、recovery/audit/deletion capacity 被吞噬。
- provider fallback 绕过 policy/residency/budget/capability。
- autoscaler 无 bounded limit、无 dry run、无 rollback 或无法解释 cost。
- queue/run/usage/settlement reconciliation 有不可解释差异。
- DR/failover 无 target reservation、tombstone、idempotency 或 side-effect query。

Soft gate：forecast 偏差、非关键 queue latency、低风险 cost、dashboard freshness 和非关键 pool 利用率。

### 发布前证据

- 新 workflow version 提供 resource contract、fan-out 上限、token/byte estimate、deadline、retry、artifact 和 sandbox demand。
- 新 provider/model/tool/region 提供 capability、quota、latency、cost、privacy、residency、failure 和 delete/receipt contract。
- 新 tenant/workspace 提供 quota、reserved share、burst、budget、fairness、region、DR 和 SLO。
- 运行 load/soak/stress/chaos、capacity forecast、reconciliation、rollback 和 incident drill。
- 证明 CPU、queue、provider、artifact、storage、budget、headroom、fairness 和 deadline 不是单点瓶颈。

## 反模式

1. 只看 CPU 利用率 dashboard 就宣布 workflow 有容量。
2. 用 queue depth 一个数字代表所有 tenant、priority、region 和 resource class。
3. 让 worker 自己决定 retry、fallback、scale 或 quota。
4. 只扩 worker，不检查 provider TPM/RPM、tool rate、artifact/storage、event 和 budget。
5. 把 desired replicas 当作 ready allocatable supply。
6. 用平均 arrival/service 隐藏 burst、p99、fan-out、dependency block 和 deadline。
7. 没有 reservation 就 enqueue，导致并发超卖和 admission 竞态。
8. reservation 过期后旧 lease 仍能写 usage 或完成 job。
9. primary route 的 capacity allow 被 fallback、hedge、shadow 自动复用。
10. 把 burst 当作无限容量，不计算 fairness debt、cost 和 headroom。
11. 一个全局 FIFO 伪装公平，导致 noisy neighbor 和 starvation。
12. 高 priority 永久压过 recovery、低优先级 tenant 或关键维护。
13. 用 autoscaling 掩盖 quota、policy、privacy、residency 或 provider contract deny。
14. 过载时关闭 admission、audit、settlement、DLP 或安全检查。
15. shedding audit、deletion、incident、hold、reconciliation 或 unknown query。
16. 将 model response、worker lease、Host ack 当作业务 settlement。
17. 只记录 CPU/memory，不记录 token、byte、tool、sandbox、queue、storage 和 egress。
18. 只测稳态 load，不测 soak、stress、retry storm、region failover 和 reservation leak。
19. forecast 只用历史平均，不记录假设、confidence、故障场景和版本。
20. 容量 incident 只加实例，不保留 CapacitySnapshot、原因、证据和永久修复。
21. 用 CPU utilization 直接做 scale-to-zero，忽略 warmup、deadline 和 reserved share。
22. 把跨 region failover 当成复制字符串，不重做 policy、quota、budget、capacity 和 side-effect query。
23. 允许 subagent fan-out 无 parent budget、depth、child quota 和 recovery reserve。
24. 只测单租户 happy path，不测多租户 burst、fairness、cross-tenant 和 noisy neighbor。
25. 用 dashboard red/green 覆盖 durable queue、run truth、usage ledger 和 reconciliation 差异。

## 实施清单

### P0：正确 admission 与账本

- [ ] 定义 ResourceClass、CapacityPool、WorkDemand、Reservation、Usage、Snapshot、Decision 和 Evidence schema。
- [ ] 将 workflow definition 的 token、tool、sandbox、artifact、fan-out、retry、deadline 和 region demand 显式化。
- [ ] 实现 tenant/workspace quota、reserved share、burst、concurrency、fairness 和 cost reservation。
- [ ] 实现 admission CAS、idempotency、fencing、lease、heartbeat、release、settlement 和 unknown。
- [ ] 建立 queue/run/lease/reservation/usage/provider receipt reconciliation。
- [ ] 以 queue age、service rate、deadline risk、headroom、provider quota 和 cost 驱动决策。

### P1：弹性与安全降级

- [ ] 按 interactive、background、recovery、provider/model/tool、sandbox、artifact、embedding/rerank 分池。
- [ ] 实现 backpressure、bounded retry、fairness aging、priority、reservation protection 和 load shedding。
- [ ] 实现 autoscaling、drain、warmup、attestation、cooldown、rollback 和 cost cap。
- [ ] 实现 regional capacity、DR reservation、failover、fencing、side-effect query 和 replay。
- [ ] 建立 capacity incident、backlog、reservation leak、provider/region runbook。

### P2：预测与持续验证

- [ ] 建立 demand/service/forecast 数据集，输出 p50/p95/p99、headroom、capacity gap 和成本区间。
- [ ] 每周做 tenant/provider/tool/storage review，每月做 region/DR/reserved capacity review。
- [ ] 实施 load、soak、stress、chaos、replay、fault injection 和 side-effect oracle。
- [ ] 将容量 evidence、reconciliation、hard/soft release gate 接入 workflow/version/provider/model/tool 发布。
- [ ] 对 forecast 偏差、deadline miss、fairness debt、reservation leak 和 shed 结果做复盘。

### Definition of Done

- [ ] 任何 workflow request 都能解释 demand、供给、quota、reservation、backlog、deadline、budget、region、fairness 和 decision。
- [ ] CPU dashboard 不是唯一容量证据；所有关键 resource class 都有 durable meter、SLO、headroom、quota 和 owner。
- [ ] 过载、provider outage、worker crash、region failover、unknown outcome、DR restore 和 reservation leak 可安全恢复。
- [ ] 多租户 burst 不会跨 scope，低优先级不会永久饥饿，recovery/audit/deletion capacity 受保护。
- [ ] Capacity Evidence、reconciliation、incident/runbook、预测和 release gate 可重放、可审计、可验证。

## 五个参考项目的启发来源

### Pi

- 极小 headless loop、统一 provider event、session tree 和 compaction 启发了 work unit、ContextPlan demand、事件事实和恢复边界。
- 取舍：默认执行隔离和生产容量控制较弱，不能直接作为多租户 quota 或 DR 方案。

### Grok Build

- Rust actor、采样器分层、permission decision、并行工具、路径锁和 sandbox 启发了 pool、resource lock、tool concurrency、worker isolation 和公平执行。
- 取舍：状态机复杂，必须额外记录 capacity snapshot、reservation、fencing 和 reconciliation。

### OpenCode

- client/server 分离、session/message/part、事件总线、durable projector、snapshot/patch/revert 启发了 queue/run truth、event capacity、projection lag、replay 和容量 evidence。
- 取舍：状态迁移与分布式 projector 会扩大 storage/event capacity，不能只扩执行 worker。

### Claude Code

- permission modes、hooks、subagents、skills、memory、MCP、计划和任务工作流启发了 approval latency、subagent fan-out、delegated quota、工具池和用户可见 backpressure。
- 取舍：产品级扩展不能默认继承全部 scope、credential 或容量；每个 child run 要有预算和上限。

### OpenClaw

- AgentHarness registry、独立 agent-core、多渠道 gateway、provider runtime、tool/sandbox/elevated 分层启发了 pool 边界、channel delivery、provider/model/tool capacity 和远程执行隔离。
- 取舍：单 Gateway 或插件进程可能形成大故障域，必须按 region、queue、provider、tenant 和 execution profile 分片。
