# Data Governance Engineering 细粒度工程设计

> 本文把 Data Governance 设计为贯穿 Model、Prompt、Context、Tool、State/Memory、Policy、Harness、Provider Runtime、Artifact、Event、Operations、Security 和 Privacy 的数据控制系统。
>
> 依据仅来自当前目录已有参考架构、Agent Harness、Prompt、Context、Tool、State/Memory、Permission/Sandbox、Subagent、Event/Observability、Evaluation、Coding Agent、Provider Runtime、Provider Routing、Provider Runtime Conformance、Artifact、Multi-tenant、Host Adapter、Workspace Isolation、Production Operations、Security Operations、Privacy、Cost Governance 与本地五个参考项目源码调研结论；不依赖 README，不新增网络搜索结论。
>
> **边界声明：** Data Governance 不是数据库字段命名规范。它不等于给表增加 `tenant_id`、统一列名或编写一份 schema style guide，而是让每个数据对象的来源、所有者、分类、目的、权限、lineage、质量、驻留、加密、保留、删除、导出、外发、派生副本和事故恢复都可发现、可决定、可验证、可审计。

## 目录

1. [目标与非目标](#目标与非目标)
2. [核心判断与职责边界](#核心判断与职责边界)
3. [治理范围与数据平面](#治理范围与数据平面)
4. [总体架构与控制面](#总体架构与控制面)
5. [Data Inventory、Catalog 与 Ownership](#data-inventorycatalog-与-ownership)
6. [Classification、Purpose 与 Legal Basis](#classificationpurpose-与-legal-basis)
7. [Lineage、Provenance 与派生关系](#lineageprovenance-与派生关系)
8. [Schema、Data Contract 与质量 SLO](#schemadata-contract-与质量-slo)
9. [核心数据模型与 TypeScript 接口](#核心数据模型与-typescript-接口)
10. [生命周期与状态机](#生命周期与状态机)
11. [访问控制与 Least Privilege](#访问控制与-least-privilege)
12. [Tenant、Workspace 与 Scope Boundary](#tenantworkspace-与-scope-boundary)
13. [Provider、Artifact、Memory、Event、Log 与 Backup Copies](#providerartifactmemoryeventlog-与-backup-copies)
14. [Residency、Cross-border 与 Egress](#residencycross-border-与-egress)
15. [Encryption、Key Lifecycle 与 Crypto-shred](#encryptionkey-lifecycle-与-crypto-shred)
16. [DLP、Scanning 与 Redaction](#dlpscanning-与-redaction)
17. [Retention、TTL、Legal Hold 与 Archive](#retentionttllegal-hold-与-archive)
18. [Deletion、Export 与 DSAR](#deletionexport-与-dsar)
19. [Reconciliation 与治理证明](#reconciliation-与治理证明)
20. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
21. [决策流程](#决策流程)
22. [故障恢复与安全降级](#故障恢复与安全降级)
23. [Incident Response 与 Runbook](#incident-response-与-runbook)
24. [可观测性、指标与报告](#可观测性指标与报告)
25. [测试策略与 Evaluation](#测试策略与-evaluation)
26. [治理 Board 与责任制度](#治理-board-与责任制度)
27. [反模式](#反模式)
28. [实施清单](#实施清单)
29. [五个参考项目的启发来源](#五个参考项目的启发来源)

## 目标与非目标

### 目标

Data Governance Runtime 必须能够：

- 建立覆盖输入、Context、Prompt、ModelRequest、ToolCall、ToolResult、Memory、Artifact、Session、Event、Trace、Log、Cache、Queue、Backup 和 Provider remote object 的 data inventory。
- 为每个逻辑数据对象记录来源、owner、steward、tenant、scope、sensitivity、purpose、legal basis/consent、retention、region、provider egress、加密、访问、删除和派生关系。
- 区分 logical object、immutable version、view、projection、cache copy、backup copy、remote copy 和 audit evidence。
- 让 `public | internal | confidential | secret | regulated` 与 PII、credential、source_code、customer_data、legal_hold 等标签跨模块一致。
- 把 purpose limitation、minimum necessary、least privilege、data quality 和 provider egress 变成运行时决策，而不是静态文档。
- 为 schema、字段语义、数据契约、lineage、质量 SLO、freshness、完整性、去重和 reconciliation 提供端口。
- 处理 tenant/workspace/session/run/subagent 的边界，以及 provider、artifact、memory、event、log、backup 的每个副本。
- 支持 region/data residency、cross-border、encryption、key rotation、DLP、retention、TTL、legal hold、deletion、export 和 DSAR。
- 在 provider、artifact、memory、event、log、backup、cache 和队列之间传播删除、撤销、隔离和 incident 状态。
- 让治理 board、data steward、security、privacy、SRE、product owner 和 on-call 有可执行的职责与 runbook。
- 用 deterministic fixture、side-effect oracle、replay、fault injection、质量测试和 CI gates 证明控制生效。

### 非目标

本文不负责：

- 规定数据库表字段的命名、排序、缩写或 ORM 风格。
- 用一个 `tenant_id` 字段替代入口身份、scope-aware ports、缓存隔离、worker lease、artifact 授权和 provider egress。
- 代替组织法务决定具体法律依据、通知义务、保存期限或监管解释。
- 把隐私政策文字、用户勾选、模型拒答或 provider 控制台开关当作完整治理控制。
- 规定某个具体数据库、数据湖、云 KMS、DLP 产品、SIEM 或 catalog 产品。
- 把 lineage 记录当作授权；知道数据来自哪里不等于可以访问或外发。
- 把平均数据质量分数抵消一次跨租户泄露、secret 暴露、错误删除或错误驻留。
- 把完整 prompt、hidden reasoning、原始 secret、所有工具输出或所有 provider payload 默认纳入长期保存。
- 让模型、workspace 文件、MCP 描述、plugin 或 provider response 自行扩大 purpose、scope、retention 或 egress。

### 核心公式

```text
Data Governance Quality
  = Inventory Completeness
  × Ownership Clarity
  × Purpose Correctness
  × Lineage Integrity
  × Quality SLO
  × Access Enforcement
  × Lifecycle Verifiability
  × Incident Recoverability
```

## 核心判断与职责边界

### 核心判断

```text
Inventory tells what exists.
Catalog explains what it means.
Policy decides who may use it and why.
Contracts define producer/consumer expectations.
Lineage explains where it came from and where it went.
State records semantic facts.
Artifact stores large immutable content.
Audit proves governance decisions.
Harness coordinates lifecycle and recovery.
```

- Data Governance 关注数据对象的完整生命周期，而不是单一存储系统。
- 数据分类、目的、ownership、quality 和访问权限是相互独立的轴。
- 一个 public 数据也可能没有 instruction authority；一个高 authority policy 也可能不能外发。
- `allow read` 不等于 `allow persist`、`allow model inference`、`allow provider egress` 或 `allow export`。
- 删除一个主对象不等于删除所有 derived copies、backup、cache、remote object 或日志引用。
- 数据契约是 producer/consumer 的语义协议，不是字段命名规范。

### 职责边界

| 组件 | 负责 | 不负责 |
|---|---|---|
| `DataInventory` | 逻辑对象、版本、来源、scope、copies 和状态 | 选择模型措辞 |
| `Catalog` | 语义、owner、steward、分类、purpose、schema 和 SLO | 直接授权访问 |
| `ClassificationService` | sensitivity、PII、secret、regulated、tags | 自动给任意数据授权 |
| `PurposePolicy` | purpose、basis、consent、兼容性 | 代替法务解释 |
| `LineageService` | source、transform、consumer、derived refs | 修改事实数据 |
| `DataContractRegistry` | producer/consumer schema、质量、兼容、版本 | 执行工具 |
| `QualityMonitor` | completeness、freshness、validity、drift、SLO | 修写原始事实 |
| `EgressEvaluator` | destination、provider、region、view、retention | 强制 OS 网络隔离 |
| `DlpScanner` | secret、PII、regulated、恶意内容检测 | 直接执行工具 |
| `ArtifactStore` | blob、view、scan、scope、版本、删除 | 选择 prompt 内容 |
| `Session/EventStore` | semantic facts、CAS、replay、checkpoint | 保存所有原文副本 |
| `MemoryStore` | provenance、TTL、forget、recall | 绕过 privacy policy |
| `KeyManager` | key version、加密、轮换、撤销 | 将 key 值交给模型 |
| `AccessBroker` | least privilege、短 lease、授权快照 | 修改领域数据 |
| `GovernanceBoard` | 标准、风险接受、owner 冲突、例外 | 无审计手工操作生产 |
| `Harness` | 装配、快照、监督、取消、恢复和交付 | 变成全局数据仓库 |

## 治理范围与数据平面

### 数据对象层次

```text
logical data product
  -> dataset/resource
  -> immutable version
  -> field/part/content view
  -> runtime projection
  -> cache/queue/temp copy
  -> backup/archive copy
  -> provider/remote copy
  -> audit/forensics reference
```

### Agent 数据平面

覆盖：

- Host input、附件、channel metadata、approval、steering、cancel 和 delivery ack。
- `PromptSection`、`ContextResource`、`ContextPlan`、`ModelRequest` 和 raw provider request。
- `Message/Part`、ToolCall、ToolResult、policy、approval、sandbox attestation。
- Session semantic entries、WorkingState、Checkpoint、CompactionEntry 和 MemoryRecord。
- Artifact raw、sanitized、preview、summary、structured、range 和 patch view。
- Canonical event、ephemeral event、trace、log、metric、audit、SIEM 和诊断快照。
- Provider remote file、conversation、cache、batch、embedding、rerank 和 response receipt。
- Workspace snapshot、patch、command output、queue payload、worker temp、backup、export package 和 forensic bundle。

### 控制面与数据面

控制面管理 catalog、ownership、policy、schema、contract、quality、retention、key、region、provider egress、DSAR、incident 和 exception。

数据面只使用冻结的 `ScopeRef`、`PolicySnapshot`、`EgressSnapshot`、`ContractSnapshot`、`DataAccessLease` 和 `DataContractVersion`。

## 总体架构与控制面

### 逻辑拓扑

```text
Host/Auth/TenantContext
  -> Governance Control Plane
     -> Catalog/Inventory/Ownership/Classification/Purpose
     -> Data Contract/Schema/Lineage/Quality
     -> Access/Egress/Residency/Retention/Key/DLP
     -> Deletion/Export/DSAR/Incident/Exception
  -> Harness Run
     -> Context/Prompt/Model/Tool/State/Artifact/Event
  -> Provider/Workspace/Worker/Backup/Host destinations
  -> Reconciliation/Audit/Quality/Operations
```

### 推荐包布局

```text
packages/data-governance/
  contracts.ts inventory.ts catalog.ts ownership.ts stewardship.ts
  classification.ts purpose.ts lineage.ts provenance.ts schema.ts
  quality.ts access.ts scope.ts residency.ts egress.ts dlp.ts
  encryption.ts keys.ts retention.ts legal-hold.ts deletion.ts export.ts
  dsar.ts reconciliation.ts exceptions.ts incidents.ts audit.ts
  adapters/ providers/ artifacts/ memory/ events/ testkit/
```

### 依赖方向

```text
Host -> Harness -> Governance ports
Context/Prompt -> DataPlan/Egress ports
Model/Provider -> DataContract/Egress/RemoteObject ports
Tool/Artifact/Memory/Event -> Inventory/Lineage/Retention ports
Infrastructure -> catalog/store/KMS/DLP implementations
```

Kernel 不导入数据库 schema、对象存储 SDK、KMS SDK 或具体 DLP 产品类型。

## Data Inventory、Catalog 与 Ownership

### inventory 原则

Inventory 是随生命周期更新的资源图，不是静态 spreadsheet：

```text
source -> object/version/view -> classification/purpose
-> consumer/destination -> retention -> copies -> deletion state
```

每个 data object 至少回答：

- 它是什么，哪一版，谁产生，谁拥有，谁负责日常 stewardship。
- 属于哪个 tenant、workspace、project、session、run、subagent 和 scope version。
- sensitivity、tags、authority、purpose、legal basis、consent 和 retention。
- 允许哪些 consumer、provider、region、view、tool、host 和 export destination。
- 位于何处，使用哪个 encryption context/key version，有哪些 derived/cached/backup/remote copies。
- 当前质量、freshness、完整性、扫描、删除、legal hold、incident 和 reconciled 状态。

### DataRecord

```typescript
interface DataRecord {
  dataId: string;
  logicalType: string;
  versionId: string;
  sourceRefs: SourceRef[];
  owner: DataOwner;
  steward?: DataSteward;
  scope: ScopeRef;
  classification: Classification;
  purpose: PurposeRecord;
  schema?: SchemaRef;
  lineage: LineageRef[];
  destinations: DataDestination[];
  copies: DataCopyRef[];
  quality?: QualitySnapshot;
  retention: RetentionPolicy;
  encryption: EncryptionContext;
  accessPolicy: AccessPolicyRef;
  lifecycle: DataLifecycleState;
  createdAt: string;
  updatedAt: string;
}
```

### ownership 与 stewardship

- `owner` 对业务目的、风险接受、保留和删除负责。
- `steward` 对分类、schema、质量、lineage、catalog freshness 和日常问题负责。
- `producer` 对数据契约、字段语义、版本和质量 SLO 负责。
- `consumer` 对最小化、目的、访问和下游副本负责。
- `platform operator` 对存储、备份、恢复、加密、队列和基础设施边界负责。
- `security/privacy` 对控制、例外、事件、审计和法规输入负责。

owner 不明确、owner 离职、owner 冲突或 steward 长期不响应时，数据不应自动升级为 public 或长期保留。

### Catalog 条目

```typescript
interface CatalogEntry {
  id: string;
  name: string;
  semanticDescription: string;
  dataProduct: string;
  owner: DataOwner;
  stewards: DataSteward[];
  classification: ClassificationPolicy;
  purposes: PurposeDefinition[];
  schemaRefs: SchemaRef[];
  contractRefs: DataContractRef[];
  qualitySLO: QualitySLO;
  lineageRoot?: string;
  allowedScopes: ScopePolicy;
  residency: ResidencyPolicy;
  retention: RetentionPolicy;
  accessPolicy: AccessPolicyRef;
  lifecycle: "draft" | "active" | "deprecated" | "quarantined" | "retired";
  catalogVersion: string;
}
```

## Classification、Purpose 与 Legal Basis

### 分类轴

```text
sensitivity: public | internal | confidential | secret | regulated
content tags: pii | credential | financial | health | location | source_code
              customer_data | biometric | child_data | legal_hold | security_event
provenance: user | model | tool | file | retrieval | human_review | system | provider
authority: highest | high | scoped | data | none
```

`authority` 与 `sensitivity` 分开：public 文件仍可能是低 authority 数据；internal policy 具有高 authority 也不代表可以外发。

### 分类失败

分类未知时：

- 不归为 public 或 low risk。
- provider egress 使用更高敏感度或 deny。
- model context 使用 artifact_only、summary 或 hold。
- 产生 `classification_unknown` diagnostic 和 audit。
- 若可能是 secret/regulated，触发扫描和 privacy/security review。

### PurposeRecord

```typescript
interface PurposeRecord {
  purpose: ProcessingPurpose;
  legalBasisRef?: string;
  consentRef?: string;
  actor: PrincipalRef;
  declaredAt: string;
  expiresAt?: string;
  allowedDestinations: DestinationRef[];
  compatiblePurposes: ProcessingPurpose[];
  restrictions: PurposeRestriction[];
}
```

常见 purpose：`task_execution`、`tool_execution`、`model_inference`、`memory_recall`、`memory_persistence`、`safety_detection`、`audit`、`support_diagnostic`、`evaluation`、`billing`、`export`、`delete`、`recovery`、`incident_forensics`。

### purpose 规则

- task_execution 不自动授权长期 memory、训练、营销、跨 session 分享或 provider reuse。
- audit 不等于允许保存完整原文；默认保存 hash、类型、大小、状态和 decision evidence。
- support_diagnostic 使用短 TTL、最小字段和访问审计。
- evaluation 需要脱敏、去重、最小复现和 dataset provenance。
- purpose 改变时重做 classification、basis、egress 和 retention。
- derived view 不能拥有比 source 更宽的 purpose，除非有独立授权。

## Lineage、Provenance 与派生关系

### lineage 图

```text
source object
  -> normalization
  -> classification
  -> redaction/tokenization
  -> prompt/context projection
  -> provider request
  -> provider response
  -> tool/artifact/memory/event/log/backup copies
```

### LineageRecord

```typescript
interface LineageRecord {
  lineageId: string;
  inputRefs: DataRef[];
  outputRefs: DataRef[];
  operation: "ingest" | "normalize" | "classify" | "redact" | "summarize"
    | "project" | "compact" | "embed" | "rerank" | "export" | "backup";
  actor: PrincipalRef;
  runId?: string;
  toolVersion?: string;
  policyVersion?: string;
  parametersHash?: string;
  occurredAt: string;
  evidenceRef?: EvidenceRef;
}
```

### provenance 规则

- provider metadata、模型 inferred memory、用户直接陈述、工具事实和检索文本必须区分 provenance。
- provenance 不自动提升 authority，也不能覆盖 server-side scope。
- summary、embedding、redaction view、preview、cache 和 export package 都建立 derived ref。
- provider response 作为不可信输入重新分类，不能继承 source 的 owner 或 purpose。
- 无法建立来源的对象进入 `provenance_unknown`，限制外发和长期 memory。

### lineage 质量

检测 orphan output、missing parent、cycle、跨 tenant edge、时间倒序、version mismatch、删除后仍可读的 derived ref 和未记录的 provider remote copy。

## Schema、Data Contract 与质量 SLO

### schema 的治理边界

schema 描述结构和语义约束，但不承担完整治理：

- `schema` 不决定 owner、purpose、retention、egress 或法律依据。
- `required` 不等于数据可以收集。
- `tenantId` 字段不等于租户隔离。
- `sensitivity` 字段不等于运行时 classification 已完成。
- `version` 不等于 lineage 或 migration 安全。

### DataContract

```typescript
interface DataContract {
  id: string;
  producer: ComponentRef;
  consumers: ComponentRef[];
  subject: string;
  schemaVersion: string;
  compatibility: "backward" | "forward" | "full" | "none";
  requiredSemantics: SemanticConstraint[];
  qualitySLO: QualitySLO;
  classification: ClassificationPolicy;
  purpose: PurposePolicy;
  retention: RetentionPolicy;
  residency: ResidencyPolicy;
  errorPolicy: DataErrorPolicy;
  owner: DataOwner;
  status: "draft" | "active" | "deprecated" | "suspended";
}
```

### Agent contracts

- `ModelRequestContract`：Message/Part、tool、structured output、metadata、egress view。
- `ToolResultContract`：call ID、status、schema、sensitivity、artifact refs、redaction。
- `SessionEntryContract`：semantic entry、scope、version、provenance、retention。
- `ArtifactContract`：content hash、view、MIME、scan、scope、TTL、deletion。
- `EventContract`：canonical envelope、durability、sequence、sensitivity、retention。
- `MemoryContract`：provenance、confidence、TTL、purpose、forget、recall scope。
- `ProviderEgressContract`：destination、region、training、retention、remote object。
- `AuditContract`：最小治理事实、完整性、访问、retention、forensics。

### QualitySLO

```typescript
interface QualitySLO {
  completeness?: number;
  validity?: number;
  freshnessMs?: number;
  uniqueness?: number;
  consistency?: number;
  lineageCoverage?: number;
  classificationCoverage?: number;
  reconciliationLagMs?: number;
  maxUnknownRate?: number;
  measurementWindow: string;
  owner: string;
}
```

质量维度：completeness、validity、accuracy proxy、freshness、uniqueness、consistency、lineage coverage、classification coverage、scope integrity、redaction coverage、deletion completion 和 reconciliation lag。

### Data quality 失败语义

- `warning`：可继续，但产生 diagnostic 和 owner ticket。
- `degrade`：改用 summary、artifact_only、只读或降低范围。
- `quarantine`：禁止进入 model/provider/long-term memory。
- `deny`：停止处理并保留最小错误证据。
- `unknown`：没有足够事实，不能当作 passed。

## 核心数据模型与 TypeScript 接口

```typescript
type DataId = string;
type DataVersionId = string;
type CopyId = string;
type DataContractId = string;
type LineageId = string;
type DeletionJobId = string;
type ExportJobId = string;
type DataLifecycleState = "discovered" | "cataloged" | "classified"
  | "authorized" | "active" | "restricted" | "quarantined"
  | "retention_hold" | "deleting" | "deleted" | "expired" | "unknown";
```

```typescript
interface DataOwner {
  principalId: string;
  organizationId?: string;
  team?: string;
  accountability: "business" | "technical" | "security" | "privacy";
  contactRef: string;
}
interface DataSteward {
  principalId: string;
  scope: ScopeRef;
  responsibilities: ("classification" | "schema" | "quality" | "lineage"
    | "retention" | "incident" | "access")[];
  active: boolean;
}
interface Classification {
  sensitivity: Sensitivity;
  tags: string[];
  provenance: string;
  authority: "highest" | "high" | "scoped" | "data" | "none";
  confidence: number;
  classifierVersion: string;
  classifiedAt: string;
  expiresAt?: string;
}
```

```typescript
interface DataCopyRef {
  copyId: CopyId;
  sourceDataId: DataId;
  kind: "primary" | "cache" | "queue" | "temp" | "artifact" | "memory"
    | "event" | "log" | "trace" | "backup" | "provider_remote"
    | "export" | "forensics";
  destination: DataDestination;
  versionId?: DataVersionId;
  contentHash?: string;
  encryption?: EncryptionContext;
  retention: RetentionPolicy;
  deletionState: "present" | "pending" | "deleted" | "unverified" | "held";
  lastReconciledAt?: string;
}
interface DataDestination {
  kind: "workspace" | "session" | "run" | "artifact_store" | "memory_store"
    | "event_store" | "log_sink" | "trace_sink" | "backup_store"
    | "provider" | "tool" | "host" | "export_target";
  tenantId?: string;
  region?: string;
  jurisdiction?: string;
  providerRef?: ProviderRef;
  purpose: ProcessingPurpose;
  allowedViews: string[];
}
```

```typescript
interface AccessPolicy {
  id: string;
  version: string;
  subjectRules: SubjectRule[];
  resourceRules: ResourceRule[];
  purposeRules: PurposeRule[];
  sensitivityCeiling: Sensitivity;
  maxLeaseMs: number;
  obligations: AccessObligation[];
  denyByDefault: boolean;
}
interface DataAccessLease {
  leaseId: string;
  subject: PrincipalRef;
  resource: DataRef;
  scope: ScopeRef;
  purpose: ProcessingPurpose;
  view: string;
  policyVersion: string;
  issuedAt: string;
  expiresAt: string;
  revocationVersion: string;
  hash: string;
}
```

```typescript
interface RetentionPolicy {
  class: string;
  ttlMs?: number;
  expiresAt?: string;
  legalHoldIds?: string[];
  incidentHold?: boolean;
  deleteStrategy: "hard_delete" | "tombstone" | "crypto_shred" | "provider_delete"
    | "best_effort" | "retain_for_audit";
  copies: CopyRetentionRule[];
}
interface EncryptionContext {
  algorithm: string;
  keyRef: string;
  keyVersion: string;
  tenantBinding: string;
  purposeBinding: string;
  encryptedAt: string;
  rewrappedAt?: string;
}
```

```typescript
interface GovernancePort {
  register(input: DataRecord): Promise<DataRef>;
  catalog(query: CatalogQuery): Promise<CatalogEntry[]>;
  authorize(input: DataAccessRequest): Promise<DataAccessDecision>;
  recordLineage(input: LineageRecord): Promise<void>;
  reportQuality(input: QualityObservation): Promise<void>;
  createDeletion(input: DeletionRequest): Promise<DeletionJob>;
  createExport(input: ExportRequest): Promise<ExportJob>;
  reconcile(input: ReconciliationRequest): Promise<ReconciliationReport>;
}
```

## 生命周期与状态机

### Data object lifecycle

```text
Discovered -> InventoryRegistered -> Cataloged -> Classified
-> PurposeBound -> Authorized -> Active
-> Restricted | Quarantined | RetentionHold
-> Deleting -> Deleted | DeleteUnverified | DeletionBlocked
-> Retired
```

- `Discovered`：从 host、tool、provider、artifact、event 或 backup 发现。
- `InventoryRegistered`：有 owner、scope、source 和基础 identity。
- `Cataloged`：有语义、schema、contract、steward 和 SLO。
- `Classified`：有 sensitivity、tags、provenance、authority 和 confidence。
- `PurposeBound`：有 purpose、basis、consent、destination 和 retention。
- `Authorized`：获得短期 access/egress lease。
- `Active`：可在指定 view 和 scope 使用。
- `Restricted`：只能 summary、artifact_only、只读或特定目的。
- `Quarantined`：质量、扫描、来源、scope 或 incident 问题，禁止正常消费。
- `RetentionHold`：TTL 到期但 legal/incident hold 阻止删除。
- `Deleting`：所有副本进入删除工作流。
- `Deleted`：达到定义的删除证明等级。
- `DeleteUnverified`：无法证明 provider、backup 或外部副本删除。
- `DeletionBlocked`：存在 hold、依赖或权限问题，需要 owner/board 处理。

### Governance job lifecycle

```text
Requested -> Authorized -> Planned -> Running -> WaitingForCopy
-> Verifying -> Completed | PartiallyCompleted | Failed | Blocked
```

适用于 DSAR、export、delete、reconciliation、classification scan、quality scan 和 key rotation。

### Run 内数据状态

```text
InputReceived -> Classified -> ContextSelected -> EgressApproved
-> ProviderSent -> ResponseReceived -> Projected -> Retained/Expired
```

每一步都产生 event、lineage 和必要的 data copy 记录。

## 访问控制与 Least Privilege

### 五层访问

1. `visibility`：主体能否发现对象存在或看到 catalog metadata。
2. `read`：能否读取指定 view/range。
3. `use`：能否把数据用于指定 purpose。
4. `egress`：能否发送到 provider、tool、host 或 export destination。
5. `mutate/delete/export`：能否修改、删除、导出或改变 retention。

### least privilege 规则

- 访问 lease 绑定 subject、tenant、scope、purpose、view、policy version 和 expiry。
- 默认只授予最小 range、字段、artifact view、tool result 或 summary。
- `allow read` 不自动授权 `persist`、`memory_write`、`provider_send`、`export` 或 `delete`。
- 低信任内容不能成为授权来源。
- child run 只能得到 parent scope、resources、purpose、view 和 budget 的交集。
- operator、support、forensics、governance board 的访问需要独立目的、短 TTL 和审计。

### AccessDecision

```typescript
type AccessDecision =
  | { type: "allow"; lease: DataAccessLease; obligations: AccessObligation[] }
  | { type: "transform"; view: string; obligations: AccessObligation[] }
  | { type: "ask"; approval: ApprovalRequest }
  | { type: "deny"; reasonCode: string; recoverable: boolean }
  | { type: "unknown"; missingEvidence: EvidenceRequirement[] };
```

## Tenant、Workspace 与 Scope Boundary

### Scope 层级

```text
Tenant -> User -> Workspace -> Project -> Session -> Branch
-> Run -> Turn -> Attempt -> ToolExecution/Subagent
```

数据对象默认取最窄 scope：

- user input：session/run。
- working memory：run/turn。
- semantic memory：user/workspace/project，需写入门槛。
- artifact：run/subagent/workspace，跨 session 需显式 share/copy。
- trace：run/attempt。
- audit：tenant + retention class。
- provider cache：tenant + policy + resource hash。
- tokenization map：security scope，不进入 provider 或普通 session。

### scope 不变量

- 所有下游 port 都接收 ScopeRef，并重新验证 owner。
- child run tenant 必须等于 parent，除非显式跨租户委派 policy。
- session、artifact、event、memory、queue job、backup 和 export owner 可证明。
- cache key 含 tenant、scope hash、policy version、resource hash。
- provider fallback 不得改变 tenant、workspace、region 或 purpose。
- delete/export 使用新鲜授权，不复用已过期 access snapshot。

### Workspace boundary

workspace 文件、project rules、repo map、snapshot、patch、temp、cache 和 command output 必须拥有 workspace/project scope；workspace trust 不等于 tenant ownership，也不等于允许 provider egress。

## Provider、Artifact、Memory、Event、Log 与 Backup Copies

### copy inventory

每个 source data 必须列出：

- provider request/response、remote file、conversation、batch、cache、embedding、rerank。
- artifact raw、sanitized、preview、summary、structured、range、patch 和 snapshot。
- memory candidate、memory record、embedding、index、recall cache。
- durable semantic entry、ephemeral event、trace span、log、metric、audit、SIEM。
- queue payload、worker temp、retry payload、dead-letter、backup、archive、export 和 forensics。

### Provider copy

Provider-side object 是独立 DataCopyRef，记录 provider、api family、remote ID、region、purpose、view、hash、upload time、expiry、retention、training/reuse、delete capability、status query 和 deletion receipt。

provider 不支持删除时：

- 本地引用进入 restricted/expired。
- 不允许复用到 future context、memory 或 provider request。
- 标记 `remote_delete_unverified`。
- 通知 owner 和 privacy/security。
- 保留限制证据，不声称“已删除”。

### Artifact copy

ArtifactRef 的 logical ID、version ID、content hash、view、scope、sensitivity、scan、retention 和 deletion state 单独治理；删除 raw 不自动删除 summary、preview、range 或 patch。

### Memory copy

Memory 必须记录 provenance、confidence、scope、purpose、TTL、forget policy、contradiction、source refs 和使用记录；当前 task 的 conversation 不自动写入长期 memory。

### Event/log/backup copy

- durable event 与 telemetry projection 分开治理。
- trace/log 默认使用 metadata、hash、ArtifactRef 和 redaction summary。
- backup 保留 scope、key version、retention、restore authorization 和 deletion dependency。
- audit 可保留最小治理事实，但不能成为完整 prompt/secret 的永久副本。
- dead-letter 和 retry payload 也必须 inventory，不得成为隐形永久存储。

## Residency、Cross-border 与 Egress

### EgressSnapshot

```typescript
interface EgressSnapshot {
  id: string;
  tenantId: string;
  workspaceId?: string;
  runId: string;
  purpose: ProcessingPurpose;
  policyVersion: string;
  allowedProviders: string[];
  allowedRegions: string[];
  deniedJurisdictions: string[];
  allowedDataClasses: Sensitivity[];
  artifactOnlyClasses: Sensitivity[];
  redactionProfile: string;
  trainingPolicyVersion: string;
  retentionProfile: string;
  maxBytes: number;
  maxTokens: number;
  consentRef?: string;
  legalBasisRef?: string;
  createdAt: string;
  expiresAt: string;
  hash: string;
}
```

### 决策顺序

```text
classification -> purpose/basis -> tenant/workspace policy
-> provider/model/deployment -> region/jurisdiction -> retention/training
-> transformation -> destination capability -> egress allow/degrade/deny
```

### cross-border 规则

- confidential/regulated 数据不因 primary 故障自动跨境 fallback。
- fallback、hedge、shadow、canary 重新执行 residency、purpose、retention 和 budget。
- provider remote object、backup、telemetry、support diagnostics 和 abuse review 也算 destination。
- provider region 声明与实际 deployment/endpoint 不一致时 quarantine。
- 不能证明目的地时按高敏感度或 deny 处理。

## Encryption、Key Lifecycle 与 Crypto-shred

### encryption 层次

- transport encryption：provider、artifact、event、host 和 worker 传输。
- storage encryption：session、artifact、memory、event、log、backup 和 export。
- field/view encryption：secret、token map、regulated fields 和 key material。
- tenant binding：密钥上下文包含 tenant、scope、purpose、data class 和 object version。
- key separation：普通数据、tokenization map、audit、backup、forensics 和 provider credential 分离。

### KeyRecord

```typescript
interface KeyRecord {
  keyRef: string;
  tenantId?: string;
  purpose: string;
  class: "data" | "field" | "token_map" | "audit" | "backup" | "credential";
  version: string;
  status: "preparing" | "active" | "draining" | "revoked" | "destroyed";
  createdAt: string;
  rotateAfter?: string;
  destroyedAt?: string;
  owner: string;
}
```

### rotation

rotation 产生新 version，旧数据可 rewrap 或按 policy 保持旧 key；新写入禁止旧 key；撤销/删除 key 前检查 backup、legal hold、recovery 和 audit 依赖。

### crypto-shred

crypto-shred 只在满足：所有可恢复副本都使用目标 key、legal/incident hold 已处理、restore 不会复活对象、owner 和 board 认可的 deletion evidence 存在时，才能作为删除证明的一部分。

key manager 不把 key 值放入 prompt、tool arg、artifact、log、trace、event payload 或 provider request。

## DLP、Scanning 与 Redaction

### scanner 覆盖

扫描 prompt、ContextResource、Message/Part、ToolCall、ToolResult、Artifact raw/view、provider response、remote object metadata、log、trace、export、backup、queue payload 和 memory candidate。

### 检测标签

secret、credential、PII、financial、health、location、source_code、customer_data、regulated、malware、prompt_injection、high_entropy、legal_hold。

### RedactionPipeline

```text
classify -> detect -> choose profile -> transform
-> rescan transformed view -> assign derived lineage
-> issue bounded lease -> audit decision
```

### 失败策略

- scanner unavailable 或 redaction 失败：secret/regulated deny。
- 低敏感度文本：可 summary/artifact_only，并记录 degraded。
- tokenization map 只在 security scope 可读。
- redaction view 不能提升 purpose、scope 或 destination。
- provider output、tool result 和 log 也必须扫描，不能只扫描 user input。

## Retention、TTL、Legal Hold 与 Archive

### retention 不是一个全局数字

不同 copy 分别定义 retention：session、artifact、memory、event、trace、log、audit、provider remote、cache、queue、backup、export 和 forensics。

### TTL 规则

- `until_turn_end`、`until_run_end`、`until_session_end`、`until_file_change`、`ttl`、`artifact_only`、`never_persist` 都是可用语义。
- TTL 到期前启动 deletion/reconciliation，不在读取时才临时删除。
- cache、queue retry、dead-letter、preview、embedding、backup 和 remote object 不能绕过 TTL。
- expired object 返回 tombstone/expired，不伪装为 available。

### legal hold

```typescript
interface LegalHold {
  id: string;
  scope: ScopeRef;
  dataSelectors: DataSelector[];
  purpose: "legal" | "incident" | "regulatory";
  issuedBy: PrincipalRef;
  issuedAt: string;
  expiresAt?: string;
  status: "active" | "released" | "expired";
  evidenceRef: EvidenceRef;
}
```

hold 阻止删除、压缩、crypto-shred 和某些 export，但不自动扩大读权限；release 必须有审计和重新运行 retention planner。

## Deletion、Export 与 DSAR

### deletion graph

```text
logical object -> versions -> views -> artifacts -> memory/index
-> session entries -> events/traces/logs -> caches/queues
-> backups/archives -> provider remote objects -> export/forensics copies
```

### DeletionRequest

```typescript
interface DeletionRequest {
  requestId: DeletionJobId;
  requester: PrincipalRef;
  scope: ScopeRef;
  selectors: DataSelector[];
  purpose: "user_request" | "retention" | "incident" | "admin";
  legalHoldPolicy: "respect" | "review" | "override_with_approval";
  requestedAt: string;
  authorizationRef: string;
}
```

### 删除流程

1. 认证 requester 和 scope。
2. 列出 inventory、lineage、copies、holds 和 dependencies。
3. 分类可删、需 hold、需 owner、provider unverified 和 audit-only 对象。
4. 生成 plan、估计影响和 deletion evidence requirements。
5. 对高风险/跨系统删除要求 approval 或 dual control。
6. 按 copy dependency 顺序执行，禁止先删唯一 lineage evidence。
7. query provider、backup、queue、cache 和 artifact 状态。
8. 写 tombstone、receipt、failure、unverified 和 reconciliation report。
9. 释放引用、更新 catalog 和通知 owner。

### export/DSAR

导出必须是新生成的短 TTL artifact package，包含 manifest、scope、purpose、数据版本、lineage、脱敏状态、来源、缺失/held/unverified 项和完整性 hash；不要把内部密钥、token map、无权访问的审计原文或其他租户数据放入导出包。

### 删除证明

删除证明至少区分 `deleted`、`crypto_shredded`、`tombstoned`、`provider_delete_receipt`、`unverified`、`held` 和 `failed`；不能用一条“delete succeeded”覆盖所有副本。

## Reconciliation 与治理证明

### reconciliation 对象

- inventory 与实际 artifact/session/event/provider/backup/queue 存储。
- catalog owner、steward、schema、contract 和 active consumer。
- lineage 输入输出、derived view、memory、embedding 和 export。
- retention/TTL、legal hold、deletion state、remote object 和 key version。
- usage/cost ledger 与 provider/tool/storage/egress receipt。
- provider catalog、route snapshot、contract snapshot 和实际 endpoint。

### ReconciliationReport

```typescript
interface ReconciliationReport {
  reportId: string;
  scope: ScopeRef;
  startedAt: string;
  endedAt: string;
  scanned: number;
  matched: number;
  missing: ReconciliationFinding[];
  stale: ReconciliationFinding[];
  orphaned: ReconciliationFinding[];
  crossScope: ReconciliationFinding[];
  unverified: ReconciliationFinding[];
  severity: "info" | "warning" | "high" | "critical";
  evidenceRefs: EvidenceRef[];
}
```

### 对账规则

- 发现实际存在但 inventory 无记录的 copy，进入 quarantine 或补登记。
- 发现 inventory 有记录但实际不可读的对象，区分 deleted、expired、corrupt 和 unknown。
- 发现 copy scope、region、key、retention 或 owner 不一致，阻断继续扩散。
- 发现 provider remote object 无本地 receipt，标记 unverified。
- reconciliation 结果是追加事实，不覆盖原始 entry。

## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成

### Model/Provider

- Provider Runtime 只接收经 classification、purpose、egress 和 contract 允许的 view。
- `TenantRoutingSnapshot`、`EgressSnapshot`、`ContractSnapshot` 和 `CredentialLease` 一起绑定 Attempt。
- provider response、usage、安全元数据和 remote object receipt 进入 inventory/lineage。
- provider raw request/response 默认保存 hash、size、view、artifact ref，而不是完整原文。
- fallback、retry、hedge、shadow、canary 重新创建 copy、destination、purpose 和 retention 记录。

### Prompt

- PromptCompiler 把 policy、identity、task、tools、context 和 output contract 编成 PromptSection。
- 每个 section 记录 source、authority、trust、sensitivity、purpose、retention 和 contract version。
- Prompt 解释数据处理事实，但不授权新 destination 或新 purpose。
- 检索内容、工具结果、文件注释和 provider text 是 data，不获得 policy authority。
- prompt snapshot 的持久化按最小化、短 TTL、redaction 和 audit policy 处理。

### Context

- ContextCompiler 的输入是 DataPlan，而不是一堆无元数据字符串。
- 选择、排序、去重、压缩和 artifact offload 都产生 lineage 和 context usage。
- cache key、compaction、memory recall 和 subagent handoff 带 scope、policy、purpose 和 provider capability。
- context overflow 不得随机删除高敏感度或高价值数据；使用 ContextPlan 诊断和安全降级。
- provider egress 只允许 context plan 指定的 view/range。

### Tool

- ToolSpec 声明 effect、confidentiality、result policy、artifact policy、retention 和 egress。
- Tool arguments、stdout/stderr、数据库响应、网络结果和生成 artifact 都进入 classification/DLP/lineage。
- tool result 回模型只用必要 view；完整结果留在 ArtifactStore 或受控 backend。
- tool execution 的 side-effect ledger、receipt、idempotency 和 deletion dependency 进入 inventory。
- MCP、LSP、plugin、hook 结果不能扩大 data scope。

### State/Memory

- Session entries、WorkingState、Checkpoint、Compaction、MemoryRecord 和 Branch 都是不同 data class。
- Transcript 保存语义事实；Model Context 是投影；Memory 是治理后的跨任务资源；Artifact 保存大内容。
- compaction 不能删除 policy、approval、contract、safety、lineage、retention、deletion 和 unknown outcome 事实。
- memory write 需要 purpose、source、confidence、TTL、owner、forget policy 和 privacy gate。
- replay 只读重建，不把历史 provider payload 重新外发。

### Policy/Sandbox

- Policy 决定 visibility、read/use/egress/mutate/delete/export。
- Sandbox 强制文件、网络、进程、secret、temp、cache 和 provider endpoint 边界。
- data governance allow 不替代 OS isolation；sandbox attestation 仍需单独记录。
- legal hold、revocation、deletion 和 incident block 作为 obligations 注入执行面。

### Harness

- Bootstrap 装配 tenant context、catalog、inventory、classification、purpose、access、egress、retention、key、DLP、artifact、provider 和 audit。
- Run 配置冻结 scope、policy、purpose、contract、egress、key、retention 和 quality gate。
- Supervisor 管理取消、checkpoint、recovery、background job、subagent、queue lease 和 deletion job。
- Event Router 将 data lifecycle、access、egress、quality、lineage、retention、delete 和 incident 事件投影到 State、Audit、Metrics、Host。
- Host 只显示调用者有权看到的数据处理摘要、导出/删除状态和治理告警。

## 决策流程

### 新数据进入

1. 认证主体与 TenantContext。
2. 解析 workspace/project/session/run scope。
3. 生成 DataRecord identity、source、owner 和 content hash。
4. 分类 sensitivity、tags、provenance、authority 和 confidence。
5. 绑定 purpose、legal basis/consent、destination、retention 和 residency。
6. 校验 schema/data contract、质量、DLP、malware 和 owner/steward。
7. 创建 access/egress lease 或 quarantine。
8. 写 inventory、lineage、audit 和 event。

### 使用数据

9. 请求方提交 purpose、view、range、destination 和 expected retention。
10. AccessBroker 校验 subject、scope、least privilege、policy version 和 expiry。
11. EgressEvaluator 校验 provider/tool/host/region/cross-border/training/retention。
12. 选择 full、redacted、summary、range、artifact_only 或 deny。
13. 重新扫描 transformed view，生成 derived data 和 lineage。
14. 发放短期 lease 和 capability。
15. 执行 Provider/Tool/Artifact/Memory 操作。
16. 记录实际 destination、receipt、quality、usage、cost 和 copy。

### 删除/导出

17. 认证请求与 legal hold。
18. 扩散图遍历所有 copies 和 dependencies。
19. 生成 plan 和 evidence requirements。
20. 执行、查询状态、核对 receipts。
21. 写 tombstone、unverified、held、failed 和 reconciliation。
22. 生成短 TTL export 或 deletion certificate。

## 故障恢复与安全降级

### 故障分类

catalog/inventory unavailable、classification unknown、DLP timeout、policy unavailable、key service failure、artifact partial write、event store backlog、provider upload unknown、backup restore mismatch、delete provider unverified、quality SLO breach、lineage gap、scope mismatch、worker crash 和 queue duplicate。

### fail-closed

secret/regulated、cross-tenant、provider egress、delete/export、key rotation、legal hold、生产写和高风险 tool：治理事实不可用时停止。

低风险 internal/public 只读可沿已冻结 snapshot 到安全边界结束，或退化为 summary、artifact_only、offline、read-only、manual review。

### crash recovery

- 每个治理 job 使用 durable job、lease、heartbeat、fencing token 和 idempotency key。
- 记录最后 durable boundary、已完成 copy、待确认 copy、未知 copy 和 receipt。
- provider/tool/artifact unknown 不盲重放；先 query、reconcile 或人工确认。
- deletion job 重启前重新检查 authorization、policy、legal hold、retention 和 copy state。
- key rotation 失败时保留旧 key 到恢复完成，不把未验证 rotation 当成功。
- event/projector backlog 不阻断必须安全停止的动作，但不得声称治理已完成。

### degraded 状态

`degraded` 必须声明缺失的 quality、lineage、classification、retention 或 destination evidence、受限操作、恢复条件、过期时间和通知对象；不能只返回一条 warning。

## Incident Response 与 Runbook

### 事件类型

- 跨租户读取、缓存、artifact、event、memory 或 provider egress。
- secret/PII/regulated 数据进入错误 provider、region、log、trace、backup 或 host。
- provider remote object、backup、queue 或 export 无法删除。
- scope、owner、lineage、retention、quality 或 key version 不一致。
- DLP/redaction 漏报，错误删除或 legal hold 绕过。
- provider fallback、shadow、hedge 或 retry 重复外发。
- 数据契约 drift、schema incompatibility、质量 SLO 长期 breach。

### containment

```text
detect -> classify severity -> freeze egress/access
-> quarantine data/copies -> revoke leases -> preserve evidence
-> rotate keys/credentials -> stop affected jobs
-> map propagation via lineage -> delete/export/notify as required
-> reconcile -> recover with new policy/contract -> postmortem
```

### runbook 最小内容

- 影响 tenant/workspace/session/run/copy 的识别。
- provider、artifact、memory、event、log、backup、cache 和 queue 的传播检查。
- access/egress revoke、credential/key rotation 和 route quarantine。
- legal hold、DSAR、删除证明和通知路径。
- forensic bundle 的 scope、短 TTL、访问审计和销毁。
- 恢复前 quality、lineage、classification、residency、retention 和 contract 验证。
- 将根因加入 deterministic regression fixture。

## 可观测性、指标与报告

### Canonical governance events

```text
DataDiscovered DataRegistered CatalogUpdated OwnershipChanged
ClassificationCompleted PurposeBound AccessLeaseIssued AccessDenied
LineageRecorded DataContractValidated QualitySLOBreached
EgressEvaluated RedactionApplied CopyCreated CopyDeleted
RetentionExpired LegalHoldApplied LegalHoldReleased
DeletionRequested DeletionPlanned DeletionCompleted
DeletionUnverified ExportRequested ExportCompleted
KeyRotated KeyRevoked ReconciliationStarted ReconciliationCompleted
GovernanceExceptionGranted GovernanceExceptionExpired DataIncidentDeclared
```

### 指标

- inventory coverage、catalog freshness、owner/steward coverage。
- classification coverage、unknown rate、DLP finding、redaction coverage。
- purpose/basis coverage、consent withdrawal latency、egress deny/degrade rate。
- lineage coverage、orphan/missing/cross-scope edges、provider copy visibility。
- schema compatibility、contract violations、freshness、completeness、validity、uniqueness、consistency。
- quality SLO pass/breach、reconciliation lag、unknown data rate。
- access lease denial、scope mismatch、least-privilege reduction、privileged access、break-glass。
- retention expiry backlog、legal hold count、delete success/unverified/blocked/failed。
- export completion、DSAR latency、remote delete verification、backup deletion lag。
- key rotation latency、old key usage、crypto-shred evidence、encryption coverage。
- cross-border attempt、provider egress、cache/queue/log/trace copy count。
- incident detection、containment、propagation mapping、recovery、repeat rate。

### 报告分层

- owner report：业务目的、质量、owner action、retention 和风险。
- steward report：schema、lineage、classification、SLO、异常和数据契约。
- operator report：容量、队列、worker、store、backup、key、删除和恢复。
- security/privacy report：敏感度、egress、scope、incident、DLP、DSAR 和访问。
- board report：例外、风险接受、SLO趋势、法规输入和资源决策。

### trace 和 log

默认只记录 data ID hash、type、size、scope class、purpose、destination class、decision code、contract/version、artifact ref 和 receipt ref；原文放入受控、短 TTL、最小权限的 forensics bundle。

## 测试策略与 Evaluation

### 测试分层

- unit：classification、purpose compatibility、scope、retention、lineage、hash、contract、quality。
- component：inventory、catalog、access broker、egress、DLP、key、delete、export、reconciliation。
- integration：Prompt/Context/Model/Tool/State/Artifact/Event/Provider/Harness。
- scenario：多租户、workspace、subagent、provider、backup、legal hold、DSAR、incident、rotation。
- conformance：schema、event、artifact、memory、provider remote copy 和 deletion receipt。
- online/shadow：只用 synthetic/public/sanitized 数据，禁止真实副作用。

### 正向用例

- 输入从 discovery 到 inventory、classification、purpose、access、provider egress、lineage 和 retention 完整闭环。
- ContextPlan 选择最小 view，redaction 后重新扫描且 lineage 正确。
- ToolResult 进入 artifact，model 只拿 summary/ref，session 保存 semantic entry。
- Memory write 有 provenance、confidence、TTL、purpose、forget policy。
- event、trace、log、backup、provider object 都有 copy inventory 和删除策略。
- delete/export 正确处理 legal hold、cross-copy、receipt 和 partial completion。
- key rotation、scope change、policy change 产生新 snapshot 和可审计事实。
- quality SLO breach 触发 degrade/quarantine 而非静默继续。

### 负向用例

- 没有 owner、steward、classification、purpose、basis 或 lineage 的对象进入 provider。
- 模型或 tool argument 伪造 tenant、workspace、purpose、consent、retention 或 owner。
- cross-tenant cache、artifact、memory、event、queue、worker、backup 或 export。
- provider fallback 跨 region；shadow/hedge 重复发送 regulated payload。
- DLP 漏报 secret、redaction map 泄漏、trace/log 保存完整 prompt。
- schema 改变导致语义丢失、unknown field 静默删除或 quality SLO 失真。
- deletion 只删主表，残留 preview、embedding、backup、remote object、DLQ 或 export。
- legal hold 被 TTL worker、cleanup、crypto-shred 或 compaction 绕过。
- key rotation 后新写入使用旧 key，restore 复活已删除对象。

### fault injection

catalog timeout、policy outage、DLP crash、KMS unavailable、artifact partial write、provider unknown upload、event backlog、worker crash、queue duplicate、backup restore mismatch、remote delete timeout、lineage store failure、quality monitor stale、scope resolver bug。

断言：不 fail-open、不跨 scope、不重复外发、不误删 hold、不把 unknown 算成功；治理状态、audit、lineage、receipt、job checkpoint 可恢复。

### Oracle

确定性 oracle 检查：DataRecord、CopyRef、scope、purpose、view、policy version、lineage edge、contract/schema version、quality result、retention/hold、key version、delete/export status、provider destination、side-effect ledger 和 audit evidence。

LLM judge 只评估数据处理摘要、治理解释和用户可读性，不判断删除、权限、驻留、加密或实际副作用是否发生。

## 治理 Board 与责任制度

### Governance Board

Board 负责：

- 数据分类、purpose、retention、residency 和例外标准。
- owner/steward 冲突、regulated data、跨境和 provider 例外。
- data contract、quality SLO、schema migration 和 breaking change。
- deletion/export/DSAR 的组织级优先级和风险接受。
- incident postmortem、重复问题和资源投入。
- provider、artifact、memory、event、backup 的长期治理策略。

Board 不直接绕过 Policy、AccessBroker、Sandbox、Audit 或 deletion job 改生产数据。

### RACI 轮廓

| 活动 | Owner | Steward | Platform | Security/Privacy | Board |
|---|---|---|---|---|---|
| 分类与目的 | A | R | C | C | I |
| schema/contract | A | R | C | I | C |
| quality SLO | A | R | C | C | I |
| access/egress | A | C | R | A | I |
| retention/delete | A | R | R | A | C |
| incident | A | C | R | R | I |
| exception | C | C | I | R | A |

### 例外制度

例外必须有 scope、purpose、owner、风险、补偿控制、开始/过期时间、审批、证据和回滚；不得使用永久 `allow`、全局 wildcard 或不带 tenant 的 override。

## 反模式

### Data Governance = 字段命名

症状：字段统一了，但不知道数据为什么收集、谁能看、去哪、保留多久、如何删除。

修复：用 inventory、catalog、purpose、ownership、lineage、policy、retention、egress 和 evidence 组成闭环。

### 只有 `tenant_id`

症状：cache、queue、worker、artifact、trace、provider、backup 和文件系统仍共享。

修复：入口身份、scope-aware ports、隔离 namespace、lease、sandbox、egress 和 audit 组合强制。

### catalog 代替权限

症状：catalog 上写着 owner 或 sensitivity，就直接允许读取/外发。

修复：catalog 提供事实和规则输入，AccessBroker/Policy 仍发短期 lease。

### 读取等于保存

症状：为了完成一次 task 把 prompt、tool output、provider payload、memory 和日志永久存储。

修复：区分 `read/use/egress/persist/memory/export/delete`，采用最小 view、短 TTL 和 ArtifactRef。

### lineage 等于授权

症状：因为数据“来自可信系统”就允许所有 consumer 读取。

修复：lineage 只说明来源和变换，purpose、scope、policy 决定使用。

### delete 一张表

症状：残留 cache、preview、embedding、backup、DLQ、remote file、export 和 trace。

修复：按 deletion graph 遍历 copies，分别出具 deleted/held/unverified/failed 证明。

### 只保护 provider egress

症状：数据未外发 provider，但在日志、trace、support snapshot、backup 或 host channel 泄露。

修复：所有 destination 都进入 inventory、classification、retention 和 access policy。

### 质量分数掩盖 scope 错误

症状：completeness 很高，却发生跨租户、错 region 或 owner 丢失。

修复：scope integrity、egress、deletion、classification 和 lineage 是 hard safety dimensions。

### legal hold 只在数据库

症状：TTL worker、cleanup、backup retention、crypto-shred 或 provider delete 绕过 hold。

修复：hold 进入每个 copy、job、key、retention planner 和删除 oracle。

### 治理规则写在 Prompt

症状：模型被要求“只使用当前租户数据”，但工具、缓存、provider、后台 worker 没有强制。

修复：Prompt explains，Context selects，Policy authorizes，Sandbox limits，State records，Audit proves。

## 实施清单

### 阶段一：Inventory 与 Catalog

- [ ] 建立 DataRecord、DataCopyRef、CatalogEntry、DataOwner、DataSteward。
- [ ] 覆盖 prompt、context、tool、state、memory、artifact、event、log、trace、backup、queue、provider remote object。
- [ ] 建立 source、version、content hash、scope、owner、steward、classification 和 lifecycle。
- [ ] 建立 catalog semantic description、active consumers、schema refs、contracts 和 quality SLO。
- [ ] 建立 orphan、missing、cross-scope、stale 和 unregistered copy reconciliation。

### 阶段二：Purpose、Access 与 Egress

- [ ] 建立 Classification、PurposeRecord、legal basis/consent reference 和 destination。
- [ ] 建立 read/use/egress/persist/memory/export/delete 的 least-privilege lease。
- [ ] 将 tenant/workspace/session/run/subagent scope 绑定所有 port、cache、queue、worker 和 artifact。
- [ ] 建立 EgressSnapshot、residency、cross-border、provider training、retention 和 remote object policy。
- [ ] 实现 full/redacted/tokenized/pseudonymized/summary/range/artifact_only/deny。
- [ ] 在 Prompt、Context、ToolResult、Artifact、Provider、Host、Log、Backup 前加入 DLP gate。

### 阶段三：Lineage、Contract 与 Quality

- [ ] 建立 LineageRecord、provenance、derived view、transform version 和 evidence。
- [ ] 建立 ModelRequest、ToolResult、SessionEntry、Artifact、Event、Memory、ProviderEgress data contracts。
- [ ] 为 completeness、validity、freshness、uniqueness、consistency、lineage、classification 和 deletion 建立 SLO。
- [ ] 将 schema drift、contract incompatibility、quality breach 和 unknown 连接到 degrade/quarantine/deny。
- [ ] 建立 producer、consumer、owner、steward、migration、兼容和变更审批。

### 阶段四：Copies、Retention 与加密

- [ ] 为 provider、artifact、memory、event、log、trace、cache、queue、backup、export、forensics 建立 copy inventory。
- [ ] 建立 per-copy TTL、retention class、legal hold、incident hold、archive 和 deletion dependency。
- [ ] 建立 encryption context、tenant/purpose binding、key version、rotation、revocation 和 crypto-shred evidence。
- [ ] 实现 remote delete receipt、unverified、provider limitation 和 orphan reaper。
- [ ] 确保 backup restore 不复活已删除、已撤销或跨 tenant 数据。

### 阶段五：DSAR、Incident 与运营

- [ ] 建立 deletion graph、DeletionJob、ExportJob、DSAR、tombstone 和 deletion certificate。
- [ ] 建立 scope-aware export，排除其他租户、key、token map、内部审计原文和无权数据。
- [ ] 建立 provider egress、DLP、quality、scope、retention、delete、key 和 cross-border 指标。
- [ ] 建立 incident containment、lineage propagation、credential/key rotation、revoke、quarantine 和恢复 runbook。
- [ ] 建立治理 board、owner/steward RACI、例外审批、过期和回滚。
- [ ] 定期 reconciliation inventory/catalog/storage/provider/backup/queue/log/trace。

### 阶段六：测试与发布门禁

- [ ] 建立 deterministic fixture、fake provider、fake artifact、fake KMS、fake DLP、fake queue 和 replay runner。
- [ ] 覆盖跨租户、错误 region、provider fallback、secret、legal hold、删除、导出、backup、unknown 和 crash。
- [ ] 将治理 hard assertions 接入 CI：scope、egress、lineage、retention、deletion、key、audit。
- [ ] 对质量和成本等软指标设置 baseline、告警和逐步阈值，不覆盖安全 hard gate。
- [ ] 将 incident postmortem、DSAR 缺陷、删除残留和质量漂移转为回归案例。

## 五个参考项目的启发来源

### Pi（`earendil-works/pi`）

headless loop、统一 provider event、session tree、checkpoint 和 compaction 说明 transcript、working state、event、artifact、memory 和 governance decision 必须分开建模并可恢复；CLI/TUI/RPC 共用 runtime 说明治理事实不能由单一 Host 自己解释。

### Grok Build（`xai-org/grok-build`）

actor、permission decision、并行工具、资源锁、folder trust 和 sandbox 说明数据访问、文件资源、工具副作用、workspace trust 和执行隔离是不同问题；路径和 sandbox 失败风险提醒 scope 和 cleanup 必须 fail-closed。

### OpenCode（`anomalyco/opencode`）

client/server、session/message/part、事件总线、durable projector、snapshot/patch/revert、MCP/LSP 说明 catalog、lineage、artifact、event、provider copy 和状态投影应使用稳定事件、版本和不可变引用。

### Claude Code（`claude-code-best/claude-code`）

permission mode、hooks、subagents、skills、memory、MCP、计划和任务工作流说明 data governance 必须贯穿 Prompt、Context、Tool、State、Subagent、Extension 和 Host；memory 不能脱离 purpose、scope、TTL 和用户控制。

### OpenClaw（`openclaw/openclaw`）

AgentHarness registry、agent-core、gateway、多渠道、provider runtime、tool/sandbox/elevated 分层和事务化插件注册说明 catalog、provider、tool、sandbox、channel、extension、credential 和 audit 需要统一装配、隔离和撤销；单 Gateway 故障域提醒治理控制面要有恢复、分片和 backpressure。

## 结语

Data Governance 的完成标准不是“字段命名一致”，而是可以回答：

```text
系统知道哪些数据和副本？
谁拥有、谁 steward、为何处理、依据是什么？
数据从哪里来，经过哪些变换，去了哪些 provider/artifact/memory/event/log/backup？
哪个主体在什么 scope、purpose、view 和期限内访问？
质量、驻留、加密、保留、删除、导出和 incident 状态是什么？
发生故障、撤销、DSAR、legal hold 或跨境风险时能否恢复和证明？
```

只有 inventory、catalog、policy、contract、lineage、quality、access、lifecycle、reconciliation 和 runbook 共同回答这些问题，Data Governance 才是工程控制，而不是数据库字段命名规范。
