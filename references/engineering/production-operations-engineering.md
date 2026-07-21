# Production Operations Engineering 细粒度工程设计
> Production Operations 不是只收集日志。它是把 Agent Harness 运行成可扩展、可恢复、可审计、可预算、可回滚的生产系统：控制面管理身份、配置、策略、队列、部署和恢复；数据面执行模型、工具、sandbox、session、event、artifact 和交付；两者由 SLO、容量、告警、审计和事件响应连接。
>
> 本文只整理当前目录已有的参考架构、Agent Harness 以及 Prompt、Context、Tool、State/Memory、Permission/Sandbox、Subagent、Event/Observability、Evaluation、Coding Agent、Provider Runtime、Artifact、Multi-tenant 文档中已有的源码调研结论；不依赖 README，不新增网络调研结论。
## 目录
1. [设计目标与非目标](#设计目标与非目标) 2. [核心判断与术语](#核心判断与术语) 3. [职责边界](#职责边界) 4. [生产威胁模型](#生产威胁模型) 5. [部署拓扑](#部署拓扑) 6. [Control Plane 与 Data Plane](#control-plane-与-data-plane) 7. [核心组件与包布局](#核心组件与包布局) 8. [核心数据模型](#核心数据模型) 9. [TypeScript 接口](#typescript-接口) 10. [Worker、Scheduler 与 Lease](#workerscheduler-与-lease) 11. [Session/Event/Artifact Store](#sessioneventartifact-store) 12. [健康检查与服务生命周期](#健康检查与服务生命周期) 13. [SLO、SLI 与错误预算](#slosli-与错误预算) 14. [容量模型与资源预算](#容量模型与资源预算) 15. [Queue、Backpressure 与公平性](#queuebackpressure-与公平性) 16. [Rate、Cost 与多层预算](#ratecost-与多层预算) 17. [Autoscaling 与 Noisy Neighbor](#autoscaling-与-noisy-neighbor) 18. [Provider Runtime、Circuit Breaker 与 Outage](#provider-runtimecircuit-breaker-与-outage) 19. [Rollout、Canary 与 Rollback](#rolloutcanary-与-rollback) 20. [Config、Schema 与 Migration](#configschema-与-migration) 21. [Secrets、Credential 与 Egress](#secretscredential-与-egress) 22. [Incident Response](#incident-response) 23. [Runbook](#runbook) 24. [Audit、Forensics 与诊断快照](#auditforensics-与诊断快照) 25. [Backup、Restore 与 DR](#backuprestore-与-dr) 26. [Retention、Deletion 与数据生命周期](#retentiondeletion-与数据生命周期) 27. [Alerting 与 Dashboards](#alerting-与-dashboards) 28. [Chaos、Fault Injection 与 Evaluation](#chaosfault-injection-与-evaluation) 29. [Security Operations 与 On-call](#security-operations-与-on-call) 30. [生命周期与状态机](#生命周期与状态机) 31. [与 Context/Prompt/Tool/State/Policy/Harness 集成](#与-contextprompttoolstatepolicyharness-集成) 32. [故障恢复与降级](#故障恢复与降级) 33. [测试策略](#测试策略) 34. [反模式](#反模式) 35. [实施清单](#实施清单) 36. [五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
Production Operations Runtime 必须：
- 将 Host、API、Gateway、Orchestrator、Kernel、Worker、Scheduler、Provider、Tool、Sandbox、State、Event、Artifact 和 Delivery 组成可运维拓扑。；清晰区分 control plane 与 data plane，避免配置、审批、恢复和高频模型流互相阻塞。；提供 session、event、artifact、projection、audit、checkpoint 和 queue 的持久化边界。；对服务、worker、provider、store、queue、sandbox 和 extension 定义 liveness、readiness、health 和 degraded 语义。；通过 SLI/SLO、错误预算、容量模型、队列深度、成本和租户公平性管理生产质量。；支持多层 queue、backpressure、rate limit、cost budget、concurrency limit、autoscaling 和 noisy-neighbor 防护。；对 provider rate limit、容量错误、断流、context overflow、能力不匹配和区域故障进行分类、熔断、fallback 和恢复。；支持 canary、渐进 rollout、config/schema migration、快速 rollback 和兼容窗口。；让 secret、credential、egress、audit、forensics、backup、restore、deletion 和 DR 可验证。；用 runbook、告警、dashboard、chaos/fault injection、on-call 和 incident review 建立反馈闭环。
### 非目标
本文不负责：
- 选择具体云厂商、数据库、消息队列、容器编排平台或观测产品。；用日志替代 session/event 的业务一致性、audit 或恢复事实。；把 provider 的健康状态当作 Agent run 的业务成功。；把 autoscaling 当作无限容量，或把 retry 当作可靠性唯一手段。；以 Prompt、最终文本、trace span 或 dashboard 推断真实文件/外部副作用。；在生产中用真实高权限凭据执行未隔离的 chaos case。；允许 schema/config 变更绕过 policy、approval、retention 或 tenant scope。
### 核心判断
```text
Production Reliability
  = Durable State
  × Bounded Execution
  × Queue Discipline
  × Provider Isolation
  × Safe Deployment
  × Recovery
  × Security Operations
```
```text
Operations != log collection
Operations = control + execution + state + limits + recovery + evidence
```
## 核心判断与术语
### Control Plane
管理配置、身份、tenant/workspace/session 路由、policy、approval、toolset、model catalog、queue、worker lease、部署版本、migration、预算、审计和恢复控制。
### Data Plane
承载模型 stream、tool execution、sandbox process、filesystem mount、content parts、artifact transfer、event delivery 和用户结果交付。
### Worker
消费 `TenantJob` 或 `RunJob` 的执行单元，必须以 lease、heartbeat、scope context、config snapshot、policy snapshot 和 budget lease 运行。
### Scheduler
根据 priority、tenant fairness、capacity、dependency、deadline、budget 和 circuit state 决定何时把工作交给 worker；不直接改变业务状态。
### Store
- `SessionStore`：session、branch、semantic entries、checkpoint、projection。；`EventStore`：canonical durable event、cursor、replay、retention。；`ArtifactStore`：大内容、diff、日志、二进制、snapshot、range 和视图。；`AuditStore`：安全与治理事实，独立访问控制和 retention。；`ConfigStore`：版本化配置和 migration 状态。
### SLO 边界
SLO 必须区分接受请求、首个事件、完整 run、工具执行、最终交付、durable settlement 和后台清理；不能只用 HTTP 200 或最终文本生成成功率。
## 职责边界
| 模块 | 负责 | 不负责 |
|---|---|---|
| `API/Gateway` | 认证、限流、请求规范化、流式连接和 delivery | 判断工具副作用是否安全 |
| `Orchestrator` | 路由、排队、run 创建、fallback、delivery | 直接执行 shell |
| `Scheduler` | 排队、优先级、公平、依赖和容量选择 | 修改 session 语义 |
| `Worker` | 装配 Harness、执行 run、checkpoint、settlement | 越过 policy 或自选 tenant |
| `RunSupervisor` | structured concurrency、预算、取消、恢复和终止 | 设计部署拓扑 |
| `Session/Event Store` | durable facts、CAS、replay、projection | 产生模型输出 |
| `ArtifactStore` | 大对象、扫描、range、retention 和授权 | 决定 prompt 内容 |
| `Provider Runtime` | adapter、stream、usage、retry、health、circuit | tenant policy 和 tool authorization |
| `Policy/Sandbox` | visibility/call/approval/execution/egress 和 attestation | 业务结果判断 |
| `Config/Migration` | schema、版本、兼容、rollout 和回滚 | 静默改写审计事实 |
| `Observability` | trace、metric、log、diagnostic 和告警 | 作为唯一业务 source of truth |
| `SRE/On-call` | SLO、容量、事故、runbook、演练和改进 | 通过手工命令绕过审计 |
控制面和数据面可以共享代码契约，但不能共享无界的同步阻塞路径。
## 生产威胁模型
### 可用性威胁
- provider 429、5xx、容量不足、区域故障、stream EOF、模型能力漂移。；worker crash、网络分区、event store 延迟、projection backlog、artifact backend 不可用。；queue backlog、慢消费者、subagent fan-out、重复 job、锁泄漏、sandbox orphan。；配置错误、schema migration 失败、版本不兼容、rollout 使旧 checkpoint 无法恢复。
### 安全威胁
- tenant/workspace scope 丢失、cache/queue/trace 串线、错误 worker lease。；secret 出现在 prompt、argv、artifact、日志、provider request 或诊断快照。；provider fallback 违反 region/data residency，MCP/plugin 获得过宽 credential。；operator break-glass 被滥用，audit 被删除或与业务事实不一致。；incident 期间为了恢复而静默 fail-open，导致跨 workspace、未授权执行或数据外发。
### 运营保护目标
```text
tenant/scope integrity
state durability
at-most-once or queryable side effect semantics
bounded cost and capacity
safe degradation
reproducible evidence
operator accountability
```
## 部署拓扑
### 推荐逻辑拓扑
```text
Clients / IDE / CLI / Channel
        |
   API Gateway / Host Adapter
        |
  Authn + Tenant Router
        |
 Control Plane API ---- Config/Policy/Model Catalog
        |                         |
 Orchestrator -------- Scheduler/Queue/Quota
        |                         |
        +-------------------------+
                                  |
                         Worker Pool / Sandbox Pool
                         |       |        |
                    Agent Kernel Tool   Provider Runtime
                         |       |        |
                Session/Event Store  Artifact Store
                         |       |        |
                   Projectors     Audit/Observability
```
### 故障域
- Gateway/API：连接与请求故障域。；Control API：配置、授权和调度控制故障域。；Queue/Scheduler：排队和租约故障域。；Worker/Sandbox：执行故障域，按 tenant、region、profile 或 worker pool 分片。；Provider：外部依赖故障域，按 provider/api family/model/region 独立统计。；Session/Event：语义事实故障域，必须有 durable backup 和 replay。；Artifact：大对象与交付故障域，可与 session 分离扩展。
### 数据驻留与分片
tenant policy、workspace、provider egress、artifact、event、worker 和 backup 选择由 control plane 冻结并注入 `RunScopeContext`。worker 不能仅依据 job payload 中的字符串自行改 region 或 tenant。
## Control Plane 与 Data Plane
### Control Plane 组件
- identity、membership、tenant policy、workspace/project trust。；model catalog、provider health、circuit state、tool registry snapshot。；queue、quota、budget、worker lease、deployment、config 和 migration。；session open/resume、approval、cancellation、steering、retention 和 deletion。；audit、operator action、incident、break-glass 和 recovery control。
### Data Plane 组件
- model request/stream、tool call/result、filesystem、network、sandbox process。；context/prompt render、artifact ingest/transfer、event delivery、host stream。；运行时只使用冻结 snapshot，不在数据路径隐式查询可变全局配置。
### 分离规则
1. 控制面版本变化不应中断已冻结的 run，除非安全事件要求 revoke。 2. 数据面高频 delta 不应阻塞 policy、checkpoint、audit 和 terminal event。 3. control plane 不直接读取完整 prompt、secret 或所有工具输出；使用 metadata/ArtifactRef。 4. data plane 不直接修改 policy、quota、tenant membership 或 schema registry。 5. 失去 control plane 时，正在运行的安全 run 只能继续到已授权边界；新高风险动作停止。
## 核心组件与包布局
```text
packages/operations/
  topology.ts
  service-lifecycle.ts
  health.ts
  slo.ts
  capacity.ts
  budgets.ts
  queue.ts
  fairness.ts
  autoscaling.ts
  rollout.ts
  incidents.ts
  runbooks.ts
  backup.ts
  retention.ts
  testkit/
packages/control-plane/
  identity.ts policy.ts config.ts migration.ts catalog.ts quota.ts worker-leases.ts
packages/data-plane/
  orchestrator.ts worker.ts sandbox-pool.ts delivery.ts
packages/storage/
  session-store.ts event-store.ts artifact-store.ts audit-store.ts projection-store.ts
```
依赖方向：
```text
Host -> Gateway -> Orchestrator -> Harness -> Kernel/ports
Control adapters implement policy/config/queue/lease ports
Data adapters implement provider/tool/sandbox/store ports
Observability and Audit consume canonical events, not private UI logs
```
## 核心数据模型
### Deployment 与服务
```typescript
interface DeploymentDescriptor {
  deploymentId: string;
  service: string;
  version: string;
  imageOrBuildRef: string;
  region: string;
  environment: "dev" | "staging" | "production";
  configSnapshotId: string;
  schemaVersions: Record<string, string>;
  rolloutId?: string;
  capabilities: string[];
}
interface ServiceHealth {
  service: string;
  instanceId: string;
  status: "starting" | "ready" | "degraded" | "draining" | "failed";
  liveness: HealthProbeResult;
  readiness: HealthProbeResult;
  dependencies: DependencyHealth[];
  observedAt: string;
}
```
### Job、Lease 与调度
```typescript
interface RunJob {
  jobId: string;
  tenantId: string;
  workspaceId?: string;
  sessionId: string;
  runId: string;
  trigger: "user" | "resume" | "background" | "subagent" | "system";
  priority: number;
  deadline?: string;
  requiredCapabilities: string[];
  region?: string;
  configSnapshotId: string;
  policySnapshotId: string;
  budgetReservationId?: string;
  idempotencyKey: string;
  createdAt: string;
}
interface WorkerLease {
  leaseId: string;
  jobId: string;
  workerId: string;
  tenantId: string;
  runId: string;
  fencingToken: string;
  issuedAt: string;
  heartbeatAt: string;
  expiresAt: string;
  status: "leased" | "running" | "renewing" | "completed" | "expired" | "recovered";
}
interface QueueSnapshot {
  queue: string;
  tenantId?: string;
  depth: number;
  oldestAgeMs: number;
  reserved: number;
  running: number;
  blocked: number;
  circuitState?: string;
  observedAt: string;
}
```
### SLO、预算与成本
```typescript
interface SloDefinition {
  id: string;
  scope: "global" | "tenant" | "workspace" | "provider" | "service";
  indicator: string;
  target: number;
  window: "rolling" | "calendar";
  exclusions: string[];
  errorBudgetPolicy: string;
}
interface BudgetReservation {
  id: string;
  tenantId: string;
  workspaceId?: string;
  sessionId?: string;
  runId?: string;
  maxTurns: number;
  maxToolCalls: number;
  maxWallClockMs: number;
  maxInputTokens: number;
  maxOutputTokens: number;
  maxCostMicros: number;
  maxArtifactBytes: number;
  reservedAt: string;
  expiresAt?: string;
}
interface CostLedgerEntry {
  entryId: string;
  tenantId: string;
  runId: string;
  attemptId?: string;
  category: "model" | "retry" | "fallback" | "compaction" | "subagent" | "tool" | "storage" | "egress";
  usage: Usage;
  estimatedCostMicros?: number;
  reconciledCostMicros?: number;
  source: "provider" | "estimated" | "reconciled";
  occurredAt: string;
}
```
### Incident、Backup 与 Migration
```typescript
interface IncidentRecord {
  incidentId: string;
  severity: "sev0" | "sev1" | "sev2" | "sev3";
  status: "detected" | "triaged" | "mitigating" | "recovering" | "resolved" | "reviewed";
  commander?: PrincipalRef;
  affectedScopes: ScopeRef[];
  startAt: string;
  endAt?: string;
  hypotheses: string[];
  actions: IncidentAction[];
  evidenceRefs: ArtifactRef[];
}
interface BackupManifest {
  backupId: string;
  createdAt: string;
  sourceRegion: string;
  stores: StoreBackupRef[];
  eventSequenceWatermark: string;
  encryptionKeyRef: string;
  integrityHash: string;
  restoreTestedAt?: string;
}
interface MigrationPlan {
  id: string;
  component: string;
  fromVersion: string;
  toVersion: string;
  compatibility: "backward" | "forward" | "none";
  phases: MigrationPhase[];
  rollbackPlan: string;
  configHash: string;
}
```
## TypeScript 接口
### Orchestrator、Scheduler、Worker
```typescript
interface ProductionOrchestrator {
  accept(input: HostRequest): Promise<RunAdmission>;
  resume(input: ResumeRequest): Promise<RunAdmission>;
  cancel(runId: string, reason: string): Promise<void>;
  inspect(runId: string): Promise<RunView>;
}
interface Scheduler {
  enqueue(job: RunJob): Promise<JobReceipt>;
  lease(worker: WorkerIdentity, capabilities: WorkerCapabilities): Promise<WorkerLease | undefined>;
  heartbeat(lease: WorkerLease): Promise<void>;
  complete(lease: WorkerLease, result: JobResult): Promise<void>;
  fail(lease: WorkerLease, error: NormalizedError): Promise<void>;
  recoverExpired(leaseId: string): Promise<RecoveryDecision>;
}
interface WorkerRuntime {
  start(lease: WorkerLease): Promise<RunningWorkerJob>;
  drain(reason: string): Promise<void>;
  health(): Promise<ServiceHealth>;
}
```
### Store 端口
```typescript
interface SessionStore {
  load(sessionId: string, scope: ScopeRef): Promise<SessionView>;
  append(input: AppendSessionInput): Promise<AppendReceipt>;
  checkpoint(input: CheckpointInput): Promise<CheckpointRecord>;
  listRecoveryCandidates(scope?: ScopeRef): Promise<RecoveryCandidate[]>;
}
interface EventStore {
  append(events: CanonicalEvent[]): Promise<EventAppendReceipt>;
  read(streamId: string, cursor?: EventCursor): AsyncIterable<CanonicalEvent>;
  replay(query: ReplayQuery): AsyncIterable<CanonicalEvent>;
  watermark(streamId: string): Promise<string>;
}
interface ArtifactStore {
  put(input: ArtifactInput): Promise<ArtifactRef>;
  get(ref: ArtifactRef, options?: ReadOptions): Promise<ArtifactChunk | ArtifactStream>;
  delete(ref: ArtifactRef, reason: string): Promise<void>;
  verify(ref: ArtifactRef): Promise<VerificationReceipt>;
}
interface AuditStore {
  append(record: AuditRecord): Promise<void>;
  query(scope: ScopeRef, query: AuditQuery): Promise<AuditRecord[]>;
  verify(recordId: string): Promise<IntegrityReceipt>;
}
```
### Health、SLO 与 Capacity
```typescript
interface HealthProbe {
  liveness(): Promise<HealthProbeResult>;
  readiness(): Promise<HealthProbeResult>;
  dependencyHealth(): Promise<DependencyHealth[]>;
}
interface CapacityModel {
  estimate(input: CapacityInput): CapacityEstimate;
  reserve(input: CapacityReservation): Promise<CapacityLease>;
  settle(lease: CapacityLease, actual: ResourceUsage): Promise<void>;
}
interface AlertRule {
  id: string;
  expression: string;
  severity: "page" | "ticket" | "info";
  forMs: number;
  scopeLabels: string[];
  runbookId: string;
  redactionProfile: string;
}
```
### Rollout、Config 与 Incident
```typescript
interface RolloutController {
  plan(input: RolloutPlan): Promise<RolloutRecord>;
  advance(rolloutId: string): Promise<void>;
  pause(rolloutId: string, reason: string): Promise<void>;
  rollback(rolloutId: string, reason: string): Promise<void>;
}
interface IncidentController {
  declare(input: IncidentDeclaration): Promise<IncidentRecord>;
  addAction(incidentId: string, action: IncidentAction): Promise<void>;
  resolve(incidentId: string, summary: string): Promise<void>;
  createForensicBundle(incidentId: string): Promise<ArtifactRef>;
}
```
## Worker、Scheduler 与 Lease
### Job 生命周期
```text
Created
  -> Admitted
  -> Queued
  -> Leased
  -> Preparing
  -> Running
  -> WaitingForApproval | WaitingForDependency
  -> Settling
  -> Completed | Failed | Cancelled | Unknown
```
### Admission 顺序
```text
authenticate
  -> resolve tenant/workspace/session
  -> validate request/schema
  -> snapshot config/policy/model/toolset
  -> reserve quota/cost/capacity
  -> select queue and region
  -> enqueue durable job
```
没有成功的 quota、budget、scope、config snapshot 和 idempotency key，不得将 job 交给 worker。
### Lease 规则
- lease 绑定 tenant、workspace、session、run、worker、region、config snapshot 和 fencing token。；heartbeat 只延长 lease，不改变 policy、budget 或 tenant scope。；worker 进程丢失后，scheduler 将 lease 标记 expired；恢复器先查询 durable state 和 side-effect receipt。；同一 run 同时只能有一个 active execution lease，除非任务被显式拆分为独立 child runs。；job completion 必须以 fencing token 和 expected state CAS 提交，旧 worker 无法覆盖新 worker。；worker drain 时停止领取新 job，等待安全边界；高风险 in-flight action 进入 unknown/recovery，而不是伪造取消。
### Scheduler 公平性
```text
priority
  + tenant fairness
  + deadline
  + dependency readiness
  + capability match
  + provider circuit state
  + budget availability
  -> queue order
```
禁止单一全局 FIFO 让一个 tenant 的 subagent fan-out 阻塞所有租户；同时避免只按 priority 造成低优先级永久饥饿。
## Session/Event/Artifact Store
### 一致性边界
推荐以 Event Store 或 Session append + outbox 作为 durable source of truth。禁止无协议地分别写 session、event、audit 和 projection。
```text
semantic entry/event append
  -> outbox or durable event
  -> projector / usage / audit / delivery consumers
```
projector 可重建；audit 事实追加且独立 retention；trace/metric 可由 durable events 补偿；UI buffer 不是状态真相。
### Session Store 要求
- 每次 append 带 tenant/workspace/session/branch scope 和 expectedVersion。；保留 `Run`、`Turn`、`Attempt`、ToolCall/Result、Approval、Checkpoint、Compaction、ModelChange、ToolsetChange、Delivery 和 terminal status。；支持 branch、fork、revert、recovery candidate 和 schema upcast。；projection backlog 不得阻塞 durable append；但 terminal settlement 必须等待关键 projection 或明确标记未完成。
### Event Store 要求
- `streamSeq`、sessionVersion、producerSeq、causation、correlation 和 trace 关系可回放。；durable event 不原地修改；schema migration 不重写 audit 事实。；slow consumer 使用 bounded queue、coalescing 和 replay cursor；关键事件不可静默丢失。
### Artifact Store 要求
- ref、version、hash、owner、scope、sensitivity、scan、view、retention 和 deletion tombstone 独立于 blob。；大输出、命令日志、diff、snapshot、forensic bundle 使用 ArtifactRef；provider、user、audit 使用不同 view。；object/blob backend 故障时，session 保留引用和错误状态，不伪造 artifact available。
## 健康检查与服务生命周期
### Liveness
回答“进程是否还能运行”。只检查本地 event loop、基本内存和内部状态，不因 provider 暂时 429 而杀死实例。
### Readiness
回答“是否可以接收新工作”。检查必要依赖、config snapshot、queue、store、credential broker、sandbox profile、租约能力和版本兼容。
### Degraded Health
服务可以继续低风险工作但某些能力不可用时返回 `degraded`，并在 active capability 中隐藏对应工具、provider、模式或交付方式。
### 启停顺序
```text
start process
  -> load immutable safe config
  -> authenticate to control plane
  -> verify schema compatibility
  -> check store/queue/secret/sandbox capabilities
  -> register instance
  -> report readiness
  -> accept jobs
drain
  -> mark not-ready
  -> stop new leases
  -> settle or checkpoint active runs
  -> flush event/audit/outbox
  -> release resources
  -> unregister instance
```
readiness 失败不能自动等同 liveness 失败；否则 provider outage 会造成 worker 重启风暴。
## SLO、SLI 与错误预算
### 用户路径 SLI
- request acceptance success rate。；time to first durable event、time to first visible event、TTFT/TTFE。；run completion success、completion with verified side effects、terminal settlement latency。；approval request/resume latency。；artifact upload/download success、delivery acknowledgement。；crash recovery success、unknown outcome resolution time。
### 内部路径 SLI
- queue wait、lease acquisition、worker startup、context compile、prompt compile。；provider attempt latency、429/5xx/EOF/capability error、retry/fallback ratio。；tool validation/authorization/sandbox startup/lock wait/cleanup latency。；event append latency、projection lag、artifact scan/GC lag、backup freshness。
### SLO 示例
```text
accepted run -> first durable event within target percentile
accepted run -> terminal durable status within target percentile
successful tool call -> result committed without loss
critical event loss = zero tolerated
cross-tenant isolation violation = zero tolerated
unknown side-effect rate below defined budget
provider outage does not cause unbounded queue growth
```
安全、数据完整性、审计丢失和跨 tenant 事件属于 hard invariant，不应用普通错误预算抵消。
### 错误预算动作
错误预算耗尽时：冻结非必要 rollout、降低实验并发、减少高成本 background jobs、提高审批或降级到低风险能力；不得为了恢复 SLO 而关闭审计、放宽 sandbox 或跨 region 外发敏感数据。
## 容量模型与资源预算
### 资源维度
```text
HTTP connections
provider concurrency and quota
worker CPU/memory/process slots
sandbox startup rate
session/event store writes
projector lag
artifact bytes and egress
queue depth and lease slots
lock contention
tenant cost budget
```
### 估算关系
```text
active runs
  = admission rate × average run duration
worker slots
  >= model concurrency + tool concurrency + settlement reserve
store write rate
  = durable events/run × run rate + projector/outbox overhead
artifact capacity
  >= output bytes + retention window + replication + scan staging
```
应将模型 retry、fallback、compaction、subagent、tool compute、storage 和 egress 成本归因到原始 run，而不是只看主请求。
### 预留与结算
动作前 reserve token/cost/time/worker/artifact bytes；事件后按实际 usage settle；取消或拒绝释放未使用 reservation。reservation 过期由控制面回收，不能依赖 worker 正常退出。
## Queue、Backpressure 与公平性
### 队列分层
```text
interactive-critical
interactive-standard
approval-resume
background-subagent
compaction/indexing
artifact-scan/gc
recovery/forensics
```
每层有独立容量、最大等待、并发和降级策略；critical durable events 不与 token delta 共用无界队列。
### Backpressure
- queue bounded；达到上限时拒绝、延迟或返回明确 `capacity_exhausted`。；text delta 可 coalesce；progress 保留最新；error、approval、checkpoint、terminal event 不可静默丢失。；慢客户端断开后通过 durable cursor 恢复，而不是阻塞模型网络读取。；provider stream 读取与 host delivery 解耦；host backlog 不得迫使 worker无限保存高频事件。；scheduler 根据 queue age、tenant quota、provider circuit 和 worker capacity 停止新 admission。
### Fairness
租户、workspace、session 和 subagent 分层限流；同一 tenant 的 fan-out 使用 child budget 和并发上限；优先级必须有 aging，避免 background 永久饿死。
## Rate、Cost 与多层预算
### 限制层级
```text
global safety floor
  -> tenant quota
  -> user/workspace quota
  -> session/run budget
  -> turn/attempt/tool budget
  -> provider/model/deployment quota
  -> worker/process/resource limit
```
低层只能收紧，不能突破高层上限。
### Rate Limit 维度
- requests、active runs、model attempts、tool calls、subagent count、artifact bytes、egress bytes。；provider API family、model/deployment、region、credential namespace。；高风险工具、approval 请求、background jobs 和恢复任务单独计数。
### Cost Controls
- provider usage 以 attempt 为粒度记录；retry/fallback/compaction 不能隐藏。；估算成本标记为 estimated，provider reconciled 成本覆盖估算但不删除历史。；cost budget 接近阈值时先停止 background/subagent，再限制高成本模型，最后 fail-closed。；不因“用户只看到一句话”而忽略工具 compute、storage、scan 和 egress 成本。
## Autoscaling 与 Noisy Neighbor
### 扩缩容信号
```text
queue depth/age
active leases
worker CPU/memory/process slots
provider concurrency headroom
sandbox startup latency
store write latency
artifact bytes/scan backlog
projection lag
```
不要只按 CPU 扩容；Agent workload 可能是 provider-bound、queue-bound、I/O-bound 或 sandbox startup-bound。
### 扩缩容规则
- scale-out 前检查 quota、provider headroom、store capacity 和 worker image readiness。；scale-in 先 drain worker，不能杀死持有 lease、lock、sandbox 或 pending approval 的 job。；每个 tenant 设置 concurrency/cost ceiling；超限进入 queue 或降级，不抢占其他租户。；dedicated worker pool 用于高敏感、特定 region 或高风险 profile；shared pool 必须有 scope、lease 和 runtime attestation。；orphan worker、sandbox、lock 和 artifact staging 由 reaper 处理，不依赖 autoscaler 释放。
## Provider Runtime、Circuit Breaker 与 Outage
### 错误分类
- 参数/schema/capability：修复请求或切换兼容模型，不盲重试。；认证/授权/egress：停止并报告配置或策略问题。；rate limit/temporary capacity：读取服务端提示，指数退避加 jitter，受 budget 限制。；network/5xx/stream EOF：仅对安全请求有限 transport retry；未知 provider side effect 不重放。；context overflow：交给 Context/Compaction，不把它当普通 5xx。；safety/refusal：typed outcome，不能伪造空成功。
### Circuit Breaker
```text
Closed
  -> Open on threshold
  -> HalfOpen after cooldown
  -> Closed on verified success
  -> Open on probe failure
```
breaker 维度至少包括 provider、api family、model/deployment、region、credential class 和错误类别。一个模型故障不能熔断整个 provider；一个 tenant 的错误不能污染全局健康。
### Outage 策略
```text
detect degradation
  -> stop unsafe retry amplification
  -> classify affected attempts
  -> preserve existing durable state
  -> choose policy-approved fallback/queue/pause
  -> update user/operator status
  -> reconcile unknown outcomes
  -> recover gradually after probe
```
fallback 必须重新验证 capability、region、egress、tool calling、structured output、budget 和 policy；adapter 不能偷偷切换 provider。
## Rollout、Canary 与 Rollback
### Rollout 单位
- API/Gateway、worker、Kernel/Harness、provider adapter、tool registry、sandbox backend、event schema、projector、config/policy。；每个 rollout 记录版本、config hash、schema compatibility、scope、owner、canary group 和 rollback plan。
### Canary 流程
```text
build/validate
  -> static/security/test/conformance
  -> shadow or offline replay
  -> small tenant/workspace canary
  -> compare SLO/cost/error/trajectory
  -> expand by bounded cohorts
  -> observe settlement and recovery
  -> complete or pause
```
canary 不得把高风险真实副作用直接暴露给模型；使用 shadow、fake provider、sandbox fixture 或明确 allowlist。
### Rollback
回滚应用版本不等于回滚 session/event/schema/artifact。先判断旧版本能否读取新 schema、checkpoint、toolset、policy 和 event；必要时保留 upcaster 和 dual-read。 遇到数据完整性、跨 tenant、审计丢失或 sandbox fail-open，立即暂停 rollout、冻结高风险动作、保留 forensic evidence，再恢复已验证版本。
## Config、Schema 与 Migration
### 配置层级
```text
built-in safety floor
  < organization policy
  < tenant config
  < user/workspace/project config
  < session config
  < run override
```
低层只能收紧安全、预算、egress、retention 和 capability 上限。
### 版本化要求
- config snapshot 记录 source、version、hash、tenant scope、createdAt 和 migration history。；run 使用 frozen config snapshot；中途变化通过显式 change entry 或新 run 生效。；event/schema 使用 minor optional、major semantic break 规则；保留原始 event 版本。；projector 支持 upcast/rebuild；audit 不被重写。；tool schema、sandbox profile、provider capability、artifact view 和 policy 变更都有兼容测试。
### Migration 流程
```text
validate schema
  -> dry-run on snapshot/replay
  -> estimate lock/backfill/queue impact
  -> reserve capacity
  -> deploy reader compatibility
  -> migrate bounded partitions
  -> verify counts/hashes/invariants
  -> switch writer
  -> retain rollback/upcaster window
```
migration 期间必须可暂停；不能在共享数据库上无界锁表，也不能让 worker 读到半迁移 policy。
## Secrets、Credential 与 Egress
### Secret 原则
- 配置和 session 只保存 secret reference，不保存 secret value。；broker 根据 tenant、principal、run、tool、destination、purpose、expiry 和 profile 发放短期最小凭据。；worker、plugin、MCP、provider、artifact transfer 和 operator break-glass 使用不同 credential class。；secret 不进入 prompt、tool arguments、argv、环境快照、trace、artifact 或普通 log。；rotation 后新动作使用新 secret；in-flight 状态按 policy 继续、撤销或进入 recovery。
### Egress 流程
```text
candidate resource
  -> sensitivity/classification
  -> tenant/data residency/provider policy
  -> redaction/tokenization/summary
  -> destination authentication
  -> egress decision
  -> transmit with audit
```
provider cache、artifact URL、webhook、channel、MCP/remote worker 和日志 exporter 都是 egress destination；成功执行不等于结果可以外发。
## Incident Response
### 事件级别
- `sev0`：跨 tenant、secret 泄露、审计/状态不可恢复、sandbox fail-open 或大范围生产副作用。；`sev1`：核心 run 无法恢复、长时间全局不可用、provider outage 无可接受降级。；`sev2`：区域/功能/tenant 受影响，存在明确 workaround。；`sev3`：局部错误、性能退化或可观察性缺陷。
### 处理阶段
```text
Detect
  -> Declare
  -> Triage
  -> Contain
  -> Mitigate
  -> Recover
  -> Verify
  -> Resolve
  -> Review
```
### Containment 优先级
1. 停止新高风险动作、生产部署、外部发送和跨 scope 操作。 2. 保留 durable events、audit、approval、sandbox、worker lease 和 provider request metadata。 3. 隔离受影响 tenant/workspace/region/worker pool，而不是无差别删除数据。 4. 关闭问题版本或 circuit，启用已验证 fallback/queue/pause。 5. 对 unknown outcome 做查询和对账，不能批量盲重放。
事故 commander 可以声明 break-glass，但每个动作仍需 principal、reason、scope、expiry、双人或强认证规则和 audit。
## Runbook
### Provider outage runbook
```text
1. 看 provider/model/region circuit 与错误分类。
2. 区分 transport、rate、capacity、capability、auth 和 context overflow。
3. 停止 retry amplification，降低并发和 queue admission。
4. 检查 fallback policy、region/egress/capability compatibility。
5. 保留 in-flight attempt 和 unknown outcome。
6. 对安全可重试请求使用 bounded retry；写/外部动作先查询状态。
7. 恢复时从 HalfOpen probe 开始，逐步放量。
```
### Queue backlog runbook
```text
1. 检查 queue depth/age、tenant distribution、worker leases 和 circuit。
2. 判断 provider-bound、store-bound、sandbox-bound 或 worker-bound。
3. 暂停 background/subagent/compaction，保留 interactive/approval-resume。
4. 检查预算和 quota，避免过量 scale-out 造成 provider 429。
5. 扩容兼容 worker pool，先验证 readiness 和 capacity headroom。
6. 记录丢弃/延迟 job，恢复后按 idempotency 查询，不重复副作用。
```
### Session/Event Store runbook
```text
1. 检查 append latency、CAS conflict、replication lag、projection lag 和 outbox。
2. 停止高频 best-effort consumers，保持 critical durable writer。
3. 将受影响 run 暂停或 checkpoint，不在 projection 缺口上继续交付“已完成”。
4. 从 cursor replay 或 snapshot rebuild 恢复 projector。
5. 校验 sequence、hash、terminal uniqueness 和 audit completeness。
6. 通过 reconciliation 再开放新写入。
```
### Sandbox/worker orphan runbook
```text
1. 列出 expired lease、running process、mount、lock、temp、artifact staging。
2. 验证 tenant/workspace/run ownership 和 fencing token。
3. 先 quarantine，再停止进程、unmount、释放 lock、扫描 artifact。
4. unknown side effect 写入 durable recovery entry。
5. 仅对无引用、无 hold、无 in-flight 的资源执行 GC。
```
## Audit、Forensics 与诊断快照
### Audit 与 debug 分离
Audit 保存最小、不可抵赖、可验证的治理事实；debug log 可以采样、截断和短 retention。二者不能互相替代。
### Forensic Bundle
```typescript
interface ForensicBundle {
  incidentId: string;
  scope: ScopeRef[];
  deploymentSnapshots: DeploymentDescriptor[];
  configSnapshots: ConfigSnapshot[];
  eventRanges: EventRangeRef[];
  sessionCheckpoints: CheckpointRef[];
  policyDecisions: PolicyDecisionRef[];
  approvalRecords: ApprovalRef[];
  sandboxAttestations: SandboxAttestation[];
  workerLeases: WorkerLease[];
  artifactRefs: ArtifactRef[];
  redactionProfile: string;
  integrityHash: string;
}
```
### Diagnostic Snapshot
应能回答：哪个版本、哪个 worker、哪个 tenant/workspace/session/run、哪个 model/provider/attempt、哪个 tool/policy/sandbox、哪个 queue/lease、最后 durable event 和未知副作用是什么。完整 prompt、secret 和高敏感文件默认只保存受控 ref 或 redacted view。
### 完整性
Audit、forensic bundle、backup manifest 和关键 event 使用 hash、sequence、签名或 append-only backend；operator 查询本身也产生日志和 audit。
## Backup、Restore 与 DR
### 备份对象
- session semantic entries、branch、checkpoint、schema/version metadata。；canonical event、outbox、cursor、audit 和 policy/approval records。；artifact registry、blob、view、scan、retention、tombstone。；config/migration、model/toolset snapshots 和必要的 repository/workspace metadata。
trace、metric 和 debug log 可按 retention 选择性备份，但不能替代上述业务事实。
### RPO/RTO 设计
为 session/event、artifact、audit、config、queue 和 provider routing 分别定义 RPO/RTO；不要用单一数据库备份数字覆盖所有组件。
### Restore 流程
```text
declare restore scope
  -> verify backup manifest/integrity/key access
  -> restore stores into isolated namespace
  -> replay/upcast events
  -> rebuild projections
  -> verify counts/hashes/tenant boundaries
  -> restore artifact refs and scan status
  -> run recovery candidates in paused mode
  -> compare SLO/invariants
  -> switch traffic gradually
```
恢复后不能直接重放所有 in-flight tool；先分类 `not_started/known/unknown`，对外部副作用使用查询或补偿流程。
### 灾备演练
至少演练 store failure、region loss、provider outage、worker pool loss、key rotation failure、event gap、artifact backend loss、schema migration rollback 和 cross-tenant containment。
## Retention、Deletion 与数据生命周期
### 生命周期
```text
created
  -> active
  -> archived
  -> retention_hold
  -> deletion_requested
  -> deleting
  -> tombstoned
  -> purged
```
### 删除边界
删除请求必须绑定 tenant/principal、scope、reason、policy version、retention hold、approval 和 deletion token。删除 session 不等于立即删除 audit、legal hold、backup 或不可变 event；每类数据有独立 deletion contract。
### 删除验证
- registry、blob、preview、cache、event projection、search、queue、worker lease、trace 和 backup 的状态一致。；删除后保留最小 tombstone 和 proof，防止 ID 复用、恢复误复活或跨租户查询。；provider/file API 外部副本按 egress contract 记录可删除性和结果；不能声称本地删除已抹除不可控外部副本。；reaper 采用 idempotent、bounded、可暂停和可审计流程。
## Alerting 与 Dashboards
### 告警原则
- page 只针对需要人工即时动作的用户/安全/数据完整性影响。；ticket 用于趋势、容量、投影落后、成本和可修复配置问题。；alert 必须有 owner、runbook、scope、for duration、silence 规则和 redaction profile。；不把每个 provider 5xx 或单个 delta 丢失直接变成 page；先聚合并区分用户影响。
### Dashboard 分层
1. **Executive/SLO**：可用性、完成率、延迟、成本、隔离和数据完整性。 2. **Control plane**：admission、config、policy、quota、queue、lease、migration、rollout。 3. **Data plane**：active runs、model/tool latency、sandbox、artifact、event throughput、delivery。 4. **Provider**：按 provider/api family/model/deployment/region 的错误、quota、breaker、fallback。 5. **Storage**：append latency、replication、projection lag、artifact bytes、scan/GC、backup freshness。 6. **Security**：deny/ask、secret access、egress、trust changes、cross-scope attempt、break-glass。 7. **Tenant fairness**：各租户 queue age、active runs、cost、error、noisy-neighbor 指标。
### 维度控制
metric label 不使用原始 path、prompt、tool arguments、secret、artifact URI 或高基数 user text；使用 hash、稳定 ID、scope class 和脱敏 reason code。
## Chaos、Fault Injection 与 Evaluation
### Fault Catalog
```text
provider 429/5xx/EOF/slow stream/context overflow
worker crash before/after tool side effect
queue duplicate/delay/out-of-order
lease expiry/heartbeat loss
session CAS conflict/event gap/projector lag
artifact upload/scan/range/delete failure
sandbox prepare/attestation/unmount failure
lock timeout/deadlock/fence mismatch
secret broker unavailable/rotation during run
config/schema migration partial failure
host disconnect/slow consumer
```
### 评测原则
Evaluation Runner 使用真实 Harness 入口，只替换 ModelPort、Tool backend、Clock、ID、Store、Host 或 Fault injector。每个 scenario 检查 trajectory、events、durable state、side effects、usage/cost、latency 和 recovery，不只评 final text。
### 安全边界
chaos 只能在隔离 tenant、测试 credential、sandbox fixture、fake provider 或 shadow traffic 中执行；production fault injection 需明确 blast radius、停止条件、审批和 rollback。
## Security Operations 与 On-call
### Security Operations
- 定期审查 tenant/workspace scope、provider egress、credential bindings、plugin/MCP provenance、project trust 和 break-glass。；监控 cross-scope、secret detector、异常 artifact download、provider destination、sandbox degradation 和 operator query。；凭据轮换和 revoke 后验证新旧 run 的行为；旧 worker lease 不能继续使用过期 secret。；安全事件按 incident 流程隔离、保全、通知和删除；不在日志中复制泄露 secret。
### On-call 轮值
on-call 必须能：
- 查询 SLO、queue、worker、provider、session/event/artifact、audit 和 rollout 状态。；执行受控 pause/drain/circuit/rollback/replay/recovery，而不是手工直接改数据库。；读取对应 runbook，知道哪些操作需要二人批准、break-glass、客户沟通和事后 review。；在失去 control plane 时识别 data plane 的安全降级边界。
### 交接
每次交接记录 active incident、pending migration、provider degradation、quota risk、backup freshness、unknown outcome、paused tenant/workspace 和已执行 operator action。
## 生命周期与状态机
### Service 状态
```text
Starting -> CheckingDependencies -> Ready
Ready -> Degraded | Draining | Failed
Degraded -> Ready | Draining | Failed
Draining -> Stopped
```
### Rollout 状态
```text
Planned -> Validating -> Canarying -> Expanding -> Completed
Canarying/Expanding -> Paused -> Resuming | RollingBack
RollingBack -> RolledBack | Failed
```
### Incident 状态
```text
Detected -> Declared -> Triaged -> Mitigating -> Recovering -> Resolved -> Reviewed
```
### Run Settlement
```text
Running
  -> TerminalRequested
  -> FlushingDurable
  -> SettlingUsage/Artifacts/Delivery
  -> Completed | Failed | Cancelled | Unknown
```
terminal result 在关键 durable event、artifact、usage、audit 和必要 projection settle 前不能被运维层宣称为 fully settled；若部分失败，返回结构化 diagnostics。
## 与 Context/Prompt/Tool/State/Policy/Harness 集成
### Context
ContextCompiler 使用 scope、trust、freshness、policy、provider jurisdiction、token budget 和 artifact projection 选择资源。生产运维必须记录 `ContextPlan` hash、dropped/offloaded resources 和 model egress decision，但不保存不必要的完整敏感内容。
### Prompt
Prompt 解释当前模式、可用工具、预算、等待/审批/重试/完成标准和降级状态。Prompt 不决定 SLO、quota、tenant、provider fallback、sandbox 或真实 health；这些由 control/data plane 强制。
### Tool
Tool Runtime 在动作前预检 quota、rate、lock、budget、policy、sandbox capability 和 provider/tool health；执行后写 `ToolExecutionCompleted`、usage/cost、artifact、side-effect receipt 和 error taxonomy。高频 progress 可合并，关键结果 durable。
### State/Memory
Session/Run/Checkpoint 保存 config、model/toolset/policy/sandbox、budget、lease、approval、attempt、retry/fallback、unknown outcome、delivery 和 cleanup。Memory recall 不得绕过 tenant/retention/egress；schema migration 必须能重建 projection。
### Policy/Sandbox
Production policy 选择 provider、region、worker pool、sandbox profile、network、secret、artifact 和 operator action。执行前必须有 attestation；control plane 不可用时 fail-closed 的高风险边界不能被 worker 自行放宽。
### Harness
Harness Bootstrap 从 control plane 获取冻结 snapshot；Run Supervisor 将 model、tools、approvals、subagents、event consumers、checkpoint、delivery 和 cleanup 放入 structured concurrency。Worker 只负责执行该 snapshot，不隐式读取最新全局配置。
### Event/Observability
Canonical events 是 source for projection、trace、metric、audit、evaluation、delivery 和 recovery。`occurredAt`、`streamSeq`、`sessionVersion` 和 causation 比时间戳可靠；host/UI 到达顺序不能覆盖 durable truth。
## 故障恢复与降级
### 分层恢复
1. **Transport**：安全请求有限重试，指数退避和 jitter。 2. **Attempt**：重新生成或 fallback，创建新 attempt，保留失败 usage。 3. **Tool**：按幂等、unknown outcome 和业务查询恢复。 4. **Run**：checkpoint/resume，重新验证 scope、policy、budget、provider、lease 和 sandbox。 5. **Worker**：expired lease recovery、fencing、requeue 或 pause。 6. **Store**：replay、projection rebuild、backup restore、quarantine。 7. **Deployment**：pause、canary rollback、旧版本兼容恢复。
### 安全降级
允许的降级示例：
- provider 不支持 structured output 时改为应用端 schema validation，若策略允许。；artifact preview 失败时只返回 metadata/ref，不返回未经扫描的原文。；host 断开时继续到安全 checkpoint，不必自动取消 run。；provider 暂时不可用时排队、切兼容模型或暂停；不把敏感数据发送到未批准 provider。
禁止：
- sandbox 不可用改用 host shell。；queue 满时无限制接受并丢 durable event。；session store 不可写时只返回 final text 并宣称完成。；unknown side effect 直接重放。；migration 失败时强制 worker 使用半迁移 schema。；为了 SLO 关闭 audit、rate limit、approval 或 tenant check。
## 测试策略
### 单元与契约
- SLO/SLI 窗口、错误预算、成本归因、quota reserve/settle/release。；queue ordering、fairness、backpressure、coalescing、lease/fence 和 autoscaling decision。；provider error taxonomy、circuit transition、fallback capability intersection。；health/readiness/degraded/drain、config merge、schema compatibility、upcaster。；event envelope、sequence、terminal uniqueness、CAS、idempotency 和 audit integrity。
### 集成
- Gateway -> Orchestrator -> Scheduler -> Worker -> Harness -> Store 全链路。；worker crash、lease expiry、session conflict、event replay、artifact partial upload、sandbox failure、host disconnect。；多租户配额、provider egress、worker pool、cache、trace、artifact、queue 和 deletion 隔离。
### 场景与回归
| 主题 | 正常 | 边界 | 故障/断言 |
|---|---|---|---|
| admission | 有预算入队 | 接近 quota | scope/预算拒绝 |
| queue | 公平消费 | fan-out | backlog/backpressure |
| provider | 正常 stream | fallback | 429/EOF/circuit |
| worker | heartbeat | drain | crash/expired lease |
| session | append | CAS conflict | event gap/replay |
| artifact | put/get | range/scan | blob outage/quarantine |
| sandbox | attested | degraded | fail-closed |
| rollout | canary | pause | rollback/schema incompatibility |
| security | allow | ask | cross-tenant/secret egress |
| DR | backup verify | restore paused | unknown side effects |
| deletion | tombstone | retention hold | orphan reference |
### 性能与容量
固定时钟、ID、seed、provider script 和环境；记录 TTFT、TTFE、queue wait、tool latency、store append、projection lag、artifact transfer、cost 和资源使用。性能测试不能吞掉安全与审计断言。
### 线上反馈闭环
从生产筛选、脱敏、去重、审核后形成 regression scenario；不把原始 transcript 直接当黄金答案；重点保留错误轨迹、state、side effect、cost、latency 和 recovery evidence。
## 反模式
1. **只收集日志**：没有 durable state、audit、replay、checkpoint 或 side-effect oracle。 2. **一个健康检查**：把 liveness、readiness、provider health、sandbox capability 混成一个布尔值。 3. **全局 FIFO**：一个 tenant 或 subagent fan-out 阻塞所有用户。 4. **无界 retry**：429/EOF 导致成本和队列放大。 5. **adapter 偷偷 fallback**：丢失 attempt、policy、capability、usage 和审计事实。 6. **scale-out 解决一切**：provider quota、store、sandbox 或成本约束未解决却继续扩容。 7. **terminal text 即成功**：没有 durable settlement、artifact、usage 和 side-effect verification。 8. **部署与 schema 同时硬切**：旧 worker 无法读取 checkpoint/event，回滚也无法恢复。 9. **共享无 namespace cache**：跨 tenant/workspace 泄露 context、artifact 或 prompt cache。 10. **control plane 失联时 fail-open**：worker 自行改变 tenant、provider、secret 或 sandbox。 11. **备份只备数据库**：忽略 artifact blob、event cursor、audit、config 和 key。 12. **删除直接物理清理**：违反 retention、hold、audit、backup 和外部副本语义。 13. **告警高基数**：把 path、prompt、tool arguments 和 artifact URI 当 label。 14. **chaos 只测进程崩溃**：不测未知副作用、event gap、lease fence、projection、provider outage 和 cleanup。 15. **on-call 手工改表**：绕过 policy、audit、migration 和可重复 runbook。
## 实施清单
### P0：生产安全底座
- [ ] 定义 control/data plane、故障域、tenant/workspace/session/run scope。；[ ] 实现 durable session/event/artifact/audit 边界、CAS、outbox/replay 和 terminal settlement。；[ ] 实现 job admission、quota/budget reservation、queue、worker lease、heartbeat 和 fencing。；[ ] 实现 liveness/readiness/degraded/drain、provider error taxonomy 和 circuit breaker。；[ ] 建立 secret broker、egress policy、scope-aware cache、redaction 和 audit。
### P1：可靠性与发布
- [ ] 定义用户路径和内部路径 SLI/SLO、错误预算与告警 runbook。；[ ] 建立 capacity model、fair scheduler、backpressure、autoscaling 和 noisy-neighbor 限制。；[ ] 建立 config/schema registry、compatibility window、migration dry-run、pause 和 rollback。；[ ] 建立 provider canary、fallback、reconciliation、unknown outcome 和 outage runbook。；[ ] 实现 backup manifest、restore、projection rebuild、artifact verify 和 DR 演练。
### P2：运营治理
- [ ] 建立 dashboard、page/ticket/info 告警、on-call 轮值和 incident commander 流程。；[ ] 实现 forensic bundle、operator action audit、break-glass、retention hold 和 deletion proof。；[ ] 建立 chaos/fault injection、Evaluation CI gates、生产反馈脱敏回归集。；[ ] 为 worker/sandbox/mount/lock/temp/artifact/event 建立 orphan reaper 和 cleanup SLO。；[ ] 定期审查 provider egress、plugin/MCP provenance、credential rotation、cross-tenant invariant。
### Definition of Done
- 每个 run 都能回答“谁、在哪个 worker、用哪个 snapshot、消耗多少预算、执行了什么、最后 durable boundary 是什么”。；provider、worker、store、queue、sandbox、artifact 和 host 故障都有结构化分类、有限恢复和明确降级。；canary/rollback、migration、backup/restore、deletion、incident 和 on-call 都有可执行 runbook。；不需要依赖最终文本或普通日志来证明状态、副作用、权限和恢复结果。
## 五个参考项目的启发来源
### Pi
- 极小 headless loop、统一 provider event、session tree、checkpoint/compaction 和多 host runtime 启发 control/data plane 的协议化边界。；它执行隔离较弱，提醒生产部署不能把“可恢复 loop”误当作 worker、sandbox、secret 和容量治理。
### Grok Build
- Rust actor、采样器分层、permission decision、并行工具、路径锁、folder trust 和 sandbox 启发 scheduler/lock/policy/execution 的分层。；actor 并发也会放大状态复杂度，因此必须用 durable event、预算、fence 和 recovery 约束 worker。
### OpenCode
- client/server、session/message/part、事件总线、durable event/projector、snapshot/patch/revert、MCP/LSP 启发 store、projection、delivery 和运维回放设计。；分布式状态和迁移复杂度提醒生产系统必须有 schema version、replay、projection lag 与 rollback 方案。
### Claude Code
- permissions、hooks、subagents、skills、memory、MCP、计划和任务工作流启发完整 Harness 的控制面能力。；扩展近似可信宿主代码，生产运维必须把 provenance、trust、sandbox、secret 和 audit 纳入发布与安全运营。
### OpenClaw
- AgentHarness registry、agent-core、Gateway、provider runtime、tool/sandbox/elevated 分层、事务化插件注册启发多 channel、多 provider 的组件拓扑。；单 Gateway 和插件进程权限会扩大故障域，生产部署应拆分 worker pool、provider circuit、artifact/event store 和 operator control，避免单点故障扩散。
