# Data Quality Operations Engineering 细粒度工程设计
> 本文定义 Agent 系统中数据质量的控制面、运行面、治理责任、质量 SLO、检测、隔离、修复和恢复工程。
>
> 依据仅来自当前目录已有的参考架构、Agent Harness、Data Governance、Privacy、Provider Runtime、Provider Routing、Provider Runtime Conformance、Provider Schema Evolution、Event/Observability、Evaluation、Durable Queue、Security Operations、Production Operations、Artifact、State/Memory、Tool、Context 与五个参考项目源码调研结论；不依赖 README，不新增网络搜索结论。
>
> **边界声明：** Data Quality Operations 不是“定期跑一条 `COUNT(*)`”。它必须覆盖质量维度、数据契约、schema 与语义验证、freshness、completeness、accuracy、consistency、uniqueness、timeliness、lineage、SLO/SLI、ownership、steward、on-call、隔离、重放、回填、删除、DSAR、驻留、外发、修复、回滚和事故恢复。
## 目录
1. [目标与非目标](#目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [职责边界](#职责边界)
4. [质量范围与总体架构](#质量范围与总体架构)
5. [Quality Dimensions](#quality-dimensions)
6. [Data Contract](#data-contract)
7. [Schema 与 Semantic Validation](#schema-与-semantic-validation)
8. [核心数据模型](#核心数据模型)
9. [TypeScript 接口](#typescript-接口)
10. [Ownership、Steward 与 On-call](#ownershipsteward-与-on-call)
11. [Quality SLI、SLO 与 Error Budget](#quality-sli、slo-与-error-budget)
12. [Data Catalog 与 Quality Dashboard](#data-catalog-与-quality-dashboard)
13. [Ingestion Quality](#ingestion-quality)
14. [Queue 与 Job Quality](#queue-与-job-quality)
15. [Provider 与 Model Quality](#provider-与-model-quality)
16. [Artifact 与 File Quality](#artifact-与-file-quality)
17. [Memory 与 Context Quality](#memory-与-context-quality)
18. [Event、Log 与 Trace Quality](#eventlog-与-trace-quality)
19. [Backup、Archive 与 Restore Quality](#backuparchive-与-restore-quality)
20. [Reconciliation](#reconciliation)
21. [Drift 与 Anomaly Detection](#drift-与-anomaly-detection)
22. [Quarantine、DLQ、Replay 与 Backfill](#quarantinedlqreplay-与-backfill)
23. [Incident、Severity 与 Runbook](#incidentseverity-与-runbook)
24. [Deletion、DSAR 与 Retention Quality](#deletiondsar-与-retention-quality)
25. [Tenant、Residency 与 Egress Checks](#tenantresidency-与-egress-checks)
26. [Sampling 与 Great-Expectations-like Checks](#sampling-与-great-expectations-like-checks)
27. [CI、Production Gate 与 Release](#ciproduction-gate-与-release)
28. [Repair、Rollback 与 Recovery](#repairrollback-与-recovery)
29. [生命周期与状态机](#生命周期与状态机)
30. [决策流程](#决策流程)
31. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
32. [安全、隐私与可观测性](#安全隐私与可观测性)
33. [测试策略](#测试策略)
34. [反模式](#反模式)
35. [实施清单](#实施清单)
36. [五个参考项目的启发来源](#五个参考项目的启发来源)
37. [Definition of Done](#definition-of-done)
## 目标与非目标
### 目标
Data Quality Operations 必须能够：
- 为 Agent 数据平面和治理控制面定义统一的质量维度、指标、阈值、证据与责任。
- 用 `DataContract` 描述 producer、consumer、schema、字段语义、版本、质量 SLO 和失败处理。
- 同时验证结构合法性、语义正确性、业务一致性、scope 安全性和生命周期完整性。
- 覆盖 ingestion、queue、provider、artifact、memory、event、log、backup、cache、remote object 和导出副本。
- 测量 freshness、completeness、accuracy、consistency、uniqueness、timeliness、validity、integrity、lineage 和 availability。
- 把质量 SLI、SLO、error budget、owner、steward、on-call 和 escalation 绑定起来。
- 在 schema drift、semantic drift、volume anomaly、freshness lag、scope leak 和 lineage gap 出现时提前检测。
- 支持 quarantine、dead-letter、replay、backfill、repair、rollback、reconciliation 和人工处置。
- 让删除、DSAR、retention、legal hold、tenant isolation、residency 和 provider egress 也有可测质量。
- 提供 CI gate、生产 gate、dashboard、runbook、incident regression 和回滚证据。
- 让质量修复不覆盖 immutable facts，不伪造历史成功，不绕过 Policy、Privacy 或 Security Operations。
### 非目标
本文不负责：
- 规定某个数据库、数据湖、消息队列、catalog、质量平台或云产品。
- 用一个总分掩盖安全、隐私、驻留、删除或跨租户硬失败。
- 仅以 `COUNT(*)`、row count、HTTP 200、平均延迟或 schema parse 证明数据质量。
- 把 lineage 当成授权，把 catalog 当成访问控制，把质量分数当成合规证明。
- 直接修改原始事实、审计事件、provider response 或用户 session 来“修好”结果。
- 把模型输出自述当作 accuracy，把日志到达当作 event durable commit。
- 允许质量 pipeline 使用生产 secret、未脱敏 prompt 或无隔离的真实副作用。
- 让 repair、backfill、replay 或 rollback 绕过 tenant、purpose、retention、egress 和 approval。
- 用自动修复替代 owner、steward、incident commander 和风险接受。
### 核心公式
```text
Data Quality Operations
  = Contract Correctness
  × Semantic Validity
  × Timeliness
  × Lineage Completeness
  × Scope Integrity
  × Lifecycle Verifiability
  × Repair Safety
  × Operational Ownership
```
任一乘项接近零，数据都可能看起来“有记录”但不能安全使用。
## 核心判断与术语
### 核心判断
```text
Producer emits facts.
Data Contract defines expectations.
Catalog explains meaning and ownership.
Quality Monitor measures evidence.
Policy decides allowed use.
Lineage explains source and propagation.
State/Event Store preserves durable truth.
ArtifactStore holds large immutable content.
Operations detects, contains, repairs and verifies.
```
- 数据质量是每个副本、视图、队列和生命周期阶段的属性，不是单表属性。
- `schema valid` 不等于 semantic valid，semantic valid 不等于 policy allowed。
- freshness 不等于 timeliness；完整不等于准确；有 lineage 不等于可访问。
- deletion completed 不等于所有 derived、cache、backup、remote copy 都已删除。
- provider response 的格式正确不等于模型事实正确；需要业务、来源和对账证据。
- 质量异常需要保留原始事实和诊断证据，不能只修改结果表。
- unknown data quality 不能默认为 good；关键数据默认 hold 或 quarantine。
### 稳定术语
- `DataProduct`：由明确 owner、consumer、contract 和质量 SLO 管理的数据产品。
- `DataRecord`：逻辑数据对象、版本、scope、classification、lineage、copies 和生命周期状态。
- `DataContract`：producer/consumer 对 schema、语义、质量、兼容和失败处理的协议。
- `QualityDimension`：freshness、completeness、accuracy、consistency、uniqueness、timeliness 等质量轴。
- `QualityCheck`：对数据、事件、文件、队列或治理事实执行的可重复检查。
- `QualityObservation`：某次检查在时间窗口、scope、采样和版本上的观测。
- `QualityIncident`：超出阈值、影响业务或违反硬约束的质量事件。
- `Quarantine`：阻断数据继续传播但保留证据、原因和恢复路径的隔离状态。
- `Reconciliation`：比较两个或多个 source of truth、receipt、manifest 或派生视图并解释差异。
- `Repair`：不覆盖原始事实的修复动作，可以创建新版本、补偿事件或派生视图。
- `Backfill`：使用明确版本、范围、幂等键和 checkpoint 重算历史派生结果。
- `Quality SLO`：某个 quality SLI 在窗口内的可接受目标。
## 职责边界
### Data Contract Registry 负责
- 注册 data product、schema、字段语义、版本、owner、steward 和 consumer。
- 定义 quality dimensions、checks、thresholds、severity 和 compatibility。
- 记录 contract status、freshness、evidence、exception 和 review 时间。
- 不直接读写业务事实，不在失败时静默改数据。
### Producer 负责
- 生成符合 contract 的事实、schema、source timestamp、event ID 和 lineage。
- 提供 producer version、watermark、checksum、idempotency key 和 receipt。
- 在无法满足 contract 时显式拒绝、降级或送入 quarantine。
- 不能把 consumer 的修复逻辑藏在 producer 中。
### Consumer 负责
- 按 contract、purpose、scope、schema 和 quality gate 使用数据。
- 对下游 view、cache、artifact、prompt、model request 和 export 维护 lineage。
- 发现 invalid、stale、scope mismatch 或 deletion hold 时停止继续传播。
- 不能因缺数据而擅自放宽 policy 或填充未经证实的事实。
### Quality Monitor 负责
- 执行 schema、semantic、freshness、completeness、accuracy、consistency、uniqueness、lineage 和 lifecycle checks。
- 生成 observation、metric、diagnostic、incident、quarantine 和 dashboard projection。
- 保留采样、规则版本、source watermark 和 evidence refs。
- 不直接修改 source of truth。
### Data Catalog 与治理角色负责
- Catalog 维护语义、分类、owner、steward、purpose、retention、region、SLO 和下游引用。
- Data owner 负责目的、风险接受、资源优先级和例外批准。
- Data steward 负责 schema、字段语义、质量规则、lineage 和日常治理。
- On-call 负责检测、分诊、containment、恢复、沟通和升级。
- Governance board 负责跨团队标准、重大例外和不可接受风险。
### Operations、Security 与 Privacy 负责
- Production Operations 负责容量、队列、备份、恢复、发布和 SLO。
- Security Operations 负责 scope leak、secret、egress、audit integrity 和安全 incident。
- Privacy 负责 purpose、classification、retention、删除、DSAR、驻留和 provider remote copy。
- Policy/Sandbox 负责执行边界，质量系统不能替代授权。
### 强制边界
```text
Producer -> Contract -> Ingest/Queue/Store
-> Quality Checks -> Catalog/Lineage/SLI
-> Consumer Gate -> Derived Copy/Provider/Artifact/Event
-> Reconciliation -> Incident/Repair/Backfill -> Verification
```
## 质量范围与总体架构
### 覆盖对象
```text
Host input
PromptSection / ContextResource / ContextPlan
ModelRequest / ProviderResponse / UsageLedger
ToolCall / ToolResult / SideEffectReceipt
SessionEntry / Checkpoint / MemoryRecord
Artifact / File / Preview / Summary / Patch
QueueCommand / Job / Lease / DeadLetter
CanonicalEvent / Trace / Log / Metric / Audit
Cache / Embedding / Backup / Archive
Provider remote object / Export package / DSAR record
```
### 控制面
控制面管理：
- data product、schema、contract、quality rule 和版本。
- owner、steward、consumer、on-call 和 escalation。
- classification、purpose、retention、region、egress 和 deletion policy。
- sampling、threshold、SLO、error budget、exception 和 quarantine policy。
- repair、backfill、replay、rollback、catalog freshness 和 incident state。
### 数据面
数据面承载：
- 原始输入、模型消息、provider payload、工具结果和文件内容。
- queue/job/event、session/checkpoint、artifact、memory、cache 和 backup。
- quality observation 所需的 watermark、manifest、hash、receipt、schema 和 lineage。
数据面只使用冻结的 `ScopeRef`、`PolicySnapshot`、`EgressSnapshot`、`DataContractVersion` 和 `QualityPolicySnapshot`。
### 推荐包布局
```text
packages/data-quality/
  contracts.ts
  dimensions.ts
  schema-validation.ts
  semantic-validation.ts
  freshness.ts
  completeness.ts
  accuracy.ts
  consistency.ts
  uniqueness.ts
  timeliness.ts
  lineage.ts
  catalog.ts
  ownership.ts
  quality-slo.ts
  observations.ts
  dashboard.ts
  reconciliation.ts
  drift.ts
  anomaly.ts
  quarantine.ts
  dead-letter.ts
  replay.ts
  backfill.ts
  repair.ts
  rollback.ts
  deletion-quality.ts
  egress-quality.ts
  incidents.ts
  runbooks.ts
  testkit/
```
### 依赖方向
```text
Host -> Harness -> Data Quality Ports
Provider/Tool/Event/Artifact/Queue -> Data Contract + Lineage
Quality Monitor -> Canonical data and metadata ports
Operations -> SLO/Incident/Repair ports
Infrastructure -> store/catalog/queue/metrics adapters
```
Kernel 不导入质量平台 SDK、数据库 schema 或 dashboard client。
## Quality Dimensions
### Schema Validity
- 数据能否按声明的 schema 解析。
- required 字段、类型、枚举、格式、嵌套和版本是否满足。
- unknown field 是否被保留、忽略、诊断或阻断。
- schema hash、producer version 和 contract version 是否匹配。
- schema validity 失败不得自动推断业务值。
### Semantic Validity
- 字段值是否符合业务语义、单位、范围、状态机和跨字段约束。
- `completed` 是否有 terminal evidence，`tool result` 是否有对应 call。
- `region` 是否为允许的 jurisdiction，`tenantId` 是否属于 scope。
- usage、cost、timestamps、artifact size 和 token count 是否符合定义。
- provider response 的文本可读不等于 semantic valid。
### Freshness
- 数据从 source event/record 产生到可消费的年龄。
- catalog、capability、policy、quality observation 和 backup manifest 的新鲜度。
- freshness watermark、observedAt、sourceUpdatedAt 和 ingestionAt 分开记录。
- 过期 catalog 不得用于新的硬 capability 判断。
- stale data 可以用于诊断，但不能静默进入关键 run。
### Completeness
- 预期实体、字段、事件、part、tool result、usage、receipt 和 lineage 是否存在。
- 处理窗口内已接收、已验证、已持久化和已投影的数量是否可解释。
- completeness 不只看 row count，还要看 sequence gap、partition、tenant 和 source watermark。
- 缺失记录需区分尚未到达、被拒绝、被隔离、被删除和未知。
### Accuracy
- 数据是否与可信 source、receipt、external status 或业务 oracle 一致。
- model usage 与 provider receipt、artifact hash 与 blob、queue status 与 execution record 是否一致。
- accuracy 需要定义 ground truth、容忍度、版本和观测窗口。
- 模型生成的开放文本不能仅靠 self-report 判准确。
- 无 ground truth 时使用 corroboration、confidence、provenance 和 `inconclusive`。
### Consistency
- 同一事实在 session、event、projection、artifact、usage、queue 和 audit 中是否一致。
- 强一致字段与最终一致字段必须分别声明。
- 同一 attempt 的 provider ID、attempt ID、run ID 和 tenant scope 不能冲突。
- projector lag 可暂时不一致，但必须有 watermark 和修复路径。
- 不能用后写入的低可信副本覆盖高可信 immutable fact。
### Uniqueness
- eventId、requestId、attemptId、toolExecutionId、artifactVersionId 和 idempotency key 是否按 scope 唯一。
- 重复事件、重复 remote upload、重复 job 和重复 usage 是否能检测。
- 全局唯一与 tenant 内唯一要分开定义。
- dedupe 不得删除两个真实但语义不同的事件。
- duplicate 的保留、合并和回放规则必须可解释。
### Timeliness
- 数据是否在业务 deadline 前到达并可用于决策。
- Provider first-event、tool completion、queue lease、delivery ack、backup RPO 和 DSAR deadline 分开测量。
- timeliness 是相对任务 deadline，freshness 是相对 source update。
- 延迟数据不能因最终到达就抹去已发生的 SLA breach。
### Integrity
- hash、checksum、sequence、signature、fencing token 和 CAS 是否有效。
- 事件是否被篡改、重排、截断或跨 scope 复制。
- artifact blob、manifest、backup 和 export package 是否可验证。
- integrity failure 默认进入 security/quality incident。
### Lineage Completeness
- source、transform、consumer、destination、copy、view 和 deletion dependency 是否齐全。
- derived summary、memory、embedding、provider remote object 和 log 不能脱离 parent ref。
- lineage 记录 transform version、schema version、policy/egress snapshot 和 actor。
- lineage 缺失时关键数据不得进入不可逆外发或长期 memory。
### Lifecycle Quality
- created、validated、active、stale、quarantined、deleted、expired、reconciled 状态是否可查询。
- retention、TTL、legal hold、deletion、export 和 DSAR 是否有每副本证据。
- provider remote object 不能因本地删除而自动标记 deleted。
- backup restore 后必须重新验证 scope、schema、lineage 和 retention。
## Data Contract
### Contract 组成
1. `Identity`：data product、logical type、version、owner、steward。
2. `Schema`：结构、字段类型、required、enum、unknown field 策略。
3. `Semantics`：单位、状态、业务不变量、source of truth。
4. `Quality`：dimension、check、threshold、window、severity、SLO。
5. `Lineage`：source、transform、consumer、destination、copy。
6. `Scope`：tenant、workspace、session、run、purpose、classification。
7. `Lifecycle`：retention、TTL、deletion、legal hold、archive、replay。
8. `Failure`：quarantine、DLQ、retry、replay、backfill、manual action。
9. `Compatibility`：reader/writer range、migration、dual-read、dual-write。
10. `Evidence`：receipt、hash、watermark、sample、runbook 和 audit reference。
### Producer Contract
producer 必须提供：
- `schemaVersion` 和 `contractVersion`。
- `producedAt`、`sourceUpdatedAt`、`sequence` 或 `watermark`。
- `eventId`、`idempotencyKey`、`payloadHash` 或 `contentHash`。
- `tenantId`、`scope`、`sensitivity`、`purpose` 和 `provenance`。
- `sourceRefs`、`lineageRefs`、`providerReceipt` 或 `sideEffectReceipt`。
- 失败时的 typed error、quarantine reason 和 retryability。
### Consumer Contract
consumer 必须声明：
- 支持的 schema/contract 版本范围。
- 需要的字段、语义、freshness、completeness 和 latency ceiling。
- 允许的 scope、classification、purpose、provider、region 和 view。
- 是否允许 stale、estimated、degraded 或 unknown 数据。
- 处理 invalid、late、duplicate、quarantined 和 missing 的行为。
- 下游输出、lineage、retention、deletion 和 rollback 依赖。
### Contract Compatibility
- additive optional field 通常兼容。
- 增加 required field、改变单位、状态、顺序或 scope 语义通常 breaking。
- 改变 freshness、accuracy ground truth、SLO 或 deletion 语义需要治理审查。
- provider projection 不能删除 canonical required constraint。
- 历史数据必须有 upcaster、migration 或明确不支持范围。
### Data Contract 状态机
```text
Draft -> Reviewed -> Registered -> Validated
-> Active -> Degraded -> Suspended -> Deprecated -> Retired
```
## Schema 与 Semantic Validation
### Validation 分层
```text
scope/auth check
-> envelope/schema parse
-> field/type/enum validation
-> semantic rules
-> cross-record consistency
-> lineage/provenance
-> quality SLO
-> policy/egress/lifecycle gate
-> accepted | degraded | quarantined | rejected
```
### Schema 检查
- JSON/structured event 可解析。
- required 字段存在。
- 类型、格式、范围、枚举和 nested schema 正确。
- unknown field 按 contract 规则处理。
- version 与 reader/writer compatibility 匹配。
- payload hash、content hash 和 compression metadata 可验证。
- event sequence、correlation、causation 和 tenant scope 存在。
### 语义检查
- `ToolCallReady` 之前不能有 execution completed。
- `ToolExecutionCompleted` 必须对应唯一 `toolCallId` 和 execution ID。
- `RunCompleted` 必须有 terminal outcome 和 settlement 摘要。
- usage 不得为负，重复 update 必须可合并或去重。
- artifact size、content hash、view、retention 和 source version 一致。
- checkpoint 必须引用兼容的 session/event schema。
- provider response 不得改变 server-side tenant、workspace、run、region 或 purpose。
### 跨记录检查
- parent/child lineage 存在且 scope 一致。
- event sequence 无 gap，或 gap 有已知 quarantine/late reason。
- queue job、lease、execution record 和 terminal event 状态可解释。
- provider request receipt 与 attempt、usage、cost 一致。
- deletion request 的所有 copy 都有状态。
- backup manifest 与 restore inventory 一致。
### Great-Expectations-like 规则模型
```typescript
interface QualityExpectation {
  expectationId: string;
  datasetRef: string;
  dimension: QualityDimension;
  expression: string;
  scope?: ScopePredicate;
  severity: "info" | "warning" | "blocking";
  threshold: Threshold;
  sampling?: SamplingPlan;
  owner: string;
  evidencePolicy: EvidencePolicy;
}
```
规则表达式可以类似：
- not_null。
- unique_within_scope。
- accepted_values。
- value_between。
- regex_match。
- row_count_between。
- freshness_under。
- completeness_above。
- referential_integrity。
- sequence_no_gap。
- schema_version_in。
- lineage_exists。
- egress_region_allowed。
- deletion_state_reconciled。
## 核心数据模型
### DataContract
```typescript
interface DataContract {
  contractId: string;
  dataProductId: string;
  logicalType: string;
  version: string;
  producer: DataOwner;
  consumers: DataConsumer[];
  schema: SchemaRef;
  semantics: SemanticRule[];
  quality: QualitySpec;
  scope: ScopeSpec;
  lifecycle: LifecycleSpec;
  compatibility: CompatibilityPolicy;
  failurePolicy: FailurePolicy;
  status: "draft" | "active" | "degraded" | "suspended" | "deprecated" | "retired";
}
```
### QualitySpec
```typescript
interface QualitySpec {
  dimensions: QualityDimensionSpec[];
  slis: QualitySliSpec[];
  slos: QualitySloSpec[];
  errorBudget: ErrorBudgetPolicy;
  checkSchedule: CheckSchedule;
  criticality: "low" | "medium" | "high" | "critical";
}
```
### QualityObservation
```typescript
interface QualityObservation {
  observationId: string;
  contractId: string;
  checkId: string;
  scope: ScopeRef;
  window: TimeWindow;
  status: "passed" | "failed" | "degraded" | "unknown" | "skipped";
  value?: number | string | boolean;
  numerator?: number;
  denominator?: number;
  threshold: Threshold;
  sourceWatermark?: string;
  observedAt: string;
  ruleVersion: string;
  sampleRef?: ArtifactRef;
  evidenceRefs: EvidenceRef[];
  diagnostics: Diagnostic[];
}
```
### QualityIncident
```typescript
interface QualityIncident {
  incidentId: string;
  severity: "sev0" | "sev1" | "sev2" | "sev3";
  status: "detected" | "triaged" | "contained" | "repairing" | "verifying" | "resolved" | "reviewed";
  contractIds: string[];
  affectedScopes: ScopeRef[];
  dimensions: QualityDimension[];
  firstObservedAt: string;
  lastObservedAt?: string;
  owner?: DataOwner;
  commander?: PrincipalRef;
  impactSummary: string;
  actions: IncidentAction[];
  evidenceRefs: EvidenceRef[];
}
```
### QuarantineRecord
```typescript
interface QuarantineRecord {
  quarantineId: string;
  dataRef: DataRef;
  reasonCodes: string[];
  detectedBy: string;
  contractId: string;
  scope: ScopeRef;
  sourceWatermark?: string;
  retryable: boolean;
  replayPlan?: ReplayPlan;
  expiresAt?: string;
  status: "open" | "replayed" | "repaired" | "discarded" | "expired";
}
```
### ReconciliationRecord
```typescript
interface ReconciliationRecord {
  reconciliationId: string;
  leftSource: SourceRef;
  rightSource: SourceRef;
  scope: ScopeRef;
  comparisonWindow: TimeWindow;
  matched: number;
  missingLeft: number;
  missingRight: number;
  mismatched: number;
  duplicateCount: number;
  unknownCount: number;
  status: "matched" | "diverged" | "blocked" | "inconclusive";
  diffRef?: ArtifactRef;
  createdAt: string;
}
```
## TypeScript 接口
### QualityMonitor
```typescript
interface QualityMonitor {
  validate(data: DataEnvelope, contract: DataContract): Promise<ValidationReport>;
  observe(input: QualityObservationInput): Promise<QualityObservation[]>;
  reconcile(input: ReconciliationInput): Promise<ReconciliationRecord>;
  detectDrift(input: DriftInput): Promise<DriftFinding[]>;
  openIncident(input: QualityIncidentInput): Promise<QualityIncident>;
}
```
### CatalogPort
```typescript
interface DataCatalogPort {
  register(product: DataProduct): Promise<RegistrationReceipt>;
  resolve(ref: DataRef, scope: ScopeRef): Promise<DataCatalogEntry>;
  updateQuality(ref: DataRef, snapshot: QualitySnapshot): Promise<void>;
  owners(ref: DataRef): Promise<OwnershipRecord>;
  lineage(ref: DataRef, scope: ScopeRef): Promise<LineageGraph>;
}
```
### RepairPort
```typescript
interface RepairPort {
  plan(input: RepairRequest): Promise<RepairPlan>;
  execute(plan: RepairPlan, signal: AbortSignal): Promise<RepairResult>;
  verify(result: RepairResult): Promise<VerificationReport>;
  rollback(input: RollbackRequest): Promise<RollbackResult>;
}
```
### QuarantinePort
```typescript
interface QuarantinePort {
  hold(input: QuarantineRequest): Promise<QuarantineReceipt>;
  inspect(ref: DataRef, scope: ScopeRef): Promise<QuarantineView>;
  replay(input: ReplayRequest): Promise<ReplayReceipt>;
  release(input: ReleaseQuarantineRequest): Promise<void>;
  discard(input: DiscardQuarantineRequest): Promise<void>;
}
```
### Quality SLO Port
```typescript
interface QualitySloPort {
  evaluate(contract: DataContract, window: TimeWindow): Promise<SloEvaluation>;
  budget(contractId: string, window: TimeWindow): Promise<ErrorBudgetStatus>;
  gate(input: QualityGateInput): Promise<QualityGateDecision>;
}
```
## Ownership、Steward 与 On-call
### 角色定义
- `Data Owner`：对数据产品目的、业务风险、质量预算和例外负责。
- `Data Steward`：对 schema、字段语义、分类、lineage、规则和质量日常负责。
- `Producer Owner`：对产生事实的 runtime、adapter、worker、工具或 provider 负责。
- `Consumer Owner`：对下游使用、最小化、视图和下游副本负责。
- `Platform Operator`：对存储、队列、备份、恢复、扫描和容量负责。
- `Security/Privacy Owner`：对 scope、egress、删除、retention、secret 和 incident 负责。
- `On-call`：对告警响应、分级、containment、状态沟通和升级负责。
- `Incident Commander`：对高严重度事故的统一决策和关闭证据负责。
### Ownership 规则
- 未分配 owner 的数据产品不能进入 critical production gate。
- owner 与 steward 可以不同，但职责必须可查询。
- 每个质量规则必须有 rule owner、review date 和 escalation target。
- provider、artifact、queue、event 和 backup 质量可以有技术 owner，但 data owner 仍负责业务影响。
- owner 离职、团队迁移或 contract retired 时必须更新 catalog，不得遗留 orphan data product。
### On-call 轮值输入
- alert severity、affected scope、quality dimensions、first observed、last good watermark。
- producer/consumer/contract/provider/region/queue/backup 版本。
- quarantine、DLQ、replay、backfill、repair 和 rollback 状态。
- 已触发的 security、privacy、retention、DSAR 或 residency 影响。
- runbook、dashboard、evidence refs 和升级联系人。
### 责任矩阵
| 活动 | Owner | Steward | Producer | Consumer | Platform | Security/Privacy |
|---|---|---|---|---|---|---|
| contract 定义 | A | R | C | C | C | C |
| schema 发布 | A | R | R | C | C | C |
| ingestion 修复 | A | C | R | C | R | C |
| lineage 修复 | A | R | C | R | C | C |
| egress 违规 | C | C | C | C | C | A/R |
| deletion/DSAR | A | R | C | C | R | R |
| incident 关闭 | A | C | C | C | R | C |
`A` 表示 accountable，`R` 表示 responsible，`C` 表示 consulted。
## Quality SLI、SLO 与 Error Budget
### SLI 类型
- `freshness_lag_ms`：source update 到可消费的延迟。
- `completeness_ratio`：预期对象中已收到并验证的比例。
- `schema_valid_ratio`：通过结构验证的比例。
- `semantic_valid_ratio`：通过语义规则的比例。
- `accuracy_match_ratio`：与可信 source/receipt/oracle 匹配的比例。
- `consistency_match_ratio`：跨副本比较一致的比例。
- `uniqueness_violation_rate`：重复键、事件或执行的比例。
- `timeliness_ratio`：在业务 deadline 前完成的比例。
- `lineage_coverage_ratio`：具备完整 lineage 的对象比例。
- `integrity_failure_rate`：hash、sequence、signature 或 CAS 失败比例。
- `deletion_completion_ratio`：所有副本有可验证删除状态的比例。
- `quarantine_age_ms`：异常数据在隔离区停留时间。
- `replay_success_ratio`：重放后通过质量验证的比例。
- `restore_validation_ratio`：备份恢复后通过 schema、scope、lineage 和 lifecycle 验证的比例。
### SLO 设计
- critical event、audit、security、deletion 和 tenant scope 使用硬阈值。
- interactive data 重点关注 timeliness、freshness、completeness 和 provider receipt。
- background data 允许较高 latency，但必须有 deadline 和 watermark。
- SLO 按 global、tenant、workspace、provider、data product 和 contract 分层。
- SLO 必须定义 window、exclusions、sampling、unknown 处理和 error budget policy。
### Error Budget
- error budget 只能用于可接受的质量波动，不能抵消跨租户、secret、错误删除或未授权 egress。
- budget 消耗由 observation、incident、scope 和版本归因。
- budget 耗尽可冻结非关键发布、降低 backfill 并要求 owner 复盘。
- 数据产品的质量例外必须有 expiry、批准人、影响范围和回滚计划。
- `unknown` 和数据缺失不能默认算作成功样本。
### Gate 类型
- `hard_gate`：失败即阻断读取、发布、外发、交付或删除完成声明。
- `soft_gate`：失败产生 warning、降级、人工复核或 owner ack。
- `observe_only`：只收集指标，不改变路径，但需设置 expiry。
- `hold_gate`：进入 quarantine，等待证据或人工决定。
## Data Catalog 与 Quality Dashboard
### Catalog 必备字段
- data product、logical type、version、schema、contract、owner、steward。
- producer、consumer、source、destination、region、provider、view 和 copy。
- classification、purpose、legal basis、retention、deletion dependency。
- quality dimensions、SLO、last observation、last good watermark。
- lineage graph、known limitations、quarantine policy、runbook、on-call。
- exception、risk acceptance、contract status 和 deprecation date。
### Dashboard 层次
1. Executive：critical product、SLO、error budget、开放 incident 和业务影响。
2. Steward：schema、semantic checks、field quality、lineage、drift 和 ownership。
3. SRE：queue depth、freshness lag、backlog、worker、provider、store 和 backup。
4. Security/Privacy：scope violations、egress、DLP、deletion、DSAR、residency、remote object。
5. Developer：fixture、failed expectation、diff、rule version、replay 和 repair plan。
### Dashboard 规则
- 指标必须区分 scope、source、version、provider、region 和 status。
- 折线图同时展示 threshold、last good、unknown、quarantine 和 deploy marker。
- 不用平均值掩盖 tail latency、少量 critical tenant 或高风险数据失败。
- 详细数据受 sensitivity、tenant 和 operator access control 约束。
- dashboard 不是 source of truth，必须能追到 observation/evidence/event。
### 质量报告
- 每日质量摘要只作趋势视图，不替代实时 hard gate。
- 每次发布生成 contract、schema、quality、security、privacy 和 restore evidence。
- 每个 incident 生成影响范围、时间线、根因、修复、验证和 regression refs。
- 报告中的 unknown、skipped、inconclusive 独立展示。
## Ingestion Quality
### Ingestion 阶段
```text
receive
-> authenticate/scope
-> envelope parse
-> schema validate
-> dedupe/idempotency
-> semantic validate
-> lineage/register
-> persist durable fact
-> publish downstream event
-> quality observation
```
### Ingestion 检查
- source identity、tenant、workspace、purpose 和 classification 正确。
- content hash、event ID、sequence、watermark 和 producer version 存在。
- payload 不超过 bytes、parts、field、attachment 和 queue limit。
- 重复 payload、重复 event 和同 key 不同 payload 能区分。
- invalid 数据进入 quarantine/DLQ，并保留原始引用和 reason code。
- durable persist 与 downstream publish 通过 outbox/inbox 或等价事实关联。
- ingestion success 只有在明确 durable receipt 后才可声明。
### Ingestion SLI
- accepted、rejected、quarantined、duplicate、unknown 数量。
- source-to-ingest freshness、ingest-to-persist latency。
- schema、semantic、scope、lineage failure rate。
- last source watermark、partition lag、sequence gap。
- payload hash mismatch、outbox backlog、DLQ age。
### Ingestion 修复
- repair 不修改原始 incoming payload。
- 可以通过 upcaster、补充 metadata、重放或新版本派生视图修复。
- source watermark 不可倒退，除非执行显式 backfill。
- late data 使用 arrival reason，不覆盖原始 occurredAt。
- source contract breaking 时暂停 consumer，不能用默认值批量填充。
## Queue 与 Job Quality
### Queue 质量对象
- Command、Job、Queue、Lease、Worker、Checkpoint、Receipt、Event 和 DeadLetter。
- 质量检查必须区分“已入队”“已租约”“已执行”“已提交结果”“副作用已确认”。
- queue visible 不代表 job 未执行，lease expired 不代表没有副作用。
- Host ack 不代表 terminal result 或 durable settlement。
### Queue Quality Checks
- enqueue receipt、idempotency、payload hash 和 tenant scope。
- job schema、config snapshot、policy snapshot、required capabilities。
- partition、priority、fairness、deadline、availableAt 和 lease version。
- heartbeat、fencing token、visibility timeout 和 worker identity。
- retry count、backoff、DLQ reason、poison message 和 replay eligibility。
- queue-to-worker、worker-to-event、event-to-projector 的 watermark。
- duplicate job、duplicate execution、unknown outcome 和 stale lease。
### Queue SLO
- enqueue durability latency。
- oldest job age、queue depth、lease wait、worker start latency。
- deadline miss ratio、retry storm ratio、DLQ age。
- checkpoint freshness、terminal settlement latency。
- tenant fairness、noisy-neighbor、backpressure 和 capacity admission。
### Queue 质量故障
- lease store unavailable：暂停新 lease，保护现有高风险动作边界。
- worker crash：读取 execution record、receipt、checkpoint 和 fencing token。
- event store lag：不声称 terminal 已提交。
- duplicate delivery：由 idempotency receipt 和 side-effect oracle 识别。
- poison job：quarantine，不无限重试。
## Provider 与 Model Quality
### Provider 数据质量
- `ResolvedModel`、provider、api family、model、deployment、region 和 catalog version。
- capability declaration、conformance status、adapter version 和 contract version。
- request/response/event normalization、finish reason、usage、error、retry、cancel。
- provider request receipt、raw response reference、remote object、cost evidence。
- provider health、circuit、rate limit、capacity、drift 和 live smoke freshness。
### Provider Quality Checks
- request hash 与 projection hash 是否对应冻结 snapshots。
- capability matrix 是否有新鲜证据。
- stream sequence、terminal、tool pairing 和 unknown event。
- usage observed/estimated/reconciled 与 ledger 是否一致。
- response scope、tenant、artifact ref、safety、citation 和 grounding metadata。
- provider fallback 是否重新满足 capability、egress、region 和 policy。
- adapter quarantine 是否阻止 active route。
### Model Accuracy 边界
- provider contract 主要检查协议语义，不宣称开放文本事实正确。
- 需要业务准确性时，使用 Evaluation scenario、reference answer、tool oracle、source citation 或 reconciliation。
- model self-report 只能是低可信 provenance。
- structured output 可验证 schema 和 business constraints，但不能自动证明现实事实。
- provider quality dashboard 分离 protocol quality、model quality、business outcome 和 safety outcome。
### Provider 质量 SLI
- normalized completion rate。
- terminal integrity rate。
- tool call pairing success。
- structured validation pass rate。
- usage completeness and reconciliation rate。
- unknown outcome rate。
- capability false-positive rate。
- drift detection latency。
- live smoke pass rate。
- provider-induced retry/fallback rate。
## Artifact 与 File Quality
### Artifact 质量层
```text
raw blob
-> scan
-> manifest
-> sanitized/structured/preview/summary/range view
-> provider/user delivery
-> retention/deletion/archive
```
### Artifact 检查
- content hash、size、MIME、encoding、version、parent ref 和 source scope。
- upload receipt、scan status、virus/DLP/classification 状态。
- raw、sanitized、preview、summary、range 和 model_ref view 的 lineage。
- artifact version 与 event/session/checkpoint 引用一致。
- 大输出 offload 后 inline summary 的 truncation metadata 正确。
- remote provider object 的 ID、expiry、delete status 和 purpose 单独对账。
- preview、thumbnail、embedding、cache、backup 和 export package 都在 inventory 中。
### Artifact 质量异常
- content hash mismatch：阻断交付，保留原始引用。
- scan pending：敏感数据不进入 provider/user/public host。
- scan failed：quarantine，不能用 unknown 当 clean。
- missing parent：lineage incident。
- remote upload success/local record missing：reconciliation incident。
- local delete/remote delete unknown：lifecycle degraded，不声称 fully deleted。
### Artifact SLO
- ingest-to-scan latency。
- scan completeness、classification completeness、view generation success。
- artifact hash integrity、delivery success、remote delete completion。
- preview/summary freshness、range read correctness、restore success。
## Memory 与 Context Quality
### Memory Quality
- memory candidate、provenance、confidence、scope、purpose、TTL、lastVerifiedAt 和 source refs。
- model inferred 不是 active fact，需 user confirmation 或明确可信来源。
- memory write、recall、forget、compaction flush 和 index update 有一致 lineage。
- secret、regulated 和高风险 PII 默认不写长期 memory。
- 删除 memory 必须传播到 recall index、embedding、cache、derived view、backup 和 provider copy。
### Memory 检查
- recall 结果属于当前 tenant/user/workspace/project/session scope。
- recall freshness、TTL、contradiction、duplicate 和 confidence。
- memory candidate 未绕过 purpose、consent、retention 和 user control。
- memory projection 没有把低 authority 数据包装成 policy authority。
- forget 完成后新 ContextPlan 不再引用该 memory。
### Context Quality
- selected、summarized、offloaded、dropped 资源有原因和 hash。
- context resource 的 source version、authority、sensitivity、purpose、view 和 TTL。
- token/byte budget、context window 和 provider projection 可解释。
- context ordering、system/policy/data authority 分层保持。
- stale、missing、quarantined、scope mismatch 资源不能静默进入 request。
- context overflow、compaction 和 fallback 产生可追踪 quality event。
### Context SLI
- context compile success。
- resource selection completeness。
- stale/unknown resource rate。
- context token/byte budget breach。
- wrong-scope reference rate。
- compaction loss/regression rate。
- provider projection dropped-constraint rate。
## Event、Log 与 Trace Quality
### Event Quality
- canonical envelope、schema version、layer、durability、sequence、correlation、causation。
- eventId、streamId、streamSeq、attempt、tool、approval、checkpoint 和 tenant scope。
- durable event 原子追加、幂等、CAS、retention、replay 和 projector watermark。
- unknown event、late event、sequence gap、duplicate event 和 terminal uniqueness。
### Event 检查
- occurredAt 与 observedAt 分开；顺序以 sequence，不以 wall clock。
- durable 与 ephemeral 不混用；关键事件不能被 coalesce 或 sampling 丢失。
- `RunCompleted`、`RunFailed`、`RunCancelled` 终态互斥。
- `ToolExecutionCompleted`、`UsageUpdated`、`CheckpointWritten` 有完整 correlation。
- host event 不得成为 durable truth。
### Log Quality
- log 必须有 service、instance、version、trace、scope、event/operation ID。
- sensitive payload 只能 metadata-only、redacted 或受控 artifact ref。
- error log 包含 normalized error、retryability、dependency、runbook code。
- duplicate、missing、late、sampled、dropped 和 redacted 状态可见。
- log retention 与 audit、session、event、privacy policy 分开。
### Trace Quality
- trace/span 关联 run、attempt、provider、tool、queue、store 和 delivery。
- trace sampling 不影响 audit、quality observation、terminal 和 security evidence。
- cardinality 控制不能删除 tenant、provider、contract 或 incident 维度。
- span duration 不替代 durable settlement、side-effect receipt 或 deletion receipt。
### Event/Log/Trace SLI
- event durable commit rate。
- sequence gap、duplicate、unknown、late event rate。
- projector lag、cursor recovery success、replay success。
- redaction failure、missing correlation、trace drop rate。
- audit completeness、retention/deletion reconciliation rate。
## Backup、Archive 与 Restore Quality
### Backup 质量对象
- session/event store、artifact metadata/blob、config、catalog、queue state、audit、quality observation 和 DSAR records。
- backup manifest、snapshot version、scope、region、encryption key、retention、RPO/RTO。
- backup copy、archive copy、provider remote copy 和 forensic copy 分开建模。
### Backup 检查
- backup 是否覆盖声明的数据 product 和依赖。
- manifest、object count、checksum、schema、scope 和 lineage。
- backup 时间、watermark、lag、RPO 和 retention。
- 加密、key version、restore principal 和 residency。
- partial backup、orphan blob、missing event、broken reference 和 archive expiry。
### Restore 验证流程
```text
select backup
-> verify manifest/checksum
-> restore isolated scope
-> validate schema
-> validate tenant/scope
-> validate lineage
-> validate retention/legal hold
-> replay projector
-> reconcile counts/receipts
-> run quality suite
-> approve promotion
```
### Restore 规则
- restore 到隔离环境，不能直接覆盖生产事实。
- 不用 restore 后的 projection 替代 immutable source event。
- restore 后重新执行 deletion、DSAR、egress、DLP 和 access checks。
- restore quality 未通过时保持 degraded/hold，不声称 DR 成功。
- 定期 restore drill 进入 production quality SLO 和 incident regression。
## Reconciliation
### Reconciliation 对象
- queue job 与 execution record。
- provider receipt 与 attempt/event/usage。
- artifact manifest 与 blob、preview、remote object。
- session entries 与 event stream/projector/checkpoint。
- memory record 与 recall index/embedding/cache。
- event store 与 audit/security event。
- backup manifest 与 source inventory。
- deletion request 与各 copy deletion receipt。
- DSAR export manifest 与授权范围、对象版本和 hash。
### 对账流程
```text
choose source of truth
-> freeze scope/window/version
-> collect manifests/receipts
-> normalize identity
-> compare existence/hash/status/time
-> classify missing/duplicate/mismatch/unknown
-> open incident or repair plan
-> execute controlled action
-> rerun reconciliation
-> commit evidence
```
### 对账规则
- 先按 stable ID、content hash、event sequence 和 scope 对齐，不能只比 row count。
- 允许最终一致时记录 lag window 和 last known good watermark。
- source 不可查询时标记 unknown，不当作 missing 或 success。
- 对账本身也要有 schema、lineage、retention 和 access control。
- repair 后必须再次对账，不能仅凭命令返回 0 判断成功。
### Reconciliation SLI
- matched ratio、mismatch ratio、missing ratio、duplicate ratio、unknown ratio。
- reconciliation age、repair completion、recheck pass rate。
- provider remote object、backup、deletion 和 DSAR 的未对账数量。
## Drift 与 Anomaly Detection
### Drift 类型
- schema drift：字段、类型、required、enum、版本变化。
- semantic drift：单位、状态、默认值、事件含义变化。
- volume drift：数量、分布、partition、tenant share 异常。
- freshness drift：watermark、source lag、provider latency 变化。
- quality drift：validity、accuracy、duplicate、scope 或 error rate 变化。
- lineage drift：新 consumer、destination、provider、region 或 copy 未注册。
- operational drift：queue、worker、backup、store、catalog 或 rule version 变化。
- privacy/security drift：classification、egress、retention、training 或 credential scope 变化。
### Detection 方法
- contract/schema diff。
- baseline 与 rolling window。
- per-tenant/per-provider/per-region 分层比较。
- robust percentile、rate-of-change、seasonality 和 change-point。
- sequence gap、hash mismatch、receipt mismatch。
- sample-based semantic reference。
- shadow/differential replay。
- provider live smoke 与 catalog freshness。
### Anomaly 规则
- anomaly detection 只产生 finding，不自动修改 source。
- critical scope、secret、regulated、deletion 和 egress 异常采用 hard hold。
- 低置信度 anomaly 标记 observe/inconclusive，不能触发大范围破坏性 rollback。
- 自动 quarantine 必须有可解释 rule、阈值、scope、expiry 和解除条件。
- anomaly model/rule 版本和训练/基线数据 provenance 必须记录。
## Quarantine、DLQ、Replay 与 Backfill
### Quarantine
适用于：
- schema/semantic/scope/lineage/integrity 失败。
- provider unknown、remote object unknown、DLP/scan pending。
- deletion、DSAR、retention 或 residency 无法证明。
- duplicate/poison/late 数据超过 contract 允许范围。
- backup restore 尚未完成质量验证。
Quarantine 必须保存：
- 原始引用或 content hash，不默认复制全部敏感 payload。
- reason codes、contract、rule、scope、watermark、版本和检测时间。
- retryable、replayable、repairable、discardable 状态。
- owner、steward、on-call、expiry、runbook 和 evidence refs。
### Dead Letter
- DLQ 是无法继续按当前 contract 消费的 durable work，不是垃圾桶。
- 每条 DLQ 记录原 job/event、失败 attempt、最后 error、retry count 和 next action。
- DLQ retention、访问和删除独立于主队列。
- poison message 不应无限重试或污染主队列。
- DLQ replay 必须使用新 execution ID、幂等键、scope 和 contract snapshot。
### Replay
- replay 使用 immutable source event、固定 schema、版本、clock、ID 和 policy。
- replay 不产生真实外部副作用，除非有独立 sandbox 和 side-effect oracle。
- replay 结果写新 projection、repair branch 或 evidence，不覆盖源事实。
- replay 前重新检查 retention、deletion hold、egress、tenant 和 credential。
- replay 失败仍保留 original 和 replay evidence。
### Backfill
- backfill 必须有范围、版本、依赖、幂等键、checkpoint、预算、限速和 rollback plan。
- backfill 不应越过当前 tenant、purpose、region 或 retention policy。
- 新结果使用新 `versionId`、transform version 和 lineage。
- backfill 中途失败从 checkpoint 恢复，不重复不可逆副作用。
- backfill 完成后执行 count、hash、semantic、lineage、SLO 和 reconciliation。
## Incident、Severity 与 Runbook
### 严重度
- `sev0`：跨租户泄露、secret/regulated 外发、错误删除、audit integrity 破坏或大范围错误副作用。
- `sev1`：critical data product 不可用、provider/queue/event 全局质量失败、关键删除/DSAR 超时。
- `sev2`：单租户或单 provider 重要质量退化、可控 backlog、局部 drift 或重复执行风险。
- `sev3`：低风险字段、非关键 view、dashboard、文档或非阻塞规则退化。
### 事故状态机
```text
Detected
-> Triaged
-> Contained
-> Investigating
-> Repairing
-> Verifying
-> Resolved
-> Reviewed
```
### Triage 问题
- 影响哪些 tenant、workspace、provider、region、data product 和版本。
- 影响哪个 quality dimension、SLO、error budget 和业务流程。
- 是否存在 scope leak、secret、egress、retention、deletion 或 DSAR 风险。
- source of truth 是否可读，是否有 unknown outcome。
- 是否需要停止 ingestion、consumer、provider route、queue、delivery 或 export。
- 最近的 deploy、schema、config、provider、policy、backup、migration 是什么。
### Runbook 结构
1. 触发条件与告警。
2. 影响判定和 dashboard。
3. 证据收集命令与访问范围。
4. containment 操作及禁止操作。
5. owner/steward/on-call/escalation。
6. repair/replay/backfill/rollback 选项。
7. 验证和 reconciliation。
8. 用户、租户、安全、隐私和治理沟通。
9. 回归测试和 postmortem。
10. 关闭标准与证据。
### Containment 规则
- 质量不确定时优先 hold/quarantine，不优先全局删除。
- security/privacy 风险立即冻结 egress、远端上传、cache reuse 和低信任 delivery。
- provider drift 可降低 route 或 quarantine capability，不能改写历史响应。
- queue poison 或 duplicate risk 时暂停相关 partition/consumer。
- audit、event、source facts 只读保护，repair 通过新版本或补偿事件完成。
## Deletion、DSAR 与 Retention Quality
### 生命周期对象
- session、branch、run、turn、attempt、tool result、memory、artifact、event、trace、log、cache、queue、backup、provider remote object、export package、forensics copy。
- 每个对象有 retention class、TTL、legal hold、deletion dependency、owner 和 scope。
### 删除质量检查
- 删除请求身份、scope、purpose、authorization、createdAt、deadline。
- inventory 是否覆盖所有 derived、cached、backup、remote 和 export copies。
- delete task 是否入 durable queue，有 lease、retry、DLQ 和 receipt。
- local delete、index delete、preview delete、backup mark、remote delete 的状态分别记录。
- deletion 完成不能只检查主表 row count。
- legal hold、audit、incident、backup 和 unknown outcome 需要明确保留或延迟删除。
- 删除后 recall、ContextPlan、provider egress、cache 和 export 不再引用对象。
### DSAR 质量
- subject identity、scope、tenant、purpose、request version 和 authorization。
- export manifest 的对象清单、版本、hash、redaction、遗漏和原因。
- delete/forget/rectify/limit request 的每个副本状态。
- provider remote object、embedding、backup、log 和 artifact view 单独对账。
- export package 本身有 sensitivity、retention、expiry、access audit 和 deletion path。
- DSAR unknown 或 timeout 不得声明完成。
### Retention SLI
- expired objects pending deletion。
- deletion receipt completeness。
- remote delete unknown ratio。
- DSAR on-time completion ratio。
- legal hold conflict count。
- orphan copy count。
- post-delete reference rate。
- retention policy drift rate。
### 删除修复
- 先停止新传播，再建立 copy inventory。
- 对可删除副本执行幂等 delete；对不可删除副本记录 limitation 和 owner。
- 使用 crypto-shred、index purge、cache invalidation、provider delete 或 expiry 组合。
- 删除失败进入 incident/quarantine，不用本地成功覆盖远端未知。
- 完成后运行 lineage、search、recall、egress、backup 和 reconciliation checks。
## Tenant、Residency 与 Egress Checks
### Scope 检查
- tenant/workspace/session/run/attempt/tool/artifact/event/queue/cache key 一致。
- provider response、job payload、artifact URI 和 model output 不能覆盖 server-side scope。
- cross-tenant read 返回 stable `resource_not_available` 或 `scope_denied`，不泄露存在性。
- worker lease、queue partition、backup restore 和 replay 都重新授权 scope。
- aggregate dashboard 必须限制小样本和高敏感 tenant 推断。
### Residency 检查
- tenant policy、workspace preference、provider jurisdiction、deployment region、artifact/event/backup region。
- region unknown、catalog stale、fallback region mismatch 默认 hold 或 deny。
- backup、archive、remote object、support diagnostic 和 shadow 流量也属于 destination。
- provider egress 改变时重新评估 purpose、classification、retention、training 和 consent。
### Egress Quality
- EgressSnapshot 的 provider、api family、model、deployment、region、view、bytes、tokens、purpose、retention 和 policy version。
- request projection 是否只包含允许的 fields、parts、artifact views 和 redaction。
- DLP、secret、PII、regulated 和 URL/SSRF 检查结果。
- fallback、hedge、shadow、canary、retry 是否创建新的 egress evidence。
- remote upload、response、cache、log、trace 和 export 都有 destination lineage。
### Egress SLI
- denied egress blocked-before-send ratio。
- unknown classification/region/retention rate。
- redaction failure、secret detection、scope mismatch rate。
- provider remote object reconciliation ratio。
- cross-region fallback violation count。
- post-deletion egress reference count。
## Sampling 与 Great-Expectations-like Checks
### Sampling 策略
- full scan：critical event、audit、deletion、scope、integrity、small dataset。
- stratified sample：按 tenant、provider、region、status、severity、version、partition 分层。
- reservoir sample：大规模持续流。
- boundary sample：最小值、最大值、空值、异常值、版本切换点。
- temporal sample：窗口开始、峰值、窗口结束、late data。
- replay sample：真实案例的脱敏最小复现。
### Sampling 约束
- sample plan 记录 population、seed、method、size、scope、privacy profile。
- 高风险字段采样前执行最小化、tokenization 或 metadata-only。
- sample 不能改变 source of truth 或业务状态。
- 统计置信不足时标记 inconclusive。
- sampling 不替代关键 hard gate；critical scope 可要求 full scan。
### Expectation 分类
- envelope expectations。
- schema expectations。
- field expectations。
- cross-field semantic expectations。
- cross-record consistency expectations。
- reference/foreign-key expectations。
- event sequence expectations。
- lifecycle/retention/deletion expectations。
- scope/residency/egress expectations。
- SLO and freshness expectations。
### 规则版本
- 每个 expectation 有版本、owner、review date、severity、threshold、sampling、evidence policy。
- 规则变更有 diff、影响评估、历史回放、灰度和 rollback。
- 规则不能在 incident 期间偷偷放宽为 pass。
- exception 必须有 scope、reason、approver、expiry 和 residual risk。
## CI、Production Gate 与 Release
### CI 检查
- contract/schema compile、typecheck、lint。
- fixture schema、semantic、lineage、privacy 和 scope validation。
- provider adapter、event normalizer、tool、structured、multimodal 和 usage conformance。
- queue lease、dedupe、DLQ、replay、backfill 和 repair testkit。
- deletion、DSAR、retention、residency、egress 和 backup restore checks。
- drift/anomaly baseline、dashboard query 和 runbook smoke。
- incident regression、replay compatibility、migration dual-read/dual-write。
### Production Gate
- data contract active、owner/steward/on-call 已分配。
- schema、semantic、lineage、quality SLO 和 catalog evidence 新鲜。
- provider、artifact、event、queue、backup 和 deletion checks 通过。
- no open sev0/sev1 quality/security/privacy incident。
- error budget 未耗尽或有明确批准的 exception。
- restore drill、reconciliation、retention 和 DSAR gate 不为 unknown。
- repair/backfill 有 checkpoint、budget、rollback 和 observer。
### Release 流程
```text
Draft
-> Contract Review
-> Fixture/Rule Validation
-> Replay Historical Data
-> Shadow Observe
-> Canary Scope
-> Production Gate
-> Active
-> Monitor
-> Rollback or Supersede
```
### 发布后观察
- schema/semantic failure、freshness、completeness、accuracy、duplicate、scope、lineage。
- queue/provider/event/backup latency 和 backlog。
- error budget burn、quarantine age、DLQ age、repair lag。
- deletion/DSAR/egress/security/privacy 负向指标。
- tenant/provider/region 维度的异常，而不是只看全局平均。
## Repair、Rollback 与 Recovery
### Repair 原则
- 原始事实、immutable event、audit 和 provider receipt 不原地修改。
- repair 通过新版本、补偿事件、derived view、upcaster、index rebuild 或 metadata correction。
- repair plan 明确范围、输入版本、输出版本、幂等键、预算、权限、风险和验证。
- repair 只能使用当前允许的 tenant、purpose、region、retention 和 egress。
- repair 失败进入 quarantine/incident，不能反复重放不可逆副作用。
### Repair 类型
- schema upcast/downcast。
- missing metadata enrichment。
- projection rebuild。
- duplicate collapse with provenance。
- index/cache invalidation and rebuild。
- artifact view regeneration。
- usage/cost reconciliation correction。
- queue job requeue with idempotency receipt。
- provider remote object status/delete reconciliation。
- deletion propagation and orphan cleanup。
### Rollback
- rollback 到已验证的 contract、schema、rule、adapter、config 或 projection version。
- rollback 不抹掉 bad version 产生的事实；新 projection 标记 source version。
- 对有副作用的数据，不执行“反向写入”除非有独立 compensating contract。
- rollback 需检查 current data、pending queue、active leases、provider requests、retention 和 incident hold。
- rollback 完成后重新运行 quality、security、privacy、lineage 和 reconciliation。
### Recovery 状态
```text
Detected -> Held -> Diagnosed -> Planned
-> Repairing -> Reconciled -> Verified -> Released
```
### Recovery 不变量
- `Held` 数据不得继续进入高风险 consumer/provider。
- `Repairing` 期间保留原始版本和 checkpoint。
- `Reconciled` 仅表示 source/copy 差异已解释，不自动表示业务正确。
- `Verified` 需要质量、scope、lifecycle 和 evidence checks。
- `Released` 必须更新 catalog、dashboard、incident 和 downstream watermark。
## 生命周期与状态机
### DataRecord 状态
```text
Discovered
  -> Registered
  -> Ingested
  -> Validating
  -> Accepted | Degraded | Quarantined | Rejected
  -> Projected
  -> Published
  -> Stale | Expired
  -> DeletionPending
  -> Deleted | DeletionUnknown | LegalHold
  -> Archived | Restored
```
### Quality Check 状态
```text
Scheduled
-> Running
-> Observed
-> Evaluated
-> Passed | Failed | Warning | Unknown | Skipped
-> IncidentOpened | EvidenceCommitted
```
### Quality Incident 状态
```text
Detected
-> Triaged
-> Contained
-> Investigating
-> Repairing
-> Verifying
-> Resolved
-> Reviewed
```
### 状态不变量
- `Accepted` 必须有 schema、semantic、scope 和 lineage evidence。
- `Published` 必须满足 consumer hard gate 或有明确 degraded contract。
- `Quarantined` 不能被普通 consumer 读取，除非 operator scope 明确允许。
- `Deleted` 必须完成允许的所有 copy receipt；unknown 单独保留。
- `Restored` 必须重新验证 schema、scope、lineage、retention 和 egress。
- terminal quality event 后不得出现未关联的新业务事实。
## 决策流程
### 数据进入前
```text
authenticate source
-> resolve tenant/scope/purpose
-> resolve contract/version
-> classify sensitivity
-> validate schema
-> validate semantic/scope/lineage
-> reserve queue/storage/quality budget
-> accept | degrade | quarantine | reject
```
### 数据传播前
```text
check consumer contract
-> freshness/completeness/accuracy status
-> provider/artifact/event/host egress
-> residency/retention/deletion hold
-> select view/redaction/summary
-> emit destination lineage
-> publish or hold
```
### 异常处理
```text
detect observation
-> dedupe/group
-> assess scope and severity
-> open incident
-> contain/quarantine
-> choose replay/backfill/repair/rollback
-> reconcile
-> verify SLO and safety
-> release and regression
```
### 质量 Gate 决策表
| 条件 | 结论 | 动作 |
|---|---|---|
| schema invalid | reject/hold | quarantine，通知 producer |
| semantic invalid | hold | owner/steward 分诊 |
| stale but allowed | degraded | 限制 consumer，标记 stale |
| missing critical lineage | blocking | 禁止 provider/export/memory |
| duplicate event | dedupe/incident | 保留原始事实和 receipt |
| unknown provider status | unknown | 查询或暂停，不声称成功 |
| residency unknown | deny/hold | 不发送、不归档到未知区 |
| deletion remote unknown | degraded | 不声明 fully deleted |
| error budget exhausted | release block | 冻结非关键发布/启动 review |
| restore validation failed | hold | 隔离恢复环境并修复 |
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### Model 与 Provider
- Provider quality 使用 `ResolvedModel`、capability snapshot、adapter version、contract version 和 receipt。
- request/response/event normalized quality 与业务模型质量分开。
- usage/cost、retry/fallback、unknown outcome 和 remote object 进入 lineage 与 ledger。
- provider drift 触发 capability quarantine、routing degradation 或 incident。
### Prompt 与 Context
- PromptSection、ContextResource、ContextPlan 都是有 schema、purpose、authority、sensitivity、version 和 lineage 的数据对象。
- context quality 检查 selected、summarized、offloaded、dropped 的完整性和理由。
- context compiler 不得把 stale、quarantined、wrong-scope 或 deletion-pending 数据放入 request。
- prompt 文案不能替代 egress、DLP、policy、retention 和 quality hard gate。
### Tool
- ToolCall、ToolResult、ToolExecution、ArtifactRef 和 side-effect receipt 形成完整 lineage。
- tool result quality 检查 schema、business semantics、truncation、artifact ref、status 和 execution ID。
- tool provider error、retry、unknown 和 duplicate execution 进入 reconciliation。
- quality 修复不能重放未查询状态的非幂等工具。
### State 与 Event
- Session/Event Store 是 durable semantic facts 的 source of truth。
- projector、cache、host delivery、memory、artifact view 和 backup 都是可对账的副本。
- event sequence、checkpoint、CAS、replay compatibility 和 schema version 属于质量门。
- terminal event、checkpoint 和 usage settlement 不可由 dashboard 或 log 推断。
### Policy、Privacy 与 Security
- quality 检查消费冻结的 PolicySnapshot、EgressSnapshot、ScopeRef 和 DataContractVersion。
- classification unknown、scope mismatch、residency unknown、secret/regulated 发现默认 fail-closed。
- quality dashboard、sample、repair、backfill 和 evidence 也受 privacy、retention 和 access control。
- repair 和 replay 不得通过更宽 provider 或更长 retention 绕过原策略。
### Harness 与 Durable Queue
- Harness 管理质量 gate、预算、取消、checkpoint、queue job、lease 和恢复。
- Quality job 使用 durable queue，拥有 idempotency key、lease、heartbeat、fencing token、retry、DLQ。
- quality observation、incident、repair、backfill、reconciliation 和 deletion task 必须可恢复。
- worker 使用 frozen snapshot，不用最新全局配置覆盖运行中 job。
## 安全、隐私与可观测性
### 安全质量
- scope、tenant、workspace、worker、provider、artifact、event、backup 和 dashboard 的隔离。
- secret、PII、regulated、credential、tokenization map 和 forensic data 的分类和最小化。
- audit/event/hash/sequence/receipt 的完整性。
- repair、backfill、replay、delete、export 和 break-glass 的 actor、scope、reason、approval 和 evidence。
- provider egress、remote object、region、retention、training 和 deletion contract。
### 隐私质量
- quality observation 不复制全部 prompt、hidden reasoning、tool raw output 或 secret。
- sample、golden、dashboard、log、trace、backup 和 export 使用不同 view/retention。
- DSAR、forget、consent withdrawal 和 retention expiry 传播到派生质量数据。
- production-derived regression 需脱敏、去重、最小化、provenance 和短 TTL。
- unknown deletion 不得被误报为 completed。
### 可观测性事件
```text
quality.check.scheduled
quality.check.started
quality.observation.recorded
quality.expectation.failed
quality.drift.detected
quality.anomaly.detected
quality.quarantine.opened
quality.reconciliation.diverged
quality.repair.started
quality.backfill.completed
quality.rollback.executed
quality.incident.opened
quality.incident.resolved
quality.deletion.verified
quality.restore.verified
```
### 关键指标
- check pass/fail/warning/unknown/skipped。
- dimension SLI、SLO burn、error budget、last good watermark。
- quarantine/DLQ depth、age、replay、repair、backfill 和 rollback rate。
- schema/semantic/scope/lineage/integrity violation。
- provider/queue/artifact/event/memory/backup quality。
- deletion/DSAR/retention/residency/egress reconciliation。
- incident MTTD、MTTA、MTTC、MTTR、reopen rate。
- false positive、false negative、flaky、inconclusive 和 rule coverage。
### 证据
- observation 有 rule version、contract、scope、window、sample、watermark、evidence ref。
- repair/backfill/rollback 有 plan、actor、lease、checkpoint、input/output version、result、verification。
- dashboard 只投影 evidence，不成为 source of truth。
- critical evidence 不被 sampling、coalescing、普通 retention 或日志清理删除。
## 测试策略
### 分层
1. schema/type unit。
2. semantic rule unit。
3. contract compatibility unit。
4. quality expectation component。
5. producer/consumer integration。
6. queue/lease/DLQ/replay integration。
7. provider/artifact/event/memory/backup reconciliation。
8. privacy/security negative。
9. production-like shadow/canary。
10. restore、repair、rollback 和 incident drill。
### Deterministic Testkit
- fixed clock、ID、random、scheduler。
- fake producer、consumer、provider、queue、store、artifact、memory 和 backup。
- scripted late、duplicate、missing、malformed、drift、unknown、timeout 和 crash。
- fake DLP、classification、policy、egress、retention、delete 和 receipt。
- side-effect recorder、lineage recorder、audit recorder 和 evidence store。
### 质量场景
- happy path 只是最小基线，不是完成标准。
- 每个维度覆盖正常、边界、缺失、重复、乱序、过期、错误、unknown、恢复和回滚。
- 每个数据产品覆盖 producer、consumer、provider、artifact、event、backup 和 deletion copies。
- 每个 contract 变更覆盖旧数据 replay、新数据 write、dual-read、dual-write 和 rollback。
- 每个 incident 修复覆盖最小复现、相邻样本、历史回放和生产指标 guard。
### Property-based / Fuzz
- 任意 event split、字段顺序、unknown field、Unicode、null/missing、duplicate 和 late event。
- 任意 queue redelivery、lease expiry、worker crash、checkpoint 和 fence。
- 任意 artifact view、MIME、range、size、hash、remote status。
- 任意 provider usage、error、retry-after、finish reason、stream close。
- 约束：不应跨 tenant、不应错误 completed、不应丢 lineage、不应产生未授权 egress。
### 评测与线上反馈
- Evaluation 检查 trajectory、event、state、side effect、usage、cost、latency 和 recovery。
- LLM judge 只能评开放语义质量，不能判断 scope、receipt、删除、权限或数据库事实。
- production feedback 经过脱敏、审核、最小复现和污染防护后进入 regression dataset。
- 线上质量趋势不能绕过 CI gate，也不能将 inconclusive 计为 pass。
### 测试数据治理
- synthetic 优先；真实案例只使用最小化、脱敏、tokenized 或 restricted profile。
- fixture、sample、observation、incident、backup、forensics 和 export 分别定义 retention。
- 质量测试不使用生产 secret，不访问未授权 tenant，不执行真实写副作用。
- DSAR/deletion/retention 测试需要验证 test copy、cache、backup、remote object 和 evidence。
## 反模式
### 定期跑一条 COUNT(*)
表现：只比较表行数，结果稳定就报告质量正常。
后果：无法发现字段 invalid、重复事件、sequence gap、错误 tenant、stale、lineage 缺失、provider remote orphan 或删除残留。
修复：结合 schema、semantic、freshness、completeness、accuracy、consistency、uniqueness、timeliness、lineage 和 lifecycle checks。
### 只做 schema validation
表现：JSON 能解析就进入下游。
后果：单位、状态、scope、tool pairing、receipt、purpose 和业务语义错误被传播。
修复：执行 cross-field、cross-record、source receipt、scope、lineage 和 semantic validation。
### 只看 ingestion 成功数
表现：队列接受消息就算数据可用。
后果：可能尚未 durable persist、未过 quality gate、未投影、未对账或已进入错误 region。
修复：区分 accepted、validated、persisted、projected、published、reconciled 和 usable。
### 直接修写原始事实
表现：用 SQL update 把错误值改成期望值。
后果：破坏审计、无法解释来源、污染回放和 incident 证据。
修复：新版本、补偿事件、derived view、upcaster、repair plan 和 evidence。
### 把 lineage 当权限
表现：因为知道数据来自某处就允许读取或外发。
后果：绕过 tenant、purpose、classification、egress 和 retention。
修复：lineage、Policy、Privacy、Scope 和 Egress 独立决策。
### 把 stale 当 fresh
表现：数据最终会到，所以先当作当前数据使用。
后果：模型 context、路由、配额、删除和业务决策使用过时事实。
修复：记录 source watermark、freshness SLI、consumer freshness ceiling 和 hold/degraded 策略。
### 把缺失当零
表现：没有 usage、receipt、事件或字段时填 0 或空字符串。
后果：掩盖 unknown outcome、账单差异、工具失败和安全证据缺失。
修复：明确 missing、unknown、not_applicable、estimated 和 observed。
### 把 DLQ 当垃圾桶
表现：错误消息移入 DLQ 后不再关注。
后果：数据丢失、重复重试、DSAR 残留、业务 backlog 和无 owner。
修复：DLQ 有 owner、SLO、reason、retention、replay、repair、discard 和 incident。
### 无隔离地回放或回填
表现：直接对生产队列、provider、工具或用户 session replay。
后果：重复副作用、跨租户访问、provider 外发和成本爆炸。
修复：sandbox、scope snapshot、idempotency、side-effect oracle、预算、checkpoint 和 dry-run。
### 用平均质量分掩盖硬失败
表现：总体 99.9% 通过，所以接受一次跨租户或删除错误。
后果：安全和隐私损害不可用平均值抵消。
修复：critical dimension hard gate，按 tenant/provider/region 分层并 fail-closed。
### 长期放宽规则
表现：把 drift/异常标为 observe-only，永不回收。
后果：质量债务、误用数据和未知风险常态化。
修复：exception 有 expiry、owner、审批、风险、回滚和复查。
### 用 dashboard 代替 source of truth
表现：图表显示绿色就认为数据已可靠。
后果：dashboard 延迟、采样、缓存或 query bug 隐藏事实差异。
修复：dashboard 追溯到 canonical observation、event、receipt、manifest 和 audit。
## 实施清单
### Contract 与 Catalog
- [ ] 建立 data product、DataContract、schema、semantic rule、quality SLO 和 failure policy。
- [ ] 为每个产品分配 owner、steward、producer、consumer、on-call 和 runbook。
- [ ] 注册 source、destination、copy、view、region、provider、retention 和 deletion dependency。
- [ ] 定义 reader/writer compatibility、schema migration、dual-read、dual-write 和 rollback。
### Quality Engine
- [ ] 实现 schema、semantic、freshness、completeness、accuracy、consistency、uniqueness、timeliness、integrity 和 lineage checks。
- [ ] 实现 QualityObservation、SloEvaluation、ErrorBudget、QualityIncident 和 EvidenceBundle。
- [ ] 支持 full scan、stratified、reservoir、boundary、temporal 和 replay sampling。
- [ ] 规则版本化、可解释、可回放、可审计并有 expiry。
### Agent 数据平面
- [ ] 覆盖 ingestion、queue/job/lease、provider/model/usage、artifact/file、memory/context、event/log/trace、backup/restore。
- [ ] 对 provider receipt、tool execution、artifact manifest、event sequence、checkpoint 和 usage ledger 做 reconciliation。
- [ ] 对 tenant、workspace、scope、residency、egress、classification、retention、deletion 和 DSAR 建立 hard gate。
- [ ] 将 stale、missing、unknown、quarantined、degraded 和 rejected 明确建模。
### Quarantine 与恢复
- [ ] 实现 quarantine、DLQ、replay、backfill、repair、rollback、checkpoint、lease 和 fencing。
- [ ] 保留原始事实、hash、lineage、reason、scope、版本和 evidence。
- [ ] repair/backfill/replay 不覆盖 immutable facts，不产生未授权副作用。
- [ ] 完成后执行质量、scope、lineage、lifecycle、security/privacy 和 reconciliation verification。
### SLO 与运营
- [ ] 定义 freshness、completeness、schema/semantic validity、accuracy、consistency、uniqueness、timeliness、lineage、deletion、restore SLI。
- [ ] 建立 global、tenant、workspace、provider、region 和 data product dashboard。
- [ ] 连接 error budget、release gate、quarantine age、DLQ age、incident severity 和 on-call。
- [ ] 编写 sev0-sev3 runbook、containment、升级、恢复、沟通和关闭标准。
### CI 与生产
- [ ] CI 执行 contract/schema/semantic/lineage/privacy/security/replay/repair/restore suite。
- [ ] production gate 检查 owner、catalog freshness、SLO、error budget、reconciliation、deletion 和 restore evidence。
- [ ] 发布采用 shadow、canary、observe、rollback 和 versioned evidence。
- [ ] 事故最小复现自动进入 regression dataset，并有污染、脱敏和 retention 控制。
## 五个参考项目的启发来源
### Pi
- headless loop、session tree、event stream 和 compaction 说明质量系统应验证语义状态、事件顺序和恢复，而不是只看最终文本。
- CLI/TUI/RPC 共用 runtime 启发数据质量契约与 Host projection 分离。
- 可恢复 session 启发 checkpoint、lineage、replay 和 post-repair verification。
### Grok Build
- actor、permission decision、并行工具、路径锁和 sandbox 说明 queue、tool、scope、side-effect receipt 需要独立质量检查。
- folder trust 与 fail-closed 思路启发数据 quality gate 不能把未知 scope 当允许。
- 明确状态机启发 quarantine、repairing、verifying 和 recovered 的生命周期设计。
### OpenCode
- session/message/part、client/server、event bus 和 projector 启发 canonical facts、derived views、event quality 和 reconciliation 分层。
- snapshot、patch、revert 说明 repair/rollback 必须保留版本与可恢复证据。
- MCP/LSP 与扩展模型启发 lineage、provider/artifact/event 多目的数据副本必须进入 inventory。
### Claude Code
- permissions、hooks、subagents、skills、memory 和 task workflow 说明 context、memory、tool、approval 和扩展数据必须有 scope、purpose、quality 和恢复路径。
- 用户可见的计划、进度和结果交付启发 quality dashboard 与 Host projection 不应成为事实源。
- 非权威源码定位提醒质量规则必须落在本地 contract、event、receipt 和 evidence 上。
### OpenClaw
- AgentHarness registry、agent-core、provider runtime、tool/sandbox/elevated 分层启发数据质量控制面与数据面分离。
- 多 channel gateway 说明 delivery、event、artifact、notification 和 remote copy 也要做质量与对账。
- 事务化插件注册启发 data contract、catalog、owner、quarantine、rollback 和 extension provenance。
## Definition of Done
- [ ] 每个关键 data product 都有 DataContract、owner、steward、on-call、schema、semantic rules 和 quality SLO。
- [ ] 质量系统覆盖 schema、semantic、freshness、completeness、accuracy、consistency、uniqueness、timeliness、integrity 和 lineage。
- [ ] ingestion、queue、provider、artifact、memory、event、log、backup、remote object 和 deletion 都有质量检查与 reconciliation。
- [ ] quality SLI、SLO、error budget、dashboard、incident severity 和 runbook 已连接。
- [ ] drift/anomaly、quarantine/DLQ、replay/backfill、repair/rollback 和 restore drill 可运行。
- [ ] tenant、residency、egress、retention、deletion、DSAR、DLP 和 privacy checks 为 hard/soft gate 明确分层。
- [ ] CI、production gate、shadow、canary、release、rollback 和 incident regression 有版本化证据。
- [ ] 修复不覆盖 immutable facts，不把 unknown、stale、missing 或 inconclusive 伪装为 success。
- [ ] dashboard、catalog 和 report 都能追溯到 durable observation、event、receipt、manifest 和 audit。
- [ ] 故障恢复会区分 stale、missing、unknown、quarantined、degraded 和 rejected，并在 replay、backfill、repair、rollback 前完成 scope、privacy、egress 与 reconciliation 检查。
