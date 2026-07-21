# Durable Queue Engineering 细粒度工程设计
> 本文定义 Agent Harness 中 Durable Queue 的工程边界、命令与任务语义、租约、重试、幂等、公平调度、恢复、事件集成、安全和运维。
>
> 本设计只使用当前目录已有参考架构、Agent Harness、Harness Engineering、State/Memory、Tool、Subagent、Event/Observability、Evaluation、Provider Runtime、Provider Routing、Session Replay、Artifact、Multi-tenant、Host Adapter、Workspace Isolation、Permission/Sandbox、Coding Agent 和 Production Operations 文档中已记录的本地源码调研结论。
## 目录
1. [设计目标与非目标](#设计目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [职责边界](#职责边界)
4. [总体架构与包布局](#总体架构与包布局)
5. [Queue、Command、Job、Event 的区别](#queuecommandjobevent-的区别)
6. [核心数据模型与 TypeScript 接口](#核心数据模型与-typescript-接口)
7. [队列分层与分区](#队列分层与分区)
8. [Enqueue](#enqueue)
9. [Lease、Visibility Timeout 与 Worker Heartbeat](#leasevisibility-timeout-与-worker-heartbeat)
10. [Ack、Nack、Complete 与 Fail](#acknackcomplete-与-fail)
11. [Retry、Backoff 与 Dead Letter](#retrybackoff-与-dead-letter)
12. [Idempotency 与 Deduplication](#idempotency-与-deduplication)
13. [Ordering、Partition 与并发](#orderingpartition-与并发)
14. [Priority、Fairness 与 Noisy Neighbor](#priorityfairness-与-noisy-neighbor)
15. [Backpressure、Capacity 与 Admission](#backpressurecapacity-与-admission)
16. [Delayed/Scheduled Jobs](#delayscheduled-jobs)
17. [Cancel、Timeout 与 Expiry](#canceltimeout-与-expiry)
18. [Poison Message](#poison-message)
19. [Outbox、Inbox 与 Durable Event Integration](#outboxinbox-与-durable-event-integration)
20. [Exactly-once Illusion](#exactly-once-illusion)
21. [Worker Crash Recovery](#worker-crash-recovery)
22. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
23. [生命周期与状态机](#生命周期与状态机)
24. [决策流程](#决策流程)
25. [安全、隐私与租户隔离](#安全隐私与租户隔离)
26. [可观测性、SLO 与诊断](#可观测性slo-与诊断)
27. [灾备与恢复](#灾备与恢复)
28. [测试、Chaos 与 Conformance](#测试chaos-与-conformance)
29. [反模式](#反模式)
30. [实施清单](#实施清单)
31. [五个参考项目的启发来源](#五个参考项目的启发来源)
32. [Definition of Done](#definition-of-done)
## 设计目标与非目标
### 目标
Durable Queue 必须使系统能够：
- 在进程崩溃、worker 重启、Host 断线和 provider outage 后恢复后台运行。 - 区分命令、任务、事件和队列容器的语义。 - 支持 enqueue、lease、heartbeat、ack、nack、retry、dead-letter、cancel 和 status query。 - 以幂等键、deduplication、fencing token 和 durable execution record 降低重复副作用。 - 明确 visibility timeout、lease expiry 与实际业务执行状态的关系。 - 支持 ordering、partition、priority、fairness、deadline 和 capacity admission。 - 防止单一 tenant、session、subagent fan-out 或 provider retry storm 占满全局资源。 - 与 Session/Event Store、Outbox/Inbox、ArtifactStore、UsageLedger、Policy/Sandbox 和 Host Delivery 集成。 - 对未知执行结果保留 `unknown`，而不是把“消息再次可见”当作“任务一定未执行”。 - 为 delayed/scheduled jobs、background subagents、compaction、memory、artifact scan、recovery 和 notification 提供统一机制。 - 以可重放事件、checkpoint、receipt、side-effect ledger 和 operator runbook 支持诊断与灾备。
### 明确边界判断
```text
Durable Queue != 把任务丢进内存数组 Durable Queue = 持久化命令/任务 + 租约所有权 + 可见性超时 + 幂等/去重 + 重试/死信 + 公平调度 + 背压 + 崩溃恢复 + 可观测性 + 安全隔离
```
内存数组无法提供：
- 进程重启后的任务事实； - 多 worker ownership； - lease expiry 和 fencing； - 重复投递与幂等语义； - 可靠的取消和查询； - tenant quota/fairness； - outbox/inbox 一致性； - dead-letter 和人工重放； - DR、审计和 replay。
### 非目标
本文不规定：
- 某个具体消息中间件、数据库或云队列产品； - Agent Kernel 的模型—工具循环实现； - provider 选型和 fallback 排序； - 工具业务校验、审批或 sandbox 规则本身； - 以 exactly-once 作为传输层承诺； - 让 queue worker 直接修改 session/event truth 而不经过 durable protocol； - 用普通日志代替 job receipt、execution record 或 audit。
## 核心判断与术语
### Queue
Queue 是持久化调度容器，负责：
- 保存可消费的工作引用； - 根据 partition、priority、fairness 和 capacity 选择候选； - 管理 lease、visibility 和 retry metadata； - 返回可验证的 enqueue/lease receipt。
Queue 不等于业务任务本身，也不等于事件日志。
### Command
Command 是希望系统执行某个动作的意图，具有：
- command ID； - actor/principal； - target scope； - payload schema； - idempotency key； - causation/correlation； - expected version； - expiry/deadline； - authorization context。
Command 可以被接受、拒绝、排队、取消或过期。
### Job
Job 是可被 worker 执行的持久化工作单元。它包含：
- command 或 run assignment 引用； - frozen config/policy/model/toolset snapshot； - required capabilities； - budget reservation； - retry/lease policy； - checkpoint/ref； - owner tenant/workspace/session/run； - side-effect classification。
Job 表示“可执行的工作”，但不证明执行成功。
### Event
Event 是已经发生的事实，通常 append-only、可排序、可回放。
Event 不应被当作待执行 job；将 `ToolExecutionCompleted` 再次入队可能导致副作用重复。
### Receipt
Receipt 是对某个持久化动作或外部状态的可查询证明，例如：
- enqueue receipt； - lease receipt； - idempotency receipt； - provider request receipt； - external side-effect receipt； - artifact upload receipt； - terminal result receipt。
Receipt 不一定证明业务成功，必须带 outcome、source 和可查询状态。
### Lease
Lease 是 worker 在限定时间内拥有处理某 job 的暂时权利。
Lease 不是永久锁，也不是业务 approval。
### Visibility Timeout
Visibility Timeout 是“当前 lease owner 在未续租前，其他 worker 不应看到该 job”的时间窗口。
它解决重复领取，不解决真实副作用是否发生。
### Exactly-once Illusion
多数队列只能提供至少一次或至多一次的投递语义。
业务系统通过：
```text
stable idempotency key + durable execution record + status query/receipt + fencing token + transactional outbox/inbox + compensating action
```
构造“看起来 exactly once”的体验，但不能把它写成传输层事实。
## 职责边界
### Durable Queue 负责
- durable enqueue、lease、heartbeat、ack/nack、retry 和 dead-letter； - visibility timeout、lease version、fencing token； - queue partition、ordering、priority、fairness 和 capacity； - job cancellation、expiry、scheduled delivery； - tenant-aware quota、rate limit 和 noisy-neighbor protection； - durable job status、receipt、history 和 recovery candidate； - 与 Outbox/Inbox、Event Store、Worker Lease、Artifact、Usage 和 Audit 端口集成。
### Orchestrator/Harness 负责
- 将 HostRequest、SubagentSpec、resume、compaction、recovery 等转为 job； - 冻结 run config、policy、model/toolset/context/sandbox snapshot； - 监督 job 对应 RunScope、budget、checkpoint、approval、delivery 和 settlement； - 根据错误分类选择 retry、fallback、pause、manual 或 terminal。
### Worker 负责
- 验证 lease、fence、tenant scope 和 config snapshot； - 执行 job 对应的 kernel/tool/state workflow； - 定期 heartbeat； - 在 durable boundary 写 checkpoint、execution record 和 event； - 结束时提交完整 outcome 或明确 unknown。
Worker 不得：
- 直接修改 job payload 覆盖 tenant； - 在 lease 过期后继续提交结果； - 发现 provider 失败就无限重试； - 绕过 Policy/Sandbox 或使用最新全局配置覆盖 frozen snapshot。
### State/Event Store 负责
- 保存 command/job lifecycle facts； - 提供 CAS、append-only、replay、projector 和 checkpoint； - 通过 outbox 或统一 source of truth 保证 durable event 一致性。
### Tool/Provider Runtime 负责
- 执行具体 provider/tool 协议； - 进行 schema、业务、能力、错误和 usage 处理； - 返回 side-effect receipt、unknown outcome 或 normalized error。
它们不负责 queue fairness、tenant admission 或 job ownership。
### Host Adapter 负责
- 提交 command、取消、审批、resume、查询和订阅； - 投影 job/run/event 状态； - 断线重连、cursor、artifact delivery 和 ack。
Host ack 不证明 job 成功，断线不等于 cancel。
## 总体架构与包布局
```text
Host Adapter / Gateway / Batch -> Command Normalizer -> Admission + Policy + Quota -> Durable Queue -> Scheduler / Lease Manager -> Worker Runtime -> Harness / RunScope -> Agent Kernel -> Model Runtime -> Tool Runtime -> State/Event/Artifact -> Outbox/Event Router -> Projector / Usage / Audit / Delivery
```
推荐包布局：
```text
packages/queue/ contracts.ts command.ts job.ts queue-store.ts scheduler.ts partitioner.ts priority.ts fairness.ts admission.ts lease.ts heartbeat.ts retry.ts dead-letter.ts dedup.ts cancellation.ts scheduling.ts outbox.ts inbox.ts recovery.ts capacity.ts metrics.ts testkit/
```
依赖方向：
```text
Host -> Orchestrator -> Queue ports Worker -> Queue lease + Harness ports Queue -> Event/State/Quota/Audit ports Provider/Tool -> Harness/Execution ports Infrastructure -> Queue/Store/Lease adapters
```
Queue 不应 import TUI、provider SDK、具体 shell 或业务 ORM。
## Queue、Command、Job、Event 的区别
| 对象 | 语义 | 是否待执行 | 是否事实 | 是否可重放 | 典型 ID |
|---|---|---:|---:|---:|---|
| Command | 请求执行动作 | 是 | 否 | 可重提议 | commandId |
| Job | 可调度工作单元 | 是 | 否 | 需幂等 | jobId |
| Queue | 持久化容器 | 否 | 否 | 查询/恢复 | queueId |
| Event | 已发生事实 | 否 | 是 | 是 | eventId |
| Receipt | 状态证明 | 否 | 取决于来源 | 查询 | receiptId |
| Lease | 临时所有权 | 否 | 是 | 可恢复 | leaseId |
| Checkpoint | 可恢复工作视图 | 否 | 是 | 可加载 | checkpointId |
### 转换规则
```text
Host request -> Command Command admission -> Job Job lease -> Worker execution Execution -> Event + Result/Receipt Event -> Projector/Delivery/Recovery
```
不得：
- 将 event 当 job 无条件重新执行； - 将 queue visible 当 command 未执行； - 将 job completed 当外部副作用成功而无 receipt； - 将 host ack 当 terminal event； - 将 memory/cache state 当 durable queue source of truth。
## 核心数据模型与 TypeScript 接口
```typescript
type QueueId = string; type CommandId = string; type JobId = string; type LeaseId = string; type WorkerId = string; type TenantId = string; type Sequence = number; type JobStatus = | "created" | "admitted" | "queued" | "scheduled" | "leased" | "running" | "checkpointed" | "waiting" | "cancelling" | "completed" | "failed" | "cancelled" | "expired" | "dead_lettered" | "unknown";
```
```typescript
interface CommandEnvelope<T = unknown> { commandId: CommandId; commandType: string; schemaVersion: string; tenantId: TenantId; principal: PrincipalRef; scope: ScopeRef; payload: T; idempotencyKey: string; expectedVersion?: number; correlationId: string; causationId?: string; deadlineAt?: string; createdAt: string; sensitivity: Sensitivity; }
```
```typescript
interface QueueJob<T = unknown> { jobId: JobId; queueId: QueueId; commandId?: CommandId; jobType: string; schemaVersion: string; tenantId: TenantId; scope: ScopeRef; owner: JobOwner; payload: T; payloadHash: string; configSnapshotId: string; policySnapshotId: string; capabilityRequirements: string[]; priority: number; fairnessClass: string; partitionKey: string; idempotencyKey: string; deduplicationKey?: string; status: JobStatus; availableAt: string; deadlineAt?: string; attemptCount: number; maxAttempts: number; lease?: LeaseRef; checkpointRef?: CheckpointRef; lastError?: NormalizedError; createdAt: string; updatedAt: string; }
```
```typescript
interface JobOwner { principalId: string; workspaceId?: string; sessionId?: string; runId?: string; parentRunId?: string; childRunId?: string; }
```
```typescript
interface JobLease { leaseId: LeaseId; jobId: JobId; queueId: QueueId; tenantId: TenantId; workerId: WorkerId; leaseVersion: number; fencingToken: string; issuedAt: string; visibilityUntil: string; heartbeatAt: string; expiresAt?: string; status: "active" | "renewing" | "expired" | "released" | "recovered"; }
```
```typescript
interface JobReceipt { jobId: JobId; queueId: QueueId; status: "accepted" | "duplicate" | "conflict" | "rejected"; idempotencyKey: string; durableVersion: number; acceptedAt: string; existingJobId?: JobId; }
```
```typescript
interface JobResult<T = unknown> { jobId: JobId; leaseId: LeaseId; workerId: WorkerId; status: "completed" | "failed" | "cancelled" | "unknown"; output?: T; resultRef?: ArtifactRef; checkpointRef?: CheckpointRef; sideEffectReceipts?: ArtifactRef[]; usage?: Usage; error?: NormalizedError; completedAt: string; fencingToken: string; }
```
```typescript
interface DurableQueue { enqueue<T>(job: QueueJob<T>, idempotencyKey: string): Promise<JobReceipt>; lease(filter: LeaseFilter, worker: WorkerIdentity): Promise<JobLease | undefined>; heartbeat(lease: JobLease): Promise<LeaseReceipt>; ack(lease: JobLease, result: JobResult): Promise<void>; nack(lease: JobLease, error: NormalizedError, policy: RetryPolicy): Promise<NackReceipt>; cancel(input: CancelJobRequest): Promise<CancelReceipt>; inspect(jobId: JobId, scope: ScopeRef): Promise<JobView>; recoverExpired(input: RecoverLeaseRequest): Promise<RecoveryDecision>; }
```
```typescript
interface WorkerIdentity { workerId: WorkerId; tenantScopes: ScopeRef[]; capabilities: string[]; region?: string; sandboxProfiles: string[]; configVersion: string; }
```
```typescript
interface LeaseFilter { queueIds?: QueueId[]; tenantScope?: ScopeRef; jobTypes?: string[]; capabilityRequirements?: string[]; partitionKeys?: string[]; maxPriority?: number; now: string; }
```
## 队列分层与分区
### 队列类别
建议至少分离：
```text
interactive-critical interactive-standard approval-resume background-run subagent compaction-memory artifact-scan-gc recovery-forensics notification-delivery
```
不同队列拥有独立：
- capacity； - worker pool； - priority range； - retry policy； - retention； - SLO； - dead-letter policy； - tenant fairness。
### Partition Key
常见 partition：
```text
tenant + queue class tenant + session tenant + run workspace + resource class provider + deployment + region
```
选择原则：
- session queue 便于保持同一 session 的顺序； - run queue 便于并发后台 run； - tenant queue 便于公平与配额； - provider/deployment queue 便于容量和 circuit； - 热 session 需要分片、actor 或串行 owner。
### 分区不变量
- Job、lease、event、artifact、quota 和 audit 的 tenant scope 一致。 - partition key 不是授权证明；每次读取仍做 owner check。 - 一租户 burst 不能让其他租户没有 worker 或 event capacity。 - 迁移 partition 时保留 job ID、idempotency key、ordering cursor 和 lease state。 - 跨 partition move 产生 durable requeue/migration event。
## Enqueue
### Admission 顺序
```text
authenticate principal -> resolve tenant/workspace/session/run -> validate command schema -> evaluate visibility/call/policy -> reserve quota/budget/capacity -> create idempotency record -> freeze config/policy/model/toolset snapshot -> create job payload and hash -> append command/job accepted event -> enqueue durable job -> return receipt
```
没有以下任一项不得入队：
- tenant/scope； - valid idempotency key； - schema version； - policy snapshot； - budget/quota reservation； - required capability； - owner/session/run reference； - deadline/expiry； - payload hash。
### Enqueue 幂等
相同 tenant、operation、idempotency key 和 payload hash：
- 已存在 queued/running job：返回 duplicate receipt； - 已完成：返回原 job/result reference； - 同 key 不同 payload：返回 conflict； - 已取消/过期：按 policy 返回既有 terminal 或允许新 key 重提； - 不得悄悄创建第二个不可逆 job。
### Enqueue 与 Event
建议：
```text
command accepted + job created + outbox record -> durable commit -> queue visibility -> projector/delivery
```
不能先发“已排队”事件，再异步尝试写 job 而不补偿。
## Lease、Visibility Timeout 与 Worker Heartbeat
### Lease 获取
Worker lease 时必须原子确认：
- job 当前 status 可领取； - `availableAt <= now`； - deadline 未过期； - tenant quota 和 worker capability 满足； - 没有有效 lease； - partition ordering barrier 已满足； - priority/fairness 允许； - lease version/CAS 成功。
### Visibility Timeout
visibility timeout 应根据阶段动态设置：
- admission/preparing：短 lease； - provider stream：按 first-event/total timeout 加 margin； - tool execution：按工具 timeout 和 side-effect policy； - compaction/index：按 checkpoint interval； - artifact scan：按 bytes/scan budget。
不要把 visibility timeout 当作任务 wall-clock timeout。
### Heartbeat
Worker heartbeat 只能延长 lease，不改变：
- tenant； - policy； - config snapshot； - budget； - required capabilities； - job payload； - side-effect authorization。
```typescript
interface HeartbeatRequest { leaseId: LeaseId; jobId: JobId; workerId: WorkerId; leaseVersion: number; fencingToken: string; progress?: ProgressSnapshot; checkpointRef?: CheckpointRef; observedAt: string; }
```
### Heartbeat 失败
- transient store error：有限重试，不超过 lease margin； - lease version conflict：停止提交，进入 recovery； - tenant/policy mismatch：停止新动作，等待 Harness； - worker clock skew：使用 store time 或 monotonic deadline； - heartbeat timeout：标记 worker_lost，启动 recovery probe。
### Visibility 与重复领取
Lease expiry 后 job 可能再次可见，但这不证明旧 worker 没有执行。
恢复器必须读取：
- execution record； - side-effect receipt； - checkpoint； - provider/tool status； - fencing token； - event sequence。
## Ack、Nack、Complete 与 Fail
### Ack 语义
`ack` 表示 queue 记录该 lease 的最终处理结果，并释放队列所有权。
它不自动证明：
- provider response 成功； - tool side effect 成功； - artifact 可交付； - session projector 已追平； - Host 已收到结果。
### Complete
只有满足以下条件才允许 completed：
- worker lease/fence 有效； - required durable event 已提交； - result/receipt 已保存； - checkpoint/usage/artifact settlement 达到 job contract； - 没有未分类的 in-flight side effect； - terminal status 可查询。
### Nack
Nack 表示当前 worker 无法完成 job，并请求 queue 根据 retry policy 决定后续状态。
Nack 必须带：
- normalized error； - retryable； - outcomeKnown； - attempts consumed； - nextAvailableAt； - checkpoint/result refs； - side-effect status； - worker/lease evidence。
### Fail 与 Unknown
```text
failed  = 已确认未成功或不应再试 unknown = 可能已发生但无法确认
```
`unknown` 不能自动 dead-letter 后再重放，也不能被 UI 隐藏为 failed。
## Retry、Backoff 与 Dead Letter
### 重试层级
必须分离：
```text
transport retry   同一安全请求、同一 attempt 内 agent retry       修改 context/generation，创建新 attempt tool retry        Tool Runtime 自己决定 job retry         Queue 重新调度同一 job/新 execution attempt fallback          Routing 选择新 provider/model/deployment recovery retry    查询状态、补写结果或恢复 checkpoint
```
### RetryPolicy
```typescript
interface RetryPolicy { maxAttempts: number; maxElapsedMs: number; backoff: "none" | "fixed" | "exponential_jitter"; baseDelayMs: number; maxDelayMs: number; retryableCategories: string[]; requireStatusQueryForSideEffects: boolean; deadLetterAfterExhaustion: boolean; }
```
### 可重试
通常可有限重试：
- queue store transient failure； - worker startup failure； - provider 429/temporary capacity； - 安全网络错误； - artifact scan backend temporary outage； - projector lag 或可恢复 event consumer failure； - 未开始且无副作用的 job preparation。
### 不可盲重试
- schema/business validation； - 401/403/policy deny； - 资源 ownership mismatch； - 已可能成功的非幂等写操作； - provider-side batch/file/job unknown； - payment/send/delete/deploy unknown； - sandbox unavailable 的危险动作； - deadline 已过期； - poison message。
### Backoff
使用：
- server `Retry-After`； - 指数退避； - jitter； - total elapsed budget； - tenant/provider quota； - circuit state； - retry amplification guard。
### Dead Letter
Dead-letter job 必须保留：
- 原 job/command ID； - tenant/scope； - payload hash； - schema/config/policy snapshot； - attempt history； - error taxonomy； - last lease/worker； - checkpoint/result/artifact refs； - unknown outcome； - next action hint； - retention/expiry。
Dead-letter 不是删除，不能自动无限重放。
### DLQ 处理流程
```text
dead-lettered -> inspect and classify -> validate schema/current policy -> query side-effect status -> choose retry_modified | resume_checkpoint | compensate | discard | manual -> create new job/idempotency key if safe -> append recovery/dead-letter resolution event
```
## Idempotency 与 Deduplication
### 三个身份
```text
commandId            用户/系统意图身份 jobId                队列工作身份 executionId           一次 worker 执行尝试 idempotencyKey       业务去重身份 deduplicationKey     同语义工作合并提示
```
它们不能混用。
### Idempotency 作用域
```text
run session workspace tenant provider operation business resource global
```
高风险动作必须选择足够宽但可解释的业务作用域。
### Fingerprint
```text
hash( command/job type + canonical validated payload + tenant/resource scope + semantic version + relevant snapshot version )
```
不包含随机 trace、UI cursor 或无关时间戳。
### Dedup 策略
- exact same idempotency key：返回已有 receipt； - same fingerprint、可合并的只读 job：可合并 waiter； - same fingerprint、非幂等写：拒绝或要求新 approval； - same business key in-flight：查询/等待； - same job after lease expiry：恢复原 execution record，不盲建副本； - scheduled duplicate：按 deterministic schedule key 去重； - 不同 payload 复用同 key：conflict。
### Idempotency Store
```typescript
interface IdempotencyStore { reserve(input: IdempotencyReservation): Promise<IdempotencyReceipt>; get(scope: ScopeRef, key: string): Promise<IdempotencyRecord | undefined>; commit(receipt: IdempotencyReceipt, result: IdempotencyResult): Promise<void>; fail(receipt: IdempotencyReceipt, error: NormalizedError): Promise<void>; }
```
## Ordering、Partition 与并发
### Ordering 类型
```text
none partition_ordered key_ordered session_ordered run_ordered causal_ordered
```
### Ordering 不变量
- 同一 ordering key 的 job 不并行执行，除非 contract 显式允许。 - 后续 job 不能越过前置 job 的 unknown outcome barrier。 - priority 不能无条件打破 destructive resource 的顺序。 - retry 不改变原逻辑序号；新 execution 有新的 attempt 序号。 - queue completion order 不等于 model feedback order。 - requeue/migration 保留 logical order 和 causation。
### 并行规则
可并行：
- 独立只读子任务； - 不共享资源的 artifact scan； - 不同 session 的安全 background work； - 明确无副作用的 provider probes。
必须串行或加锁：
- 同一 session branch append； - 同一 workspace/file/repo 写入； - 同一外部 account/resource； - 同一 provider-side conversation state； - 同一不可逆业务 key； - destructive 或 production deployment。
### Resource Lock
```typescript
interface QueueResourceLock { acquire(request: LockRequest, signal: AbortSignal): Promise<LockLease>; release(lease: LockLease): Promise<void>; recoverExpired(leaseId: string): Promise<void>; }
```
多锁按 canonical key 稳定排序获取，避免死锁。
## Priority、Fairness 与 Noisy Neighbor
### Priority
priority 只在硬约束和安全边界内排序。
建议优先级：
```text
critical recovery/security approval resume interactive critical interactive standard background user task subagent compaction/indexing artifact scan/gc notifications
```
### Aging
单纯 priority 会造成低优先级饥饿。
可使用：
```text
effective priority = base priority + aging bonus - tenant debt - retry penalty
```
aging 必须有上限，避免长期 background 反超 critical recovery。
### Weighted Fair Queue
按 tenant/workspace/session 分层：
- tenant concurrency ceiling； - tenant queue depth； - weighted worker share； - burst token； - starvation counter； - retry amplification budget； - per-provider quota reservation。
### Noisy Neighbor
隔离资源：
- queue slots； - worker leases； - provider connections； - sandbox startup； - event router queue； - artifact bandwidth； - DB connections； - memory/CPU/disk； - catalog refresh； - recovery workers。
单 tenant fan-out 不得占满全局 worker；失败 storm 不得无限产生 retry job。
## Backpressure、Capacity 与 Admission
### Capacity 维度
```text
queue depth oldest age worker slots provider concurrency session/event append rate projector lag artifact bytes sandbox instances lock contention quota/cost
```
### Backpressure 阶段
```text
observe depth/age/lag -> throttle new admission -> pause optional background -> reduce subagent fan-out -> coalesce ephemeral work -> reject non-critical jobs -> preserve recovery/approval/terminal paths
```
### 队列满时
- critical durable/recovery：保留或显式 fail with capacity error； - interactive standard：返回 queued/deferred 或 capacity_exhausted； - background/subagent：延迟、降权或暂停； - token/progress：coalesce/drop ephemeral； - terminal/error/approval/checkpoint：不可静默丢失； - 不把无限工作塞进内存等待。
### Admission Reservation
```typescript
interface CapacityReservation { tenantId: string; queueId: QueueId; jobType: string; estimatedWorkerMs: number; estimatedTokens?: number; estimatedArtifactBytes?: number; estimatedCost?: Money; idempotencyKey: string; }
```
reservation 在 enqueue 前创建，job terminal 后 settle/release。
### 超卖防护
- reservation 原子化； - 同一 tenant/queue 不超过并发上限； - shadow/hedge 使用独立低优先级 slot； - retry 预留额外预算； - lease 过期的 reservation 可回收，但必须保留 recovery 状态； - 不因 worker 数增加就忽略 provider quota、store 或 sandbox capacity。
## Delayed/Scheduled Jobs
### Scheduled Job
```typescript
interface ScheduleSpec { availableAt?: string; notBefore?: string; deadlineAt?: string; recurrence?: RecurrenceSpec; timezone?: string; misfirePolicy: "skip" | "run_once" | "catch_up_bounded"; idempotencyTemplate: string; }
```
### 规则
- scheduled job 在 `availableAt` 前不可 lease； - schedule key 必须 deterministic； - 时区、DST、clock skew 要进入 snapshot； - 过期任务按 misfire policy 处理； - catch-up 有最大补发数； - cancel schedule 不等于取消已运行 execution； - recurrence 生成的新 job 要有 parent schedule ref 和独立 job ID； - scheduled job 不绕过当前 policy、quota、egress 和 approval。
### Delayed Queue 恢复
- 时钟异常时以 store/server time 为准； - 进程重启后从 durable schedule index 恢复； - 已触发但未入队的 schedule 用 idempotency key 补偿； - 不依赖内存 timer 作为唯一调度事实。
## Cancel、Timeout 与 Expiry
### Cancel 语义
```text
cancel requested -> stop new work -> signal worker/run scope -> wait for provider/tool/child tasks -> classify outcome -> commit cancelled or unknown -> release lease/quota/locks
```
Host disconnect 不是 cancel。
### Timeout 层级
- admission timeout； - queue wait timeout； - lease acquisition timeout； - worker start timeout； - provider connect/first-event/stream timeout； - tool timeout； - approval timeout； - checkpoint timeout； - settlement timeout； - delivery timeout； - total job deadline。
每个 timeout 使用独立 error code 和指标。
### Cancel 竞态
- cancel 前已完成副作用：保留成功 receipt； - cancel 与 result commit 并发：按 durable sequence 决定事实； - cancel 请求已发送但未知：写 unknown； - lease 释放前必须处理 in-flight tool； - 不用 UI 显示“取消”推断副作用未发生。
### Expiry
Job expiry 时：
- 不再开始新执行； - 已运行执行按 policy settle； - 未知副作用进入 recovery； - reservation 释放未用部分； - artifact/temp/lock 按 retention/cleanup 处理； - 写 expired event 和 reason。
## Poison Message
### 定义
Poison message 是重复失败、无法解析、违反安全规则或会导致 worker 无限循环的 job。
常见来源：
- schema 永久无效； - 缺失 required snapshot； - 递归 payload/资源洪泛； - provider adapter 对该 payload 恒失败； - 业务资源已删除； - policy 永久 deny； - 旧 worker 无法理解新 schema； - side-effect unknown 且无 status query。
### 检测
```text
failure count + same error fingerprint + no state progress + retry amplification + elapsed deadline + unchanged payload hash
```
### 处理
- 暂停自动 retry； - 转 dead-letter 或 quarantine； - 保存最小 diagnostic/artifact； - 不把完整 secret 或 payload 复制到 DLQ； - 允许人工修正 schema/assignment 后新建 job； - 新 job 使用新 idempotency key，保留 parent/dead-letter reference； - 定期扫描 poison rate 和同类 fingerprint。
## Outbox、Inbox 与 Durable Event Integration
### Outbox
Outbox 用于把业务事实和“需要投递/排队的消息”绑定到同一 durable commit。
```text
append session/event/job intent + outbox record -> one durable transaction -> outbox dispatcher -> queue/event router -> mark dispatched
```
### Inbox
Inbox 用于接收外部或上游事件，保证重复投递不会重复处理。
```typescript
interface InboxRecord { source: string; messageId: string; tenantId: string; payloadHash: string; receivedAt: string; status: "received" | "processing" | "processed" | "failed" | "quarantined"; resultRef?: string; }
```
### Outbox/Inbox 不变量
- source message ID、tenant、payload hash 必须绑定； - 相同 message ID 不同 payload 是 conflict； - dispatcher 至少一次发送； - consumer 通过 inbox/idempotency 保证重复安全； - dispatch success 不等于业务执行 success； - event store、session store、queue 双写必须有 source-of-truth 或 outbox 协议。
### Durable Event Integration
Queue lifecycle events：
```text
job.created job.admitted job.queued job.scheduled job.leased job.heartbeat job.checkpointed job.retry_scheduled job.nacked job.completed job.failed job.cancel_requested job.cancelled job.expired job.dead_lettered job.recovered job.unknown_outcome
```
Token delta、spinner 和高频 progress 默认 ephemeral；lease、checkpoint、terminal、unknown outcome 和 side-effect receipt durable。
## Exactly-once Illusion
### 不能承诺的事实
队列不能单独保证：
- worker 只运行一次； - provider 只接受一次； - 外部 API 只写一次； - result commit 与 side effect 原子； - 网络断开后没有副作用。
### 构造安全语义
```text
queue delivery at-least-once + idempotency record + execution record + status query + external receipt + lease fencing + transactional outbox/inbox + compensating action = bounded duplicate risk + explainable recovery
```
### Execution Record
```typescript
interface ExecutionRecord { executionId: string; jobId: JobId; leaseId: LeaseId; callId?: string; idempotencyKey: string; fingerprint: string; state: "prepared" | "started" | "committed" | "failed" | "cancelled" | "unknown"; sideEffectClass: "none" | "reversible" | "irreversible"; backendRef?: string; resultRef?: string; receiptRef?: string; startedAt: string; endedAt?: string; version: number; }
```
### Side-effect Recovery
1. 查询 execution record。
2. 查询 provider/tool/business status。
3. 若成功，补写 result/event。
4. 若失败，按 policy retry/compensate。
5. 无法确认，写 unknown outcome。
6. 高风险动作等待人工处理。
## Worker Crash Recovery
### 失联检测
```text
heartbeat timeout -> mark worker_lost -> stop old lease acceptance -> preserve old fencing token -> inspect checkpoint and execution records -> probe side effects -> acquire recovery lease -> resume | retry safe | manual | dead-letter
```
### Fencing
旧 worker 即使恢复，也不能使用旧 fencing token 提交 ack、heartbeat、result 或 cleanup。
### Recovery Lease
Recovery lease 必须：
- 使用新的 lease ID/version； - 引用旧 lease 和 worker； - 绑定相同 tenant/scope； - 重新验证 policy、quota、model/toolset/sandbox； - 防止两个 worker 同时 probe/execute； - 具有较短 recovery timeout； - 所有动作写 durable recovery event。
### Checkpoint
Background job checkpoint 至少保存：
- last durable event； - Run/Turn/Attempt； - working state； - pending approval； - in-flight tools； - budget used/reserved； - model/toolset/config/policy hash； - context plan hash； - artifact refs； - lease/execution refs； - retry/fallback state。
### Resume
resume 前重新验证：
- tenant membership； - session/branch ownership； - schema/projector compatibility； - policy/egress/approval expiry； - workspace/base snapshot； - provider capability/catalog/route； - tool side-effect status； - remaining deadline/budget； - lock/sandbox/secret lease。
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### Model Runtime
队列 worker 执行 Model Attempt 时：
- job payload 只引用 ResolvedModel/RouteSnapshot； - provider request 经过当前 job 的 egress、schema、capability snapshot； - provider retry 和 job retry 分开计数； - provider unknown outcome 不自动 requeue； - usage/cost 归因到 job、attempt、run、tenant。
### Prompt
Prompt 只解释：
- 当前任务是 foreground/background； - 可能需要等待、审批、取消或恢复； - 工具结果可能异步返回； - 大结果使用 ArtifactRef； - queued job 不等于 completed； - unknown outcome 不应被模型假设为失败。
Prompt 不实现 queue ownership、lease、retry 或 idempotency。
### Context
后台 job 的 ContextPlan 保存为可恢复 snapshot 或 ref：
- objective； - selected resources； - token budget； - egress/redaction； - model/toolset/policy； - compaction state； - artifact refs； - parent assignment（subagent）。
队列重试不应每次无边界复制完整 transcript；应从 checkpoint、ContextPlan 和 semantic entries 重建。
### Tool
Queue 与 Tool Runtime 的交接：
```text
job lease -> run scope -> tool prepare -> policy/approval/sandbox -> execution record -> tool execute -> result/artifact -> durable event -> job ack/nack
```
后台工具必须返回 durable job reference，不应伪装成同步 ToolResult。
### State/Memory
Queue lifecycle 和 run state 分离但关联：
- Queue 事实：queued/leased/heartbeat/retry/dead-letter； - Session 事实：run/turn/attempt/tool/result/checkpoint； - Memory 事实：候选、写入、召回和 retention； - Artifact 事实：上传、扫描、结果和 expiry； - Usage 事实：reservation、observation、settlement。
每个事实有自己的 projector，不用 job status 覆盖 session truth。
### Policy/Sandbox
Enqueue 时做 admission/call policy；执行时再次做 execution/egress policy。
Worker 不能因为 job 已在队列中就跳过：
- tenant membership； - approval expiry； - policy version； - sandbox attestation； - secret lease； - resource ownership。
### Harness
Harness 负责：
```text
Host/Orchestrator -> create Job -> reserve budget/quota -> enqueue -> worker lease -> create RunScope -> execute Kernel -> checkpoint/event/result -> ack/nack -> delivery/notification
```
`RunScope` 取消必须传播到 queue lease、model stream、tool tasks、child runs、approval wait、event consumers 和 delivery。
### Host Adapter
Host 可查询：
- accepted/queued/leased/running/checkpointed/waiting/terminal； - queue position/oldest age 的安全摘要； - pending approval； - artifact/result ref； - resume cursor。
Host 不应显示未经授权的其他 tenant queue，也不能根据 queue visible 猜测副作用状态。
## 生命周期与状态机
### Command 状态机
```text
Received -> Authenticated -> Validated -> Admitted -> Rejected | Accepted -> Enqueued -> Superseded | Cancelled | Expired
```
### Job 状态机
```text
Created -> Admitted -> Queued -> Scheduled -> Leased -> Preparing -> Running -> WaitingForApproval | WaitingForDependency -> Checkpointed -> Running -> Settling -> Completed | Failed | Cancelled | Unknown
```
### Lease 状态机
```text
Issued -> Active -> Renewing -> Released -> Expired -> RecoveryPending -> Recovered | Abandoned
```
### Retry 状态机
```text
FailureObserved -> Classified -> RetryBudgetChecked -> RetryScheduled -> Requeued -> LeasedAgain -> Exhausted -> DeadLettered
```
### Delivery 状态机
```text
Pending -> Enqueued -> Sent -> Acknowledged -> Failed -> Retrying -> DeadLettered
```
### 关键不变量
- job terminal 后不能再次 lease； - expired lease 不能被旧 worker ack； - dead-letter job 不自动重新执行； - queue ack 不覆盖 session terminal truth； - unknown job 不可直接转 completed； - cancellation 不删除 execution receipt； - schedule recurrence 不复用旧 job ID； - tenant scope 缺失时拒绝 enqueue、lease、ack、cancel。
## 决策流程
### Admission 决策
```text
request -> normalize command -> authenticate/tenant scope -> schema/business validation -> policy/approval requirement -> quota/capacity reservation -> idempotency/dedup -> select queue/partition/priority -> persist command + job/outbox -> return receipt
```
### Lease 决策
```text
worker hello -> authenticate worker -> verify capabilities/region/sandbox -> select eligible queues -> apply tenant fairness/priority/aging -> check ordering barrier -> reserve lease atomically -> issue fencing token -> start heartbeat
```
### Retry 决策
```text
failure -> classify error -> known/unknown outcome -> check side-effect class -> check retry budget/deadline/quota -> check policy/circuit/capability -> retry same | retry modified | fallback | wait | manual | dead-letter
```
### Recovery 决策
```text
lease expired/worker crash -> inspect execution record -> load checkpoint -> probe provider/tool/business status -> classify not_started/known_success/known_failure/unknown -> recovery lease -> resume/checkpoint | safe retry | compensate | manual
```
### Backpressure 决策
```text
queue depth/age/lag above threshold -> stop optional admission -> throttle tenant or class -> pause background/subagent -> preserve approval/recovery/terminal -> scale compatible worker if quota allows -> return capacity diagnostic
```
## 安全、隐私与租户隔离
### Tenant Boundary
Queue API 必须要求可信 `TenantContext`，不信任 job payload、prompt、模型参数或 URL 中的 tenant ID。
所有操作都做二次 owner check：
- enqueue； - lease； - heartbeat； - ack/nack； - cancel； - inspect； - replay； - dead-letter read/requeue； - artifact/result fetch； - metrics/diagnostic。
### Worker 权限
Worker identity 只拥有：
- 明确 tenant/workspace/run scopes； - job type/capability 子集； - 允许 provider/tool/backend； - sandbox profile； - 短期 secret binding； - queue lease 操作权限。
Worker 不得通过 payload 扩大 scope。
### Queue Payload
Job payload 应尽量保存：
- schema-validated command； - snapshot IDs/hashes； - artifact refs； - checkpoint refs； - secret handles； - minimal assignment。
不要把明文 secret、完整 prompt、完整工具输出和大二进制直接放进 queue payload。
### Egress
Job 执行产生的 provider/tool/artifact/notification egress 都重新检查：
```text
sensitivity + tenant policy + destination + purpose + retention -> allow | redact | summarize | artifact_only | deny
```
### Poison/Injection
Job payload、event、artifact、tool result、MCP description、provider metadata 和用户文本都可能包含 prompt injection。
它们不能：
- 改 queue priority； - 绕过 approval； - 改 tenant； - 选择 worker 或 provider； - 关闭 sandbox； - 注入任意 secret； - 把 dead-letter 自动重放。
### 加密与保留
- queue payload、receipt、checkpoint、artifact 和 audit 按 sensitivity 加密； - idempotency key 可使用 keyed hash； - secret 仅保存 reference/lease； - dead-letter retention 独立于业务 job； - 删除 tenant 时先冻结新 enqueue，再处理 running/unknown/dead-letter/backup； - deletion 不伪造 unknown side effect 已取消。
## 可观测性、SLO 与诊断
### Trace 层级
```text
request -> admission -> quota reservation -> enqueue -> lease -> worker -> run -> attempt/model -> tool -> checkpoint -> result -> ack/nack/retry -> event/outbox -> delivery
```
### 必备字段
```text
trace_id tenant_scope_hash queue_id job_id command_id partition_key_hash priority/fairness_class idempotency_key_hash deduplication_key_hash lease_id/version worker_id fencing_token_hash available_at/deadline queue_wait_ms lease_wait_ms heartbeat_age_ms run/session/turn/attempt IDs config/policy/model/toolset/context hashes retry_count error_category checkpoint_id result/artifact refs usage/cost side_effect outcome terminal status
```
### 指标
Queue：
- enqueue accepted/rejected/duplicate/conflict； - depth、oldest age、queue wait p50/p95/p99； - lease success/failure/expiry； - heartbeat miss； - active/running/completed/failed/cancelled/unknown； - retry amplification； - dead-letter rate； - poison fingerprint rate； - cancel latency； - scheduled misfire； - partition hotness。
Fairness：
- per-tenant queue wait； - reserved/actual worker share； - starvation count； - throttle/reject rate； - noisy-neighbor incidents； - tenant quota settlement drift。
Recovery：
- worker_lost； - recovery lease success； - resume success； - unknown outcome resolution time； - duplicate side-effect prevented； - checkpoint age/lag； - orphan process/lock/sandbox/temp。
### SLO
至少定义：
- enqueue durable acceptance； - accepted job 到 first durable event； - accepted job 到 lease； - lease 到 heartbeat health； - job terminal 可查询率； - critical/recovery job completion； - approval resume latency； - dead-letter inspection latency； - event/outbox delivery completeness； - unknown outcome resolution； - cross-tenant isolation violation target 为零； - durable event loss target 为零。
### Diagnostic Snapshot
```typescript
interface QueueDiagnosticSnapshot { queueId: QueueId; tenantScopeHash?: string; depth: number; oldestAgeMs: number; activeLeases: number; expiredLeases: number; workerHealth: WorkerDiagnosticView[]; partitionHotspots: PartitionDiagnosticView[]; retrySummary: RetryDiagnosticView; deadLetterSummary: DeadLetterDiagnosticView; backlogByClass: Record<string, number>; projectorLag?: number; outboxLag?: number; recentErrors: Diagnostic[]; redactionState: string; }
```
默认 metadata-only、短 TTL、重新授权；不显示 payload、secret、完整 prompt、原始命令或跨 tenant job。
### Audit
Audit 必须记录：
- 谁 enqueue/cancel/retry/requeue/dead-letter/inspect； - 哪个 tenant/workspace/session/run； - 哪个 policy/quota/config snapshot； - 哪个 worker/lease/fencing token； - 是否发生 unknown outcome； - 是否执行 recovery、compensation、break-glass； - 哪个 artifact/receipt 被读取或导出； - operator 是否修改 retry/priority/queue policy。
## 灾备与恢复
### 备份对象
必须备份：
- queue metadata、job、command、idempotency record； - lease/recovery state； - retry/dead-letter history； - schedule index； - outbox/inbox； - session/event/checkpoint； - artifact registry/blob/view/scan/retention； - quota/budget ledger； - policy/config/schema snapshots； - audit/forensic references。
仅备 queue 表而不备 outbox、checkpoint、event、artifact 和 receipts，不能保证恢复。
### RPO/RTO
分别定义：
- interactive queue； - background/subagent； - recovery/forensics； - event/outbox； - artifact； - audit； - idempotency store； - quota/budget。
不能用一个全局数据库备份数字代表所有组件。
### Restore 流程
```text
declare restore scope -> verify backup manifest/integrity/key access -> restore into isolated namespace -> validate tenant/partition/sequence -> replay outbox/events -> rebuild projections -> restore queue indexes and schedules -> classify jobs not_started/known/unknown -> pause recovery candidates -> query side effects -> open traffic gradually
```
### Region/Provider Outage
- 暂停 retry amplification； - 检查 circuit、quota、provider capability 和 egress； - 可安全请求进入 queue wait； - 可能副作用请求保留 unknown； - fallback 重新 routing，不跨越 tenant/region policy； - 恢复从 half-open probe 和 bounded canary 开始。
### Worker Pool Loss
- 标记 lease expired； - 重新读取 checkpoint； - 获取 recovery lease； - 先 probe side effect； - 安全读任务可重试； - 写任务 unknown/manual； - 不创建并行不可逆副本。
## 测试、Chaos 与 Conformance
### Testkit
```text
InMemoryDurableQueue FakeQueueStore FakeQuotaPort FakePolicy FakeWorkerRuntime DeterministicClock DeterministicIds ScriptedProvider FakeToolRuntime FakeEventStore FakeOutbox/Inbox FakeArtifactStore FakeSideEffectRecorder SlowConsumer CrashInjector LeaseRaceHarness FairSchedulerHarness ReplayRunner
```
### 单元测试
- command/job schema、hash、scope、idempotency； - enqueue duplicate/conflict； - lease CAS/version/fence； - heartbeat 延长和超时； - ack/nack/complete/fail； - retry backoff、budget、deadline； - DLQ、poison fingerprint； - partition/order barrier； - priority aging、weighted fairness； - schedule/misfire/cancel； - cancellation/expiry； - outbox/inbox dedup； - quota reservation/settlement/release； - diagnostic redaction。
### Queue Contract Tests
每个 queue backend 必须验证：
1. durable enqueue 后重启仍可读；
2. expected version 冲突不覆盖；
3. 相同 idempotency key 返回同一 receipt；
4. 不同 payload 同 key 返回 conflict；
5. lease 只发给一个有效 worker；
6. lease expiry 后可恢复；
7. 旧 fencing token 无法 ack；
8. heartbeat 可续租但不能改 payload；
9. ack/nack 原子更新状态；
10. retry 后不丢 attempt history；
11. dead-letter 可查询且不自动重放；
12. tenant partition 不串线；
13. ordering barrier 生效；
14. queue full 返回明确 capacity outcome。
### 集成测试
至少包括：
1. foreground background run 断线后继续；
2. subagent lease 过期安全接管；
3. compaction/memory/artifact scan job；
4. approval resume job 恢复；
5. provider 429 有限 retry；
6. tool timeout 不重复 side effect；
7. side effect 后 crash、result commit 前恢复；
8. checkpoint 后 worker crash resume；
9. outbox 发送重复；
10. inbox duplicate message；
11. queue backlog 触发 backpressure；
12. tenant noisy neighbor 被限流；
13. scheduled job misfire；
14. cancel 与 completion race；
15. dead-letter 修复后新 job；
16. artifact upload unknown 不盲传；
17. event projector lag 不伪造 terminal；
18. Host disconnect 不误取消；
19. policy/version 变化使旧 job pause；
20. cross-tenant lease/inspect/ack 被拒绝。
### Chaos/Fault Injection
注入：
- queue store 断电/延迟/部分写； - lease commit 后 worker crash； - side effect 后 heartbeat 丢失； - result commit 前 process kill； - duplicate enqueue/ack/nack； - outbox dispatcher crash； - inbox commit 前后 crash； - provider EOF/429/5xx； - tool ignored abort； - artifact backend outage； - event projector lag/gap； - clock skew； - worker capability downgrade； - policy/credential rotation； - partition hot spot； - queue full/backpressure； - dead-letter store failure； - region loss； - network split。
### 必测断言
不能只比较最终文本，必须同时断言：
- durable job status； - queue/lease sequence； - worker execution count； - side-effect count/receipt； - idempotency/dedup outcome； - retry/dead-letter； - checkpoint/replay； - usage/cost； - tenant isolation； - event/outbox completeness； - resource cleanup。
### Property Tests
```text
same idempotency key + same payload -> at most one logical result old fencing token -> never commits after recovery lease cancel(parent) -> descendants eventually settle lease expiry -> no concurrent irreversible execution replay(job events) -> same job projection queue fairness -> bounded starvation under sustained load unknown outcome -> never auto becomes success DLQ replay -> requires new explicit decision and safe idempotency
```
## 反模式
1. 把 Durable Queue 实现成内存数组。
2. 只保存 payload，不保存 schema、tenant、scope、hash、deadline 和 idempotency。
3. 把 queue visible 当作旧 worker 一定未执行。
4. lease 只有 job ID，没有 version、expiry 和 fencing token。
5. heartbeat 失败后旧 worker 继续 ack。
6. queue ack 早于 durable result/event commit。
7. 429/5xx/EOF 无界重试。
8. 把 transport retry、agent retry、tool retry、job retry 和 fallback 混成一层。
9. 不区分 failed 与 unknown。
10. 可能成功的写操作在网络失败后盲目重放。
11. 只用 call ID 作为业务幂等键。
12. 同一 tenant 无限 fan-out，占满全局 worker。
13. 单一 FIFO 导致 approval/recovery 饥饿。
14. priority 没有 aging，background 永久饥饿。
15. queue 满时无界缓存或静默丢 durable job。
16. token delta、progress 和 job 共享无界队列。
17. outbox、session、event、queue 双写没有事务或补偿。
18. inbox 不做 message ID/payload hash 去重。
19. scheduled job 依赖进程内 timer。
20. cancel 只停止 UI，不停止 worker/tool/provider 子任务。
21. timeout 后直接释放 lease，不分类 side effect。
22. poison message 自动反复重试。
23. dead-letter 直接批量重放生产副作用。
24. worker 读取最新全局 policy 覆盖 frozen job snapshot。
25. worker payload 可以覆盖 tenant、workspace、secret 或 sandbox。
26. queue partition 与 artifact/event/session scope 不一致。
27. 恢复时只重放 job，不查询 provider/tool/business status。
28. 只备份 queue，不备 outbox、checkpoint、artifact、event 和 audit。
29. Host 断线被当成 cancel 或 failure。
30. queue metrics 使用完整 payload、prompt、path、tenant ID 高基数标签。
31. 用最终文本声称 job 完成，没有 receipt 和 durable terminal。
32. chaos 只测 worker crash，不测 lease race、unknown、outbox、quota、DR 和 cross-tenant。
## 实施清单
### P0：持久化与契约
- [ ] 定义 Queue、Command、Job、Event、Receipt、Lease、Checkpoint。 - [ ] 定义 Job/Command/Execution/Idempotency IDs。 - [ ] 定义 schemaVersion、payloadHash、scope、tenant、deadline、priority。 - [ ] 实现 durable enqueue、inspect、status 和 event append。 - [ ] 实现 expectedVersion、CAS、idempotency 和 duplicate/conflict。 - [ ] 实现 lease version、visibility timeout 和 fencing token。
### P1：Worker 执行与恢复
- [ ] 实现 heartbeat、ack、nack、complete、fail、cancel。 - [ ] 实现 retry policy、backoff、budget 和 deadline。 - [ ] 实现 checkpoint、execution record、status query 和 unknown outcome。 - [ ] 实现 worker crash recovery 和 recovery lease。 - [ ] 将 model/tool/approval/artifact/event/usage settlement 接入 job lifecycle。 - [ ] 实现 dead-letter、quarantine 和人工恢复流程。
### P2：调度、公平与容量
- [ ] 实现 queue classes、partition、ordering barrier。 - [ ] 实现 priority、aging、weighted fairness 和 tenant quota。 - [ ] 实现 noisy-neighbor protection、backpressure 和 capacity admission。 - [ ] 实现 delayed/scheduled/misfire/cancel/expiry。 - [ ] 将 provider quota、sandbox capacity、artifact bytes 和 event lag 纳入 reservation。 - [ ] 建立 queue/lease/worker/partition diagnostic snapshot。
### P3：一致性与安全
- [ ] 实现 transactional outbox、inbox、dispatcher 和 consumer dedup。 - [ ] 定义 durable queue 与 Event Store source-of-truth。 - [ ] 实现 tenant-aware repository、worker scope、artifact ACL 和 audit。 - [ ] 实现 secret handle、egress、policy revalidation 和 sandbox attestation。 - [ ] 防止旧 fencing token、旧 policy、旧 lease、旧 approval 提交动作。 - [ ] 对未知副作用 fail-closed 并提供 status query/compensation。
### P4：运维、DR 与评测
- [ ] 定义 queue、recovery、delivery、fairness、unknown outcome SLO。 - [ ] 建立 retry amplification、DLQ、poison、backlog 和 noisy-neighbor 告警。 - [ ] 备份 queue/outbox/inbox/event/session/checkpoint/artifact/audit/config。 - [ ] 进行 restore、region loss、provider outage、worker pool loss 演练。 - [ ] 建立 contract、integration、property、chaos、security 和 conformance suites。 - [ ] 建立 production feedback -> minimized regression case -> CI gate 闭环。
## 五个参考项目的启发来源
### Pi
- headless loop、EventStream、session tree 和 checkpoint/compaction 启发后台 run 必须由独立 Harness/State/Queue 管理，而不是由 Host 连接生命周期决定。 - CLI/TUI/RPC 共用 runtime 启发 queue job 与 delivery adapter 分离。 - tool loop 中执行并发、结果顺序稳定启发 queue scheduler 保持 call ordinal 与 completion order 分离。 - 可恢复 session 启发 queue job、checkpoint、unknown outcome 和 replay 必须可追溯。
### Grok Build
- actor 化 Session/ChatState/Sampler 启发 queue worker 的状态所有权、单写者和串行提交。 - permission decision、folder trust、sandbox 启发 enqueue admission、执行 policy 和 sandbox 不能混为 queue allow。 - 并行工具和路径级锁启发 partition/order/resource lock。 - 输出上限和上下文修剪启发 queue backpressure、artifact offload 和容量预算。
### OpenCode
- server/client、durable event/projector 和多客户端事件启发 queue status、outbox、projection、cursor 和 resume。 - session/message/part 与 snapshot/patch/revert 启发 queue job 不能替代 semantic state，恢复要依赖 checkpoint 与可审计事实。 - permission、tool、MCP/LSP 分离启发 worker 只调度，不越权执行。
### Claude Code
- subagents、后台任务、skills、hooks、memory、permission modes 和任务工作流启发 background job、child run、approval-resume 和最小上下文。 - 计划、任务与验证工作流启发 job acceptance criteria、checkpoint、structured result 和 parent fan-in。 - 项目级资源与长期 memory 启发 queue payload 只携带必要 artifact/ref，不复制全部 transcript 或 secret。 - 公开能力和安全语义以现有本地文档中标注的 Anthropic 官方资料为准，辅助源码不作为规范。
### OpenClaw
- AgentHarness registry、agent-core、Gateway/channel 和 provider runtime 启发 queue、worker、Host delivery 和 provider 调用分层。 - 后台运行、session key、memory flush 和多渠道 delivery 启发 scheduled/background job 不依赖前台连接。 - tool、sandbox、elevated 分离启发 worker execution profile、secret binding 和 fail-closed。 - 事务化插件注册启发 outbox/registration rollback、job admission snapshot 和失败清理。
## Definition of Done
Durable Queue 实现只有在以下条件同时满足时才算完成：
- queue、command、job、event、receipt、lease 的语义和接口明确； - enqueue、lease、heartbeat、ack、nack、retry、DLQ、cancel、schedule 都是 durable、可查询、可审计； - visibility timeout 与业务 execution status 分离； - idempotency、deduplication、fencing 和 status query 能防止盲目重复副作用； - ordering、partition、priority、fairness、tenant isolation 和 noisy-neighbor 有硬约束； - backpressure/capacity 能暂停或拒绝工作，而不是无限缓存； - worker crash、lease expiry、provider outage、artifact failure、outbox/inbox crash 有恢复路径； - unknown outcome 不被伪装成 failed 或 success； - background run、subagent、compaction、memory、artifact、notification 与 Harness/State/Event 集成； - policy、approval、sandbox、secret、egress 和 tenant ownership 在 enqueue 与 execution 两端重新校验； - SLO、metrics、audit、diagnostic snapshot、DR 和 runbook 可运行； - contract、integration、property、chaos、security 和 conformance 测试覆盖正常、边界、恢复和负向路径； - 不依赖内存数组、UI 状态或最终文本证明任务已成功。
