# Provider Recovery Engineering 细粒度工程设计
> 本文定义 Agent Harness 中 Provider Recovery 的恢复控制面、运行面、状态持久化、故障隔离和验证闭环。
>
> 设计依据仅来自当前目录已有的参考架构、`SKILL.md`、`agent-reference-architecture.md`、`agent-harness.md` 以及 Provider Runtime、Provider Routing、Provider Runtime Conformance、Provider Schema Evolution、Provider Incident Response、Provider Security Contract、Production Operations、Durable Queue、Workflow Orchestration、Workflow Scheduling、Data Lineage、Data Governance、Data Quality Operations、Privacy、Session Replay、Event/Observability、Evaluation、Artifact、Workspace Isolation 和 Multi-tenant 文档中的本地调研结论；不依赖 README，不进行网络搜索。
>
> **边界声明：** Provider Recovery 不是“重试三次”。恢复必须先判断请求是否已被 provider 接受、是否存在外部副作用、是否满足能力和 egress 契约，再决定 retry、hedge、fallback、drain、quarantine、checkpoint、replay、reconcile 或人工接管。任何恢复动作都必须留下新的 `Attempt`、`CanonicalEvent`、`UsageLedger` 和证据引用。标题映射约定：`Recovery Decision Flow` 即“恢复决策流程”，`Circuit Breaker` 即“熔断器”，`Unknown Outcome` 即“未知结果”，`Recovery Receipt` 即“恢复证明”。
## 目录
1. [目标与非目标](#目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [职责边界](#职责边界)
4. [故障域与恢复对象](#故障域与恢复对象)
5. [Provider Outage/Failure Taxonomy](#provider-outagefailure-taxonomy)
6. [Health Signal 与 Evidence](#health-signal-与-evidence)
7. [Failure Budget、Recovery SLO 与 RTO/RPO](#failure-budgetrecovery-slo-与-rtorpo)
8. [总体架构与包布局](#总体架构与包布局)
9. [核心数据模型](#核心数据模型)
10. [TypeScript 接口](#typescript-接口)
11. [Attempt、Request Identity 与状态记录](#attemptrequest-identity-与状态记录)
12. [Recovery State Machine](#recovery-state-machine)
13. [Circuit Breaker](#circuit-breaker)
14. [Bulkhead、Admission 与 Noisy Neighbor](#bulkheadadmission-与-noisy-neighbor)
15. [Retry、Backoff 与 Jitter](#retrybackoff-与-jitter)
16. [Hedging 与重复请求控制](#hedging-与重复请求控制)
17. [Fallback、Degraded Mode 与能力保持](#fallbackdegraded-mode-与能力保持)
18. [Routing Drain、Quarantine 与流量止损](#routing-drainquarantine-与流量止损)
19. [Idempotency、Dedup 与 Unknown Outcome](#idempotencydedup-与-unknown-outcome)
20. [In-flight Requests 与资源收敛](#in-flight-requests-与资源收敛)
21. [Stream Resume、Abort 与终止语义](#stream-resumeabort-与终止语义)
22. [Queue Replay、Workflow Checkpoint 与恢复](#queue-replayworkflow-checkpoint-与恢复)
23. [Artifact Consistency 与大对象恢复](#artifact-consistency-与大对象恢复)
24. [Credential/Config Rollback](#credentialconfig-rollback)
25. [Regional Failover 与 Residency Guard](#regional-failover-与-residency-guard)
26. [Data Loss、Duplication 与 Settlement Semantics](#data-lossduplication-与-settlement-semantics)
27. [Recovery Phases](#recovery-phases)
28. [Recovery Decision Flow](#recovery-decision-flow)
29. [Recovery Verification 与 Reconciliation](#recovery-verification-与-reconciliation)
30. [Incident Handoff 与 Recovery Runbook](#incident-handoff-与-recovery-runbook)
31. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
32. [安全、隐私与多租户](#安全隐私与多租户)
33. [可观测性、Dashboard 与 Alerts](#可观测性dashboard-与-alerts)
34. [测试策略与 Evaluation](#测试策略与-evaluation)
35. [Chaos、Fault Injection 与 Game Day](#chaosfault-injection-与-game-day)
36. [反模式](#反模式)
37. [实施清单](#实施清单)
38. [五个参考项目的启发来源](#五个参考项目的启发来源)
39. [Definition of Done](#definition-of-done)
## 目标与非目标
### 目标
Provider Recovery 必须能够：
- 以 `ProviderSurface`、`Attempt`、`RouteSnapshot`、`CredentialScope`、`EgressSnapshot` 和 `RunScopeContext` 描述受影响的最小故障域。
- 识别 outage、degraded、capacity、rate limit、transport、protocol、schema、capability、credential、regional、billing、artifact、stream、settlement 和 adapter failure。
- 把 provider 事实、health signal、routing decision、queue job、workflow checkpoint、artifact receipt、usage settlement 和 incident evidence 关联起来。
- 区分 transport retry、agent retry、tool retry、hedged attempt、fallback attempt 和 queue replay；每种动作具有独立预算和审计事实。
- 在可能成功的写请求、文件上传、缓存写入、远程删除和批处理提交前后处理 `unknown outcome`，避免盲目重放。
- 通过 circuit breaker、bulkhead、admission、drain、quarantine 和 degraded mode 防止单一 provider 故障扩散到全局。
- 支持流式响应的安全 abort、有限 resume、partial result 保存和未完成 tool call 的阻断。
- 支持 queue replay、workflow checkpoint、session replay、artifact reconciliation 和 side-effect receipt 查询。
- 在 credential、配置、adapter 或 routing 发布错误时执行版本化 rollback，并保留已运行 attempt 的冻结 snapshot。
- 支持区域故障下的显式 regional failover，并重新检查 policy、residency、retention、training、credential 和 capability。
- 明确 RTO、RPO、数据丢失、重复和延迟结算语义；不以“最终恢复”掩盖已发生的重复副作用。
- 将恢复结果转化为 Provider Incident、Conformance、Schema Evolution、Routing、Security、Privacy、Data Quality 和 Evaluation 回归证据。
- 建立 recovery SLO、错误预算、runbook、incident handoff、演练和 game day。
### 非目标
Provider Recovery 不负责：
- 代替 Provider Runtime 解析 provider SDK、HTTP frame、usage 或 finish reason。
- 代替 Provider Routing 进行普通候选排序；恢复只提供健康、隔离、禁止使用和候选可恢复性事实。
- 通过无上限 retry、扩大 worker 或跨 region 发送敏感数据来掩盖故障。
- 把 provider status page、HTTP 200、stream EOF、模型自述或 UI 完成当作唯一成功证据。
- 把 queue visible、lease 获得、request sent 或 provider accepted 当作业务副作用完成。
- 承诺 transport exactly-once；传输层默认假设至少一次、断线、重复投递和 unknown。
- 让 adapter 自行修改 tenant、region、credential、retention、training 或 fallback policy。
- 通过 recovery 绕过 Policy、Approval、Sandbox、DLP、Data Governance、Privacy 或 Audit。
- 把本地 session、artifact、cache、backup 删除当作 provider remote object 已删除。
- 用一次 green probe 证明所有 model、deployment、tool、structured output、region 和租户都已恢复。
### 核心公式
```text
Provider Recovery Quality
  = Failure Classification
  × Health Signal Quality
  × Blast Radius Control
  × Retry Safety
  × State Durability
  × Side-effect Reconciliation
  × Security/Privacy Enforcement
  × Recovery Verification
```
```text
Provider Recovery != retry three times
Provider Recovery = classify + contain + preserve + recover + reconcile + verify + learn
```
## 核心判断与术语
### 稳定术语
- `ProviderSurface`：`Provider`、`ApiFamily`、`Model`、`Deployment`、`Region`、`Endpoint`、`CredentialClass`、`AdapterVersion` 的组合。
- `ProviderFailure`：某次 `Attempt` 观察到的规范化失败事实，带 `failureClass`、证据、retryability 和 unknown outcome。
- `HealthSignal`：liveness、readiness、request acceptance、TTFE、stream integrity、capacity、usage settlement、artifact receipt 等观测。
- `HealthSnapshot`：某一时间点、surface、探针版本和 evidence window 的不可变健康视图。
- `FailureBudget`：允许被 recovery、retry、hedge、fallback 和 unknown outcome 消耗的有限预算。
- `RecoveryPlan`：给定 scope、attempt、policy、budget 和 checkpoint 的恢复动作计划。
- `CircuitBreaker`：对 provider surface 的闭合、开启、半开放和恢复试探控制。
- `Bulkhead`：按 tenant、provider、region、model class、queue、worker pool 或 side-effect class 划分的资源舱壁。
- `Drain`：停止新流量，允许安全完成已授权的 in-flight work，或在 deadline 到达时转为 abort/unknown。
- `Quarantine`：将 surface、credential、adapter、artifact、run 或 replay 从正常路径移除，保留诊断和恢复能力。
- `RecoveryReceipt`：status query、provider ack、artifact verify、credential rotation、delete、reconciliation 或 canary 验证的可查询证明。
- `Unknown Outcome`：请求可能已被 provider 接受或副作用可能已发生，但当前无法确认结果的恢复状态。
- `Settlement`：最终 result、usage、cost、artifact、receipt、checkpoint 和终态的 durable 结算。
### 三种 truth
```text
Provider Truth  provider request/response/receipt/status query 的外部事实
Platform Truth  event/session/queue/checkpoint/ledger/audit 的内部事实
Business Truth  工具、工作流、文件、artifact 或外部业务系统的结果事实
```
恢复不得用 Platform Truth 覆盖 Provider Truth，也不得用 Provider Truth 直接声称 Business Truth 已成立。三者不一致时必须进入 reconciliation 或 manual handling。
### 恢复不变量
1. 每个新的 retry、hedge、fallback、queue replay 和 region failover 都产生新的 `Attempt`。
2. 每个 `Attempt` 必须引用冻结的 `ResolvedModel`、`RouteSnapshot`、`ContractSnapshot`、`PolicySnapshot` 和 `EgressSnapshot`。
3. `unknown outcome` 不能自动转为 `failed`，也不能自动转为 `completed`。
4. 未完成的 tool call、structured output 和 artifact upload 不得伪造为完整成功。
5. 运行中配置变化不覆盖已冻结 run；安全撤销是唯一可强制中断已运行 scope 的控制面变化。
6. circuit open 只阻止新 attempt，不自动终止已有 attempt；in-flight 需要单独 drain/abort 计划。
7. fallback 必须重新检查 capability、egress、credential、quota、privacy、residency 和 tool contract。
8. recovery 事件必须 durable，token delta、probe heartbeat 等可保持 ephemeral。
9. 恢复验证必须比故障探测使用更高质量或更多样化的 evidence。
10. 任何无法核实的敏感外发、删除、账单和副作用都按高风险 unknown 处理。
## 职责边界
| 组件 | 负责 | 不负责 |
|---|---|---|
| `ProviderRuntime` | attempt、stream、raw receipt、usage、error、transport facts | 声明全局事故、选择业务补偿 |
| `ProviderHealth` | liveness、readiness、capacity、settlement、stream probe | 代替 incident commander |
| `ProviderRouting` | candidate、route、fallback compatibility、circuit input | 绕过 policy/egress、执行 recovery |
| `ProviderRecovery` | failure classification、budget、breaker、drain、recovery plan、verification | 直接解析 SDK 或执行工具 |
| `IncidentResponse` | severity、scope、commander、containment、沟通、关闭 | 代替 runtime parser |
| `DurableQueue` | enqueue、lease、retry metadata、DLQ、recovery candidate | 判断业务动作成功 |
| `WorkflowOrchestrator` | checkpoint、step transition、compensation、最终 task settlement | 修改 provider health |
| `SessionReplay` | recorded replay、fork、divergence、evidence | 无隔离重放副作用 |
| `ArtifactStore` | blob、view、hash、scan、range、retention、receipt | 宣称 provider remote delete 完成 |
| `Policy/Sandbox` | visibility、call、approval、execution、egress | 用 prompt 定义安全边界 |
| `ProviderSecurityContract` | credential、trust、retention、training、residency、revocation | 解析所有原始 frame |
| `DataLineage` | source、transform、consumer、residency、deletion edges | 直接授权外发 |
| `DataQuality` | completeness、freshness、consistency、reconciliation、quarantine | 修改 immutable facts |
| `Harness/RunSupervisor` | 预算、取消、structured concurrency、checkpoint、delivery | 变成 provider policy database |
| `Event/State/Audit` | durable facts、sequence、replay、audit integrity | 产生健康判断 |
| `Operations/SRE` | SLO、容量、runbook、on-call、演练 | 无审计手工改事实 |
强制关系：
```text
Runtime facts
  -> failure classifier and health signals
  -> recovery plan and incident command
  -> route/circuit/bulkhead enforcement
  -> checkpoint/queue/artifact settlement
  -> reconciliation and verification
  -> incident regression and SLO feedback
```
## 故障域与恢复对象
### ProviderSurface 分层
```text
Provider
  -> ApiFamily
    -> Model
      -> Deployment/Endpoint/Profile
        -> Region/Location
          -> CredentialClass
            -> AdapterVersion/ConfigVersion
```
健康状态必须至少能下钻到 deployment、region 和 credential class。只按 provider 粗粒度熔断会把健康的 model 或 region 一起隔离；只按 request 记录又无法阻止 blast radius。
### 恢复对象
- `Attempt`：当前一次调用和它的 raw receipt、stream cursor、usage 状态。
- `Turn`：模型采样与工具批次，可能需要暂停、重新采样或发送 typed error。
- `Run`：预算、route、checkpoint、delivery 和 cancellation 的完整边界。
- `WorkflowStep`：可能处于 running、waiting、retrying、unknown 或 compensation。
- `QueueJob`：可能持有 lease、checkpoint、attempt count 和 idempotency key。
- `ArtifactTransfer`：上传、下载、range、preview、remote object 或 delete 的中间状态。
- `CredentialLease`：可能已过期、撤销、错绑或需要 rotation。
- `RouteSnapshot`：可能因 circuit、health、policy 或 catalog 失效，需要重新规划。
- `UsageSettlement`：可能只知道估算 token，等待 provider receipt 或账单对账。
### 故障域矩阵
| 故障域 | 典型信号 | 默认动作 | 是否允许盲重放 |
|---|---|---|---|
| DNS/TLS/连接 | connect timeout、TLS、DNS | 有界 transport retry、breaker evidence | 仅无副作用 |
| Provider 5xx | 5xx、reset、EOF | retry budget、health degrade | 需看 outcome |
| 429/容量 | retry-after、capacity error | backoff、quota/bulkhead、route fallback | 通常可重试 |
| 4xx schema | invalid request、unsupported | stop、contract diagnostic | 否 |
| 401/403 | auth/permission | credential lease 检查、停止新流量 | 否 |
| stream integrity | sequence gap、partial tool args | abort、partial persist、unknown | 否 |
| usage settlement | usage missing、billing lag | provisional ledger、reconcile | 否 |
| remote artifact | upload ack lost、delete unknown | status query、quarantine | 否 |
| capability drift | tool/schema/finish 语义变化 | quarantine、conformance | 否 |
| regional | endpoint/location mismatch | egress stop、region isolation | 需重评估 |
| adapter/config | parser/config regression | rollback、drain、replay | 否 |
| workflow/store | checkpoint/event failure | pause、queue recovery | 需检查 lease |
## Provider Outage/Failure Taxonomy
### 分类原则
Provider Runtime 先返回规范化 `ProviderFailure`，Recovery 再结合时间窗口、surface、影响面和 attempt history 决定动作。不能把所有失败都标记为 retryable。
### `transport_unavailable`
连接未建立、DNS/TLS 失败、连接池耗尽、网络分区、代理拒绝或 provider endpoint 不可达。若请求尚未发出，通常属于安全 retry；若请求 body 已发送但没有 receipt，属于 unknown candidate。
### `provider_overloaded`
provider 仍可连接，但因容量、并发、区域负载或系统保护拒绝或延迟请求。需要结合 `Retry-After`、capacity signal、bulkhead 和 queue backlog，避免 retry storm。
### `rate_limited`
服务端或租户级限流。必须保留 scope、limit bucket、retry-after、reservation 和 quota evidence；不能简单等待固定时间后全量重试。
### `server_error`
5xx、upstream reset、服务端异常或 provider 明确表示 transient failure。重试前判断是否已接受请求，尤其是有副作用的 remote object、batch、file 和 conversation 操作。
### `protocol_error`
原始 response 无法按 API family 解码、terminal 事件缺失、frame 非法或 provider SDK 返回未知形状。默认停止当前 surface 的高风险流量，并记录 raw reference。
### `schema_or_capability_mismatch`
工具、structured output、多模态、reasoning、citation、grounding 或 stream 能力不匹配。必须返回 stable error 或使用显式 degraded mode，不能通过修改用户输入掩盖。
### `credential_failure`
401、403、签名过期、错误 tenant binding、rotation epoch 不一致、credential scope 不足或 provider 端撤销。单租户凭据错误通常是 request error；同一 credential class 的集中失败是 incident candidate。
### `context_overflow`
冻结模型限制不足或 projection 后超过 provider limit。交给 Context Runtime 进行可审计压缩、摘要或 artifact offload；不要把 overflow 伪装成 provider outage。
### `stream_interrupted`
连接中断、心跳超时、sequence gap、partial tool args、未知 finish reason 或中途 safety event。必须保存 partial state，不能把 EOF 当 completed。
### `settlement_unknown`
请求或上传可能成功，但 usage、artifact receipt、业务 ack 或 remote status 尚未可知。恢复路径是 query/reconcile，而不是立即重传。
### `regional_or_residency_violation`
实际 endpoint、provider-side object、backup 或 failover 目标违反 region、jurisdiction、retention 或 residency policy。优先 egress stop 和 quarantine。
### `billing_or_usage_drift`
usage 字段缺失、价格 profile 失效、账单与 UsageLedger 不一致、quota settlement 延迟或 currency/unit 变化。硬预算系统应进入 provisional settlement 和 conservative cap。
### `adapter_or_config_regression`
本地 adapter、projection、SDK、配置或 catalog 变更导致多个 surface 同类失败。需要 rollback、traffic drain、conformance fixture 和 release gate。
### 复合故障
故障可同时属于多个分类，例如：
```text
server_error + stream_interrupted + settlement_unknown
credential_failure + regional_violation + data_exposure
schema_or_capability_mismatch + adapter_regression
provider_overloaded + rate_limited + queue_backlog
```
Recovery 使用主分类决定 immediate action，辅分类决定安全、账务和数据治理动作。
## Health Signal 与 Evidence
### Signal 分层
1. **Liveness**：DNS、TCP、TLS、认证握手和基础 endpoint 可达。
2. **Readiness**：目标 deployment、model、region、api family 可接受最小安全请求。
3. **Acceptance**：请求是否被 provider 接受，是否有 request/response receipt。
4. **Stream**：首事件、事件间隔、sequence、terminal、tool call 完整性。
5. **Capacity**：429、容量错误、排队时间、并发、retry-after 和 quota。
6. **Semantic**：tool、structured output、finish、usage、safety、citation 和 multimodal conformance。
7. **Settlement**：usage、cost、artifact、delete、remote object、billing receipt 可查询。
8. **Security/Privacy**：region、credential、retention、training、DLP、egress 和 cross-tenant invariants。
### Probe 类型
```typescript
interface HealthProbeSpec {
  probeId: string;
  surface: ProviderSurfaceRef;
  kind: "liveness" | "readiness" | "semantic" | "settlement" | "security";
  requestProfile: "empty_safe" | "text_echo" | "tool_fixture" | "structured_fixture" | "artifact_fixture";
  sensitivity: Sensitivity;
  maxLatencyMs: number;
  maxCost: number;
  region: string;
  expectedCapabilities: string[];
  schedule: string;
}
```
生产 probe 必须使用合成、最小、不可敏感的 fixture；tool fixture 不得触发真实副作用；artifact fixture 使用可删除、可验证的测试对象。
### Health Observation
```typescript
interface HealthObservation {
  observationId: string;
  probeId: string;
  surface: ProviderSurfaceRef;
  attemptId?: string;
  observedAt: string;
  durationMs: number;
  result: "pass" | "fail" | "degraded" | "unknown";
  failure?: NormalizedProviderFailure;
  signals: HealthSignalValue[];
  evidenceRefs: EvidenceRef[];
  catalogVersion: string;
  adapterVersion: string;
  configSnapshotId: string;
  policySnapshotId: string;
}
```
### Signal 质量
每个 signal 必须带：
- source、observedAt、window、sample count 和 aggregation。
- surface key、tenant class、region、model/deployment 和 credential class。
- probe version、adapter version、catalog version 和 config snapshot。
- confidence、freshness、sensitivity、redaction state 和 evidence refs。
- 是否为直接观察、聚合推断或 provider 外部声明。
单个成功 probe 不能清除历史故障；恢复需要连续窗口、真实流量样本和 semantic/settlement evidence 的组合。
## Failure Budget、Recovery SLO 与 RTO/RPO
### Budget 维度
Failure budget 不只是错误次数，至少分为：
- `attemptBudget`：允许的 provider attempts。
- `retryBudget`：transport/agent retry 次数或 token/cost。
- `hedgeBudget`：并行 duplicate attempt 数量和持续时间。
- `fallbackBudget`：跨 provider/deployment 的替代次数。
- `unknownBudget`：允许处于 unknown 的时间和数量。
- `queueReplayBudget`：恢复重放的工作量和窗口。
- `recoveryCostBudget`：恢复 probes、reconciliation、backfill 的成本。
- `dataExposureBudget`：必须为零；任何疑似违规都不允许以可用性预算抵消。
```typescript
interface FailureBudget {
  budgetId: string;
  scope: ScopeRef;
  surface?: ProviderSurfaceRef;
  window: BudgetWindow;
  maxAttempts: number;
  maxRetries: number;
  maxHedges: number;
  maxFallbacks: number;
  maxUnknownMs: number;
  maxRecoveryCost?: CostBudget;
  consumed: BudgetConsumption;
  policyVersion: string;
}
```
### SLI
- request acceptance rate。
- safe completion rate：有可验证 terminal、usage 和 settlement 的完成比例。
- recovery success rate：故障后按原语义或明确 degraded 语义恢复的比例。
- unknown resolution latency。
- circuit open detection latency。
- containment latency：从首个高置信 signal 到 traffic stop/drain。
- checkpoint recovery latency。
- duplicate side-effect rate。
- artifact reconciliation success rate。
- credential rollback/rotation completion rate。
- regional failover policy-compliant rate。
- recovery verification false-positive rate。
### Recovery SLO 示例
> 以下是设计接口，不是对任何现有部署的承诺，具体阈值应由 Operations 和 tenant policy 配置。
| SLO | 目标表达 |
|---|---|
| 故障发现 | 高置信 surface outage 在告警窗口内被标记 |
| containment | 关键数据面在声明后进入 drain/quarantine |
| unknown resolution | 高副作用请求在有限窗口内 query 或转人工 |
| run recovery | 具有有效 checkpoint 的 run 可在 RTO 内恢复 |
| queue recovery | 过期 lease 在 RTO 内进入可审计候选 |
| artifact consistency | 已确认上传对象的 hash/size 与本地 manifest 一致 |
| settlement | provisional usage 在 RPO 窗口内对账或保留差异 |
| failover | 目标 region 满足 policy/egress/capability 后才接流量 |
### RTO/RPO
- `RTO`：从故障确认到服务进入可接受恢复态的最长时间。
- `RPO`：恢复后允许缺失的 durable 事实、事件、checkpoint、usage、artifact manifest 或业务输入范围。
- 高敏感和高副作用系统的 RPO 不应只用“最后一次日志”；必须明确 EventStore、SessionStore、ArtifactStore、UsageLedger 和 remote receipt 各自 RPO。
- RTO 不允许通过 fail-open、跨区外发、跳过 approval 或放宽 idempotency 实现。
## 总体架构与包布局
```text
Provider Runtime / Health / Routing / Incident
  -> Failure Normalizer
  -> Signal Aggregator
  -> Budget and Recovery Policy
  -> Circuit / Bulkhead / Drain Controller
  -> Recovery Planner
  -> Queue / Workflow / Session / Artifact / Credential Coordinators
  -> Reconciliation and Verification
  -> Event / Audit / Evaluation / SLO Projection
```
推荐包布局：
```text
packages/provider-recovery/
  contracts.ts
  failure-taxonomy.ts
  health-signals.ts
  budgets.ts
  circuit-breaker.ts
  bulkhead.ts
  retry.ts
  jitter.ts
  hedging.ts
  fallback.ts
  drain.ts
  quarantine.ts
  idempotency.ts
  inflight.ts
  stream-recovery.ts
  queue-replay.ts
  workflow-recovery.ts
  artifact-reconciliation.ts
  credential-rollback.ts
  regional-failover.ts
  planner.ts
  verification.ts
  reconciliation.ts
  runbook.ts
  metrics.ts
  testkit/
```
依赖方向：
```text
Harness -> ProviderRecoveryPort
ProviderRecovery -> Runtime/Health/Routing/Queue/Workflow/Artifact/Credential ports
Recovery -> Event/State/Audit/Lineage/Quality/Evaluation ports
Adapters -> provider protocol only
Infrastructure -> concrete probes, stores, queues and secret brokers
```
Recovery 不应 import TUI、具体 provider SDK、业务 ORM 或 shell 实现。
## 核心数据模型
```typescript
interface ProviderSurfaceRef {
  providerId: string;
  apiFamilyId: string;
  modelId?: string;
  deploymentId?: string;
  endpointId?: string;
  regionOrLocation?: string;
  credentialClass?: string;
  adapterVersion: string;
  configSnapshotId: string;
}
interface NormalizedProviderFailure {
  code: string;
  class: ProviderFailureClass;
  phase: "resolve" | "compile" | "connect" | "send" | "stream" | "parse" | "settle";
  retryability: "never" | "safe" | "conditional" | "unknown";
  outcome: "not_sent" | "rejected" | "accepted" | "unknown";
  providerStatus?: number;
  providerCode?: string;
  retryAfterMs?: number;
  messageForModel?: string;
  diagnostic: Diagnostic[];
  evidenceRefs: EvidenceRef[];
}
type ProviderFailureClass =
  | "transport_unavailable"
  | "provider_overloaded"
  | "rate_limited"
  | "server_error"
  | "protocol_error"
  | "schema_or_capability_mismatch"
  | "credential_failure"
  | "context_overflow"
  | "stream_interrupted"
  | "settlement_unknown"
  | "regional_or_residency_violation"
  | "billing_or_usage_drift"
  | "adapter_or_config_regression"
  | "cancelled"
  | "unknown";
```
```typescript
interface RecoveryContext {
  requestId: string;
  runId: string;
  sessionId: string;
  turnId: string;
  attemptId: string;
  scope: ScopeRef;
  surface: ProviderSurfaceRef;
  resolvedModel: ResolvedModel;
  routeSnapshot: RouteSnapshot;
  contractSnapshotId: string;
  policySnapshotId: string;
  egressSnapshotId: string;
  failureBudget: FailureBudget;
  checkpoint?: Checkpoint;
  streamCursor?: StreamCursor;
  sideEffectClass: "none" | "read" | "write" | "external" | "destructive";
  signal: AbortSignal;
}
```
```typescript
interface RecoveryPlan {
  planId: string;
  contextId: string;
  action: RecoveryAction;
  reasonCodes: string[];
  nextAttempts: PlannedAttempt[];
  drain?: DrainPlan;
  quarantine?: QuarantinePlan;
  checkpointAction?: CheckpointAction;
  reconciliationPlan?: ReconciliationPlan;
  verificationPlan: VerificationPlan;
  requiresApproval: boolean;
  expiresAt: string;
}
type RecoveryAction =
  | "complete"
  | "retry_transport"
  | "retry_agent"
  | "hedge"
  | "fallback"
  | "degraded_mode"
  | "pause"
  | "abort_stream"
  | "query_status"
  | "reconcile"
  | "drain_surface"
  | "quarantine_surface"
  | "rollback_config"
  | "rollback_credential"
  | "regional_failover"
  | "manual_intervention"
  | "terminal_failure";
```
```typescript
interface RecoveryReceipt {
  receiptId: string;
  kind: "provider_status" | "artifact_verify" | "delete" | "rotation" | "rollback" | "reconcile" | "canary" | "checkpoint";
  subjectRef: string;
  outcome: "confirmed" | "not_found" | "rejected" | "unknown" | "partial";
  observedAt: string;
  providerRequestId?: string;
  contentHash?: string;
  evidenceRefs: EvidenceRef[];
  nextAction?: string;
}
```
## TypeScript 接口
```typescript
interface ProviderRecoveryPort {
  classify(input: FailureClassificationInput): Promise<NormalizedProviderFailure>;
  plan(context: RecoveryContext, failure: NormalizedProviderFailure): Promise<RecoveryPlan>;
  execute(plan: RecoveryPlan): Promise<RecoveryExecution>;
  verify(input: VerificationInput): Promise<VerificationResult>;
  reconcile(input: ReconciliationInput): Promise<ReconciliationResult>;
}
```
```typescript
interface HealthPort {
  observe(spec: HealthProbeSpec): Promise<HealthObservation>;
  snapshot(key: HealthKey): Promise<HealthSnapshot>;
  record(observation: HealthObservation): Promise<void>;
  transition(key: HealthKey, next: HealthState, reason: string): Promise<HealthTransitionReceipt>;
}
```
```typescript
interface CircuitBreakerPort {
  state(key: CircuitKey): Promise<CircuitState>;
  allow(input: CircuitAdmission): Promise<CircuitDecision>;
  record(input: CircuitObservation): Promise<void>;
  open(input: CircuitOpenCommand): Promise<ControlReceipt>;
  halfOpen(input: CircuitProbeCommand): Promise<ControlReceipt>;
  close(input: CircuitCloseCommand): Promise<ControlReceipt>;
}
```
```typescript
interface BulkheadPort {
  reserve(input: BulkheadReservation): Promise<ResourceLease | undefined>;
  settle(lease: ResourceLease, outcome: ResourceSettlement): Promise<void>;
  drain(key: BulkheadKey, reason: string): Promise<ControlReceipt>;
  inspect(key: BulkheadKey): Promise<BulkheadSnapshot>;
}
```
```typescript
interface RetryController {
  decide(input: RetryDecisionInput): RetryDecision;
  nextDelay(input: BackoffInput): number;
  consumeBudget(input: BudgetConsumptionInput): Promise<BudgetReceipt>;
}
```
```typescript
interface InFlightRegistry {
  register(input: InFlightRequest): Promise<InFlightReceipt>;
  heartbeat(input: InFlightHeartbeat): Promise<void>;
  markAccepted(input: AcceptanceReceipt): Promise<void>;
  markTerminal(input: TerminalReceipt): Promise<void>;
  list(filter: InFlightFilter): Promise<InFlightRequest[]>;
  abort(input: AbortInFlightRequest): Promise<AbortReceipt>;
}
```
```typescript
interface ProviderStatusPort {
  query(input: ProviderStatusQuery): Promise<RecoveryReceipt>;
  queryArtifact(input: RemoteObjectQuery): Promise<RecoveryReceipt>;
  queryBatch(input: BatchStatusQuery): Promise<RecoveryReceipt>;
}
```
```typescript
interface RecoveryVerifier {
  verifySurface(input: SurfaceVerificationInput): Promise<VerificationResult>;
  verifyRun(input: RunVerificationInput): Promise<VerificationResult>;
  verifyArtifact(input: ArtifactVerificationInput): Promise<VerificationResult>;
  verifySettlement(input: SettlementVerificationInput): Promise<VerificationResult>;
}
```
这些接口是 provider-neutral port。具体 provider SDK、HTTP client、云签名和 status API 必须在 adapter/infrastructure 层实现。
## Attempt、Request Identity 与状态记录
### ID 分离
```text
requestId                 一次用户/系统请求语义
attemptId                 provider/model/deployment 的一次尝试
providerRequestId         provider 返回或生成的请求身份
hedgeGroupId              一组可能重复的并发尝试
idempotencyKey            业务副作用幂等身份
toolCallId                模型提出的调用身份
toolExecutionId           工具执行身份
artifactTransferId        上传/下载传输身份
checkpointId              可恢复状态身份
recoveryPlanId            恢复计划身份
```
`attemptId` 不能作为 `idempotencyKey`，因为 retry、fallback 和 hedge 必须能够被识别为不同尝试，而相同业务动作可能需要共享幂等键。
### AttemptRecord
```typescript
interface AttemptRecord {
  attemptId: string;
  requestId: string;
  runId: string;
  turnId: string;
  ordinal: number;
  routeSnapshotId: string;
  surface: ProviderSurfaceRef;
  requestHash: string;
  idempotencyKey?: string;
  hedgeGroupId?: string;
  phase: "created" | "compiled" | "sent" | "streaming" | "terminal" | "unknown";
  outcome: "not_sent" | "accepted" | "completed" | "failed" | "cancelled" | "unknown";
  failure?: NormalizedProviderFailure;
  usageRef?: string;
  rawReceiptRef?: string;
  checkpointRef?: string;
  startedAt: string;
  terminalAt?: string;
}
```
### Commit 顺序
1. 生成并持久化 `AttemptStarted`。
2. 冻结 request、route、contract、policy、egress、credential class 和 budget snapshot。
3. 注册 in-flight request，再发送 provider request。
4. 记录 acceptance 或 `unknown` evidence。
5. 归一化 stream/response，保存 durable terminal 或 failure。
6. 结算 usage、cost、artifact、checkpoint 和 delivery。
7. 最后推进 `Turn`、`Step` 或 `Run` 状态。
若在步骤 3–5 之间崩溃，恢复器必须从 in-flight registry、provider status、event log 和 side-effect ledger 推断候选，而不是重建一个“从未执行”的 attempt。
## Recovery State Machine
```text
Healthy
  -> Suspected
  -> Degraded
  -> Containing
  -> Draining
  -> Quarantined
  -> Recovering
  -> Verifying
  -> Restored | PartiallyRestored | Failed
```
单次 run/attempt 状态：
```text
Created
  -> Prepared
  -> Sent
  -> Accepted | NotAccepted | Unknown
  -> Streaming
  -> Completed | Interrupted | Failed | Cancelled | Unknown
  -> Querying
  -> Reconciled | RetryEligible | FallbackEligible | Manual
  -> Settling
  -> Settled | SettlementUnknown
```
### 状态转移约束
- `Healthy -> Degraded` 需要 observation 或聚合信号；不能只由人工状态文本触发。
- `Degraded -> Containing` 必须产生 scope、reason、TTL、operator 和 audit。
- `Containing -> Draining` 只停止新 admission，不等同于杀死已有请求。
- `Draining -> Quarantined` 需要处理 in-flight、queue、credential、artifact 和 remote object。
- `Recovering -> Verifying` 前必须完成配置、route、credential、capacity 和 semantic preflight。
- `Verifying -> Restored` 需要多层 verification；单个 liveness probe 不足。
- `Unknown` 只能通过 status query、receipt、reconciliation 或人工结论离开。
- `Failed` 与 `Unknown` 的数据处理路径不同：前者可在安全条件下 retry，后者先查询事实。
## Circuit Breaker
### 维度
Breaker key 至少支持：
```text
provider + apiFamily + model/deployment + region + credentialClass + failureClass
```
高风险 capability 可以拥有独立 breaker，例如 tool calling、structured output、artifact upload 和 remote delete。
### 状态
```text
Closed      正常接收，按窗口记录失败
Open        拒绝新 attempt，返回稳定 recovery hint
HalfOpen    只允许受限 probe/canary
Draining    不接新任务，等待 in-flight settle
Quarantined 不允许生产流量，保留诊断/回放
```
### 打开条件
Breaker 不应使用单一错误计数；应结合：
- 连续或窗口化错误率与基线偏差。
- timeout、TTFE、EOF、sequence gap 和 unknown 比例。
- retry amplification 与 queue backlog。
- 多 tenant、多 model 或多 region 的共同失败。
- semantic conformance failure。
- security/privacy violation；此类可直接 open/quarantine。
### 半开放策略
- 只允许合成、低敏、无副作用 probe。
- 固定并发和预算，不允许模型自由生成工具调用。
- 对每种高价值 capability 至少有一项 semantic 验证。
- 记录 probe 的 adapter、catalog、config、credential class 和 region。
- probe 失败回到 Open；连续多个窗口成功才进入 Restored。
## Bulkhead、Admission 与 Noisy Neighbor
### Bulkhead 维度
- tenant、organization、workspace。
- provider、api family、model class、deployment、region。
- interactive、background、subagent、recovery、probe。
- read、write、external、destructive side effect class。
- stream、artifact、status-query、reconciliation。
- credential class、worker pool、queue partition。
### Admission 顺序
```text
Scope valid
  -> Policy/Egress valid
  -> Circuit allow
  -> Failure budget available
  -> Tenant quota available
  -> Bulkhead capacity available
  -> Provider capability valid
  -> Queue/worker capacity available
  -> Send attempt
```
如果 recovery 自身消耗了大部分 provider capacity，应优先暂停低优先级 background、shadow、canary 和非关键 batch，不能让用户主路径被恢复风暴饿死。
### Bulkhead 释放
- attempt terminal、abort settle 或 lease fence 后释放。
- unknown 不等于资源已释放；需要 status query 或明确 provider connection settle。
- provider 断流后连接池、stream slot、artifact transfer slot 和 token budget 要分别结算。
- 过期 lease 由 fencing token 阻止旧 worker 再提交结果。
## Retry、Backoff 与 Jitter
### Retry 层次
| 层次 | 适用 | 不适用 |
|---|---|---|
| transport retry | 未建立连接、明确未发送 | 已发送且副作用未知 |
| provider retry | provider 明确 transient、无副作用或可幂等 | schema、credential、policy、region 错误 |
| agent retry | 重新编译 context、修复可验证 request | 盲目重放写操作 |
| tool retry | Tool Runtime 业务语义允许 | provider response 解析未完成 |
| queue retry | worker crash、lease expiry、暂时不可运行 | 已有 unknown 副作用无查询 |
| workflow retry | step policy 允许且 checkpoint 可复用 | 不可补偿的 destructive action |
### Backoff
默认使用指数退避并加入 jitter：
```text
base = min(maxDelay, initialDelay * 2^attempt)
serverHint = retry-after if present
delay = bounded(max(base, serverHint)) + jitter
```
jitter 可以是 full、equal 或 decorrelated，但必须使用 deterministic clock/random 进行测试。恢复系统不能让所有 worker 在同一时刻重试。
### Retry Decision
```typescript
interface RetryDecision {
  allowed: boolean;
  layer: "transport" | "provider" | "agent" | "queue" | "workflow";
  delayMs?: number;
  reasonCodes: string[];
  consumes: BudgetConsumption;
  createsNewAttempt: boolean;
  requiresStatusQuery: boolean;
  idempotencyMode: "same_key" | "new_key" | "none";
}
```
### 禁止条件
- provider 已返回 structured output、tool call 或 artifact receipt，但本地提交失败；先重建本地状态。
- request 可能成功且无 status query；进入 unknown。
- error 是 schema、policy、credential、residency 或 capability mismatch。
- failure budget、tenant quota、cost cap 或 privacy gate 不足。
- retry 会跨越不允许的 region/provider 或改变 retention/training 语义。
## Hedging 与重复请求控制
### 适用条件
Hedging 只适用于：
- 低副作用或纯读取模型请求。
- 明确可安全取消 loser attempt。
- 业务幂等键和 provider dedup 机制可用，或不存在外部副作用。
- hedge budget、cost budget、provider quota 和 tenant policy 明确允许。
- latency tail 足以证明 hedging 的收益，而不是用来掩盖持续 outage。
### Hedge Plan
```typescript
interface HedgePlan {
  hedgeGroupId: string;
  primaryAttemptId: string;
  delayedAlternatives: Array<{ attemptId: string; delayMs: number; surface: ProviderSurfaceRef }>;
  maxConcurrent: number;
  cancelLosers: boolean;
  winnerRule: "first_terminal" | "first_valid" | "quality_ranked";
  budgetId: string;
}
```
### Winner 规则
- `first_terminal` 仅适用于响应完整性可验证的纯读取请求。
- `first_valid` 需要 schema、tool call completeness、finish reason 和 usage 证据。
- `quality_ranked` 适合 shadow/canary 或离线评估，不能直接用于有副作用的主路径。
- loser 取消后仍要记录其 provider acceptance、usage 和可能的 partial result。
### 禁止 hedging
- provider-side 写操作、上传、删除、批处理提交、支付、部署或不可逆工具。
- 未知结果未被 query/reconcile 的 attempt。
- 受限 region、regulated data 或 provider contract 不允许 duplicate egress 的请求。
- circuit open、quota 紧张或 recovery storm 期间。
## Fallback、Degraded Mode 与能力保持
### Fallback 不是任意换模型
fallback 必须重新执行：
```text
ModelRef resolution
-> capability matching
-> schema projection
-> Policy/Egress/Residency
-> Credential scope
-> Quota/Budget
-> Health/Circuit
-> Tool/Structured/Multimodal contract
-> RouteSnapshot
```
### Degraded Mode
```typescript
type DegradedMode =
  | "text_only"
  | "non_streaming"
  | "no_tools"
  | "read_only_tools"
  | "structured_relaxed_with_local_validation"
  | "artifact_reference_only"
  | "summary_only"
  | "manual_review"
  | "queue_until_recovered";
```
每个 degraded mode 必须声明：
- 丢失的能力和对用户/模型的可见提示。
- 是否仍允许 tool、artifact、memory、external side effect。
- output schema、finish reason、usage 和 delivery 的变化。
- 是否需要 approval、confirmation 或新的 run。
- 对上下文、提示和评测的影响。
### Fallback 失败
如果没有满足全部硬约束的 fallback：
- 对 interactive run 返回 typed `provider_unavailable` 或 `provider_degraded`。
- 对 workflow run 写 checkpoint 并进入 waiting/retryable。
- 对 background job 延迟排队或 DLQ，保留 recovery candidate。
- 对高风险动作进入 manual approval/unknown，不得伪造成功。
## Routing Drain、Quarantine 与流量止损
### Drain
1. 更新 control-plane `AdmissionPolicy`，阻止新 attempt。
2. 停止 shadow、canary、hedge 和低优先级 background。
3. 标记 surface 为 `draining`，设置 TTL 和 operator reason。
4. 允许安全的 in-flight 请求到 terminal；对超时请求执行 abort 或 unknown。
5. 释放 bulkhead、queue reservation、credential lease 和 stream slot。
6. 生成 `RouteDrainStarted`、`InFlightSettled`、`RouteDrainCompleted` durable events。
### Quarantine
Quarantine 适用于：
- data exposure、region violation、credential compromise。
- capability/schema drift 无法解释。
- adapter/config regression。
- artifact remote object 状态不可控。
- recovery verification 结果不一致。
Quarantine 必须带 scope、reason、TTL、解除条件、owner、approval、evidenceRefs 和回滚命令。Quarantine 不能删除证据，不能阻止 forensic read 和受控 status query。
### Quarantine 与 Route
Routing 只能消费 quarantine snapshot，不能猜测 operator 意图。已 quarantine 的 surface 不应出现在 primary、fallback、hedge、shadow 或 canary 候选中，除非专门的 forensic/recovery route 明确声明。
## Idempotency、Dedup 与 Unknown Outcome
### 三层幂等
1. **协议层**：provider 支持的 idempotency header/key。
2. **平台层**：`requestHash`、`attemptId`、`idempotencyKey`、`executionRecord` 和 inbox/outbox。
3. **业务层**：目标资源版本、状态查询、业务 operation ID、side-effect receipt 和 compensation。
### Dedup 记录
```typescript
interface IdempotencyRecord {
  key: string;
  scope: ScopeRef;
  operation: string;
  requestHash: string;
  firstAttemptId: string;
  status: "reserved" | "in_progress" | "completed" | "failed" | "unknown" | "expired";
  resultRef?: string;
  receiptRefs: string[];
  expiresAt?: string;
}
```
相同 key 但 request hash 不同必须返回 conflict；不能把 dedup 当作“请求一定完成”的证明。
### Unknown 处理表
| 状态 | 允许动作 | 禁止动作 |
|---|---|---|
| 未发送 | 安全 retry | 声称 provider 已处理 |
| 已发送未 ack | status query、同 key query | 换 key 盲重发 |
| remote upload unknown | query hash/size/list | 直接再次上传同内容 |
| tool call unknown | 查询业务状态、人工审批 | 自动再次执行 destructive action |
| stream unknown | 保存 partial、abort、new attempt with new turn | 把 partial 当 final |
| delete unknown | provider delete status、保留 hold | 声称已删除 |
| usage unknown | provisional ledger、账单对账 | 释放硬预算到无限 |
## In-flight Requests 与资源收敛
### 注册时机
在发送前注册 `InFlightRequest`，包含：
- attempt、request、run、tenant、surface、side-effect class。
- request hash、idempotency key、provider request id（可后补）。
- connection、stream、artifact transfer、budget 和 lease references。
- deadline、abort signal、last heartbeat、last observed sequence。
### Drain 行为
- 新 request 直接拒绝或路由到新 surface。
- 已 `not_sent` 的 request 取消并释放 reservation。
- 已 `sent` 未 acceptance 的 request 查询或标记 unknown。
- 已 streaming 的 request 尝试 graceful abort；超过 grace period 转 unknown。
- 已 terminal 的 request 进入 normal settlement，不因 breaker open 被回滚。
- 所有旧 worker 写入必须携带 fencing token。
### 资源清理
资源清理是分阶段的：
```text
abort signal
  -> close stream
  -> release connection slot
  -> settle budget/quota
  -> persist partial/unknown
  -> reconcile remote state
  -> remove temp resources
```
不能在未保存 partial state 前先删除临时 artifact 或 stream buffer。
## Stream Resume、Abort 与终止语义
### 默认原则
多数模型 stream 不应被假设支持从任意 token resume。Provider Runtime 必须显式声明 `streamResume` capability；不支持时只能保存 partial、终止当前 attempt，并决定 new turn、fallback 或 manual。
### Stream Cursor
```typescript
interface StreamCursor {
  attemptId: string;
  providerRequestId?: string;
  providerSequence?: string | number;
  canonicalSequence: number;
  contentHash: string;
  completedParts: string[];
  openToolCalls: string[];
  lastUsage?: Usage;
  lastObservedAt: string;
}
```
### Abort 类型
- `user_cancelled`：用户控制命令，写 RunCancelled。
- `budget_exhausted`：预算控制，写 typed budget error。
- `surface_draining`：恢复控制，写 drain reason。
- `security_revoke`：安全撤销，立即阻断新外发并按策略终止。
- `provider_timeout`：provider/transport timeout，可能 unknown。
- `consumer_disconnect`：Host 断线，不默认 cancel；Run 可后台继续。
### Tool Call 完整性
只在 `ToolCallReady` 或明确 completion boundary 后执行工具。若 stream 在参数中断：
- 保存原始 partial arguments 或 artifact reference。
- 标记 `incomplete`，不执行。
- 记录 provider sequence gap/abort evidence。
- 若可安全重采样，创建新 attempt；否则交给用户或 workflow recovery。
## Queue Replay、Workflow Checkpoint 与恢复
### Queue Replay
queue replay 只能基于 job state、lease、attempt、checkpoint 和 side-effect record。不可把 `JobVisible` 当作未执行。
```text
expired lease
  -> inspect execution record
  -> inspect provider acceptance
  -> inspect checkpoint
  -> query/reconcile unknown
  -> retry same idempotency key OR pause/manual
```
### Workflow Checkpoint
Checkpoint 至少包括：
- workflow version、run snapshot、step cursor、dependency results。
- provider route/contract/policy/egress snapshots。
- last durable event、pending approval、attempt state。
- tool idempotency records、artifact refs、side-effect receipts。
- context hash、prompt compiler version、toolset snapshot、usage/budget。
- recovery phase、unknown subjects 和 next action。
```typescript
interface RecoveryCheckpoint extends Checkpoint {
  workflowVersion?: string;
  stepCursor?: string;
  lastSafeBoundary: "before_send" | "after_acceptance" | "after_terminal" | "after_settlement";
  pendingUnknowns: UnknownSubject[];
  providerState: ProviderRecoveryState;
  artifactManifestHash?: string;
  usageLedgerVersion?: string;
}
```
### Resume 规则
- 从 `after_settlement` 恢复：推进 workflow，不重发 provider request。
- 从 `after_terminal` 恢复：补写 usage/artifact/delivery settlement，不重采样。
- 从 `after_acceptance` 恢复：先 query/reconcile，不直接 retry。
- 从 `before_send` 恢复：可在预算、policy 和 route 仍有效时创建新 attempt。
- checkpoint 不完整：进入 `manual_intervention` 或 controlled replay。
## Artifact Consistency 与大对象恢复
### Artifact 闭环
```text
begin upload
  -> local hash/size manifest
  -> provider upload attempt
  -> remote receipt or unknown
  -> provider status/hash query
  -> verify local/remote consistency
  -> commit ArtifactRef/LineageEdge
```
### 一致性条件
必须区分：
- 本地 blob 已完成与 provider remote object 已完成。
- `ArtifactRef` 已持久化与用户可访问 view 已发布。
- preview/sanitized/summary view 完成与 raw 内容完成。
- remote object 已上传与 provider request 实际引用成功。
- provider-side delete accepted 与 delete confirmed。
### 恢复动作
- hash/size 一致：补写 missing receipt 或本地 manifest。
- remote object 存在但本地未知：创建受控 reference，重新做 scope/egress 校验。
- 本地存在、远端不存在：可按原幂等 key 重试上传，不能换业务身份。
- hash 不一致：quarantine，禁止 provider 或用户继续读取。
- 删除 unknown：保留 tombstone、legal hold 和 remote status query。
- provider artifact API 不可用：停止新的敏感上传，允许本地 artifact-only degraded mode。
## Credential/Config Rollback
### Credential 恢复
credential 变化必须版本化：
```text
CredentialClass + leaseId + rotationEpoch + scope + destination + expiry
```
检测到泄露、错绑、过宽或集中 401 时：
1. 停止新 lease。
2. 对目标 credential class 进行 revoke/quarantine。
3. 保全 audit、request hash、surface 和 exposure evidence，不复制 secret。
4. 生成新 credential version，执行最小 scope 验证。
5. 以 synthetic readiness 和 semantic probe 验证。
6. 逐步恢复 primary/fallback，观察 settlement 和 privacy signals。
7. 对旧 attempt 做 unknown/egress/usage reconciliation。
### Config Rollback
配置快照必须包含：
- provider/API family/model/deployment/region。
- timeout、retry、hedge、fallback、breaker、bulkhead 参数。
- adapter、projection、schema、catalog、policy、egress 和 credential references。
- probe、SLO、budget、runbook 和 rollout versions。
rollback 不重写已经完成的 attempt；新 attempt 使用旧版本 snapshot。运行中的敏感 egress 若必须撤销，由 Security/Policy 控制中断或 quarantine。
### Rollback 验证
- 配置 schema 与旧 adapter compatible。
- 旧 snapshot 的 route/contract 可解析。
- fake/conformance fixture 通过。
- synthetic probe、tool fixture、structured fixture 和 usage fixture 通过。
- old config 不重新启用已撤销 credential 或不合规 region。
## Regional Failover 与 Residency Guard
### Failover 前置条件
```text
candidate region allowed
  AND provider contract valid
  AND credential scope valid
  AND data residency compatible
  AND retention/training semantics compatible
  AND model capability compatible
  AND artifact/backup path compatible
  AND quota/capacity available
```
任何条件 unknown 都不能自动 failover 敏感数据；可以选择 summary-only、artifact-only、queue-until-recovered 或 manual review。
### Failover 语义
- 同 region deployment failover：通常可新建 attempt，但仍需 capability/credential 检查。
- 跨 region failover：必须新建 `EgressSnapshot`、`RouteSnapshot` 和 `Attempt`。
- 跨 provider failover：重新做 Provider Security Contract、schema projection、usage/cost 和 data lineage。
- 高副作用 workflow：默认 pause，等原 provider outcome reconciliation 后再推进。
- provider-side remote object：region failover 不能假设对象可见或可复制。
### Region 故障恢复
先恢复 residency-safe traffic，再恢复低敏 interactive，再恢复 background、shadow、canary 和高风险 external actions。每一层有独立 verification 和 rollback。
## Data Loss、Duplication 与 Settlement Semantics
### 数据丢失等级
- `no_loss_confirmed`：durable event、artifact、usage、business receipt 全部可验证。
- `partial_output_loss`：模型 partial token 或 ephemeral progress 丢失，但 semantic outcome 可重建。
- `context_loss`：ContextPlan/Prompt raw 不可恢复，但 hash/summary 存在；需评估 replay 可信度。
- `artifact_loss`：本地或远端大对象缺失；不得继续引用。
- `usage_loss`：provider usage 暂缺；进入 provisional settlement。
- `business_fact_loss`：外部业务 receipt 缺失；必须 manual/compensation。
- `audit_loss`：durable evidence 缺失；属于平台事故，不可用 debug log 补齐。
### 重复语义
- `duplicate_attempt`：同一 request 产生多次 provider attempt。
- `duplicate_delivery`：同一结果多次交付 Host；delivery 层去重。
- `duplicate_tool_execution`：工具副作用执行多次；必须由业务 receipt/compensation 判定影响。
- `duplicate_artifact`：内容相同但版本/引用不同；可通过 content hash 合并视图，但不覆盖审计。
- `duplicate_usage`：多个 attempt usage 被错误汇总；UsageLedger 需按 attempt 和 settlement status 对账。
### Settlement 状态
```text
provisional -> observed -> reconciled
                    \\-> disputed -> manual
```
不能因 provider 没有返回 usage 就把 cost 记为零；也不能因网络异常把 unknown attempt 从 chargeback 中删除。
## Recovery Phases
### Phase 0：Prepare
- 为每个 surface 建立 route、contract、policy、egress、credential、health 和 budget snapshot。
- 注册 in-flight、idempotency、checkpoint 和 artifact manifest。
- 预置 synthetic probe、status query、runbook 和 escalation 联系方式。
### Phase 1：Detect
- 聚合 Runtime、Health、Routing、Queue、Workflow、Usage、Artifact、Lineage、Security 和 tenant signals。
- 计算 baseline deviation、confidence、scope 和 severity。
- 生成 `RecoveryCandidate` 或 `IncidentCandidate`。
### Phase 2：Classify
- 区分 request error、provider incident、adapter regression、data exposure 和 unknown。
- 标记 side-effect class、可能已接受、是否需要 query、是否允许 retry。
- 生成第一版 blast radius 和 failure budget consumption。
### Phase 3：Contain
- open circuit、收紧 bulkhead、停止 hedge/shadow/canary。
- drain surface，暂停新 queue jobs，必要时 quarantine credential、artifact 或 remote object。
- 对敏感数据执行 egress stop；对高风险动作暂停 workflow。
### Phase 4：Preserve
- durable 写入 failure、timeline、route/config/credential versions、raw refs、partial stream、checkpoint 和 evidence。
- 保留未知状态，不删除本地或远端引用。
- 生成 incident handoff packet。
### Phase 5：Recover
- 选择 retry、status query、fallback、degraded、rollback、regional failover、queue replay 或 manual。
- 新 attempt 重新通过 policy、capability、egress、quota 和 budget gates。
- 逐步恢复低风险到高风险流量。
### Phase 6：Reconcile
- 对 provider request、tool/business receipt、artifact、usage、billing、lineage、delete 和 delivery 做对账。
- 处理 duplicate、partial、missing、unknown 和 conflicting facts。
- 形成 compensation 或 manual action。
### Phase 7：Verify
- liveness/readiness 之外，验证 stream、tool、structured、usage、artifact、region、credential 和 recovery SLO。
- 检查 circuit、bulkhead、queue、checkpoint、projector 和 audit 是否正常。
- 通过 canary window 后恢复 route state。
### Phase 8：Learn
- 生成 postmortem、回归 fixture、conformance case、schema change、routing rule、runbook 和 game day action。
- 更新 failure budget、SLO、alert threshold 和 owner。
## Recovery Decision Flow
```text
receive failure/health signal
  -> locate ProviderSurface and Scope
  -> determine request phase and acceptance
  -> classify failure and confidence
  -> check security/privacy/region impact
  -> consume failure budget
  -> check circuit/bulkhead/admission
  -> if unknown: query provider/remote object/business receipt
  -> if safe retry: schedule bounded retry with same/new idempotency key
  -> else if compatible: plan fallback or degraded mode
  -> else pause/drain/quarantine/manual
  -> persist checkpoint and durable events
  -> settle usage/artifact/delivery
  -> verify and reconcile
```
### 决策表
| 条件 | 首选动作 | 后续验证 |
|---|---|---|
| 未发送、连接失败、无副作用 | transport retry | acceptance + terminal |
| 已发送、无 ack、读请求 | status/query 或同 key retry | provider receipt + result |
| 已发送、写请求、无 ack | unknown + query | business receipt |
| 429、retry-after 明确 | delayed retry / route change | error rate + quota |
| capability drift | quarantine surface | conformance + canary |
| credential compromise | revoke + rotate | scoped probe + audit |
| region violation | egress stop + quarantine | residency evidence |
| stream partial tool args | abort + checkpoint | no tool execution + new attempt |
| artifact hash mismatch | quarantine artifact | hash/scan/remote query |
| checkpoint missing | pause/manual | reconstruct from event log |
| provider outage但安全 fallback 存在 | fallback | capability/egress/usage |
## Recovery Verification 与 Reconciliation
### Verification 层次
1. **Control-plane verification**：circuit、bulkhead、route、credential、config、catalog 和 policy 状态。
2. **Data-plane verification**：连接、request acceptance、TTFE、stream terminal、tool/structured 结果。
3. **State verification**：event sequence、session CAS、checkpoint、queue lease、projector lag。
4. **Artifact verification**：hash、size、MIME、scan、view、ACL、TTL 和 remote receipt。
5. **Governance verification**：lineage、purpose、scope、residency、retention、deletion 和 DSAR。
6. **Business verification**：业务状态查询、版本、receipt、compensation 和用户可见结果。
### Reconciliation 输入
```typescript
interface ReconciliationInput {
  subject: "attempt" | "stream" | "artifact" | "usage" | "tool" | "workflow" | "delete" | "route";
  localFacts: EvidenceRef[];
  providerFacts?: EvidenceRef[];
  businessFacts?: EvidenceRef[];
  timeWindow: TimeWindow;
  scope: ScopeRef;
  idempotencyKey?: string;
}
```
### Reconciliation 结果
```typescript
interface ReconciliationResult {
  status: "matched" | "partial" | "conflict" | "missing" | "unknown" | "manual";
  canonicalOutcome?: "completed" | "failed" | "cancelled" | "unknown";
  duplicateCount: number;
  dataLoss: "none" | "partial" | "material" | "unknown";
  usageSettlement: "exact" | "estimated" | "provisional" | "disputed";
  actions: ReconciliationAction[];
  evidenceRefs: EvidenceRef[];
}
```
### 影响分析
Provider Recovery 必须把 `ProviderSurface` 关联到 Data Lineage：
```text
provider request view
  -> provider response/tool result
  -> session/event/checkpoint
  -> artifact/memory/cache/usage
  -> workflow/business side effect
```
发生 data exposure、region violation、schema drift 或 capability drift 时，影响分析不能只查 trace；应沿 immutable lineage edges 查找所有 materialization、consumer、backup、remote object 和 deletion obligations。
## Incident Handoff 与 Recovery Runbook
### Handoff Packet
```typescript
interface RecoveryHandoffPacket {
  incidentId?: string;
  surface: ProviderSurfaceRef;
  scopeSummary: ScopeSummary;
  firstObservedAt: string;
  lastObservedAt: string;
  primaryFailure: NormalizedProviderFailure;
  affectedAttempts: string[];
  inFlight: InFlightSummary;
  unknownSubjects: UnknownSubject[];
  containmentActions: ControlReceipt[];
  snapshots: {
    route: string;
    contract: string;
    policy: string;
    egress: string;
    credentialClass: string;
    config: string;
    catalog: string;
  };
  checkpoints: string[];
  artifactRefs: string[];
  usageLedgerRefs: string[];
  nextDecision: string;
  owner: string;
  expiresAt: string;
}
```
### Runbook：Provider Surface Outage
1. 确认 surface、region、model/deployment、credential class 和时间窗口。
2. 检查是否为单 request、单 tenant、单 adapter 或跨 tenant failure。
3. 对照 health baseline、retry amplification、queue backlog 和 circuit evidence。
4. 打开对应 circuit，停止 shadow/hedge/canary，设置 drain TTL。
5. 列出 in-flight，区分 not-sent、accepted、streaming、terminal 和 unknown。
6. 对未知写请求执行 provider/business status query；禁止换 key 重传。
7. 评估安全 fallback；重新做 egress、residency、capability、credential 和 quota preflight。
8. 对 interactive 请求选择 fallback/degraded；对 workflow/background 写 checkpoint 并暂停。
9. 保存 partial stream、artifact manifest、usage provisional ledger 和 recovery events。
10. 运行 synthetic readiness、semantic tool/structured、stream 和 settlement probes。
11. 小比例 canary 恢复；观察 error、unknown、duplicate、latency 和 usage。
12. 通过 verification window 后逐步解除 drain；否则回到 quarantine。
13. 完成 reconciliation、tenant communication、postmortem 和 regression fixture。
### Runbook：Credential/Config Regression
1. 停止新 lease 或配置 rollout。
2. 确认影响版本、surface、tenant 和 region。
3. 保全 snapshot/hash，不打印 secret。
4. 关闭或隔离坏版本，执行版本化 rollback。
5. 对 credential 执行 revoke/rotate，验证 scope 和 expiry。
6. 运行 conformance、projection、semantic probe 和 usage test。
7. 逐步恢复读路径，再恢复写路径。
8. 检查旧 attempt 的 egress、unknown、usage、artifact 和 lineage。
9. 将缺陷写入 release gate、schema registry 或 adapter quarantine 规则。
### Runbook：Artifact/Remote Object Unknown
1. 固定 local ArtifactRef、content hash、size、view 和 scope。
2. 查询 provider remote object、upload session、delete state 或 batch status。
3. 若对象存在，重新校验 region、tenant、purpose、retention 和 access。
4. 若 hash mismatch，quarantine 并阻止继续消费。
5. 若无法查询，保留 tombstone/hold，不宣称删除或失败。
6. 对 provider 恢复后运行 reconciliation 和 deletion proof。
7. 更新 Data Lineage、Data Quality 和 Privacy incident 证据。
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### Model
Model Runtime 提供 `ResolvedModel`、capabilities、raw receipt、stream、usage 和 normalized error。Recovery 不直接调用 SDK；只通过 ModelPort/Provider Runtime port 创建新 attempt。
### Prompt
Prompt Compiler 必须能根据 degraded mode 编译不同的能力说明，例如 no-tools、text-only、summary-only。Prompt 不能声明“已恢复”或“请求已成功”；事实来自 event/state/receipt。
### Context
Context Runtime 负责 overflow、compaction、artifact offload 和 freshness。Recovery 可以请求新的 `ContextPlan`，但必须保存 source hash、resource versions、egress view 和 compaction entry。恢复不得静默删除关键工具结果或 policy。
### Tool
Tool Runtime 负责 schema、业务校验、policy、approval、sandbox、idempotency 和 side-effect receipt。Provider Recovery 只能决定 tool call 是否完整、是否应暂停或等待 provider result；不能直接执行工具。
### State/Session/Replay
所有 attempt、failure、retry、fallback、checkpoint、unknown、reconcile 和 verification 都应成为 durable semantic entry 或 canonical event。Session Replay 使用 recorded input 或 quarantine runtime，不能把 recovery replay 当作生产副作用。
### Policy/Security/Privacy
每个恢复动作重新消费 immutable `PolicySnapshot`、`EgressSnapshot`、`ContractSnapshot` 和 credential scope。安全撤销、DSAR、residency 变化可阻断已有 attempt；普通配置变化不能静默重写 run。
### Harness
Harness 装配 `RecoveryContext`，监督 structured concurrency、预算、取消、queue/workflow、delivery 和 settlement。RunSupervisor 必须能在 recovery action 期间继续接收用户 cancel、approval、resume 和 status query。
### Event/Observability
至少发出：
```text
ProviderFailureClassified
HealthObservationRecorded
FailureBudgetConsumed
CircuitOpened / CircuitHalfOpened / CircuitClosed
BulkheadDraining
RouteQuarantined
RetryScheduled
HedgeStarted / HedgeCancelled
FallbackSelected
StreamAborted
RecoveryCheckpointWritten
UnknownOutcomeDetected
StatusQueryCompleted
ArtifactReconciled
CredentialRotated
RegionalFailoverSelected
RecoveryVerified
RecoveryFailed
IncidentHandoffCreated
```
## 安全、隐私与多租户
### 安全边界
- provider response、status payload、error message、artifact metadata 和 model output 都是不可信输入。
- recovery operator command 必须带 principal、scope、reason、TTL、approval 和 audit。
- break-glass 不能扩大 provider allowlist、region、credential scope 或 data class；只能在显式、短时、可回收策略内操作。
- quarantine 期间应保留 evidence read，但阻止普通模型 context、tool execution、provider egress 和 user export。
### 隐私与最小化
- recovery logs 保存 code、class、hash、size、status、timing 和 refs，默认不保存完整 prompt、secret、hidden reasoning 或 regulated payload。
- status query 使用最小必要 identifier 和短期 credential lease。
- artifact、stream partial 和 provider raw payload 进入 ArtifactStore 的受控 view，带 sensitivity、retention、TTL 和 redaction。
- incident 影响分析依赖 Data Lineage 的 source/consumer/region/purpose edges，不把日志副本自动视为授权。
### 多租户
- circuit/bulkhead 可共享 control plane，但 tenant quota、credential、cache、queue、event、artifact 和 trace 必须隔离。
- 一个 tenant 的 provider 失败不应自动熔断其他 tenant，除非 failure evidence 指向 shared provider surface 或安全风险。
- fallback 不能从 tenant scope 读取其他租户 healthy route、credential 或 prompt。
- queue replay、checkpoint resume、status query 和 reconciliation 都要重新检查 scope 和 authorization。
## 可观测性、Dashboard 与 Alerts
### 指标维度
避免无限 cardinality；按 provider、api family、model class、deployment class、region、credential class、tenant class、failure class、route kind 和 sensitivity class 聚合。原始 IDs 进入 trace/audit，不直接作为高基数 metric label。
### 核心指标
- `provider_attempt_total{outcome,failure_class}`。
- `provider_unknown_total{phase,side_effect_class}`。
- `provider_recovery_action_total{action}`。
- `retry_amplification_ratio`。
- `hedge_duplicate_ratio`。
- `circuit_open_seconds` 与 open transitions。
- `bulkhead_saturation`、queue backlog、lease expiry。
- `time_to_detect`、`time_to_contain`、`time_to_recover`。
- stream sequence gap、partial tool call rate、abort settle latency。
- artifact remote mismatch、delete unknown、reconciliation conflict。
- provisional usage age、billing mismatch、duplicate charge candidate。
- fallback policy-compliant rate、region-safe failover rate。
- checkpoint recovery success、RPO violation、RTO violation。
### Dashboard 分层
1. Executive/SLO：可用性、RTO/RPO、unknown、duplicate、data exposure。
2. Surface：provider/api/model/deployment/region health、breaker、capacity、latency。
3. Recovery：phase、action、budget、queue、checkpoint、reconciliation。
4. Security/Privacy：credential、egress、region、quarantine、lineage、deletion。
5. Debug：attempt timeline、event sequence、raw refs、snapshot hashes、artifact manifest。
### Alerts
- 高置信 shared surface outage。
- unknown outcome 超过时间预算。
- retry amplification 或 hedge cost 激增。
- recovery action 反复失败或 circuit flap。
- credential failure 跨 tenant 扩散。
- region/egress mismatch。
- artifact/hash/delete reconciliation conflict。
- checkpoint recovery RTO/RPO 违约。
- usage/billing settlement 长时间 provisional。
- semantic probe 失败但 liveness 仍成功。
告警是投影；事件、状态、证据和 audit 才是事实来源。
## 测试策略与 Evaluation
### 单元测试
覆盖 failure classifier、retryability、backoff/jitter、budget consumption、breaker transitions、bulkhead admission、idempotency conflict、stream cursor、state transition 和 verification quorum。
### Contract/Conformance 测试
对每个 provider/API family 验证：
- raw error 到 normalized failure 的分类。
- request acceptance、provider request id、terminal 和 unknown 语义。
- stream sequence、tool call 完整边界、usage、finish reason、安全事件。
- status query、artifact、delete、batch、credential 和 region metadata。
- capability drift、unknown event、schema version 和 adapter rollback。
### 组件测试
使用 `FakeProvider`、`ScriptedModelStream`、`FakeCredentials`、`InMemorySessionRepository`、`DeterministicClock`、`CrashInjector`、`EventRecorder` 和 `ReplayRunner` 验证 recovery path。不要依赖真实付费 endpoint。
### 场景矩阵
| 场景 | 断点 | 预期 |
|---|---|---|
| connect timeout before send | send 前 | bounded transport retry |
| reset after body sent | send 后 | unknown/query，不盲重放 |
| 429 storm | admission | backoff、bulkhead、fallback |
| stream EOF before tool complete | stream | partial persist、no execute |
| tool result committed but next sample fails | turn boundary | checkpoint 后 fallback |
| worker crash with accepted provider request | queue | query/reconcile |
| artifact upload ack lost | remote object | hash/status query |
| bad config rollout | control plane | drain、rollback、canary |
| credential revoked mid-run | security | stop new egress、settle/unknown |
| region endpoint mismatch | egress | quarantine、no failover until safe |
| usage missing | settlement | provisional ledger、reconcile |
| provider semantic drift | conformance | surface quarantine |
| cross-tenant recovery request | scope | deny、不泄露存在性 |
### Evaluation 断言
- 轨迹断言：正确 recovery action 顺序、reason code、attempt IDs 和 budget。
- 状态断言：checkpoint、queue、breaker、lease、session 和 run terminal state 一致。
- 副作用断言：工具、artifact、remote object、业务状态没有未证明重复。
- 安全断言：没有跨 tenant、错误 region、secret、未授权 egress 或 fail-open。
- 成本断言：retry/hedge/fallback/recovery usage 被正确归因。
- 时间断言：RTO、unknown resolution、containment 和 settlement 满足配置 SLO。
## Chaos、Fault Injection 与 Game Day
### 注入点
- DNS/TLS/connection reset、首事件延迟、随机 EOF、sequence gap。
- provider 429、5xx、容量、错误 retry-after、错误 usage、错误 region metadata。
- credential expiration、revoke、wrong scope、rotation race。
- adapter parser throw、unknown event、schema drift、config mismatch。
- EventStore/SessionStore/ArtifactStore/UsageLedger 延迟、部分写和恢复。
- queue lease expiry、worker crash、duplicate delivery、fencing failure。
- provider status query unavailable、eventual consistency、conflicting receipts。
### Game Day 规则
1. 使用 synthetic tenant、synthetic secret 和隔离 region。
2. 预先声明 blast radius、stop condition、operator、observer 和 evidence store。
3. 不让 shadow/canary/fault 注入触发真实外部副作用。
4. 记录 detection、containment、recovery、reconciliation、communication 和 rollback 时间。
5. 演练结束后清理 artifact、remote object、credential、queue job 和 test lineage。
6. 失败项转为 Evaluation fixture、runbook action、SLO/alert 调整或 architecture change。
### Chaos 成功标准
- incident 被正确分类，且未把普通 4xx 升级为大面积事故。
- circuit/bulkhead/drain 阻止故障扩散。
- unknown 副作用没有被盲目重复。
- queue/workflow/session/artifact/usage 可从 checkpoint 或 receipt 恢复。
- fallback 不违反 capability、egress、residency、credential 和 tenant policy。
- recovery verification 没有被单一 liveness probe 误导。
- evidence、audit、lineage 和 reconciliation 完整。
## 反模式
1. 把 Provider Recovery 实现为固定“重试三次”。
2. 把所有 5xx、429、EOF、401、schema error 放入同一个 retry loop。
3. 把 stream EOF 当作 completed。
4. 把 request sent 当作 provider accepted，把 accepted 当作业务成功。
5. 用 `attemptId` 代替业务幂等键。
6. hedge 写操作、上传、删除或支付。
7. circuit open 后仍允许后台 retry storm。
8. 用 provider status page 或一个 probe 直接关闭 breaker。
9. fallback 不重新检查 capability、egress、region、credential 和 schema。
10. provider outage 时静默切换到不合规 region。
11. worker crash 后把 queue visible 当作未执行。
12. checkpoint 只保存最终文本，不保存 route、tool、artifact、usage 和 unknown。
13. 恢复时从最新全局配置覆盖 frozen run snapshot。
14. 把本地 artifact 删除当作 provider remote object 已删除。
15. 用 trace 或 UI spinner 证明业务副作用。
16. 把 provisional usage 记为零成本。
17. 为了 RTO 关闭 DLP、Policy、Audit、Approval 或 Sandbox。
18. 只按 provider 熔断，导致健康 deployment 被误伤。
19. 只按单请求统计，导致 shared surface outage 无法发现。
20. 恢复后不做 reconciliation、postmortem 和回归门禁。
## 实施清单
### 契约与模型
- [ ] 定义 `ProviderSurfaceRef`、failure taxonomy、Attempt、RecoveryPlan、Receipt、UnknownSubject。
- [ ] 区分 requestId、attemptId、providerRequestId、idempotencyKey、artifactTransferId 和 checkpointId。
- [ ] 为所有 attempt 冻结 route、contract、policy、egress、credential、catalog、config 和 budget snapshot。
- [ ] 定义 Provider Truth、Platform Truth、Business Truth 的 reconciliation 协议。
### 健康与控制
- [ ] 实现 liveness、readiness、stream、semantic、settlement 和 security probes。
- [ ] 实现 breaker、half-open、drain、quarantine 和 TTL/reason/audit。
- [ ] 按 tenant/provider/region/model/side-effect 设计 bulkhead 和 admission。
- [ ] 设计 failure budget、retry budget、hedge budget、unknown budget 和 recovery cost budget。
### 重试与降级
- [ ] 将 transport、provider、agent、queue、workflow、tool retry 分开。
- [ ] 实现 server hint、指数退避、jitter、预算消耗和 deterministic test。
- [ ] 实现安全条件下的 hedging，并记录 loser acceptance/usage。
- [ ] 为 text-only、no-tools、summary-only、artifact-only、manual-review 等 degraded mode 定义契约。
- [ ] fallback 重新执行 capability、egress、credential、quota、schema 和 policy gate。
### 状态与恢复
- [ ] 建立 in-flight registry、heartbeat、abort、fencing 和 settle。
- [ ] 保存 partial stream、open tool calls、artifact manifest、usage provisional 和 unknown。
- [ ] 实现 queue replay、workflow checkpoint、session replay 和 controlled fork。
- [ ] 实现 artifact/status/delete/usage/business reconciliation。
- [ ] 定义 RTO/RPO、data loss、duplicate、provisional settlement 语义。
### 安全与治理
- [ ] credential revoke/rotation 和 config rollback 可审计、可验证、可回收。
- [ ] regional failover 必须经过 residency、retention、training、egress 和 capability guard。
- [ ] recovery command 有 scope、TTL、reason、approval、operator 和 audit。
- [ ] 将 provider recovery 与 Data Lineage、Data Quality、Privacy、Incident Response 连接。
### 运营与测试
- [ ] 建立 recovery SLI/SLO、dashboard、alerts 和 runbook。
- [ ] 为每个 provider/API family 建立 conformance、fault injection、replay 和 semantic probe。
- [ ] 建立 synthetic game day，覆盖 outage、stream、credential、artifact、region、queue 和 checkpoint。
- [ ] 每次事故生成 fixture、regression gate、runbook 更新和 postmortem。
## 五个参考项目的启发来源
### Pi
- headless agent loop、provider-neutral event stream、session tree、compaction entry 和可恢复控制边界。
- 对 Provider Recovery 的启发：attempt 与 event 分离、恢复依赖 durable semantic entry，而不是只依赖 UI transcript。
### Grok Build
- actor/采样器/工具运行时分层、结构化 permission decision、并行工具与路径锁、sandbox 和明确状态所有权。
- 对 Provider Recovery 的启发：高并发状态写入需要 owner/actor/fencing；工具和资源锁不能由 retry loop 隐式处理。
### OpenCode
- client/server 分离、session/message/part 数据模型、事件总线、durable event/projector、snapshot/patch/revert 和多客户端交付。
- 对 Provider Recovery 的启发：recovery、replay、delivery 和状态投影应建立在 durable event 上，不能用临时连接状态当事实。
### Claude Code
- permissions、hooks、subagents、skills、memory、MCP、计划与任务 workflow 形成完整 harness。
- 对 Provider Recovery 的启发：恢复动作必须与 approval、subagent、memory、MCP 和交付层的生命周期集成，而不是只处理模型 HTTP 错误。
### OpenClaw
- AgentHarness registry、独立 agent-core、多渠道 Gateway、provider runtime、tool/sandbox/elevated 分层和事务化插件注册。
- 对 Provider Recovery 的启发：扩展、渠道和 provider 组合会放大故障域；恢复需要显式注册/撤销、隔离和全链路事件。
这些启发只用于本地架构模式归纳，不把任一参考项目当作 Provider Recovery 的现成规范。
## Definition of Done
- [ ] 文档术语与 Provider Runtime、Routing、Incident Response、Queue、Workflow、Lineage、Quality、Privacy、Artifact、Event、Replay、Operations 和 Multi-tenant 一致。
- [ ] 已明确 Provider Recovery 不是简单重试，并覆盖 failure taxonomy、health、budget、breaker、bulkhead、retry、hedge、fallback、drain、quarantine、idempotency、in-flight、stream、queue、checkpoint、artifact、credential、region、RTO/RPO、reconciliation 和 game day。
- [ ] 所有恢复动作均可映射到 durable event、Attempt、UsageLedger、checkpoint、receipt 或 audit evidence。
- [ ] 任何 unknown、副作用、敏感外发和删除状态都没有被静默简化为成功或失败。
- [ ] 实现团队可以从本文直接拆分 contracts、ports、state machine、runbook、metrics、tests 和 release gates。
