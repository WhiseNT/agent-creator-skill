# Agent Memory Privacy Operations Engineering 细粒度工程设计
> 本文定义 Agent Harness 中 Memory Privacy Operations 的控制面、数据面与运营边界。
> 它覆盖 data inventory、PII/secret/regulated 分类、purpose/legal basis/consent/notice、最小化、memory write/recall/egress/redaction、provider/embedding/rerank/subagent/backup copies、retention/TTL/legal hold、delete/forget/DSAR/export、access request、privacy incident、DLP、residency/cross-border、privacy SLO、reconciliation、case/runbook、break-glass、用户通知与解释、隐私测试和运营指标。
> 核心判断：隐私运营不是在 memory 表增加一个 `privacy` 字段，而是管理每个数据资产、派生视图、副本、外发尝试、保留决定和删除证据。标题映射约定：`Decision table` 即“决策表”，`BreakGlassGrant` 即“紧急访问授权”，`PrivacyCase` 即“隐私案件”，`Release Gate` 即“发布门禁”，代码类型名保留英文以便实现对齐。
## 目录
1. [目标与非目标](#目标与非目标)
2. [核心 truth 与术语](#核心-truth-与术语)
3. [职责边界与架构](#职责边界与架构)
4. [Data Inventory 与血缘](#data-inventory-与血缘)
5. [PII、Secret、Regulated 与敏感度](#piisecretregulated-与敏感度)
6. [Purpose、Legal Basis、Consent、Notice](#purposelegal-basisconsentnotice)
7. [最小化与数据视图](#最小化与数据视图)
8. [核心模型与 TypeScript 接口](#核心模型与-typescript-接口)
9. [Memory Write](#memory-write)
10. [Memory Recall 与 ContextPlan](#memory-recall-与-contextplan)
11. [Egress、Redaction 与 DLP](#egressredaction-与-dlp)
12. [Provider、Embedding、Rerank、Subagent 副本](#providerembeddingreranksubagent-副本)
13. [Artifact、Cache、Queue、Trace、Backup](#artifactcachequeuetracebackup)
14. [Retention、TTL、Legal Hold](#retentionttllegal-hold)
15. [Delete、Forget、DSAR、Export](#deleteforgetdsarexport)
16. [Access Request 与 Break-glass](#access-request-与-break-glass)
17. [Privacy Case、Incident 与 Runbook](#privacy-caseincident-与-runbook)
18. [生命周期与状态机](#生命周期与状态机)
19. [决策流程与解释](#决策流程与解释)
20. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
21. [Residency、Cross-border 与 Provider Contract](#residencycross-border-与-provider-contract)
22. [Privacy SLO 与运营指标](#privacy-slo-与运营指标)
23. [Reconciliation 与 Evidence](#reconciliation-与-evidence)
24. [测试、发布门禁与评估](#测试发布门禁与评估)
25. [故障恢复与安全降级](#故障恢复与安全降级)
26. [反模式](#反模式)
27. [实施清单](#实施清单)
28. [五个参考项目的启发来源](#五个参考项目的启发来源)
## 目标与非目标
### 目标
Memory Privacy Operations 必须：
- 对 Session、Run、Turn、Attempt、Message/Part、ToolCall、ToolResult、Artifact、Memory、Embedding、Rerank、Cache、Queue、Trace、Backup、Provider Remote Object 和 Export 建立可查询 inventory。
- 将保护强度与数据类别分轴表达：`public/internal/confidential/secret/regulated` 不替代 `pii/credential/health/financial/location`。
- 为每次处理绑定 purpose、legal basis、consent/notice、scope、owner、destination、retention 和 deletion contract。
- 将 memory candidate 经过来源、分类、最小化、冲突、授权、TTL 和派生副本检查后，才变成 durable memory。
- 将 recall 视为受治理的资源选择；向量相似度只能参与排序，不能授权访问。
- 在 ContextPlan、Provider Runtime、Tool、Subagent、Embedding、Rerank、Artifact、Analytics 和 Backup 边界执行 egress/redaction/DLP。
- 识别 raw、summary、tokenized、embedding、rerank feature、cache、日志、诊断、导出包、备份和远端对象。
- 支持 retention、TTL、legal hold、incident hold、forget、delete、DSAR、export、access request 和 deletion proof。
- 以 privacy case、incident、runbook、通知、解释、reconciliation 和 evidence 支持运营。
- 对 scope isolation、secret egress、跨境、错误删除和未知远端副本设置不可被普通可用性预算抵消的硬门禁。
### 非目标
- 不代替法务确定具体司法辖区的最终法律结论。
- 不以一个 `consent: boolean`、provider 问卷或“不会训练”文字证明合规。
- 不把 MemoryStore 变成所有 transcript、文件和 provider response 的万能仓库。
- 不允许模型、Prompt、RAG、ToolResult 或用户文本授予 purpose、retention、consent、外发或删除权限。
- 不承诺本地删除自动删除不可控 provider、搜索、备份或下游副本。
- 不因恢复、吞吐或成本而关闭 DLP、audit、residency、approval 或 hold。
- 不把 privacy operations 归并为数据库 GC、日志清理或 CPU dashboard。
### 正确性公式
```text
Privacy Correctness
  = Inventory Completeness
  × Classification Quality
  × Purpose/Lawfulness Binding
  × Scope Enforcement
  × Egress Control
  × Retention Execution
  × Deletion Reconciliation
  × Incident Readiness
```
任一因子为零，都可能出现“看起来已删除”但仍可 recall、恢复或外发的情况。
## 核心 truth 与术语
### 三种 truth
```text
User Truth   用户的保存、查看、撤回、忘记、删除、导出和通知意图
Policy Truth 租户、workspace、purpose、retention、region、provider policy
Data Truth   实际存在的 asset、copy、derived view、状态、receipt 和证据
```
- 用户说“忘记它”是控制意图，不是删除证明。
- Policy 决定允许边界；模型文本不具有 policy authority。
- DataInventory、MemoryStore、Index、Artifact、Provider Receipt、Backup Manifest 和 EventStore 证明实际状态。
### 关键术语
- `DataAsset`：可被处理、存储、派生、外发、备份或删除的逻辑对象。
- `DataCopy`：asset 在某个 store、provider、index、cache、queue、trace、analytics 或 backup 中的具体副本。
- `DerivedView`：由 raw、summary、redacted、tokenized、embedding、rerank 或 projection 产生的视图。
- `MemoryCandidate`：待治理的候选事实；不能直接进入 active memory。
- `MemoryRecord`：具备 provenance、scope、purpose、retention 和删除路径的 memory。
- `PrivacySnapshot`：一次操作冻结的 scope、policy、purpose、consent、DLP、region 和 retention 输入。
- `EgressDecision`：向一个确定 destination 发送一个确定 view 的决定。
- `Forget`：从 active recall/index 排除并阻止新写回；不等同物理删除。
- `Delete`：依 contract 删除指定 raw、派生物、副本和可控远端对象。
- `Unknown`：证据不足以确认发生或未发生；不得转换成 `deleted`、`not_sent` 或 `no_exposure`。
- `LegalHold`：只阻止匹配资产/副本删除，不自动扩大读取或外发权限。
- `PrivacyEvidence`：证明分类、授权、发送、保留、删除、通知、恢复或对账的引用。
### Memory 边界
- Memory 是跨任务可复用资源，不是 transcript 的默认副本。
- Memory write 是独立 processing operation。
- Memory recall 是 ContextPlan 的输入，不是 permission、approval 或 capability 的来源。
- Embedding、rerank、subagent delegation、provider upload、backup 和 export 都是独立处理。
- provider delete unknown 必须保持 unknown，并触发查询、人工升级或补偿路径。
## 职责边界与架构
### 组件边界
| 组件 | 负责 | 不负责 |
|---|---|---|
| `DataInventory` | 资产、来源、派生、复制图、owner 和 manifest | 自行批准外发 |
| `Classifier/DLP` | 敏感度、PII、secret、regulated 和恶意内容发现 | 代替法务得出全部法律结论 |
| `PurposeRegistry` | purpose、legal basis、notice、consent schema | 保存不必要原文 |
| `PrivacyPolicyEngine` | scope、purpose、retention、region、destination decision | 调用 provider |
| `MemoryWriter` | candidate 提取、验证、审批、写入和索引计划 | 越过 DLP 或 consent |
| `MemoryRecall` | hard filter、排序、最小化、ContextPlan 引用 | 改写 memory 状态 |
| `EgressGateway` | view、redaction、DLP、destination、receipt | 自行选择任意 provider |
| `RetentionScheduler` | TTL、hold、reaper、deletion job | 伪造删除完成 |
| `DeletionCoordinator` | delete、forget、DSAR、export 编排与对账 | 直接绕过 store contract |
| `ProviderRuntime` | 协议、usage、remote object、状态查询 | tenant policy、consent |
| `Embedding/Rerank` | 派生计算、索引和查询协议 | 将派生物视为匿名公开数据 |
| `SubagentSupervisor` | child scope、purpose、预算、view 和结果合并 | 自动继承父级全部 memory |
| `Backup/DR` | manifest、加密、restore、hold、删除传播 | 以备份豁免 retention |
| `Case/IncidentService` | case、containment、通知、operator workflow | 擅自删除证据 |
| `Host/Product` | 展示解释、收集控制、提交 command | 以 UI 隐藏代替 canonical truth |
### 总体拓扑
```text
Host/API
 -> Auth + TenantContext + Scope Resolver
 -> Purpose/LegalBasis/Consent/Notice Resolver
 -> Inventory + Classifier + DLP
 -> PrivacyPolicy + Residency + Retention Snapshot
 -> Memory Write/Recall + ContextPlan
 -> EgressGateway + Redaction/Tokenization
 -> Provider/Embedding/Rerank/Tool/Subagent
 -> Memory/Index/Artifact/Queue/Trace/Analytics
 -> Backup/DR + DeletionCoordinator
 -> Event/Audit + Case/Incident + Notification
```
### 控制面与数据面规则
- 控制面保存 policy、purpose、consent、notice、classification、retention、hold、case、grant、contract 和 deletion plan。
- 数据面只读取冻结的 `PrivacySnapshot`、`EgressSnapshot`、`RetentionSnapshot` 和 `ScopeRef`。
- 数据面不能在发送中途读取 latest 配置覆盖已冻结边界。
- 撤回 consent、provider revoke、incident 和 legal hold 变化可生成 durable control event，阻断后续高风险动作。
- 控制面不可用时，secret、regulated、未知分类、跨境和远端删除默认 fail-closed。
### 包布局
```text
packages/privacy-operations/
  contracts.ts inventory.ts lineage.ts classification.ts pii.ts secret.ts regulated.ts
  purpose.ts legal-basis.ts consent.ts notice.ts minimization.ts views.ts
  egress.ts redaction.ts dlp.ts residency.ts cross-border.ts
  retention.ts ttl.ts legal-hold.ts reaper.ts deletion.ts forget.ts dsar.ts export.ts
  access-request.ts break-glass.ts cases.ts incidents.ts runbooks.ts notifications.ts
  reconciliation.ts evidence.ts audit.ts metrics.ts testkit/
packages/memory-runtime/
  writer.ts recall.ts candidate.ts contradiction.ts index.ts embedding.ts rerank.ts
packages/privacy-adapters/
  provider.ts embedding.ts artifact.ts backup.ts analytics.ts queue.ts trace.ts
```
## Data Inventory 与血缘
### Inventory 覆盖范围
至少登记以下对象：
- User/Assistant `Message`、`Part`、附件、PromptSection、ContextResource 和 ContextPlan。
- MemoryCandidate、MemoryRecord、normalized fact、contradiction、supersede 和 tombstone。
- ToolCall、参数投影、ToolResult、ExecutionReceipt、错误诊断和重试记录。
- Artifact raw、sanitized、summary、preview、range、diff、snapshot、export、forensic bundle。
- embedding input、vector、metadata、index shard、rerank feature、query log 和 cache。
- queue command、job payload、checkpoint、lease、retry、dead-letter 和 recovery record。
- provider request、response metadata、remote file、batch、cache、usage、safety 和 support object。
- subagent assignment、delegated context、child memory view、child output 和 parent fan-in。
- trace、metric、analytics、audit、backup、replica、snapshot、tombstone 和通知包。
### DataAsset 与 DataCopy
```typescript
type Sensitivity = "public" | "internal" | "confidential" | "secret" | "regulated";
type DataClass =
  | "pii" | "credential" | "financial" | "health" | "biometric" | "location"
  | "identity" | "communication" | "source_code" | "business_confidential"
  | "child_data" | "legal" | "security_event" | "public_content";
type DataViewKind =
  | "full" | "redacted" | "tokenized" | "pseudonymized" | "summary" | "range"
  | "metadata_only" | "artifact_only" | "embedding_input" | "rerank_features" | "deny";
interface ScopeRef {
  tenantId: string;
  userId?: string;
  workspaceId?: string;
  projectId?: string;
  sessionId?: string;
  runId?: string;
  scopeVersion: number;
}
interface DataAsset {
  assetId: string;
  kind: string;
  ownerScope: ScopeRef;
  sourceRefs: string[];
  parentAssetId?: string;
  sensitivity: Sensitivity;
  dataClasses: DataClass[];
  purposeRefs: string[];
  legalBasisRefs: string[];
  consentRefs: string[];
  retentionPolicyId: string;
  residencyProfileId: string;
  status: "active" | "quarantined" | "held" | "deleting" | "deleted" | "unknown";
  contentHash?: string;
  metadataHash: string;
  createdAt: string;
  updatedAt: string;
}
interface DataCopy {
  copyId: string;
  assetId: string;
  storeKind: string;
  backendId: string;
  ownerScope: ScopeRef;
  view: DataViewKind;
  region?: string;
  jurisdiction?: string;
  purposeRef: string;
  retentionExpiresAt?: string;
  legalHoldIds: string[];
  deletionStatus: "present" | "requested" | "processing" | "deleted" | "unverified" | "blocked";
  remoteReceiptRef?: string;
  lastReconciledAt?: string;
  evidenceRefs: string[];
}
```
### Lineage 图
```text
source message/file
 -> candidate claim
 -> memory record
 -> redacted/tokenized view
 -> embedding input/vector/index
 -> recall hit
 -> ContextPlan
 -> provider request/response
 -> summary/artifact/trace/backup/export
```
每条 lineage edge 记录：
- `extract/summarize/redact/tokenize/embed/rerank/project/export/backup` 转换类型。
- transform version、输入/输出 hash、执行主体、purpose、时间和 policy snapshot。
- 是否可逆、是否包含 raw、是否改变 sensitivity、是否创建新副本。
- 删除时需要传播 tombstone、revoke、delete request 或 rebuild 的下游边。
### Inventory 不变量
- 新 store、provider、index、cache、backup、export sink 必须先注册 adapter。
- 未登记副本不能进入 production allowlist。
- inventory 与真实 backend manifest 周期性 reconciliation。
- `unknown_copy` 阻断高敏感对象的 deletion complete 声明。
- 不只扫描 MemoryStore；必须覆盖 embedding、backup、trace、queue 和 provider remote object。
- orphan copy、orphan token map、orphan index 和未归属 artifact 都创建 finding。
## PII、Secret、Regulated 与敏感度
### 双轴分类
```text
Sensitivity: public | internal | confidential | secret | regulated
DataClass:   pii | credential | financial | health | biometric | location
             | identity | communication | source_code | business_confidential
             | child_data | legal | security_event | public_content
```
Sensitivity 表示保护强度，DataClass 表示风险类型；两者不能互相替代。
### ClassificationResult
```typescript
interface DetectedEntity {
  type: string;
  spanHash: string;
  confidence: number;
  source: "pattern" | "ml" | "provider" | "human";
  action: "redact" | "tokenize" | "retain" | "review";
}
interface ClassificationResult {
  assetId: string;
  sensitivity: Sensitivity;
  classes: DataClass[];
  entities: DetectedEntity[];
  confidence: number;
  detectorVersions: string[];
  rulesApplied: string[];
  allowedViews: DataViewKind[];
  redactionRequired: boolean;
  reviewRequired: boolean;
  status: "classified" | "uncertain" | "quarantined" | "failed";
  evidenceRefs: string[];
}
```
### 分类规则
- `secret`、credential、private key、session token、password、bearer token 和 provider secret 默认 deny 长期 Memory、embedding、trace 和 provider egress。
- `regulated`、health、biometric、child_data 和高风险 PII 默认 deny 或短 TTL、最小 view、强审批。
- PII 只有在 purpose、scope、legal basis、notice、consent/例外和 provider contract 均满足时才可进入受限 memory。
- source code、workspace rule 和 project fact 可是 confidential，但不自动等于 PII。
- provider response、tool result、artifact 和模型推断必须重新扫描，不能继承输入分类。
- embedding、rerank feature、cache、backup 和 summary 继承 source 的最严格 scope、purpose、retention 和删除义务。
- 分类器失败、超时、规则过期或意见冲突进入 `uncertain`，不能降级为 public。
### 人工复核
人工只能改变有范围、有版本、有 expiry 的 classification decision，不能删除原始检测证据。
复核记录 reviewer、scope、reason、旧/新分类、允许 view、destination、是否重新 notice/consent、expiry 和 evidence。
## Purpose、Legal Basis、Consent、Notice
### Purpose
```typescript
interface ProcessingPurpose {
  purposeId: string;
  code: string;
  description: string;
  allowedOperations: string[];
  allowedDataClasses: DataClass[];
  allowedScopes: string[];
  allowedDestinations: string[];
  defaultRetentionPolicyId: string;
  noticeVersion: string;
  status: "draft" | "active" | "retired";
  owner: string;
  createdAt: string;
}
```
典型 purpose：
- `task_execution`：完成当前任务。
- `memory_write`：保存未来可复用事实或偏好。
- `memory_recall`：为当前任务选择受治理 memory。
- `embedding_indexing`、`rerank_retrieval`：生成和查询检索派生物。
- `provider_inference`：向模型 provider 发送最小工作集。
- `subagent_delegation`：向 child run 委派最小信息。
- `security_detection`、`reliability_diagnostics`、`billing_usage`：安全、恢复和计量。
- `legal_hold`、`user_export`：保全和主体导出。
Purpose 不变量：
- purpose 必须具体到 operation 和 destination，不能用“产品改进”覆盖全部处理。
- 一个 asset 可以有多个 purpose，但每个 purpose 有独立 retention、notice 和访问规则。
- embedding 不是 recall 的隐式步骤；provider fallback 不是 primary purpose 的自动继承。
- purpose 变化创建新 processing record，不覆盖历史事实。
### LegalBasis
```typescript
interface LegalBasisRef {
  basisId: string;
  jurisdiction: string;
  basisType: "consent" | "contract" | "legitimate_interest" | "legal_obligation"
    | "vital_interest" | "public_task" | "internal_policy" | "unknown";
  purposeId: string;
  scope: ScopeRef;
  sourceRef: string;
  effectiveAt: string;
  expiresAt?: string;
  withdrawnAt?: string;
  version: string;
}
```
- legal basis 是控制面引用，不由模型文本解释。
- `unknown` 对 confidential、secret、regulated provider egress 默认 deny。
- contract basis 允许当前任务不等于允许长期 memory、analytics 或 training。
- jurisdiction、purpose、destination 或 data class 改变时重新评估 basis。
### Consent 与 Notice
```typescript
interface ConsentReceipt {
  consentId: string;
  subjectRef: string;
  tenantId: string;
  purposeId: string;
  scope: ScopeRef;
  dataClasses: DataClass[];
  noticeVersion: string;
  choice: "granted" | "denied" | "withdrawn" | "expired";
  mode: "explicit" | "configured" | "delegated";
  capturedAt: string;
  effectiveAt: string;
  expiresAt?: string;
  withdrawalAt?: string;
  evidenceRef: string;
}
interface NoticeVersion {
  version: string;
  effectiveAt: string;
  coveredPurposes: string[];
  coveredDestinations: string[];
  summaryHash: string;
  locale: string;
}
```
Notice 应说明：
- 哪些数据会被记忆、召回、embedding、发送、备份或导出。
- purpose、provider/region、retention、远端副本和删除限制。
- 哪些动作需要 approval，哪些是安全、计费、法定义务例外。
- 用户如何查看、修改、忘记、删除、导出、限制处理或撤回。
- 当前 notice version、变更摘要和生效时间。
Notice 展示不等于 consent；consent grant 也不越过 tenant、security、legal hold 或 provider contract。
撤回 consent 后：
- 停止新写入、召回、embedding、rerank、provider egress 和 subagent delegation。
- 现有事实按 retention、audit、legal hold 和安全证据规则处理。
- 不将既有 provider copy 伪装成已消失；启动 copy inventory 与 deletion reconciliation。
## 最小化与数据视图
### View 类型
```text
full -> redacted -> tokenized/pseudonymized -> summary/range
      -> metadata_only/artifact_only -> deny
```
- `full` 仅限确有必要且被当前 purpose、scope、destination 允许。
- `redacted` 删除或掩码指定类别。
- `tokenized` 只在可信本地 token broker 内可逆，token map 不进入 prompt、provider、embedding、日志或 backup。
- `summary` 必须保留 provenance，并标记不确定推断。
- `metadata_only` 也可能泄露 PII、路径、租户关系和时间模式，仍须分类。
- `artifact_only` 通过受控引用访问，不等于无隐私风险。
### 最小化原则
- 先确定 purpose，再选择字段、片段、时间范围和关系；不能复制全 transcript 后再过滤。
- recall 同时限制 item count、token budget、sensitivity ceiling、freshness、destination 和成本。
- 不把 summary 当匿名化；不把 pseudonymization 当不可识别。
- transform 失败时 secret/regulated deny；低风险可退化为 metadata-only、summary 或人工复核。
- 每次 view transform 产生新的 asset/copy、hash、规则版本、removed/retained classes 和 evidence。
```typescript
interface ViewTransformRequest {
  assetId: string;
  targetView: DataViewKind;
  purposeId: string;
  destination: string;
  sensitivityCeiling: Sensitivity;
  redactionProfileId?: string;
  tokenizationProfileId?: string;
  maxBytes?: number;
  maxTokens?: number;
}
interface ViewTransformResult {
  outputAssetId: string;
  outputView: DataViewKind;
  sourceHash: string;
  outputHash: string;
  transformVersion: string;
  removedClasses: DataClass[];
  retainedClasses: DataClass[];
  reversible: boolean;
  obligations: string[];
  evidenceRefs: string[];
}
```
## 核心模型与 TypeScript 接口
### PrivacySnapshot
```typescript
interface PrivacySnapshot {
  snapshotId: string;
  scope: ScopeRef;
  tenantContextHash: string;
  purposeRefs: string[];
  legalBasisRefs: string[];
  consentRefs: string[];
  noticeVersion: string;
  policyVersion: string;
  classificationVersion: string;
  dlpProfileVersion: string;
  residencyProfileId: string;
  retentionPolicyId: string;
  allowedDestinations: string[];
  allowedViews: DataViewKind[];
  createdAt: string;
  expiresAt: string;
  revokedAt?: string;
  hash: string;
}
```
### PrivacyMemoryRecord 与 Candidate
```typescript
interface PrivacyMemoryRecord {
  memoryId: string;
  type: "semantic" | "episodic" | "procedural" | "working";
  claim: string;
  sourceRefs: string[];
  provenance: { actor: string; method: string; confidence: number; version: string };
  scope: ScopeRef;
  sensitivity: Sensitivity;
  dataClasses: DataClass[];
  purposeRefs: string[];
  legalBasisRefs: string[];
  consentRefs: string[];
  noticeVersion: string;
  retentionPolicyId: string;
  expiresAt?: string;
  legalHoldIds: string[];
  embeddingRefs: string[];
  rerankRefs: string[];
  providerCopyRefs: string[];
  subagentCopyRefs: string[];
  status: "candidate" | "active" | "stale" | "contradicted" | "forgotten" | "deleting" | "deleted" | "unknown";
  supersedes?: string;
  tombstoneRef?: string;
  createdAt: string;
  updatedAt: string;
}
interface PrivacyMemoryCandidate {
  candidateId: string;
  claim: string;
  type: PrivacyMemoryRecord["type"];
  sourceRefs: string[];
  proposedScope: ScopeRef;
  classes: DataClass[];
  proposedPurposeId: string;
  confidence: number;
  requiresConsent: boolean;
  requiresApproval: boolean;
  contradictionRefs: string[];
  reasonCodes: string[];
  status: "proposed" | "classifying" | "awaiting_consent" | "awaiting_review" | "accepted" | "rejected" | "expired";
}
```
### Decision、Evidence 与端口
```typescript
type PrivacyOperation = "read" | "write" | "recall" | "embed" | "rerank" | "egress" | "export" | "backup" | "delete" | "forget" | "notify";
type PrivacyDecision = "allow" | "redact" | "summarize" | "tokenize" | "artifact_only" | "ask" | "hold" | "deny" | "unknown";
interface PrivacyDecisionRecord {
  decisionId: string;
  operation: PrivacyOperation;
  subjectAssetRefs: string[];
  actor: string;
  scope: ScopeRef;
  purposeId: string;
  decision: PrivacyDecision;
  reasons: string[];
  snapshotId: string;
  inputHashes: string[];
  outputRefs: string[];
  obligations: string[];
  expiresAt?: string;
  evidenceRefs: string[];
  createdAt: string;
}
interface PrivacyEvidence {
  evidenceId: string;
  kind: "classification" | "consent" | "notice" | "policy" | "egress" | "redaction" | "provider" | "deletion" | "backup" | "access" | "incident" | "reconciliation";
  subjectRefs: string[];
  source: string;
  contentHash?: string;
  status: "observed" | "verified" | "expired" | "conflicted" | "missing";
  capturedAt: string;
  expiresAt?: string;
  integrityRef?: string;
}
interface PrivacyOperationsPort {
  classify(input: unknown): Promise<ClassificationResult>;
  evaluate(input: unknown): Promise<PrivacyDecisionRecord>;
  createSnapshot(input: unknown): Promise<PrivacySnapshot>;
  requestDelete(input: unknown): Promise<unknown>;
  requestForget(input: unknown): Promise<unknown>;
  createDSAR(input: unknown): Promise<DSARCase>;
  requestAccess(input: AccessRequest): Promise<AccessReceipt>;
  reconcile(input: unknown): Promise<ReconciliationReport>;
}
```
## Memory Write
### 写入必须回答的问题
- claim 对未来是否有明确复用价值，还是仅为当前 turn 的 transient context？
- 来源是 user、tool、file、retrieval、model inference 还是 human review？
- scope 是否清楚，是否越过 session、workspace、user 或 tenant？
- purpose、legal basis、notice、consent/例外是否满足？
- 是否含 PII、secret、regulated、第三方数据或不可验证推断？
- 是否需要审批、短 TTL、redaction、tokenization 或不写入？
- 生成哪些 embedding、rerank、backup、provider、cache、subagent copy？
- contradiction、supersede、forget 和 deletion path 是否存在？
### Write 流程
```text
observe transcript/tool/artifact
 -> extract candidate claims
 -> attach provenance and source refs
 -> resolve scope and purpose
 -> classify sensitivity/PII/secret/regulated
 -> run minimization and DLP
 -> check legal basis/consent/notice
 -> check duplicate/contradiction/freshness
 -> compute TTL/retention/hold
 -> ask user or create policy decision
 -> persist MemoryRecord and tombstone links
 -> create only approved derived copies
 -> update index/projector
 -> emit audit, evidence and notification
```
### Decision table
| 条件 | 决策 |
|---|---|
| public/internal、来源清晰、稳定、目的合法 | `allow`，默认 TTL |
| confidential、用户明确保存、scope 清晰 | `ask` 或受 tenant policy 允许后写入 |
| secret、credential、private key、token | `deny`，只记录最小 reason |
| regulated 或第三方敏感数据 | `deny` 或短 TTL 加强审批 |
| 只有模型推断、无可验证来源 | 保持 candidate 或 reject |
| 当前任务需要但长期保存无 basis | 允许 working memory，不写长期 memory |
| 分类器/DLP unknown | `hold`，等待复核 |
| contradiction 未解决 | 不覆盖既有记录，进入 review |
| embedding/provider 不满足 residency | 本地保存或禁用派生外发 |
| consent withdrawn | 停止新处理并启动 downstream review/delete |
### 用户可见状态
产品必须区分“发现候选”“已保存当前任务”“已保存 user/workspace memory”“已创建索引”“尚未发送 provider/embedding”“因敏感度或权限未保存”。
助手说“我会记住”不等于 `MemoryRecord` 已 active。
### Write 恢复
- candidate append 成功但分类失败：保持 `classifying`，不进入 recall。
- consent 请求后 Host 断线：保持 awaiting，不自动批准。
- record 已写但 embedding 失败：memory active，index pending，召回标记不完整。
- embedding 已发送但 receipt unknown：copy unknown，不能声称未外发。
- backup 失败：按 policy 进入 backup_pending，不能绕过 deletion contract。
## Memory Recall 与 ContextPlan
### Recall 是治理后的检索
```text
tenant/scope
 -> purpose/legal basis/consent
 -> sensitivity ceiling
 -> status/TTL/legal hold
 -> provider/region/egress compatibility
 -> freshness/contradiction
 -> relevance/authority/task-stage fit
 -> token/byte budget
 -> view transformation
 -> ContextPlan evidence
```
### Recall 接口
```typescript
interface MemoryRecallRequest {
  query: string;
  scope: ScopeRef;
  purposeId: string;
  privacySnapshotId: string;
  sensitivityCeiling: Sensitivity;
  allowedTypes?: string[];
  maxItems: number;
  tokenBudget: number;
  includeStale: boolean;
  includeContradicted: boolean;
  destination: string;
  requestedView: DataViewKind;
}
interface PrivacyMemoryHit {
  memoryId: string;
  viewRef: string;
  score: number;
  reasonCodes: string[];
  sourceRefs: string[];
  scope: ScopeRef;
  sensitivity: Sensitivity;
  stale: boolean;
  contradicted: boolean;
  redactionState: string;
  egressDecisionId: string;
  expiresAt?: string;
}
```
### 排序与 ContextPlan
```text
recall score
 = relevance × scope_match × authority × freshness × confidence × task_fit
 - contradiction_penalty - sensitivity_cost - redundancy - retention_risk
```
- 向量相似度只能参与 soft ranking，不能覆盖 scope、purpose、consent、hold、TTL 或 DLP deny。
- ContextPlan 记录 selected、filtered、redacted、summarized、dropped 及每个 reason。
- memory view 进入模型时标记为 data，不获得 instruction authority。
- ContextPlan 保存 purpose、provider、region、token budget、sensitivity、transform hash 和 evidence。
- compaction 不能丢失 source、consent、retention、remote object、deletion state 或 privacy deny。
- subagent 只能获得 delegated view 的交集，不能查询全局 memory index。
### 运行中撤回
撤回、forget、delete 或 incident 发生时：
- 停止新的 recall、embedding、provider egress 和 child delegation。
- 下一安全边界重新编译 ContextPlan，并排除 forgotten/tombstoned asset。
- 已发送的 provider request 进入 remote copy/in-flight reconciliation，不伪装可撤回。
- UI 同时展示“后续处理已停止”和“既有外发正在核查”。
## Egress、Redaction 与 DLP
### Destination 分类
- Model Provider、provider cache、batch、file object、safety review、support access。
- Embedding、Rerank、Vector DB、Search、Feature Store、query log。
- Tool、MCP、Plugin、Subagent、Remote Worker、Webhook、Notification。
- Artifact share、Export、Analytics、Trace、Support、Forensics、Backup。
- Cross-region replica、DR restore namespace、operator diagnostic。
### Egress 流程
```text
asset inventory
 -> classify
 -> purpose/legal basis/consent/notice
 -> tenant/workspace policy
 -> destination contract/residency
 -> choose minimum view
 -> DLP/secret/PII/regulated scan
 -> token/byte/cost/retention check
 -> send with idempotency and receipt
 -> register copy and lineage
 -> reconcile remote status
```
### RedactionProfile
```typescript
interface RedactionProfile {
  profileId: string;
  version: string;
  rules: Array<{ class: DataClass; action: "remove" | "mask" | "hash" | "tokenize" | "generalize" | "summarize"; destinationAllowlist?: string[] }>;
  preserveStructure: boolean;
  reversible: boolean;
  mapScope?: ScopeRef;
  mapExpiresAt?: string;
  failMode: "deny" | "summary" | "metadata_only";
  detectorVersions: string[];
}
```
- token map 只在可信 control plane 保存，并绑定 tenant、scope、purpose、destination、expiry。
- 反替换必须在受控本地边界完成；provider output 不能任意回填 secret。
- 输入、memory view、tool result、provider response、artifact、export、backup 都必须可扫描。
- scanner timeout、规则过期、冲突或 payload 未完成状态为 unknown，不是 clean。
- DLP allow 只证明当前 view 和当前 destination，不自动授权 retry、fallback、hedge 或 shadow。
- DLP 事件默认记录 hash、类别、规则版本、decision 和 evidence，不记录原文。
- scanner 自身的样本、debug、cache 和模型输入也进入 inventory。
## Provider、Embedding、Rerank、Subagent 副本
### Provider copy
Provider 请求可能产生 request/response retention、cache、conversation state、batch、file object、abuse detection、human review、quality evaluation、usage metadata 和 support export；每一种都登记为独立 `DataCopy`。
Provider contract 至少覆盖：
- 训练/质量使用、retention、abuse review、human access 和 region。
- request、response、file、batch、cache 和 remote delete API。
- status query、receipt、删除延迟、不可删除对象和通知义务。
- fallback、retry、hedge、shadow、canary 的 destination 变化。
### Embedding 与 Rerank
- embedding 记录输入 view、purpose、model/provider、region、版本、usage、vector、metadata、shard 和 deletion API。
- embedding 不是匿名化；vector、metadata、batch、cache 和 query log 继承 source 的 scope、sensitivity、retention 和删除义务。
- rerank 记录 query、candidate refs、feature、score、cache 和 telemetry；只传 ID 也可能产生可关联个人数据。
- backend 不满足 residency、retention 或 per-item delete 时，使用本地排序、metadata-only 或 deny。
### Subagent delegated view
```typescript
interface DelegatedMemoryView {
  assignmentId: string;
  parentRunId: string;
  childRunId: string;
  sourceMemoryIds: string[];
  viewRefs: string[];
  purposeId: string;
  scope: ScopeRef;
  sensitivityCeiling: Sensitivity;
  allowedOperations: PrivacyOperation[];
  expiresAt: string;
  noWriteBackByDefault: boolean;
  privacySnapshotId: string;
}
```
- child 只能访问 delegated view 的交集；不继承 raw memory、secret、credential 或全量 workspace history。
- child output 回 parent 前重新分类、DLP、purpose、scope 和 egress。
- child candidate 默认归 child scope，不自动升级为 user/workspace memory。
- cancel、forget、delete、incident 和 consent revoke 必须传播到 child copy。
- primary allow 不自动授权 fallback；每个 retry/fallback/hedge/shadow/canary 创建新的 Attempt 与 EgressDecision。
- unknown provider request 在状态查询前不得复制到另一个 provider。
## Artifact、Cache、Queue、Trace、Backup
### Artifact 视图
```text
raw -> sanitized -> summary/preview/range -> export/forensic
```
- raw 使用最短 retention、最小 owner 和强 ACL。
- sanitized 经过 DLP/secret/PII 处理；summary 保留 provenance。
- export 有短 TTL、加密、下载审计、撤销和独立删除路径。
- forensic bundle 通常受 incident/legal hold，不代表允许普通访问。
- artifact publish、provider upload、user delivery 是三个不同事实。
### Cache
cache key 绑定 tenant、scope、purpose、policy、provider、region、view、source hash 和 expiry。
- prompt、memory、embedding 和 provider cache 不得跨 tenant 共享。
- cache hit 仍需检查当前 scope、consent、revocation、retention 和 hold。
- forget/delete 后使 cache key 失效并保存验证证据。
- 无法定位 cache copy 时，删除 case 不能 complete。
### Queue 与 Trace
Queue payload 只放 asset/copy refs、snapshot hash、purpose、scope、分类摘要、idempotency key 和最小 assignment。
- 不放明文 secret、完整 transcript、完整 raw memory 或未经最小化文件。
- delete、DSAR export、reconciliation、embedding、provider status query 都是 durable job。
- dead-letter 使用 protected reference 和最小诊断，不复制敏感 payload。
- trace 使用 hash、类别、大小、version、decision、provider class、latency、receipt ref。
- 普通 metrics label 不使用 raw tenant ID、prompt、memory claim、路径、token map 或 provider URL。
### Backup
```typescript
interface BackupManifest {
  manifestId: string;
  store: string;
  region: string;
  tenantScope: ScopeRef;
  watermark: string;
  keyRef: string;
  retentionClass: string;
  inventoryVersion: string;
  objectCount: number;
  tombstoneWatermark: string;
  legalHoldIds: string[];
  restoreNamespace: string;
  perAssetDelete: boolean;
  createdAt: string;
}
```
- backup purpose 通常是 `backup_recovery` 或 `legal_hold`，不能无限期保留。
- 删除必须知道不可变窗口、重建路径、restore 防复活和最终 purge 证明。
- restore 先加载 tombstone、hold、scope 和 deletion watermark，再开放流量。
## Retention、TTL、Legal Hold
### RetentionPolicy
```typescript
interface RetentionPolicy {
  policyId: string;
  objectKinds: string[];
  scope: ScopeRef;
  purposeId: string;
  defaultTtlMs?: number;
  trigger: "created" | "last_accessed" | "task_completed" | "incident_closed" | "period_closed" | "consent_withdrawn";
  minimumRetentionMs?: number;
  maximumRetentionMs?: number;
  legalHoldAllowed: boolean;
  incidentHoldAllowed: boolean;
  derivedCopyRule: "inherit" | "shorter_only" | "independent" | "deny";
  backupRule: "purge_with_source" | "next_window" | "hold_required" | "unavailable";
  deleteVerification: "receipt" | "manifest" | "query" | "rebuild" | "manual";
  version: string;
}
interface LegalHold {
  holdId: string;
  scope: ScopeRef;
  assetSelectors: string[];
  purposeId: string;
  authority: string;
  reason: string;
  caseRef: string;
  startsAt: string;
  expiresAt?: string;
  status: "requested" | "active" | "released" | "expired";
  evidenceRefs: string[];
}
```
### TTL 规则
- TTL 使用 server time 和 durable schedule，是治理边界而不是建议值。
- 派生 copy 默认继承 source 的最大 retention 上限，不能自行延长。
- `last_accessed` 不得被后台扫描无限刷新。
- TTL 到期先进入 `deletion_requested`，再按 backend receipt/manifest/query 完成 reconciliation。
- reaper 必须幂等、可暂停、可恢复、限速并限制 blast radius。
- hold 创建、扩展、释放都有 actor、scope、reason、expiry 和 audit。
- hold 只阻止匹配对象删除，不扩大 read、export、provider egress 或 operator access。
- deletion 与 hold 冲突进入 `blocked_by_hold`，不能伪造 failed 或 completed。
### Retention reconciliation
周期性比较：
```text
policy snapshot vs object TTL
source expiry vs derived copy expiry
hold selector vs copy status
reaper job vs backend manifest
provider retention vs contract
backup watermark vs deletion watermark
```
差异创建 `RetentionFinding`，包含 owner、severity、safe repair、deadline 和 evidence。
## Delete、Forget、DSAR、Export
### 语义区分
- `forget`：立即停止 recall、从 active index 排除、阻止新写回、生成 tombstone。
- `delete`：按 contract 处理 primary、derived、cache、provider、backup、export、trace、artifact copy。
- `DSAR delete`：身份验证、scope 解析、hold 检查、跨系统逐项结果和通知的 case。
- `retention delete`：TTL/reaper 触发，不等同主体请求。
- `incident delete`：containment 或补救触发，保留最小必要证据。
### DeletionRequest 与 Plan
```typescript
interface DeletionRequest {
  requestId: string;
  requestedBy: string;
  subjectRef?: string;
  tenantId: string;
  scope: ScopeRef;
  selectors: string[];
  reason: "user" | "retention" | "privacy" | "correction" | "incident" | "operator";
  purposeId: string;
  includeDerived: boolean;
  includeProviderCopies: boolean;
  includeBackups: boolean;
  requestedAt: string;
  deadlineAt?: string;
  idempotencyKey: string;
}
interface DeletionPlan {
  planId: string;
  requestId: string;
  targetAssets: string[];
  targetCopies: string[];
  blockedCopies: string[];
  holdRefs: string[];
  expectedEvidence: string[];
  status: "planned" | "approved" | "running" | "blocked" | "partial" | "completed" | "failed" | "unknown";
  createdAt: string;
}
```
### 删除流程
```text
authenticate requester
 -> resolve subject/tenant/workspace/session scope
 -> discover inventory and lineage
 -> classify assets and copies
 -> check legal/incident hold
 -> freeze new writes and recall
 -> create and approve bounded plan
 -> enqueue idempotent deletion jobs
 -> delete primary/derived/cache/index/artifact
 -> query provider/remote object status
 -> process backup watermark and tombstones
 -> reconcile manifests and indexes
 -> create receipts and evidence
 -> notify user with completed/partial/blocked/unverified limits
 -> close case only when contract conditions meet
```
### 删除不变量
- 不能通过删除 UI 列表项、修改 projection 或覆盖 status 完成删除。
- tombstone 防止 late event、replay、reindex、stale cache 和 restore 复活对象。
- provider delete 不可验证时为 `unverified/unknown`，通知必须准确说明限制。
- 不可逆 remote action 失败后先 query/idempotency，再决定 retry、manual 或 unknown。
- 正在运行的 tool/provider action 不可伪造为 cancelled；保留 receipt/unknown。
- legal hold、audit 和必要安全证据可保留，但需独立 purpose、最小 view 和有限 retention。
### DSARCase 与 Export
```typescript
interface DSARCase {
  caseId: string;
  type: "access" | "export" | "delete" | "correct" | "restrict" | "withdraw";
  requester: string;
  subject: string;
  tenantId: string;
  verifiedIdentity: boolean;
  scope: ScopeRef;
  noticeVersion: string;
  receivedAt: string;
  deadlineAt?: string;
  status: "received" | "verifying" | "scoping" | "collecting" | "reviewing" | "fulfilling" | "blocked" | "completed" | "rejected" | "partial";
  assetRefs: string[];
  excludedRefs: string[];
  reasonCodes: string[];
  evidenceRefs: string[];
}
interface ExportReceipt {
  exportId: string;
  caseId: string;
  artifactRef: string;
  view: DataViewKind;
  includedRefs: string[];
  excludedReasons: string[];
  expiresAt: string;
  downloadAuditRef: string;
}
```
Export 必须按 subject scope 选择 memory、session、artifact、event、consent、notice 和 provider copy metadata。
- 不默认导出 secret、第三方数据、内部安全规则或其他 tenant 数据。
- 每个对象附 source、created/expiry、scope、sensitivity、copy status 和删除限制。
- 导出包本身是新 asset，有短 TTL、加密、下载审计、撤销和删除路径。
- 用户下载是新的 egress destination，不等于允许重新发送 provider。
## Access Request 与 Break-glass
### AccessRequest
```typescript
interface AccessRequest {
  requestId: string;
  requester: string;
  targetScope: ScopeRef;
  assetSelectors: string[];
  purposeId: string;
  requestedView: DataViewKind;
  requestedFields: string[];
  approvalRefs: string[];
  expiresAt?: string;
  idempotencyKey: string;
}
interface AccessReceipt {
  requestId: string;
  decision: "allow" | "partial" | "deny" | "unknown";
  grantedView: DataViewKind;
  grantedRefs: string[];
  excludedReasons: string[];
  expiresAt: string;
  auditRef: string;
}
```
访问层级：
```text
user self-access
 -> workspace delegated access
 -> tenant privacy operator
 -> security incident access
 -> legal/forensic access
 -> break-glass
```
每一级都要求可信 identity、tenant/scope、purpose、最小字段、时间边界、访问审计和下载/解密/replay 审计。
### BreakGlassGrant
```typescript
interface BreakGlassGrant {
  grantId: string;
  actor: string;
  approvers: string[];
  scope: ScopeRef;
  purposeId: string;
  allowedOperations: PrivacyOperation[];
  allowedAssetSelectors: string[];
  reason: string;
  issuedAt: string;
  expiresAt: string;
  requireSecondPerson: boolean;
  autoRevokeAt: string;
  status: "requested" | "active" | "expired" | "revoked";
  auditRef: string;
}
```
- break-glass 只能扩大具体 access，不能放宽 tenant isolation、security floor 或 legal hold。
- 强认证、短 TTL、双人审批、metadata-only 默认视图和逐项操作审计是强制条件。
- 自动撤销失败触发 incident，不能静默延长。
- 使用过的每个 asset/copy 都需要 post-incident review。
## Privacy Case、Incident 与 Runbook
### PrivacyCase
```typescript
interface PrivacyCase {
  caseId: string;
  kind: "dsar" | "access" | "deletion" | "consent" | "egress" | "classification" | "incident" | "hold";
  severity: "low" | "medium" | "high" | "critical";
  affectedScopes: ScopeRef[];
  affectedAssets: string[];
  owner?: string;
  status: "open" | "triaged" | "containing" | "fulfilling" | "waiting" | "resolved" | "reviewed";
  actions: string[];
  deadlines: string[];
  evidenceRefs: string[];
  notificationPlan?: string;
  createdAt: string;
  resolvedAt?: string;
}
```
### Incident 触发条件
- secret、PII 或 regulated 数据发送到错误 provider、tool、subagent、analytics、backup 或 region。
- cross-tenant memory recall、cache hit、artifact、trace、vector 或 export。
- 分类漏检导致高风险数据进入长期 memory、embedding 或日志。
- purpose、legal basis、notice 或 consent 缺失却发生处理。
- TTL 到期后仍可 recall、send、export 或 restore。
- deletion/DSAR 错误报告完成、未完成、被错误恢复或无法定位副本。
- provider training、retention、abuse、region 或 remote delete contract 漂移。
- break-glass 滥用、operator access 异常、audit 缺失或 backup/index 无法删除。
### Incident 状态机
```text
Detected -> Declared -> Triaged -> Containing -> Investigating
         -> Remediating -> Verifying -> Notifying -> Resolved -> Reviewed
```
### Incident 流程
```text
detect
 -> declare severity and scope
 -> stop new write/recall/egress
 -> revoke route/lease/credential if needed
 -> quarantine affected copy/index/cache
 -> preserve minimal forensic evidence
 -> classify known/unknown exposure
 -> assess notification and contract duties
 -> remediate/delete/rotate/rebuild
 -> verify containment and reconciliation
 -> notify affected users/tenants where required
 -> close with regression fixture and review
```
### Egress Incident Runbook
1. 读取 `PrivacySnapshot`、`EgressDecision`、ContextPlan、request hash、destination 和 region。
2. 判定错误来自 view、purpose、scope、region、provider contract、credential 或 DLP。
3. 停止同类 route、embedding、rerank、subagent、cache 和 queue 写入。
4. 查询 provider remote object、request status、retention、delete capability 和 downstream copy。
5. 将 exposure 标记为 `known` 或 `unknown`，不伪造为未发生。
6. 轮换受影响 credential/token，撤销 contract、route、lease 和 grant。
7. 按 policy 处理 delete、hold、DSAR、用户通知和升级。
8. 记录时间线、影响范围、证据、修复和复发门禁。
### Delete Failure Runbook
1. 读取 deletion plan、copy inventory、hold、reaper job 和 backend manifest。
2. 区分未开始、已删除、held、failed、unknown、scope mismatch 和 unverified。
3. provider/remote object 先 query，再决定 delete、revoke、manual 或 escalation。
4. rebuild vector/rerank/cache 前先加载 tombstone，防止复活。
5. 校验 backup watermark、restore namespace 和 deletion propagation。
6. 对用户返回 completed、partial、blocked 或 unverified 的准确状态。
7. 未完成项必须有 owner、deadline 和下一次动作。
### Consent Withdrawal Runbook
1. 验证主体、scope、purpose 和 consent receipt。
2. 停止 memory write、recall、embedding、provider egress 和 subagent delegation。
3. 列出 active、derived、provider、cache、backup、export copies。
4. 生成 forget/delete plan，检查 legal/incident hold。
5. 正在运行的 Attempt 进入 safe boundary；未知外发创建 reconciliation case。
6. 更新 notice、privacy summary、policy snapshot、audit 和用户通知。
7. 重新运行 cross-store inventory reconciliation。
### 用户通知与解释
用户通知必须区分：
- 观察到什么数据、来源、purpose 和处理时间。
- 当前允许、redacted、summary、denied、held、partial、unknown 的状态。
- 哪些副本已删除，哪些正在处理，哪些由 hold 或 provider contract 限制。
- 用户能采取的下一步：查看、撤回、forget、delete、export、申诉或联系 operator。
- notice version、case ID、时间线、影响范围和不确定性。
通知成功不等于删除完成；delivery failure 也不能伪装为已通知。
## 生命周期与状态机
### MemoryCandidate
```text
Observed -> Extracted -> Classified -> PurposeResolved
         -> AwaitingConsent -> AwaitingReview -> Accepted
         -> Persisting -> Indexed -> Active
```
分支：`Quarantined`、`Rejected`、`Unknown`、`Partial`、`IndexPending`、`Contradicted`。
### EgressAttempt
```text
Planned -> SnapshotFrozen -> Classified -> Minimized -> DLPChecked
         -> ResidencyChecked -> Approved -> Sending -> ReceiptPending -> Settled
```
分支：`Redacted`、`Denied`、`CrossBorderAsk`、`ProviderRejected`、`TransportFailed`、`UnknownOutcome`、`Unverified`。
### DeletionRequest
```text
Received -> Authenticated -> Scoped -> Inventorying -> HoldChecked
         -> Planned -> Approved -> Executing -> Reconciling
         -> Completed | Partial | Blocked | Failed | Unknown
```
### DSARCase
```text
Received -> Verifying -> Scoping -> Collecting -> Reviewing
         -> Fulfilling -> Delivered -> Closed
```
分支：`Rejected`、`BlockedByHold`、`Partial`、`DeadlineEscalated`。
### 状态不变量
- terminal deletion 不能被 late worker event 回退为 active。
- unknown 不能自动转为 deleted、not_sent 或 no_exposure。
- forgotten 立即排除 recall，但不删除 legal hold 证据。
- consent withdrawn 不伪造历史 provider copy 消失。
- provider delete receipt 不等于 local index、backup、cache 和 artifact 已清理。
- projection、dashboard 和用户文案不得覆盖 canonical copy status。
## 决策流程与解释
### PrivacyEvaluationInput
```typescript
interface PrivacyEvaluationInput {
  operation: PrivacyOperation;
  subjectAssets: DataAsset[];
  sourceScope: ScopeRef;
  destination: string;
  purposeId: string;
  legalBasis?: LegalBasisRef;
  consent?: ConsentReceipt;
  noticeVersion: string;
  policyVersion: string;
  residencyProfileId: string;
  providerContractId?: string;
  retentionPolicyId: string;
  now: string;
}
```
### 决策流程
```text
authenticate principal
 -> resolve tenant/workspace/session/run scope
 -> load DataInventory and lineage
 -> classify PII/secret/regulated/sensitivity
 -> resolve purpose/legal basis/consent/notice
 -> check retention/TTL/legal hold/incident hold
 -> choose minimum view
 -> evaluate destination/region/provider contract
 -> run DLP/redaction/tokenization
 -> reserve budget/capacity if needed
 -> approve | ask | hold | redact | deny
 -> execute with idempotency and receipt
 -> register copy/lineage
 -> reconcile
 -> notify and project
```
必须记录 reason code，例如：
```text
PRIVACY_SCOPE_MISSING / PRIVACY_SCOPE_MISMATCH
PURPOSE_MISSING / LEGAL_BASIS_MISSING / CONSENT_REQUIRED / CONSENT_EXPIRED / CONSENT_WITHDRAWN
NOTICE_OUTDATED / CLASSIFICATION_UNKNOWN / SECRET_DETECTED / REGULATED_DATA_DETECTED
PII_REQUIRES_REDACTION / DLP_SCAN_FAILED / REDACTION_FAILED / MINIMIZATION_REQUIRED
DESTINATION_NOT_ALLOWED / RESIDENCY_NOT_ALLOWED / CROSS_BORDER_APPROVAL_REQUIRED
PROVIDER_RETENTION_UNKNOWN / PROVIDER_TRAINING_CONFLICT / REMOTE_DELETE_UNVERIFIED
EMBEDDING_DELETE_UNSUPPORTED / RERANK_COPY_UNTRACKED / SUBAGENT_SCOPE_TOO_WIDE
BACKUP_RETENTION_CONFLICT / LEGAL_HOLD_ACTIVE / INCIDENT_HOLD_ACTIVE / TTL_EXPIRED
MEMORY_FORGOTTEN / MEMORY_CONTRADICTED / ACCESS_GRANT_EXPIRED / BREAK_GLASS_REQUIRED
AUDIT_UNAVAILABLE / RECONCILIATION_REQUIRED / UNKNOWN_EXTERNAL_COPY
```
### Explainability 合约
每个 decision 要回答：
- 观察了哪些 asset/copy、source hash、版本和 snapshot。
- 哪个 purpose、legal basis、consent、notice、retention 和 policy 生效。
- 选择了哪个 view，移除了哪些类别，发往哪个 destination/region。
- 哪些 evidence 过期、缺失、冲突或阻断。
- 如果是 deny/ask/hold/unknown，下一步触发条件是什么。
- 哪些副本已存在，哪些正在查询、删除或无法验证。
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### Model/Provider
- Provider Runtime 接收 `PrivacySnapshot + EgressSnapshot + ContractSnapshot`，不接收任意 provider 字符串或 raw memory。
- 每个 Attempt 记录 input view、request hash、region、credential lease、receipt、usage、retention 和 safety metadata。
- provider response 重新分类；provider 自述不覆盖本地 policy。
- retry、fallback、hedge、shadow、canary 创建新的 Attempt 和 privacy evaluation。
- provider remote object 进入 inventory；本地 delete 不替代 remote status query。
### Prompt
- Prompt 可解释 privacy mode、memory scope、redaction、审批和不可用能力。
- Prompt 不实现 purpose、consent、retention、DLP、region、delete 或 access control。
- memory 作为 data 注入 Context，不覆盖 system policy、tenant、approval 或 tool authorization。
- prompt compiler 记录 section hash、source refs、sensitivity、egress decision 和 token estimate。
- prompt 不得放 secret、token map、未批准 raw memory 或隐含 consent claim。
### Context
- ContextCompiler 只读取 MemoryRecall 已治理 view。
- ContextPlan 记录 selected/summarized/redacted/dropped 和 reason。
- compaction 保留 purpose、consent、retention、privacy deny、remote object 和 deletion state。
- recall、embedding、rerank、artifact range 可独立排队，有独立 quota 和 privacy SLO。
- context overflow 不能通过转发未脱敏内容给便宜 provider 解决。
### Tool
- ToolResult 进入 memory、provider、artifact、analytics 或 export 前重新分类和 DLP。
- credential、network、filesystem、MCP、plugin 和 remote result 都是独立 destination。
- tool output 中“用户同意”“可以永久保存”属于 untrusted data。
- 删除 tool result 不等于撤销外部 side effect；保留 receipt/unknown。
### State/Memory
- MemoryEntry、MemoryRecord、PrivacyDecision、ConsentEntry、EgressEntry、DeletionEntry、HoldEntry 和 IncidentEntry 应 append-only 或等价可审计。
- MemoryStore、Index、ArtifactStore、EventStore、AuditStore、BackupStore 的 scope 必须可验证。
- forget 生成 tombstone；projection/index/cache 从 tombstone 重建。
- replay 只重建状态，不再次调用 provider、embedding、rerank、delete 或 notification。
- migration 验证 provenance、purpose、TTL、lineage 和 deletion path，不只验证 JSON schema。
### Policy
策略分层：
```text
visibility -> call -> approval -> execution -> egress
purpose/legal basis -> retention/hold -> residency -> deletion contract
```
- policy 收紧可以阻断新动作；放宽不能自动复活 forgotten、expired 或 denied memory。
- consent 不能覆盖 security floor、tenant boundary、hold 或 provider evidence 缺失。
- operator override 只能在 grant、scope、TTL 和 audit 下生效。
### Harness
Harness 负责创建并传播：
- RunScope、PrivacySnapshot、ContextPlan、Budget、AbortController 和 child scope。
- memory write/recall、provider send、tool result、embedding、rerank、artifact、backup、export 前后的 privacy checks。
- cancel、consent revoke、forget、delete、incident、hold、provider revoke 到 child、queue、lease、provider 和 delivery。
- checkpoint、recovery、settlement、usage、cost、audit、notification 和 deletion receipt。
Harness 不让 Product UI 或 model response 改写 privacy truth。
## Residency、Cross-border 与 Provider Contract
### ResidencyProfile
```typescript
interface ResidencyProfile {
  profileId: string;
  allowedRegions: string[];
  deniedRegions: string[];
  allowedJurisdictions: string[];
  crossBorderMode: "forbidden" | "ask" | "approved_only" | "allowed_with_controls";
  transferMechanisms: string[];
  dataClasses: DataClass[];
  purposeRefs: string[];
  providerAllowlist: string[];
  backupRegionPolicy: string;
  version: string;
}
```
### Destination 检查
必须检查 provider、API family、model、deployment、region、credential class、endpoint、cache、batch、file、embedding、rerank、abuse review、support、backup、replica、restore、analytics、artifact CDN、webhook、MCP、plugin 和 remote worker 的实际目的地。
### Cross-border 决策
```text
data class + purpose
 -> source jurisdiction
 -> destination jurisdiction
 -> provider contract/retention/training
 -> transfer mechanism
 -> consent/notice/approval
 -> minimize/redact/tokenize
 -> allow | ask | degrade | deny
```
- secret、regulated 和高风险 PII 跨境默认 deny，除非独立 policy、evidence 和批准。
- fallback 不能绕过 residency filter。
- provider region metadata 不能覆盖本地 route/endpoint attestation。
- residency evidence 过期进入 unknown，不继续使用旧 allow。
- 地域切换必须重新登记 embedding、rerank、backup、cache 和 remote copies。
### ContractSnapshot 交集
```text
required handling
 ∩ provider declaration
 ∩ adapter attestation
 ∩ credential scope
 ∩ residency profile
 ∩ purpose/legal basis
 ∩ retention/delete capability
 ∩ DLP/redaction result
```
只有交集非空且 evidence 新鲜，才生成可执行 `ContractSnapshot`。
## Privacy SLO 与运营指标
### Canonical events
```text
DataAssetDiscovered / DataCopyRegistered / ClassificationCompleted / ClassificationUncertain
PurposeResolved / LegalBasisResolved / ConsentRequested / ConsentGranted / ConsentWithdrawn
NoticePresented / PrivacySnapshotFrozen / MemoryCandidateCreated / MemoryWriteAllowed / MemoryWriteDenied
MemoryRecallEvaluated / MemoryForgotten / EgressEvaluated / RedactionApplied / DlpFindingCreated
ProviderCopyCreated / EmbeddingCopyCreated / RerankCopyCreated / SubagentViewDelegated
ArtifactPrivacyViewCreated / BackupManifestCreated / RetentionSweepStarted / RetentionFindingCreated
LegalHoldCreated / LegalHoldReleased / DeletionRequested / DeletionStepCompleted / DeletionStepUnknown
DeletionReconciliationCompleted / DSARCaseOpened / DSARExportCreated / AccessGrantIssued
BreakGlassActivated / PrivacyIncidentDeclared / ProviderRouteRevoked / RemoteDeletionVerified
PrivacyUserNotified
```
### Trace 与日志保护
记录 trace id、scope hash、asset/copy hash、purpose、policy、classification、view、destination class、region class、provider class、DLP version、retention、hold、consent、decision、reason、receipt、deletion status 和 incident id。
禁止普通 trace 记录完整 prompt、memory claim、secret、raw path、token map、provider URL 或第三方原文。
### Privacy SLO
至少按 tenant tier、data class、operation、region 统计：
- `inventory_registration_completeness`：发现对象有 inventory 的比例。
- `classification_before_egress`：外发前分类+DLP 完成率，高风险目标 100%。
- `purpose_binding_coverage`、`legal_basis_binding_coverage`、`consent_binding_coverage`。
- `scope_isolation_violation`、`secret_egress_violation`，目标为零。
- `regulated_fail_closed_correctness`：证据缺失时正确阻断比例。
- `forget_recall_exclusion_latency`：forget 后 index/cache/recall 排除延迟。
- `deletion_completion_latency`、`remote_delete_verification_latency`。
- `unknown_copy_resolution_window`、`retention_expiry_lag`、`legal_hold_accuracy`。
- `DSAR_ack_latency`、`DSAR_fulfillment_latency`、`export_delivery_success`。
- `privacy_incident_detection_latency`、containment latency、notification completeness。
- `audit_evidence_completeness`：decision/copy/delete/notice/operator action 的证据覆盖。
安全、跨租户、secret、regulated、audit loss 和错误删除是 hard invariant，不能用普通 availability budget 抵消。
### 运营指标
- active/candidate/stale/contradicted/forgotten memory 数量与 TTL 分布。
- PII/secret/regulated 命中率、unknown rate、人工复核率和误报率。
- recall blocked/redacted/summary/artifact-only/deny 分布。
- provider、embedding、rerank、subagent、backup、cache copy 数和未登记 copy 数。
- orphan index、orphan artifact、orphan token map、retention drift、tombstone lag。
- deletion success/partial/blocked/unknown/unverified 分布。
- consent grant/withdraw/expiry、notice adoption、access/export volume。
- break-glass 使用、过期未撤销、二次审批缺失和 operator query。
- DLP latency、timeout、redaction failure、token map leak attempt。
- region/cross-border deny/ask/degraded、route quarantine、contract drift。
- incident severity、affected scope、containment、reopen rate。
### 告警
- secret/regulated egress、cross-tenant hit、unknown classification 外发立即 page。
- deletion lag、orphan copy、backup purge failure、无 tombstone reindex 按影响范围 page/ticket。
- inventory、DLP、consent、audit、provider contract backend 不可用时按 data class 分层降级。
- PII finding 默认聚合 reason、scope、detector version 和用户影响，避免每条命中 page。
## Reconciliation 与 Evidence
### 对账对象
```text
DataInventory vs backend manifest
MemoryRecord vs vector/rerank index
Memory scope vs tenant/workspace ACL
PrivacySnapshot vs actual provider request
EgressDecision vs remote object/receipt
Retention policy vs TTL metadata
Legal hold vs deletion worker
Deletion plan vs primary/derived/backup status
Consent withdrawal vs new write/recall
DSAR export manifest vs delivered artifact
Backup manifest vs tombstone/deletion watermark
Audit events vs operator actions
```
### ReconciliationFinding
```typescript
interface ReconciliationFinding {
  findingId: string;
  category: "missing_copy" | "orphan_copy" | "scope_drift" | "retention_drift" | "delete_drift" | "receipt_gap" | "consent_gap" | "residency_drift" | "audit_gap";
  severity: "info" | "warning" | "high" | "critical";
  subjectRefs: string[];
  expected: string;
  observed: string;
  safeRepair: "none" | "tombstone" | "reindex" | "revoke" | "delete" | "manual" | "quarantine";
  evidenceRefs: string[];
  status: "open" | "acknowledged" | "repairing" | "resolved" | "accepted_risk";
  createdAt: string;
}
interface ReconciliationReport {
  reportId: string;
  scope: ScopeRef;
  startedAt: string;
  completedAt: string;
  scannedAssets: number;
  scannedCopies: number;
  findings: ReconciliationFinding[];
  evidenceRefs: string[];
}
```
### Evidence 规则
- evidence 记录 source、hash、时间、版本、scope、expiry 和 integrity reference。
- provider receipt、remote deletion、backup manifest、audit record 不能只存在普通日志。
- evidence 缺失时 decision 可以是 unknown，不能补写完成。
- 用户解释引用稳定 reason/evidence ref，但不泄露其他 tenant 或内部安全细节。
- DSAR、incident、deletion case 关闭前必须检查 evidence completeness。
- audit 写入失败应阻断高风险处理，或进入 `audit_pending` 并限制继续动作。
### 审计字段
谁在何时、什么 tenant/workspace/session/run/scope、使用哪个 snapshot/purpose/policy、处理哪些 asset/copy、采用哪个 view/redaction/DLP/region/provider、谁批准或 break-glass、结果是 allow/redact/deny/partial/unknown/unverified、使用了哪些 receipt/evidence、是否通知用户，都必须可查询。
## 测试、发布门禁与评估
### Testkit
```text
FakeMemoryStore / FakeVectorIndex / FakeRerankBackend / FakeProviderRuntime
FakeRemoteObjectStore / FakeArtifactStore / FakeBackupStore / FakeQueue
FakeDlpScanner / FakeClassifier / FakePolicyEngine / FakeConsentStore
FakeNoticeRegistry / FakeResidencyResolver / FakeAuditStore / FakeNotificationProvider
DeterministicClock / DeterministicIds / CrashInjector / SideEffectRecorder
ReconciliationOracle / ReplayRunner
```
### 单元测试
- DataAsset/DataCopy schema、lineage、hash、scope、copy status 和 tombstone。
- sensitivity、PII、secret、regulated 分类及 uncertain 分支。
- purpose、legal basis、consent、notice、版本冲突和撤回。
- minimization、view transform、redaction、tokenization、DLP failure。
- candidate、duplicate、contradiction、confidence、TTL 和 scope。
- recall hard filter、排序、token budget、stale/contradicted 标记。
- embedding/rerank/subagent copy inheritance 和 deletion propagation。
- retention、hold、reaper、DSAR、export、access、break-glass 状态机。
- reason、explanation、evidence、audit、notification 去重。
### Adapter 契约测试
每个 MemoryStore、Index、Artifact、Provider、Embedding、Rerank、Backup 和 Delete adapter 必须验证：
1. tenant/scope mismatch 被拒绝；
2. 未登记 asset/copy 不能写入；
3. copy status 可查询并可恢复；
4. deletion idempotency key 返回同一 receipt；
5. 不同 payload 同 key 返回 conflict；
6. tombstone 后 recall 不返回；
7. source delete 触发派生 copy 查询；
8. remote delete unknown 不伪造 success；
9. legal hold 阻断匹配对象删除；
10. expired consent 不能产生新 egress；
11. fallback 重新评估 residency 和 DLP；
12. restore 不复活 tombstoned asset；
13. audit 可重放且不泄露 raw secret；
14. reindex 尊重 tombstone、scope 和 retention。
### 集成与故障测试
覆盖普通偏好保存、PII summary-only、secret tool result、embedding region 不合规、rerank query delete、delegated subagent、provider upload 后 crash、forget 与 recall race、delete 与 hold race、backup restore、DSAR 混入第三方数据、break-glass expiry、cross-tenant cache/vector/artifact、provider contract drift。
在 classification、consent、memory write、embedding upload、provider send、receipt commit、remote delete、tombstone、cache purge、backup purge、hold、DSAR manifest、notification、audit append 和 break-glass revoke 边界注入 crash、timeout、duplicate、out-of-order、partial commit。
必须断言：不重复外发、不跨租户、不绕过 hold、不把 unknown 当 deleted、不丢 tombstone、不泄露 secret。
### Evaluation 边界
LLM judge 可评估隐私解释清晰度、候选相关性和 partial/unknown 文案；不能证明 consent 真实存在、provider 是否收到字段、vector/backup/cache/remote object 是否删除、region/hold/isolation 是否满足。
### Release Gate
Hard gate：
- secret/regulated egress、cross-tenant access、consent bypass、hold violation、duplicate delete、unknown-to-deleted、tombstone resurrection、audit loss。
- 未登记 copy 进入生产。
- provider/embedding/rerank/subagent fallback 绕过 egress 或 residency。
- DSAR/export 混入其他主体或 tenant 数据。
Soft gate：分类器小幅 precision/recall、解释文案、recall relevance、DLP latency、embedding throughput 和低风险成本回归。
## 故障恢复与安全降级
### 故障分类
```text
inventory_unavailable / classification_timeout / classification_conflict
DLP_unavailable / purpose_unknown / consent_store_unavailable / notice_mismatch
retention_stale / hold_store_unavailable / provider_region_mismatch
provider_delete_unknown / embedding_down / rerank_down / vector_index_drift
subagent_scope_mismatch / backup_manifest_gap / cache_purge_failed
queue_delete_job_lost / audit_commit_failed / notification_failed
delete_reconciliation_stuck / privacy_incident_active
```
### 降级矩阵
| 故障 | 可允许 | 禁止 |
|---|---|---|
| 分类不可用 | public/internal metadata-only | secret/regulated 外发或长期写入 |
| DLP timeout | 等待、summary、deny | raw 当 clean |
| consent store 不可用 | 已有有效 snapshot 到安全边界 | 新需 consent 的长期 memory/egress |
| provider residency unknown | 本地处理或 queue | 跨境 fallback |
| embedding down | 本地 index、recall disabled | 无界重试和复制 |
| remote delete unknown | query/manual/partial | 报告已删除 |
| backup restore | paused restore + tombstone replay | 直接开放流量 |
| audit down | metadata-only 低风险或暂停 | 高风险无审计执行 |
| notification failure | durable inbox/poll | 把未通知当已通知 |
| delete worker crash | recovery lease + idempotent retry | 并行盲删或盲重传 |
### 恢复顺序
```text
load PrivacySnapshot
 -> verify scope/purpose/consent/retention
 -> load inventory and lineage
 -> inspect copy/receipt/tombstone
 -> query provider/index/cache/backup
 -> classify present/deleted/unknown/held
 -> acquire recovery lease
 -> safe repair or quarantine
 -> reconcile manifests
 -> append evidence and notify
```
恢复器不能用 latest policy、latest memory 或 latest provider route 猜测旧事实。
## 反模式
1. 只在 Memory 表增加 `privacy` 字段，没有 inventory、copy lineage、purpose、retention 和 delete。
2. 所有对话自动写长期 memory。
3. 用一个 consent boolean 代替 purpose、notice、scope、版本、撤回和 evidence。
4. 用一个 redacted boolean 代替 view、规则、hash、token map 和 destination。
5. 不登记 vector/rerank/cache/backup/provider copy。
6. “provider 不训练”被当成全部安全保证。
7. forget 只删索引，raw、cache、backup 和 provider copy 可复活。
8. delete 只改 UI 或 projection。
9. TTL 由 last access 无限续期。
10. legal hold 被当作访问授权。
11. DSAR 导出全库。
12. fallback 复用 primary allow。
13. subagent 继承父级全部 memory、secret 和 workspace。
14. DLP 失败继续发 raw。
15. embedding 被当作匿名化。
16. cache key 缺 tenant/purpose/view。
17. backup 不纳入删除图。
18. operator 直接查数据库，绕过 AccessRequest、break-glass 和 audit。
19. break-glass 无 expiry、双人审批或 post-review。
20. 只看通知发送成功，不看 fulfillment、receipt 和 reconciliation。
21. 只测 happy path，不测 unknown、hold race、restore、cache resurrection 和跨租户。
22. 把 unknown 变成 not found。
23. 在 trace 打印 raw memory、secret、完整路径和 token map。
24. 让模型输出决定 purpose、consent 或 deletion。
25. 用成本或吞吐关闭 privacy check。
26. 只用 dashboard 证明合规，不保存 canonical event、receipt、manifest 和 evidence。
## 实施清单
### P0：阻断高风险错误
- [ ] 建立 DataInventory/DataCopy/lineage schema 和未登记 copy deny。
- [ ] 实现 sensitivity、PII、secret、regulated 双轴分类，unknown fail-closed。
- [ ] 实现 PrivacySnapshot、scope、purpose、legal basis、consent、notice 绑定。
- [ ] 实现 memory write gate、recall hard filter、egress gateway、redaction、DLP。
- [ ] 阻断 secret/regulated、cross-tenant、residency unknown 和 provider contract unknown。
- [ ] 为 provider、embedding、rerank、subagent、cache、queue、artifact、backup 建 copy registry。
- [ ] 实现 forget tombstone、delete idempotency、remote unknown 和 reconciliation finding。
- [ ] 实现 access request、DSAR/export、audit 和 break-glass expiry。
### P1：运营闭环
- [ ] 实现 retention/TTL/reaper/legal hold/incident hold。
- [ ] 建立 privacy case、incident severity、runbook、owner、deadline、通知和解释。
- [ ] 建立 privacy SLO、copy drift、deletion lag、unknown copy、DLP、consent 和 cross-border 指标。
- [ ] 建立 backup manifest、restore tombstone replay、provider status query 和 disaster drill。
- [ ] 建立 adapter contract、fault injection、replay、side-effect oracle 和 hard release gates。
### P2：持续改进
- [ ] 做分类器版本对比、误报/漏报复盘和 human review expiry。
- [ ] 做 provider contract drift、region route、embedding/rerank delete capability 监控。
- [ ] 做 DSAR/export 端到端演练、break-glass post-review 和通知可读性评估。
- [ ] 做跨租户、并发 forget/recall、hold/delete、restore/reindex 的 soak 与 chaos 测试。
- [ ] 每次 schema、policy、provider、index、backup 或 retention 变更运行 inventory/reconciliation release gate。
## 五个参考项目的启发来源
### Pi
- headless kernel、统一 provider event、session tree 和可恢复 compaction 启发了 privacy snapshot、ContextPlan 和 replay 边界。
- 取舍：扩展/执行隔离较弱，不能直接当作多租户隐私实现。
### Grok Build
- actor、permission decision、并行工具、路径锁和 sandbox 启发了 scope、approval、lease、隔离和故障恢复设计。
- 取舍：复杂状态机和潜在 fail-open 路径要求额外的 privacy hard gate。
### OpenCode
- client/server 分离、session/message/part、事件总线、durable projector、snapshot/patch/revert 启发了 canonical event、asset lineage、tombstone 和 case 投影。
- 取舍：状态迁移复杂，隐私 schema 必须版本化并做重放测试。
### Claude Code
- permission、hooks、subagent、skills、memory 和 MCP 的产品化组合启发了 delegated view、operator controls、notice 和 user-facing explanation。
- 取舍：扩展与外部数据不应默认拥有父级全部 scope、secret 或 memory。
### OpenClaw
- AgentHarness registry、agent-core、multi-channel gateway、provider/tool/sandbox/elevated 分层启发了 destination inventory、provider contract、channel notification 和 execution boundary。
- 取舍：Gateway、插件和跨 channel 路径都必须纳入 copy registry、egress check 和 incident runbook。
### Definition of Done
- [ ] 所有生产 data asset、copy、derived view、provider remote object、embedding、rerank、subagent、backup 和 export 都有 inventory、owner、scope、purpose、retention 和 lineage。
- [ ] 高风险对象在 classification、DLP、residency、consent/legal basis、provider contract、hold 和 audit 缺失时 fail-closed。
- [ ] memory write/recall、egress/redaction、forget/delete、DSAR/export、access、break-glass、incident 和 notification 都有 durable state machine。
- [ ] remote unknown、backup restore、cache/index resurrection、late event 和跨租户场景有可验证 reconciliation 与测试。
- [ ] Privacy SLO、运营指标、用户解释、case/runbook、evidence 和 release gate 已接入生产运营。
