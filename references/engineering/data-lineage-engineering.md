# Data Lineage Engineering 细粒度工程设计
> 本文定义 Agent 平台中 logical data object、source/producer/consumer、lineage edge、transformation、provenance、schema/version、purpose/scope/tenant/residency、影响分析、删除/DSAR 传播、catalog/graph query、drift、CI gate 与恢复工程。
>
> 依据仅来自当前目录已有的参考架构、Agent Harness、Data Governance、Privacy、Data Quality Operations、Agent Memory Governance、Artifact、State & Memory、Context、Prompt、Tool、Policy/Sandbox、Workspace Isolation、Multi-tenant、Session Replay、Provider Runtime、Provider Security Contract、Provider Schema Evolution、Cost Governance、Event/Observability、Workflow、Evaluation 与五个参考项目源码调研结论；不依赖 README，不进行网络搜索。
>
> **边界声明：** Data Lineage 不是“给数据表画一张血缘图”，也不只是“给数据库表加一个 source 字段”。它要回答数据从哪里来、由谁生产、经过什么 transformation、进入哪些 context/prompt/tool/provider/state/artifact/cache/tenant/region、谁消费、凭什么 purpose、采用什么 schema/version、何时过期、如何删除、删除证明是否完整，以及某个 provider incident、schema drift、DSAR、workspace 变更或 policy 变化会影响什么。
## 目录
1. [目标与非目标](#目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [职责边界](#职责边界)
4. [数据边界与威胁模型](#数据边界与威胁模型)
5. [总体架构与数据流](#总体架构与数据流)
6. [Logical Data Object](#logical-data-object)
7. [Source、Producer 与 Consumer](#sourceproducer-与-consumer)
8. [Lineage Edge 与 Provenance](#lineage-edge-与-provenance)
9. [Transformation 与派生数据](#transformation-与派生数据)
10. [Schema、Version 与 Contract](#schemaversion-与-contract)
11. [Purpose、Scope、Tenant、Residency 与 Data Class](#purposescopetenantresidency-与-data-class)
12. [核心数据模型](#核心数据模型)
13. [TypeScript 接口](#typescript-接口)
14. [Catalog、Index 与 Graph 存储](#catalogindex-与-graph-存储)
15. [注册、发现与采集流程](#注册发现与采集流程)
16. [Context/Prompt/Tool/State/Memory/Artifact Lineage](#contextprompttoolstatememoryartifact-lineage)
17. [Provider、Egress 与 Region Lineage](#provideregress-与-region-lineage)
18. [Workspace、文件与代码 Lineage](#workspace文件与代码-lineage)
19. [Forward Impact Analysis](#forward-impact-analysis)
20. [Backward Impact Analysis](#backward-impact-analysis)
21. [删除、DSAR 与传播证明](#删除dsar-与传播证明)
22. [Retention、Legal Hold 与 TTL](#retentionlegal-hold-与-ttl)
23. [Drift、质量与不一致检测](#drift质量与不一致检测)
24. [Catalog/Graph Query 设计](#cataloggraph-query-设计)
25. [CI、发布与运行时 Gates](#ci发布与运行时-gates)
26. [生命周期与状态机](#生命周期与状态机)
27. [端到端决策流程](#端到端决策流程)
28. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
29. [故障恢复、回填与 Unknown Lineage](#故障恢复回填与-unknown-lineage)
30. [安全、隐私、多租户与驻留](#安全隐私多租户与驻留)
31. [可观测性与审计](#可观测性与审计)
32. [测试策略](#测试策略)
33. [反模式](#反模式)
34. [实施清单](#实施清单)
35. [五个参考项目的启发来源](#五个参考项目的启发来源)
36. [Definition of Done](#definition-of-done)
## 目标与非目标
### 目标
Data Lineage 必须能够：
- 以稳定 ID 表示 logical data object，而不是只依赖文件名、表名、URL 或 Artifact path。；记录 source、producer、consumer、processing run、workflow、tenant、workspace、session、run、attempt、region 和 purpose。
- 记录输入输出、lineage edge、transformation、provenance、schema、version、hash、freshness、retention、residency 和 sensitivity。；让同一逻辑对象的 materialization、copy、cache、summary、embedding、rerank、memory、prompt、provider payload 和 artifact 形成可查询图。
- 支持 forward impact analysis：一个 source、schema、provider、workspace、policy 或 deletion 变化会影响什么。；支持 backward impact analysis：一个 prompt、tool、model、artifact、report 或 incident 的输入来源是什么。
- 支持 purpose/scope/tenant/residency 约束沿边传播，阻止越权连接和不允许外发。；支持 deletion、DSAR、retention expiry、legal hold、remote deletion、cache purge 和 deletion proof。
- 发现 schema drift、semantic drift、freshness drift、quality drift、coverage gap、orphan copy 和 cross-tenant edge。；将 lineage 作为 Data Governance、Privacy、Data Quality、Provider Security、Incident Response、Session Replay、Cost 和 Evaluation 的共同事实层。
- 在 CI、schema migration、provider route、prompt/context/toolset、workspace、artifact 和 release 时执行 lineage gates。；在运行时对高风险数据流执行 preflight、egress、residency、purpose、deletion 和 provenance 检查。
### 非目标
本文不负责：
- 代替数据库查询优化、ETL 调度器、数据仓库建模或财务总账。；只从静态代码或 SQL 猜测实际数据流并声称完整 lineage。
- 把 trace span、日志、prompt 文本、artifact URL 或模型声称当作 lineage truth。；让 data catalog 自行授予 provider egress、tool execution、secret access 或 production approval。
- 把所有复制都视为泄漏，也不把“同一个 hash”视为可共享授权。；在没有 purpose、tenant、residency、sensitivity 和 legal basis 的情况下建立跨租户边。
- 用删除 source 表替代所有 materialization、cache、embedding、remote object、backup、fixture 和 export 的传播删除。；允许 lineage graph 中任意用户输入覆盖 owner、scope、policy、schema 或 residency。
- 通过无限保留 lineage payload 反过来造成隐私和安全风险。；用 graph 查询结果替代实际 Policy、Sandbox、DLP、Artifact ACL 或 Provider Security Contract。
### 核心公式
```text
Lineage Trust
  = Identity Stability
  × Edge Completeness
  × Provenance Integrity
  × Scope/Purpose Correctness
  × Schema/Version Accuracy
  × Deletion Propagation
  × Query Explainability
  × Quality Freshness
```
### 设计原则
```text
logical identity before physical location
facts before guesses
edges are immutable evidence, not UI decoration
purpose and scope travel with data
transformation must be reproducible or explicitly unknown
materialization is a new object with parent edges
deletion is a graph operation plus external receipts
catalog does not enforce execution alone
unknown lineage is unsafe for high-sensitivity egress
```
## 核心判断与术语
### Logical data object
`LogicalDataObject` 是具有稳定语义、owner、purpose、scope、schema、版本、敏感度和生命周期的对象。它可以有多个物理 materialization：
```text
logical object: customer_support_case
  -> source record
  -> normalized event
  -> session message
  -> ContextResource
  -> PromptSection
  -> provider request view
  -> summary artifact
  -> memory candidate
  -> embedding
  -> audit projection
```
物理路径变化、存储迁移、压缩、分片或 provider 不应静默改变逻辑身份。
### Source/Producer/Consumer
- `Source`：数据最初或当前权威取得位置，如 user input、workspace file、provider response、tool result、database、event、artifact、remote object。；`Producer`：实际生成、复制、转换或发布对象的组件、principal、provider、tool、workflow step 或版本。
- `Consumer`：读取、检索、拼装、外发、执行、展示、评估、计费、删除或审计对象的组件/目的。；一个组件可以在不同 edge 上同时是 producer 与 consumer，但角色必须按 edge 记录。
### Lineage edge
`LineageEdge` 是两个 logical object、object/version 或 object/materialization 间的可验证关系，描述输入、输出、复制、摘要、嵌入、外发、消费、删除、保留或阻断。
### Transformation
`Transformation` 说明输入如何生成输出：代码版本、prompt/template、model/provider、tool、规则、参数 hash、数据集、输入范围、输出 hash、可重演性和质量证据。
### Provenance
`Provenance` 说明对象来源和事实证据，包括 origin、capture time、producer identity、source receipt、content hash、schema/version、environment、tenant scope、region、purpose、chain hash 和 evidence refs。
### Lineage state
```text
observed > declared > inferred
```
- `observed`：由运行时 event、receipt、artifact、provider response 或受信 connector 直接观察。；`declared`：由注册契约、schema、workflow 或 owner 声明，需运行时验证。
- `inferred`：由静态分析、名称、query、规则或模型推断，只能用于候选和缺口检测。
高敏感度外发、删除证明和合规报告不能只依赖 `inferred`。
## 职责边界
| 组件 | 负责 | 不负责 |
|---|---|---|
| Lineage Catalog | logical object、edge、schema、owner、purpose、scope、TTL、版本索引 | 直接执行写入/删除 |
| Lineage Collector | 从 runtime、event、artifact、provider、tool、workflow 采集观察事实 | 猜测未观察的业务语义 |
| Provenance Service | source receipt、hash、版本、环境和证据链 | 决定业务是否允许外发 |
| Schema Registry | schema、compatibility、migration、fingerprint | 记录全部运行时 copy |
| Transformation Registry | generator、代码、prompt、model、tool、参数和重演能力 | 直接调度 workflow |
| Data Governance | inventory、purpose、owner、retention、residency、policy | 代替 storage adapter |
| Privacy/DSAR Service | subject request、删除/导出传播、证明和 legal hold | 修改历史 event |
| Data Quality | completeness、freshness、drift、reconciliation、quarantine | 直接放行敏感 egress |
| Context Runtime | ContextPlan source selection、summary、token 与 freshness | 改写 lineage owner |
| Prompt Compiler | PromptSection 来源、版本、模板和渲染证据 | 授予 provider 权限 |
| Tool Runtime | tool input/output、effect、artifact、receipt 和 consumer edge | 自行扩大 scope |
| Provider Runtime | request/response/usage/remote object/provider receipt | 宣称数据治理完成 |
| Policy/Egress | purpose、scope、tenant、residency、sensitivity 和 provider allow | 建立逻辑事实 |
| ArtifactStore | 大对象、版本、ACL、retention、删除 receipt | 解释全部业务关系 |
| State/Event Store | durable event、session/run、checkpoint、replay facts | 代替 graph policy |
| Workspace/Repository | 文件、代码、branch、baseline、patch、owner 和 hash | 代替 data catalog |
| Harness | 装配、监督、checkpoint、恢复、预算、审批和传播控制 | 变成 lineage graph God Object |
| Evaluation | lineage completeness、impact、deletion、drift 和 regression gates | 生产删除 |
### 强制关系
```text
Collector observes.
Catalog indexes.
Provenance proves.
Policy authorizes.
Runtime executes.
Artifact/State stores payloads and receipts.
Data Quality challenges freshness and completeness.
Privacy governs purpose, subject rights and deletion.
Harness coordinates lifecycle and recovery.
```
## 数据边界与威胁模型
### 不可信输入
- 用户提供的 tenant、workspace、session、subject、purpose、region、object ID 和 deletion request。；模型生成的 data class、source claim、URL、file path、schema、owner、purpose 和 transform explanation。
- workspace 文件、注释、配置、AGENTS.md、脚本、测试输出、生成代码和 vendor metadata。；provider response、tool result、MCP/LSP schema、webhook、remote object metadata 和 billing receipt。
- artifact URL、cache key、event cursor、export manifest、DSAR payload 和恢复请求。；代码静态分析、SQL parser、命名规则、embedding 相似度和模型推断的 lineage edges。
### 资产
- tenant、workspace、project、repository、session、run、attempt、subject、purpose 和 legal basis。；PII、secret、regulated data、credential、provider request/response、tool input/output 和 remote object。
- schema、version、quality、retention、residency、deletion proof、legal hold 和 audit。；lineage graph 本身：节点、边、内容 hash、owner、查询结果、导出和 graph snapshot。
- 由 data lineage 生成的 ContextPlan、Prompt、Artifact、Memory、Embedding、Cache、Cost 和 Evaluation fixture。
### 主要攻击路径
- 伪造 source/producer/consumer/owner/purpose，建立越权 edge。；使用相同 hash、文件名、URL、模型 alias 或 object ID 混淆不同 tenant/region/object。
- 通过 cache、embedding、summary、prompt、provider upload、artifact export 或 replay 绕过原始 scope。；只删除 source，不删除 derived object、remote object、backup、fixture、log、cache 或 graph payload。
- schema/version 漂移导致 downstream 误读、错误外发、错误删除或错误报告。；lineage collector 失败后默认为 complete，造成高风险 unknown data flow。
- 图查询递归爆炸、恶意 payload、超大 edge、循环 lineage 或跨 scope 查询。；用当前 policy、当前 region、当前 provider 或当前 prompt 解释历史对象。
### 安全目标
```text
no forged identity
no unauthorized edge
no cross-tenant graph visibility
no unknown high-risk egress
no deletion without propagation evidence
no schema/version ambiguity
no inferred fact presented as observed fact
no graph query bypassing runtime policy
```
## 总体架构与数据流
### 逻辑拓扑
```text
Sources / Producers
  -> Capture adapters
  -> Identity + Scope Resolver
  -> Provenance Builder
  -> Lineage Event Bus
  -> Catalog + Schema Registry + Transformation Registry
  -> Graph Index / Edge Store / Object Projection
  -> Query + Impact Engine
  -> Policy/Egress/DSAR/Quality/Incident/Evaluation consumers
```
### Agent 数据链
```text
User/Workspace/Provider/Tool/Artifact/Event source
  -> logical object capture
  -> normalization/transformation
  -> ContextPlan selection
  -> Prompt compilation
  -> Provider request egress
  -> Provider response/tool call
  -> State/Memory/Artifact/Usage/Cost/Evaluation materialization
  -> retention/deletion/DSAR propagation
```
### 事实与索引分离
- `LineageEventLog` 是 append-only 事实来源。；`ObjectCatalog`、`EdgeIndex`、`ImpactProjection`、`DeletionProjection` 是可重建视图。
- `GraphSnapshot` 是查询加速和审计证据，不是新的事实源。；查询结果必须引用 cursor、graph version、policy snapshot、redaction profile 和 evidence refs。
- graph materialization 失败不能删除原 event；恢复时从 checkpoint + tail 重建。
## Logical Data Object
### 对象分类
```typescript
type LogicalObjectKind =
  | "user_input"
  | "assistant_output"
  | "workspace_file"
  | "repository_snapshot"
  | "event"
  | "session_entry"
  | "context_resource"
  | "context_plan"
  | "prompt_section"
  | "provider_request"
  | "provider_response"
  | "tool_call"
  | "tool_result"
  | "artifact"
  | "remote_object"
  | "memory_candidate"
  | "memory_record"
  | "embedding"
  | "rerank_result"
  | "cache_entry"
  | "usage_record"
  | "cost_record"
  | "evaluation_fixture"
  | "audit_record"
  | "deletion_proof"
  | "export_bundle";
```
### Logical identity
逻辑 identity 至少由以下字段决定：
```text
tenant + object namespace + stable business key + semantic kind + origin system
```
不能只用 content hash，因为：
- 两个租户可以有相同内容但不同 owner/purpose。；同一对象在版本演进中内容 hash 会变化。
- 删除、DSAR、legal hold 和报告需要追踪对象而不是只追踪内容。；相同内容的复制、摘要和 embedding 是不同 logical object。
### 版本 identity
对象版本由 `objectId + versionId + schemaVersion + contentHash + sourceCursor` 构成。materialization 有自己的 `materializationId`，引用 logical object/version，但不能替代其 identity。
### ObjectDescriptor
```typescript
interface LogicalDataObject {
  objectId: string;
  kind: LogicalObjectKind;
  namespace: string;
  tenantId: TenantId;
  owner: PrincipalRef;
  purpose: PurposeRef;
  scope: ScopeRef;
  residency: ResidencyConstraint;
  dataClass: DataClass;
  sensitivity: Sensitivity;
  subjectRefs?: SubjectRef[];
  schemaRef: SchemaRef;
  currentVersionId?: string;
  sourceRefs: SourceRef[];
  retention: RetentionPolicy;
  deletionPolicy: DeletionPolicy;
  status: "active" | "restricted" | "quarantined" | "expired" | "deleted" | "unknown";
  createdAt: string;
  updatedAt: string;
}
```
### Materialization
```typescript
interface DataMaterialization {
  materializationId: string;
  objectId: string;
  versionId: string;
  storageKind: "inline" | "event" | "database" | "artifact" | "cache" | "provider" | "workspace" | "memory" | "vector" | "backup";
  locatorRef: string;
  contentHash?: string;
  sizeBytes?: number;
  region?: string;
  encryptionRef?: string;
  aclRef: string;
  retentionUntil?: string;
  status: "available" | "pending" | "quarantined" | "deleted" | "unknown";
}
```
materialization locator 必须按 scope 受控解析；不可把不可猜 URL 当成权限。
## Source、Producer 与 Consumer
### Source 类型
```typescript
type SourceKind =
  | "user"
  | "host"
  | "workspace"
  | "repository"
  | "database"
  | "event_store"
  | "artifact_store"
  | "memory_store"
  | "vector_store"
  | "provider"
  | "tool"
  | "webhook"
  | "billing"
  | "synthetic"
  | "derived";
```
### SourceRef
```typescript
interface SourceRef {
  sourceId: string;
  kind: SourceKind;
  system: string;
  locatorHash?: string;
  tenantId: TenantId;
  workspaceId?: WorkspaceId;
  region?: string;
  capturedAt: string;
  authority: "authoritative" | "replica" | "cache" | "derived" | "unknown";
  receiptRefs: EvidenceRef[];
}
```
### Producer/ConsumerRef
```typescript
interface ProducerRef {
  producerId: string;
  kind: "user" | "agent" | "provider" | "tool" | "workflow" | "worker" | "system";
  component: string;
  version: string;
  runId?: RunId;
  attemptId?: string;
  trust: "trusted" | "untrusted" | "quarantined";
}
interface ConsumerRef {
  consumerId: string;
  kind: "context" | "prompt" | "provider" | "tool" | "state" | "memory" | "artifact" | "analytics" | "audit" | "deletion" | "export";
  component: string;
  purpose: PurposeRef;
  scope: ScopeRef;
  decisionRef?: string;
}
```
### Consumer 约束
- consumer 不能改变 object owner、tenant、purpose 或 residency。；provider consumer 必须带 `EgressSnapshot`、`ProviderSecurityContract`、region 和 data class。
- Context/Prompt consumer 必须记录 selected/dropped/summarized 语义。；Tool consumer 必须记录 input/output、effect、approval、sandbox 和 receipt。
- deletion/export consumer 必须记录 subject、legal basis、scope、retention/hold 和 completion evidence。
## Lineage Edge 与 Provenance
### Edge 类型
```typescript
type LineageEdgeKind =
  | "originated_from"
  | "copied_from"
  | "materialized_as"
  | "normalized_from"
  | "transformed_from"
  | "summarized_from"
  | "embedded_from"
  | "reranked_from"
  | "selected_for"
  | "compiled_into"
  | "sent_to"
  | "received_from"
  | "consumed_by"
  | "cached_from"
  | "indexed_from"
  | "exported_to"
  | "replicated_to"
  | "deleted_from"
  | "blocked_by"
  | "quarantined_by"
  | "restored_from";
```
### Edge 结构
```typescript
interface LineageEdge {
  edgeId: string;
  from: ObjectVersionRef;
  to: ObjectVersionRef;
  kind: LineageEdgeKind;
  producer: ProducerRef;
  consumer?: ConsumerRef;
  transformationRef?: TransformationRef;
  provenanceRef: ProvenanceRef;
  purpose: PurposeRef;
  scope: ScopeRef;
  tenantId: TenantId;
  sourceRegion?: string;
  targetRegion?: string;
  dataClass: DataClass;
  sensitivity: Sensitivity;
  schemaCompatibility: "exact" | "compatible" | "migrated" | "unknown";
  confidence: number;
  observation: "observed" | "declared" | "inferred";
  occurredAt: string;
  recordedAt: string;
  policyVersion: string;
  contentHash?: string;
  chainHash: string;
  status: "active" | "blocked" | "superseded" | "deleted" | "unknown";
}
```
### Edge 不变量
- `from.tenantId` 与 `to.tenantId` 不同必须有显式 cross-tenant policy、purpose、approval 和合规规则；默认拒绝。；source/target region 违反 residency 时 edge 状态为 `blocked`，不能伪装为 active。
- `inferred` edge 不得支持高敏感度 provider egress、删除证明或法律报告。；transformation、schema、producer version 和 policy snapshot 缺失时标记 lineage gap。
- edge append-only；更正使用 superseding edge、correction event 或新的 version。；deletion edge 不能删除原始 lineage fact，只表达传播动作和 receipt。
- graph query 返回 edge 时必须保留 observation、confidence、policy 和 evidence。
### ProvenanceRef
```typescript
interface ProvenanceRecord {
  provenanceId: string;
  sourceRefs: SourceRef[];
  producer: ProducerRef;
  captureEventIds: string[];
  sourceCursor?: string;
  requestIdHash?: string;
  providerReceiptRef?: string;
  artifactManifestRef?: ArtifactRef;
  environmentSnapshotRef?: ArtifactRef;
  schemaRef: SchemaRef;
  version: string;
  contentHash?: string;
  parentChainHash?: string;
  capturedAt: string;
  verifiedAt?: string;
  verification: "verified" | "partial" | "unverified" | "failed";
  limitations: string[];
}
```
## Transformation 与派生数据
### Transformation 类型
```typescript
type TransformationKind =
  | "parse"
  | "normalize"
  | "filter"
  | "join"
  | "redact"
  | "summarize"
  | "compact"
  | "embed"
  | "rerank"
  | "retrieve"
  | "prompt_compile"
  | "provider_encode"
  | "provider_decode"
  | "tool_execute"
  | "aggregate"
  | "export"
  | "delete"
  | "restore";
interface TransformationRecord {
  transformationId: string;
  kind: TransformationKind;
  component: string;
  implementationVersion: string;
  codeDigest?: string;
  promptTemplateRef?: string;
  modelSnapshotRef?: string;
  toolSchemaRef?: string;
  parametersHash: string;
  inputSchemaRefs: SchemaRef[];
  outputSchemaRefs: SchemaRef[];
  inputObjectRefs: ObjectVersionRef[];
  outputObjectRefs: ObjectVersionRef[];
  deterministic: boolean;
  replayMode: "exact" | "recorded" | "simulated" | "unknown";
  qualityEvidenceRefs: EvidenceRef[];
  createdAt: string;
}
```
### 派生对象原则
- summary、embedding、memory、prompt section、provider payload、cache 和 export 都是新 object/version。；派生对象不能继承 source 的全部 purpose、scope、retention 或 residency；逐项计算交集或更严格策略。
- redaction 产生的新对象必须保留被删除字段类型、redaction profile、source relation 和不可逆性。；compaction 记录 source cursor range、summary hash、token accounting 和丢失字段/不确定性。
- embedding 记录模型、维度、index、region、retention、purpose 和是否可从向量恢复内容的风险评估。；prompt compile 记录 section、模板、system instruction、tool description、context resource 和 policy version。
- provider encode/decode 记录 canonical object 与 provider payload 的 schema mapping，不能把 provider 原生格式当 canonical truth。
### Transformation 不可重演
若无法重演 transformation：
- 标记 `replayMode: "unknown"`。；保存 input/output hash、环境、版本、receipt 和 limitation。
- 影响分析仍可沿 edge 传播，但不能声称 exact reproducibility。；高敏感度外发、删除证明和合规报告需要额外 observed evidence。
## Schema、Version 与 Contract
### SchemaRef
```typescript
interface SchemaRef {
  schemaId: string;
  namespace: string;
  name: string;
  version: string;
  fingerprint: string;
  compatibility: "backward" | "forward" | "full" | "none" | "unknown";
  fieldClassifications: Record<string, DataClass>;
  migrationRefs: string[];
  registrySource: string;
}
```
### 版本维度
```text
object schema version
edge schema version
transformation version
provider request/response schema
tool schema
prompt compiler version
context plan version
policy/egress version
artifact manifest version
event/reducer/projector version
workspace snapshot version
deletion protocol version
```
### Contract 规则
- producer 只能发布注册过的 schema/version。；consumer 声明支持的 schema range、required fields、unknown field handling 和 failure mode。
- incompatible schema 不得靠字段名猜测或静默 drop。；migration 生成新 object version/edge，原版本 immutable。
- provider schema 演进必须同时更新 canonical mapping、conformance fixture、lineage transformation 和 impact cache。；prompt/context/toolset/schema 变化应触发潜在影响查询，而不是只改配置文件。
### Schema Drift
```typescript
interface SchemaDriftRecord {
  driftId: string;
  objectKind: LogicalObjectKind;
  sourceSchema: SchemaRef;
  observedSchema: SchemaRef;
  affectedEdges: string[];
  severity: "info" | "warning" | "blocking" | "security";
  detection: "runtime" | "contract" | "sampled" | "static" | "reconciliation";
  action: "observe" | "quarantine" | "migrate" | "rollback" | "deny";
  owner: PrincipalRef;
  detectedAt: string;
}
```
## Purpose、Scope、Tenant、Residency 与 Data Class
### Purpose
`PurposeRef` 说明数据为什么被收集、处理、外发、保留或删除：
```typescript
interface PurposeRef {
  purposeId: string;
  purpose: "task_execution" | "context" | "prompt" | "tool" | "memory" | "evaluation" | "security" | "billing" | "support" | "deletion" | "export";
  legalBasis?: string;
  declaredBy: PrincipalRef;
  policyVersion: string;
  expiresAt?: string;
}
```
purpose 不是标签；它决定可用 consumer、retention、provider egress、region、访问者和删除路径。
### Scope
```typescript
interface ScopeRef {
  tenantId: TenantId;
  userId?: string;
  workspaceId?: WorkspaceId;
  projectId?: ProjectId;
  repositoryId?: RepositoryId;
  sessionId?: SessionId;
  runId?: RunId;
  attemptId?: string;
  subjectIds?: string[];
  purposeId: string;
  scopeVersion: string;
}
```
### Residency
```typescript
interface ResidencyConstraint {
  allowedRegions: string[];
  deniedRegions: string[];
  jurisdiction?: string;
  providerClasses?: string[];
  crossBorder: "deny" | "approved_only" | "allow";
  backupRegions?: string[];
  supportRegions?: string[];
  verifiedAt?: string;
}
```
### DataClass
```typescript
type DataClass = "public" | "internal" | "confidential" | "pii" | "secret" | "regulated" | "security_sensitive" | "unknown";
type Sensitivity = "low" | "medium" | "high" | "critical" | "unknown";
```
### 传播规则
- edge 的 purpose 必须是 source/target purpose 的允许交集或更窄目的。；tenant、workspace、session、run 和 subject scope 只能取交集，不能由 consumer 扩大。
- target residency 必须满足 source constraint；跨 region 需要 EgressSnapshot、ProviderSecurityContract 和 policy evidence。；data class 只能提升或保持，不得无证据降级。
- unknown data class、purpose、scope、residency 或 owner 对高风险 consumer 默认 deny。
## 核心数据模型
### ObjectVersionRef
```typescript
interface ObjectVersionRef {
  objectId: string;
  versionId: string;
  schemaFingerprint: string;
  contentHash?: string;
  materializationId?: string;
  tenantId: TenantId;
  region?: string;
}
```
### Lineage Manifest
```typescript
interface LineageManifest {
  manifestId: string;
  rootObjects: ObjectVersionRef[];
  objects: LogicalDataObject[];
  materializations: DataMaterialization[];
  edges: LineageEdge[];
  transformations: TransformationRecord[];
  schemas: SchemaRef[];
  purposeRefs: PurposeRef[];
  policyVersions: string[];
  graphCursor: string;
  graphVersion: string;
  completeness: "complete" | "bounded" | "partial" | "unknown";
  generatedAt: string;
  integrityHash: string;
}
```
### LineageGap
```typescript
interface LineageGap {
  gapId: string;
  subject: ObjectVersionRef | string;
  missing: "source" | "producer" | "consumer" | "transformation" | "schema" | "purpose" | "scope" | "residency" | "deletion" | "quality";
  risk: "low" | "medium" | "high" | "critical";
  observedAt: string;
  affectedConsumers: string[];
  allowedActions: string[];
  owner: PrincipalRef;
  expiresAt?: string;
}
```
### DataQualityEvidence
```typescript
interface DataQualityEvidence {
  evidenceId: string;
  objectRef: ObjectVersionRef;
  checks: {
    check: "completeness" | "freshness" | "validity" | "uniqueness" | "consistency" | "reconciliation" | "lineage_coverage";
    status: "pass" | "warn" | "fail" | "unknown";
    observed: number | string;
    threshold?: number | string;
    methodVersion: string;
  }[];
  generatedAt: string;
  artifactRef?: ArtifactRef;
}
```
## TypeScript 接口
### Collector
```typescript
interface LineageCollector {
  observe(input: LineageObservation): Promise<LineageReceipt>;
  registerObject(input: ObjectRegistration): Promise<LogicalDataObject>;
  registerMaterialization(input: MaterializationRegistration): Promise<DataMaterialization>;
  appendEdge(input: EdgeRegistration): Promise<LineageEdge>;
  appendTransformation(input: TransformationRegistration): Promise<TransformationRecord>;
}
interface LineageObservation {
  source: SourceRef;
  producer: ProducerRef;
  consumer?: ConsumerRef;
  objectRefs: ObjectVersionRef[];
  operation: string;
  schemaRefs: SchemaRef[];
  purpose: PurposeRef;
  scope: ScopeRef;
  policyVersion: string;
  egressSnapshotRef?: string;
  receiptRefs: EvidenceRef[];
  observedAt: string;
}
```
### Catalog/Graph
```typescript
interface LineageCatalog {
  getObject(ref: ObjectVersionRef, auth: LineageAuth): Promise<LogicalDataObject | null>;
  getVersion(ref: ObjectVersionRef, auth: LineageAuth): Promise<ObjectVersionView | null>;
  queryForward(input: ForwardImpactQuery): Promise<ImpactGraph>;
  queryBackward(input: BackwardImpactQuery): Promise<ImpactGraph>;
  queryPath(input: LineagePathQuery): Promise<LineagePath[]>;
  queryGaps(input: LineageGapQuery): Promise<LineageGap[]>;
  snapshot(input: GraphSnapshotRequest): Promise<ArtifactRef>;
}
interface LineageGraphStore {
  append(event: LineageEvent): Promise<LineageReceipt>;
  read(cursor: string, scope: ScopeRef): AsyncIterable<LineageEvent>;
  reduce(snapshot?: GraphSnapshot): Promise<GraphState>;
  rebuild(input: RebuildRequest): Promise<RebuildReport>;
}
```
### Policy 与 Impact
```typescript
interface LineagePolicyEngine {
  evaluateEdge(input: EdgePolicyInput): Promise<EdgePolicyDecision>;
  evaluateConsumer(input: ConsumerPolicyInput): Promise<ConsumerPolicyDecision>;
  evaluateDeletion(input: DeletionPolicyInput): Promise<DeletionPlan>;
}
interface ImpactAnalyzer {
  forward(input: ForwardImpactQuery): Promise<ImpactGraph>;
  backward(input: BackwardImpactQuery): Promise<ImpactGraph>;
  deletion(input: DeletionImpactQuery): Promise<DeletionImpactGraph>;
  residency(input: ResidencyImpactQuery): Promise<ResidencyImpactReport>;
  schema(input: SchemaImpactQuery): Promise<SchemaImpactReport>;
}
```
### DSAR/Deletion
```typescript
interface DeletionPropagationService {
  open(request: DeletionRequest): Promise<DeletionJob>;
  plan(jobId: string): Promise<DeletionPlan>;
  execute(jobId: string, signal: AbortSignal): Promise<DeletionReport>;
  verify(jobId: string): Promise<DeletionVerification>;
  close(jobId: string): Promise<void>;
}
interface DeletionRequest {
  requestId: string;
  tenantId: TenantId;
  subjectRefs: SubjectRef[];
  objectRefs?: ObjectVersionRef[];
  purpose?: PurposeRef;
  reason: "user_request" | "retention_expiry" | "incident" | "legal" | "correction";
  legalHoldRefs?: string[];
  requestedBy: PrincipalRef;
  scope: ScopeRef;
  dueAt?: string;
}
```
### Drift/Quality
```typescript
interface LineageDriftDetector {
  checkSchema(input: SchemaDriftInput): Promise<SchemaDriftRecord[]>;
  checkEdgeCoverage(input: CoverageCheckInput): Promise<LineageGap[]>;
  checkFreshness(input: FreshnessCheckInput): Promise<DataQualityEvidence>;
  checkScope(input: ScopeConsistencyInput): Promise<LineageViolation[]>;
  checkProviderEgress(input: ProviderEgressLineageInput): Promise<LineageViolation[]>;
}
```
## Catalog、Index 与 Graph 存储
### 存储分层
```text
append-only lineage event log
  -> object/version catalog
  -> edge index by from/to/scope/time
  -> transformation/schema registry
  -> impact projection
  -> deletion projection
  -> quality/drift projection
  -> query cache and graph snapshot
```
### 索引键
至少支持：
- `objectId -> versions/materializations/parents/children`。；`versionId -> schema/contentHash/provenance/edges`。
- `tenant/workspace/session/run -> objects/edges`。；`purpose/dataClass/residency -> consumers/blocked edges`。
- `provider/apiFamily/model/deployment/region -> sent/received objects`。；`schemaFingerprint -> producers/consumers/versions/drift`。
- `subjectRef -> all active/expired/derived/remote objects`。；`transformationVersion -> outputs/quality/incident/regression`。
- `deletionRequest -> planned/completed/unknown objects`。
### Graph snapshot
```typescript
interface GraphSnapshot {
  snapshotId: string;
  graphCursor: string;
  objectCount: number;
  edgeCount: number;
  scopeHash: string;
  schemaRegistryVersion: string;
  catalogVersion: string;
  stateHash: string;
  createdAt: string;
  retentionUntil: string;
}
```
snapshot 只用于加速和证据；查询必须验证 owner、scope、policy、cursor、schema 和 snapshot hash。
### Graph consistency
- edge 两端 object/version 必须存在或有明确 pending reference。；parent/child graph cursor、chain hash 和 tenant scope 可验证。
- 删除不会物理删除历史 edge；删除 projection 标记对象/materialization/edge 状态。；object version supersession、schema migration、redaction 和 correction 必须可沿链追踪。
- graph rebuild 后比较 object count、edge count、hash relation、scope violation、gap 和 deletion state。
## 注册、发现与采集流程
### 注册来源
- Host/tenant/workspace/session 创建。；Provider Runtime request/response/usage/remote object。
- Tool Runtime call/result/artifact/side effect。；ContextCompiler selected resource、summary、embedding、rerank、cache。
- PromptCompiler section、template、system/tool instructions。；State/Event/Checkpoint/Replay/Memory。
- ArtifactStore snapshot、diff、log、fixture、export。；Workflow、subagent、worker、queue、billing、evaluation。
- Workspace Repository baseline、file、patch、test output。
### Capture 顺序
```text
authenticate principal
  -> resolve TenantContext/Scope
  -> resolve source and producer
  -> identify logical object/version
  -> validate schema/purpose/data class/residency
  -> record materialization
  -> append transformation and edge
  -> issue policy/egress receipt
  -> publish durable lineage event
  -> project catalog/graph/quality/deletion views
```
### Capture 规则
- 采集必须在关键副作用边界前后发生；只在日志端异步猜测会留下 coverage gap。；object registration 与 edge append 使用幂等 key；重复 event 不生成重复边。
- producer/consumer scope 从受信 execution context 继承；模型输出只能作为 data，不得覆盖。；对高敏感度对象，先构建 redacted metadata，再按 purpose 申请 payload access。
- provider response 的 raw payload 与 canonical response 分开建 object，并保留 mapping edge。；cache hit 也必须建 `cached_from` 或 `materialized_as` edge，不能隐藏 lineage。
- 失败、取消、unknown outcome 仍产生 lineage event，状态不伪装为成功。
### 观察与声明
- 声明性注册先进入 `declared`。；runtime receipt、content hash、request ID、artifact manifest 和 event cursor 可提升为 `observed`。
- 静态分析和模型推断进入 `inferred`，必须标识方法版本和置信度。；observed 与 declared 冲突时，进入 drift/quarantine，不静默覆盖。
## Context/Prompt/Tool/State/Memory/Artifact Lineage
### Context
ContextPlan 是一等逻辑对象：
- 记录 selected、excluded、summarized、retrieved、compacted、truncated 和 stale resource。；每个 `ContextResource` 连接 source object/version、selection reason、rank、token/byte estimate、sensitivity、purpose、freshness 和 egress permission。
- summary/embedding/rerank 是独立 transformation 和 derived object。；ContextPlan 只能选择当前 scope、purpose、policy、residency 和 provider egress 允许的数据。
- context cache 记录 source versions、policy/toolset/model/region/expiry；cache hit 仍验证 scope。
### Prompt
PromptSection、system instruction、tool description、user message、memory summary、artifact citation 和 provider wrapper 都建 object/version。
```text
source object
  -> context selection
  -> prompt section
  -> compiled prompt
  -> provider request view
```
Prompt compiler 必须记录：
- template/prompt compiler version。；section order、priority、token count、truncation、redaction 和 source hash。
- policy/tenant/purpose/egress/region snapshot。；toolset schema、approval wording、mode 和 safety floor。
Prompt 文本不拥有 source 权限；其内容不能创建新的 edge 或放宽 residency。
### Tool
Tool lineage 至少包括：
- tool call object、arguments schema、source context、approval、policy、sandbox、cwd/workspace view。；tool result、stdout/stderr、artifact、changed files、remote object、side-effect receipt。
- retry、unknown outcome、compensation、reconciliation 和 consumer。
工具生成的数据不能因“来自本地 workspace”自动被视为低敏感；文件、secret、网络、MCP/LSP、provider upload 都需要独立 lineage。
### State/Session Replay
- SemanticEntry、CanonicalEvent、Checkpoint、ReplayCursor 和 projector view 是不同 object kind。；replay 使用 recorded lineage 重建，不把当前 provider/tool/cache 当历史 source。
- fork/resume 创建新 branch/run 和新 output objects；不能覆盖源 lineage。；compaction 记录 source event range、summary、lossiness、purpose 和 retention。
### Memory
- memory candidate、confirmed memory、embedding、retrieval result、user edit、tombstone 和 deletion proof 各自建对象。；memory write 需要 purpose、scope、consent、provenance、source range、confidence、TTL 和 owner。
- recall 只创建 `selected_for`/`consumed_by` edge，不改变 memory owner。；用户拒绝、删除或 DSAR 必须沿 memory、embedding、cache、prompt、artifact 和 export 传播。
### Artifact
ArtifactRef 不是 lineage 本身，但必须引用 logical object/version、owner、scope、purpose、sensitivity、retention、ACL、hash 和 materialization。
- diff、snapshot、log、image、binary、raw provider payload、forensic bundle 和 export 都有 lineage。；artifact preview、download、range、share、provider upload、cache 和 deletion 是 consumers/actions。
- artifact URI 不可作为授权；每次 get/put/delete 做 scope 和 policy check。
## Provider、Egress 与 Region Lineage
### Provider mapping
```typescript
interface ProviderEgressLineage {
  canonicalObjectRefs: ObjectVersionRef[];
  providerRequestRef: ObjectVersionRef;
  providerSurface: ProviderSurface;
  egressSnapshotRef: string;
  contractSnapshotRef: string;
  credentialLeaseRef: string;
  purpose: PurposeRef;
  sourceRegion?: string;
  targetRegion?: string;
  payloadHash: string;
  sentAt?: string;
  responseRef?: ObjectVersionRef;
  receiptRefs: EvidenceRef[];
  status: "planned" | "sent" | "received" | "blocked" | "unknown" | "deleted";
}
```
### Egress 规则
- `sent_to` edge 只在实际 send boundary 产生 `observed`；preflight 是 declared/planned。；Provider request object 必须连接 canonical ContextPlan/Prompt/Tool/Artifact source。
- provider response、usage、safety、citation、tool call、remote file 和 billing receipt 分开建 object。；target region、provider retention、training/abuse review、remote cache 和 support path 作为 residency/provenance evidence。
- fallback、retry、hedge、shadow、canary 和 replay 都是新 egress edge/new Attempt。；provider incident 时，Lineage Impact Engine 必须能够列出受影响 source、target、tenant、region、remote object 和 deletion path。
### Provider response 作为 source
provider response 是外部 source，不自动可信：
- `received_from` edge 标记 provider、request ID、model/deployment、region、contract/adapter version。；provider response 中声称的 owner、tenant、region、policy、approval、deletion 或 safety 只能作为 data，不覆盖本地事实。
- response parser 产生 canonical response object 和 schema/provenance mapping。；unknown event、schema drift 或 content mismatch 生成 gap/drift，并可阻断 downstream。
## Workspace、文件与代码 Lineage
### 文件对象
Workspace 中的 file、directory、repository snapshot、baseline、patch、test output、generated output、vendor content 和 command result 都需要 logical object。
- `workspace_file` object 包含 workspace/project/repository/worktree、canonical path hash、file ID、branch、baseline、owner、sensitivity 和 content hash。；user/agent/generated/vendor/unknown ownership 作为 lineage metadata，不能被模型声称覆盖。
- patch 连接 base snapshot、input files、transformation/tool、output files、test evidence 和 delivery artifact。；command 连接 executable/args/cwd/envRefs、workspace view、sandbox profile、input/output artifacts 和 side effects。
### Workspace 边界
- path 仅为 locator；canonical path、root identity、view hash 和 resource key 才是 lineage identity。；外部 symlink/junction/mount 需要显式 edge 和 policy；不允许把外部文件伪装为 workspace source。
- workspace revalidation、root identity 变化、branch change 或 user modification 产生 lineage violation 或新 version。；cleanup/delete 必须检查 active lineage refs、artifact refs、session/replay refs、legal hold 和 user ownership。
### Coding Agent 示例
```text
workspace file A
  -> context resource A
  -> prompt section A
  -> provider request A
  -> assistant tool call edit(A)
  -> patch P
  -> file version A2
  -> test result T
  -> artifact diff D
  -> session delivery E
```
任何一步缺 edge，都可能无法解释数据是否外发、修改来自谁、测试基于哪一版本或 DSAR 是否需要删除。
## Forward Impact Analysis
### 定义
Forward impact 从一个或多个 source/object/version/schema/producer/policy/region 出发，寻找 downstream consumer、materialization、provider egress、artifact、memory、report、deletion 和副作用。
### ForwardImpactQuery
```typescript
interface ForwardImpactQuery {
  roots: ObjectVersionRef[];
  includeKinds?: LogicalObjectKind[];
  edgeKinds?: LineageEdgeKind[];
  maxDepth: number;
  maxNodes: number;
  asOfCursor?: string;
  scope: ScopeRef;
  purpose?: PurposeRef;
  includeInferred: boolean;
  sensitivityCeiling?: Sensitivity;
  requireObserved: boolean;
}
```
### 用例
- provider incident：从 provider request/response/region 找受影响 tenant、session、artifact、memory 和 deletion。；schema change：从 producer schema 找所有 consumer、tool、prompt、report、replay 和 migration。
- workspace file 修改：从 file version 找 ContextPlan、provider egress、patch、test、artifact 和 delivery。；purpose 撤销：从 object 找不再允许的 context、memory、cache、provider、export 和 backup。
- retention expiry：从 source 找所有 derived object/materialization 和 hold。
### 结果要求
结果列出：
- path、edge kind、depth、observation、confidence、schema compatibility 和 policy status。；每个 node 的 tenant/scope/purpose/region/data class/sensitivity/retention。
- blocked edge、lineage gap、unknown materialization 和未覆盖 consumer。；最后 observed cursor、graph version、policy snapshot、query authorization。
- 建议动作：deny、quarantine、reprocess、delete、notify、reconcile、migrate。
## Backward Impact Analysis
### 定义
Backward impact 从一个 downstream object、provider request、prompt、tool result、artifact、report、incident 或 deletion proof 追溯 source、producer、transformation、schema、policy 和原始 receipt。
### 用例
- 用户询问 provider 请求包含哪些数据。；provider incident 追溯具体 request 的 source/context/memory/artifact。
- 错误回答追溯 PromptSection、ContextPlan、memory、tool result 和 workspace baseline。；schema drift 追溯 producer、adapter、migration 和 first bad version。
- cost/billing dispute 追溯 usage、provider request、route、context token 和 retry。；deletion proof 追溯 source、derived、remote、cache、backup 和未完成动作。
### Backward 查询规则
- 默认先返回 metadata、hash、source type、scope、purpose 和 evidence，不直接返回原文。；raw payload、secret、PII、regulated data 需要更高的 purpose/role/approval。
- 如果 edge 是 inferred/declared，结果必须显式标记，不得显示为 confirmed source。；不同 tenant、region、legal hold 和删除状态的 path 需要隔离显示。
- backward query 不能因为 graph path 缺失就补写伪造 edge；生成 gap。
## 删除、DSAR 与传播证明
### 删除不是删除一个 row
删除必须覆盖：
```text
source object
  -> versions/materializations
  -> session/event projections
  -> context/prompt artifacts
  -> provider requests/remote objects
  -> tool outputs/files/cache
  -> memory/embedding/vector index
  -> artifact/export/fixture
  -> backup/replica
  -> lineage deletion markers/proof
```
### DeletionPlan
```typescript
interface DeletionPlan {
  requestId: string;
  rootObjects: ObjectVersionRef[];
  targetObjects: ObjectVersionRef[];
  targetMaterializations: DataMaterialization[];
  targetEdges: string[];
  remoteActions: RemoteDeletionAction[];
  cacheActions: CacheDeletionAction[];
  backupActions: BackupDeletionAction[];
  blockedByLegalHold: string[];
  unknownTargets: string[];
  risk: "low" | "medium" | "high" | "critical";
  policyVersion: string;
  graphCursor: string;
  generatedAt: string;
}
```
### Propagation 状态
```text
requested
  -> authorized
  -> planned
  -> propagating
  -> local_deleted
  -> remote_pending
  -> cache_pending
  -> backup_pending
  -> verified
  -> closed
```
异常状态：
```text
blocked_by_hold
partial
unknown
failed
reopened
```
### 删除策略
- append-only event 不被物理修改；敏感 payload 使用 tombstone、crypto erasure、redacted projection 或受控 deletion marker。；删除对象不意味着删除统计、不可逆 hash、审计必要事实或 legal hold 下的证据；具体保留由 Privacy/Legal policy 决定。
- provider remote delete 必须有 request ID、remote object ID、status、receipt、region 和 provider retention 说明。；vector/embedding 不只按 source ID 删除；必须清理 index、shard、cache、backup 和 retrieval projection。
- prompt/context/artifact export/fixture 删除需引用 object/version/subject/purpose，而不只按字符串搜索。；cache purge 需要 invalidation epoch、namespace、key hash 和 worker acknowledgement。
- deletion unknown 不得标记 `deleted`；保持 `unknown`、补偿计划和通知/hold 状态。
### DSAR
DSAR 流程：
1. 验证主体与 tenant scope。
2. 解析 subject refs、object refs、purpose 和 legal hold。
3. 执行 backward/forward graph expansion。
4. 分类 source、derived、remote、cache、backup、export、fixture 和 audit。
5. 输出可访问数据清单或 deletion plan，不直接暴露无关租户。
6. 运行 local、provider、artifact、memory、vector、cache、backup 和 projection action。
7. 收集 receipt、hash、tombstone、unknown 和 blocked evidence。
8. 复核 purpose、retention、legal hold、通知义务和残余风险。
9. 发布 DeletionVerification 和关闭报告。
### DeletionVerification
```typescript
interface DeletionVerification {
  requestId: string;
  verifiedObjects: ObjectVersionRef[];
  verifiedMaterializations: string[];
  verifiedRemoteActions: string[];
  pendingObjects: string[];
  unknownObjects: string[];
  heldObjects: string[];
  residualEdges: string[];
  proofRefs: EvidenceRef[];
  completeness: "complete" | "bounded" | "partial" | "unknown";
  verifiedAt: string;
}
```
## Retention、Legal Hold 与 TTL
### Retention 维度
- object kind、purpose、tenant、data class、region、provider、artifact type、security/incident hold。；source 与 derived object 的 retention 不必相同，但 derived 不能超过 policy 上限。
- lineage metadata 可能比 payload 更长寿，但不能保留可还原原文的 hash/embedding/filename/URL 组合而无必要目的。；incident forensic、legal hold、DSAR、billing、audit、evaluation fixture 和 replay artifact 分别管理 retention。
### Hold 规则
- legal hold 阻止物理删除，但不自动允许新消费或外发。；hold 创建、范围、owner、reason、expires/release 和影响对象写入 lineage。
- hold release 后重新运行 deletion impact；不能直接沿旧 plan 执行。；security/incident hold 需要最小化、访问审计和定期复核。
### TTL 传播
```text
source expiry
  -> derived expiry calculation
  -> cache invalidation deadline
  -> provider remote retention/deletion request
  -> artifact/backup/export action
  -> proof expiry and audit retention
```
## Drift、质量与不一致检测
### Drift 类型
- `schema_drift`：schema fingerprint、字段类型、required、enum、unknown event 变化。；`semantic_drift`：字段含义、provider capability、prompt/tool output 或 model behavior 变化。
- `edge_drift`：声明 edge 与 observed runtime edge 不一致。；`scope_drift`：tenant、workspace、session、purpose 或 subject scope 不一致。
- `residency_drift`：source/target region、provider、backup、support、remote object 不匹配。；`freshness_drift`：Context、memory、cache、catalog、provider status 或 artifact stale。
- `quality_drift`：completeness、validity、uniqueness、reconciliation、lineage coverage 下降。；`deletion_drift`：source 已删但 derived/remote/cache/backup 仍 active 或 proof 缺失。
- `version_drift`：producer、consumer、schema、policy、toolset、model、adapter 或 workflow version 不一致。
### 检测层次
1. 静态：代码、schema、SQL、workflow、tool registry、prompt template、workspace config。
2. 契约：producer/consumer compatibility、provider conformance、tool schema、artifact manifest。
3. 运行时：event、receipt、content hash、route/egress/region、object materialization。
4. 对账：catalog 与 storage、provider receipt、usage ledger、billing、deletion API。
5. 采样：低敏感度 synthetic/sanitized 数据、canary、shadow、replay。
6. 主体反馈：DSAR、用户更正、删除、数据驻留问题和 support case。
### Drift response
```text
observe -> classify -> bound impact -> block/quarantine if required
-> migrate/reprocess/repair -> verify -> close with regression
```
高风险 drift 不允许只告警不限制 consumer。
## Catalog/Graph Query 设计
### 查询类型
```typescript
type LineageQueryKind =
  | "object"
  | "version"
  | "forward_impact"
  | "backward_impact"
  | "path"
  | "schema_consumers"
  | "provider_egress"
  | "subject_objects"
  | "deletion_status"
  | "residency"
  | "quality_gaps"
  | "drift"
  | "orphan_materializations"
  | "incident_scope"
  | "cost_attribution";
```
### Query 安全
- 查询入口先认证、解析 TenantContext、purpose、role、data class ceiling 和 redaction profile。；graph traversal 绑定 scope、maxDepth、maxNodes、time window、edge kinds 和 cost budget。
- 不允许任意 regex/recursive query 读取所有 tenant 的原始 payload。；大图返回 bounded/partial，并列出截断、gap、unknown 和 query budget。
- 查询结果带 graph cursor、snapshot、policy、authorization、redaction 和 evidence refs。；raw content 通过 ArtifactRef/controlled fetch 另行授权，不能嵌入 graph response。
### ImpactGraph
```typescript
interface ImpactGraph {
  queryId: string;
  roots: ObjectVersionRef[];
  nodes: ObjectVersionView[];
  edges: LineageEdge[];
  gaps: LineageGap[];
  blockedPaths: BlockedPath[];
  truncated: boolean;
  graphCursor: string;
  policyVersion: string;
  redactionProfile: string;
  generatedAt: string;
}
```
### Query 解释
每个 path 输出：
```text
root -> edge kind -> transformation -> target
```
并说明：
- observed/declared/inferred。；source/target schema compatibility。
- purpose/scope/tenant/residency。；edge policy decision、blocked reason、confidence、freshness。
- 对应 event、receipt、artifact、provider request、deletion proof。
## CI、发布与运行时 Gates
### CI Gate 类型
- **Object gate**：新增 object kind 有 owner、scope、purpose、data class、schema、retention、deletion policy。；**Edge gate**：所有 producer/consumer/transformation 有 declared edge 和 runtime observation hook。
- **Schema gate**：schema fingerprint、compatibility、migration、unknown field handling 和 versioned fixture。；**Egress gate**：provider/region/credential/data class/purpose/residency mapping 完整，不能有 unknown high-risk path。
- **Deletion gate**：所有 materialization、cache、vector、artifact、remote object、backup 和 export 有 deletion action。；**Quality gate**：lineage coverage、freshness、reconciliation、scope consistency 达到 threshold。
- **Replay gate**：ContextPlan、Prompt、Toolset、Policy、Model、Workspace、Artifact 和 Event 可重建或标记缺失。；**Incident gate**：provider incident 能从 request 反查 source，从 source 前查 remote/provider/derived impact。
- **Cost gate**：provider request、context、tool、artifact、egress、worker 和 retry 可归因到 usage/cost ledger。
### Gate 严重度
| Gate 结果 | 说明 | 动作 |
|---|---|---|
| pass | observed、完整、兼容、可删除 | 发布/运行 |
| warn | declared/partial，有低风险缺口 | 记录 owner/expiry |
| block | 高风险 unknown、scope/residency/schema/deletion 不合规 | 阻断 |
| quarantine | 运行时 observed 与 contract 冲突 | 隔离 producer/consumer/object |
| manual | 需要 Privacy/Legal/Security/Owner 判断 | 等待审批 |
### 发布流程
```text
change proposal
  -> static lineage extraction
  -> schema/contract validation
  -> forward/backward impact
  -> purpose/scope/residency check
  -> deletion/replay/quality check
  -> synthetic conformance
  -> canary lineage observation
  -> promote or rollback
```
### Runtime gate
在以下边界必须执行：
- source capture、object materialization、edge append。；Context selection、Prompt compile、Tool call、Provider send。
- Artifact put/get/share/upload、Memory write/recall、Embedding index。；Session checkpoint、Replay、Workflow step、Subagent spawn。
- Export、DSAR、delete、restore、backup、billing、incident forensics。
## 生命周期与状态机
### Object 生命周期
```text
Discovered
  -> Registered
  -> Versioned
  -> Materialized
  -> Active
  -> Restricted | Quarantined | Superseded
  -> Expiring
  -> DeletionPlanned
  -> Deleting
  -> Deleted | Partial | Unknown
```
### Edge 生命周期
```text
Declared
  -> Observed
  -> Verified
  -> Active
  -> Blocked | Superseded | DeletionPending
  -> Deleted | Unknown
```
### Transformation 生命周期
```text
Registered
  -> Validated
  -> Running
  -> Succeeded | Failed | Unknown
  -> Reconciled
  -> Deprecated
```
### Deletion Job 生命周期
```text
Requested
  -> Authorized
  -> ImpactExpanded
  -> Planned
  -> Executing
  -> AwaitingRemoteReceipt
  -> AwaitingCache/BackupReceipt
  -> Verifying
  -> Completed
```
### Drift 生命周期
```text
Detected
  -> Classified
  -> Scoped
  -> Contained
  -> Repaired | Migrated | Accepted
  -> Verified
  -> Closed
```
### 状态不变量
- Registered object 必须有 tenant、owner、purpose、scope、schema、data class、retention 和 deletion policy。；Active edge 必须有 provenance、policy version、scope、purpose、schema compatibility 和 chain hash。
- unknown transformation 不能为高风险 consumer 提供 observed 证明。；Deleted object 的 active materialization 必须为零，或明确由 hold/retention/unknown 解释。
- graph projection 可以滞后，但必须暴露 cursor lag 和 completeness。；state transition 追加 event，不原地改变历史观察。
## 端到端决策流程
### 注册与消费
1. 认证 principal，冻结 TenantContext、WorkspaceView、Session/Run/Attempt scope。
2. 识别 source、producer、consumer 和 logical object kind。
3. 计算 object/version identity、schema fingerprint、content hash、data class 和 sensitivity。
4. 解析 purpose、retention、subject refs、residency、tenant、workspace、region。
5. 注册或复用 object/version；重复内容不自动复用 owner/purpose。
6. 为 materialization 分配 scoped locator、ACL、region 和 retention。
7. 注册 transformation、输入/输出 schema、code/model/prompt/tool/workflow version。
8. 评估 edge policy、purpose、scope、residency、provider contract、DLP 和 deletion path。
9. append observed/declared edge 和 receipt。
10. 发布 lineage event，更新 catalog、graph、quality、impact 和 audit projection。
### Provider Egress
11. 从 ContextPlan/Prompt/Tool/Artifact 收集 canonical source refs。
12. 创建 provider request logical object 和 egress lineage plan。
13. 运行 EgressSnapshot、ProviderSecurityContract、region、credential、purpose 和 policy gate。
14. send boundary 观察 payload hash、provider request ID、target region、credential lease。
15. 收集 response/tool/usage/remote object/billing objects 和 mapping edges。
16. 发生 error/unknown/schema drift 时记录 lineage gap、incident signal 和 recovery candidate。
### 影响/删除/漂移
17. source/schema/policy/provider/workspace/incident/deletion 变化触发 forward impact。
18. downstream 错误、用户投诉、provider request 或 report 触发 backward impact。
19. DSAR/retention/legal hold 触发 deletion impact 和 propagation plan。
20. 运行 schema/scope/residency/freshness/deletion/coverage reconciliation。
21. 对高风险 unknown 执行 block/quarantine/manual review。
22. 完成修复、迁移、删除、provider receipt、cache purge、backup action 和 proof。
23. 将结果写入 Data Quality、Incident、Evaluation、Cost、Replay 和 postmortem regression。
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### Model/Provider
- `ModelRef`、`ResolvedModel`、`Deployment`、`ProviderSurface`、`ApiFamily`、`RouteSnapshot` 和 `ProviderSecurityContract` 进入 egress lineage。；Provider request/response/usage/safety/tool/remote object 各自建 object/version。
- fallback、retry、hedge、shadow、canary、replay 是独立 Attempt 和 lineage branch。；provider adapter 不得省略 canonical-to-provider transformation 或把 remote provider cache 当本地 source。
- Provider Incident 可调用 forward impact，列出历史 egress 和派生对象；恢复需验证 lineage coverage。
### Prompt
- PromptCompiler 输出 `PromptSection`、`CompiledPrompt`、`ToolDescription`、`SystemInstruction` 对象和 transformation。；prompt section 引用 ContextResource、memory、user message、workspace、artifact 和 policy source。
- redaction、truncation、summary、tool schema 和 instruction precedence 作为 transformation metadata。；Prompt 不能创建未注册的 source、owner、purpose 或 residency。
- prompt 变化触发 backward/forward impact 和 replay/evaluation fixture 更新。
### Context
- ContextPlan 是 lineage graph 的汇合点，连接 source object/version 与 provider request、prompt、cost、cache 和 evaluation。；Context selection reason、rank、freshness、token/byte、sensitivity、purpose、provider egress 和 policy decision 必须记录。
- cache hit、retrieval、rerank、memory recall、compaction 和 artifact offload 产生独立 edges。；source 删除、scope 收紧或 provider incident 后，ContextPlan 重新计算；旧 plan 只能用于 historical replay。
### Tool
- Tool schema、arguments、approval、sandbox、workspace view、input object、output object 和 side-effect receipt 都进入 lineage。；工具执行可以生产 workspace file、artifact、remote object、event、usage、cost、memory 或 provider request。
- tool result 中的 prompt injection、fake owner、fake purpose、fake deletion claim 不得改变 edge authorization。；tool unknown outcome 生成 pending/unknown edge，不能自动复制或删除。
### State/Memory/Artifact/Replay
- Session Event、SemanticEntry、Checkpoint、ReplayCursor、ContextPlan、Prompt、ToolResult、ArtifactRef、Memory 和 Cost entry 互相可追溯。；replay 使用 historical graph cursor 和 recorded transformations；live quarantined replay 产生新 graph branch。
- compaction、projection、redaction 和 migration 不能丢失 parent chain、subject、purpose、scope、deletion 和 legal hold。；artifact deletion、export、preview、download、provider upload 和 cache 必须有 lineage edges。
### Policy/Privacy/Data Governance
- Policy 评估 edge、consumer、provider egress、residency、purpose、subject、retention 和 deletion。；Privacy 规则决定 data minimization、redaction、legal basis、DSAR、hold、notification 和 retention。
- Data Governance 维护 inventory、owner、catalog、purpose、lineage、quality、residency 和 proof。；lineage 只是 policy input/evidence，不能代替 enforcement；实际 provider/tool/file/network effect 仍由 Runtime/Sandbox 强制。
### Harness
- Harness Bootstrap 装配 Collector、Catalog、Schema Registry、Transformation Registry、Policy、Egress、Artifact、State、Quality、DSAR 和 Impact ports。；RunSupervisor 在每个 model/tool/provider/workflow/subagent/worker boundary 发布 lineage events。
- Harness 将 lineage scope 与 RunScope、WorkspaceView、BudgetReservation、CredentialLease、ContextPlan 和 ArtifactScope 冻结。；child run 只接收父 lineage view 的交集，child 产生的新 object/edge 归 child scope，并由 parent fan-in 验证。
- cancellation/crash/unknown outcome/cleanup/replay 产生 lineage 状态，不允许静默丢失。
## 故障恢复、回填与 Unknown Lineage
### Collector 失败
- 不将采集失败默认为 complete；产生 `LineageGap`、quality alert 和受限状态。；高风险 egress、delete、export、memory write 和 provider upload 在缺少 observed edge 时暂停或 quarantine。
- 低风险内部处理可继续，但输出 `bounded/partial` manifest 和 owner/expiry。；恢复后使用 event cursor、request receipt、artifact manifest、provider status、workspace snapshot 和 storage scan 回填。
### Graph projection 失败
```text
load last graph snapshot
  -> validate snapshot hash/scope/schema
  -> read lineage event tail
  -> rebuild object/edge indexes
  -> compare counts/hash/violations/gaps
  -> publish new projection cursor
```
原始 LineageEventLog 保持 immutable；不能通过删除 event 修复 graph。
### Unknown lineage
出现于：
- send boundary crash、provider request accepted 但本地无 ack。；artifact upload、remote file、cache write、backup、delete receipt 丢失。
- tool process 已启动但 output/side effect 不明。；schema mapping、static inference 或 source ownership 未确认。
- event append、queue ack、worker lease 或 cleanup 中断。
处理：
1. 标记对象/edge/transformation/materialization 为 unknown。
2. 停止复用、重试、外发、删除或承诺完成。
3. 查询幂等 receipt、provider status、storage inventory、cache namespace、worker state。
4. 生成 reconciliation candidate 和 evidence gap。
5. 只有确认未发生或已完成，才能关闭 unknown。
6. 不以当前扫描结果覆盖历史 unknown；追加 correction/reconciliation event。
### Backfill
- backfill job 有独立 run、workflow version、scope、budget、purpose、worker lease 和 output object version。；优先从 durable event、receipt、artifact manifest、workspace snapshot 和 provider logs 回填，最后才静态推断。
- inferred edge 不能直接升级 observed；升级需要新的证据。；backfill 不得跨 tenant 读取、不覆盖现有 edge、不删除 gap 证据。
- backfill 结果通过 dual-read、sample verification、count/hash/quality comparison 后发布。
## 安全、隐私、多租户与驻留
### 最小化
- catalog 默认保存 metadata、hash、type、size、schema、scope、purpose、region、retention 和 evidence refs，不保存完整 payload。；内容读取通过 ArtifactRef、ACL、purpose、sensitivity ceiling、expiry 和审计。
- graph export、impact report、DSAR bundle 和 forensic bundle 使用 redaction profile、最小必要字段和 short TTL。；embedding、summary、filename、URL、error、provider request ID 和 hash 组合也可能泄露内容，需按 sensitivity 处理。
### Cross-tenant 防护
- object、version、materialization、edge、transformation、query、snapshot、cache、artifact、worker、DSAR 和 deletion 都执行 tenant ownership check。；scope intersection 不能因 graph path、相同 hash、共享 provider、共享 cache 或 provider receipt 而扩大。
- aggregate query 只返回授权聚合，不泄露其他 tenant 的 object existence、provider usage、region 或 incident。；shared infrastructure 复制必须有明确 owner、purpose、residency、retention 和 deletion/DSAR 规则。
### Residency
必须沿 edge 验证：
```text
source region
  -> processing region
  -> provider endpoint/deployment
  -> remote object/cache
  -> artifact/log/trace/backup
  -> support/forensics/export
```
任一未知或不允许目标都产生 blocked edge；不能因为 provider 声称 region 或 URL 域名而自动通过。
### Secret/PII
- secret 原文不进入 lineage event、graph index、metric label、prompt、artifact filename 或 provider case。；保存 credential version/ref、redaction status、access purpose 和 revoke/rotation receipt。
- subject refs 使用不可逆或受控标识，并与 tenant scope 绑定。；DSAR 查询返回必要原文前先执行 purpose、role、legal basis、redaction 和 export audit。
## 可观测性与审计
### Lineage Events
```text
lineage.object.discovered
lineage.object.registered
lineage.object.versioned
lineage.materialization.created
lineage.source.captured
lineage.edge.declared
lineage.edge.observed
lineage.edge.verified
lineage.transformation.started
lineage.transformation.completed
lineage.transformation.unknown
lineage.context.selected
lineage.prompt.compiled
lineage.tool.consumed
lineage.provider.sent
lineage.provider.received
lineage.remote_object.created
lineage.cache.materialized
lineage.memory.written
lineage.embedding.indexed
lineage.schema.drifted
lineage.scope.violation
lineage.residency.blocked
lineage.quality.failed
lineage.deletion.requested
lineage.deletion.propagated
lineage.deletion.verified
lineage.retention.expired
lineage.graph.rebuilt
lineage.gap.detected
lineage.impact.queried
lineage.export.created
```
### Trace 关系
```text
source capture
  -> object/version
    -> transformation
      -> edge
        -> materialization/consumer
          -> policy/egress decision
            -> receipt/audit
```
### 关键字段
```text
object_id
version_id
materialization_id
edge_id
from/to object hash
schema fingerprint/version
producer/consumer component/version
transformation id/version
tenant/workspace/session/run/attempt
purpose/legal basis
scope version
source/target region
provider/apiFamily/model/deployment
policy/egress/credential/contract snapshot
observation/confidence
content/source/chain hash
retention/legal hold/deletion status
quality/drift/gap state
cursor/graph version
```
### 指标
- object registration、version、materialization、edge append 成功率和 latency。；observed/declared/inferred edge ratio。
- lineage coverage by object kind/source/consumer/tenant/purpose。；graph projection lag、snapshot rebuild、query latency、query truncation。
- missing source/producer/consumer/transformation/schema/purpose/scope/residency/deletion gaps。；provider egress observed ratio、unknown egress、wrong region、blocked edge。
- ContextPlan/Prompt/Tool/Memory/Artifact/Replay lineage completeness。；schema/semantic/scope/residency/freshness/deletion drift count。
- DSAR plan latency、deletion completion、remote/cache/backup pending、unknown proof。；orphan materialization、stale cache、unreconciled provider object、vector deletion lag。
- forward/backward impact false positive、false negative、bounded/partial ratio。；graph data access、export、raw content fetch、break-glass 和 cross-tenant deny。
### SLO 示例
```text
observed edge completeness = observed required edges / required operations
high-risk egress lineage = observed provider sends / provider sends
schema contract coverage = versioned compatible producers/consumers
DSAR propagation completeness = verified targets / planned targets
deletion proof timeliness = closed requests within policy deadline
residency correctness = compliant edges / all residency-sensitive edges
scope correctness = edges without tenant/scope violation / all edges
catalog freshness = objects updated within freshness window / active objects
unknown closure = resolved unknowns / total unknowns within target window
```
### Audit
审计必须能够回答：
- 哪个 source object 在什么 purpose/scope/tenant/region 下被谁生产。；哪些 transformations、schema、prompt/context/tool/model/provider 参与。
- 哪些消费者看到了什么、何时、用什么 policy/egress/credential。；哪些 copies、cache、artifact、remote object、memory、embedding、backup 和 export 存在。
- 哪些 deletion/DSAR/retention/hold 动作已执行，哪些 unknown/blocked。；查询、导出、回填、break-glass 和人工更正由谁执行。
## 测试策略
### Unit
- logical identity、version、materialization、scope intersection、purpose narrowing、residency。；edge hash、chain hash、idempotency、observation confidence、schema compatibility。
- transformation replayability、redaction、retention、deletion state、graph traversal limits。；forward/backward query、gap、unknown、blocked path、query authorization。
- deletion plan、remote/cache/backup action、hold、proof、reopen。
### Component
- Collector adapters：workspace、event、provider、tool、artifact、memory、vector、billing、workflow。；Catalog、Schema Registry、Transformation Registry、Graph Store、Snapshot、Rebuilder。
- Policy/Egress/DSAR/Quality/Drift/Impact services。；Artifact ACL、redaction、retention、cache namespace 和 provider remote object adapters。
### Contract/Conformance
每个 producer/consumer contract 至少验证：
1. object/version/schema/owner/purpose/scope/region 注册。
2. observed edge 与 receipt 对齐。
3. duplicate event 幂等。
4. unknown outcome 不伪装成功。
5. schema incompatible 时 block/quarantine。
6. provider request 与 Context/Prompt/Tool/Artifact source 可反查。
7. tool side effect、workspace patch、remote upload/delete 有 receipt。
8. cache、embedding、memory、artifact、backup 和 export 有 derived edges。
9. deletion/DSAR propagation 与 hold/retention 兼容。
10. cross-tenant、wrong region、fake owner/purpose/approval 被拒绝。
### Integration/Scenario
- user input 经 context/prompt/provider/tool/state/artifact/cost/evaluation 的完整路径。；provider fallback/retry/hedge/shadow/canary 的独立 lineage。
- workspace dirty changes、symlink/junction、worktree、patch、test output。；memory candidate/confirm/recall/edit/delete/embedding/index。
- session replay、fork、compaction、checkpoint、redaction、migration。；provider incident forward impact 与 credential/egress/remote object quarantine。
- schema drift、provider capability drift、adapter rollback、backfill。；DSAR、retention expiry、legal hold、backup restore、remote delete unknown。
### Fault injection
在以下位置 crash/timeout/gap/duplicate：
- object registration、materialization、edge append、transformation。；provider send/response/remote upload/status/delete。
- tool process、artifact put/get/delete、cache write/invalidation。；graph event append、snapshot、projection、query、rebuild。
- deletion plan、remote action、backup purge、verification。；workflow/subagent/worker lease、session checkpoint、replay。
断言：不伪造 edge、不跨 tenant、不扩大 scope、不错误标记 deleted、不重复 provider/tool/remote side effect、不丢 gap/unknown。
### Property/Invariant
- graph append/rebuild 幂等后对象、edge、hash、cursor 一致。；forward/backward 查询互为可解释的路径反转，排除已删除/blocked 的 active 误判。
- purpose、scope、data class、residency 只能收紧或保持。；deletion plan 覆盖所有 active materialization 与派生 object，或显式 hold/unknown。
- allocation、usage、cost 和 egress 的 lineage source 与 ledger attribution 一致。；schema migration 后 parent chain、scope、subject、retention、deletion 不丢失。
### Evaluation
Evaluation 断言：
- lineage completeness、coverage、freshness、drift、deletion、residency、scope。；Context/Prompt/Tool/Provider/State/Artifact/Memory 的 source/path/provenance。
- provider incident 的 affected objects、remote objects、tenant/region、unknown 和 proof。；cost attribution、usage、retry/fallback、storage、egress、worker。
- 用户可见 explanation 与事实 graph 一致，但不以自然语言替代 graph evidence。
## 反模式
1. **给表加 source 字段**：无法表达多版本、复制、转换、consumer、region、purpose 和删除。
2. **只追踪文件名/URL**：路径、URL、hash、provider object ID 不是稳定逻辑身份。
3. **只追踪 source 不追踪 derived**：summary、embedding、cache、memory、prompt、artifact 和 remote object 会脱离治理。
4. **把 hash 当授权**：相同内容不代表相同 tenant、purpose、residency 或 retention。
5. **把模型 source claim 当事实**：模型输出是 untrusted data，不能注册 owner/scope/edge。
6. **只做静态 lineage**：真实 retry、fallback、tool、provider、cache、worker 和未知副作用不可见。
7. **只做运行时日志**：缺少 logical object、schema、purpose、retention、deletion 和 impact 查询。
8. **edge 不带 purpose/scope/tenant/region**：容易产生跨租户和错误驻留。
9. **inferred edge 冒充 observed**：删除证明、合规报告和高敏感度外发失真。
10. **provider request 不连接 Context/Prompt source**：无法解释外发数据和 incident blast radius。
11. **cache hit 不记录 edge**：隐藏复制、旧数据、跨 scope 和删除遗漏。
12. **embedding 不建对象**：向量 index、模型、维度、region、retention 和删除无法治理。
13. **只删除 source row**：remote、artifact、backup、vector、cache、fixture 和 projection 仍保留。
14. **legal hold 自动放行消费**：hold 只阻止删除，不授予新 purpose 或 egress。
15. **graph snapshot 当真相**：projection lag、rebuild 和 event tail 被忽略。
16. **graph 查询绕过 runtime policy**：能够读取不代表能够执行、外发或导出。
17. **schema drift 静默 drop 字段**：下游结果、删除、质量和安全语义可能错误。
18. **schema/version 只存最新值**：历史 replay、incident、billing 和 DSAR 无法解释。
19. **删除 unknown 当 deleted**：可能违反 DSAR、合同或安全通知义务。
20. **backfill 覆盖旧 edge**：破坏原始事实、证据链和纠错能力。
21. **跨 tenant 聚合泄露存在性**：图查询结果本身也是敏感数据。
22. **把 lineage payload 无限保留**：治理图反过来成为隐私和攻击面。
23. **用最终 prompt 证明 source**：缺少 compiler、ContextPlan、selection、redaction 和 policy 证据。
24. **把 ArtifactRef 当 lineage**：URI 有存储位置但没有逻辑来源、转换和消费者。
25. **只测 happy path**：没有 crash、duplicate、unknown、drift、delete、remote receipt 和恢复。
26. **把 catalog 完成率当实际 egress 控制**：必须在 send/tool/file/network boundary 强制。
27. **将 provider response 的 region/owner/purpose 当本地事实**：外部内容不拥有本地授权。
28. **把同一模型 alias 当同一 transformation**：deployment、adapter、region、price、capability 可能不同。
29. **把删除 event 物理擦掉**：缺少 deletion proof、audit、hold 和历史事实。
30. **用一次 graph query 代替持续 drift/quality 运营**：lineage 需要 freshness、SLO、owner 和回填。
## 实施清单
### P0：身份、边和契约
- [ ] 定义 LogicalDataObject、ObjectVersion、Materialization、Source、Producer、Consumer、LineageEdge、Provenance、Transformation。；[ ] 定义 tenant、workspace、session、run、attempt、subject、purpose、scope、residency、data class、sensitivity。
- [ ] 建立 append-only LineageEventLog、幂等、cursor、chain hash 和可重建 graph projection。；[ ] 建立 SchemaRegistry、TransformationRegistry、ObjectCatalog、EdgeIndex 和 ArtifactRef 关联。
- [ ] 所有 provider/tool/context/prompt/state/memory/artifact/workspace/worker/billing 对象有最小 lineage hook。
### P1：运行时 egress 与影响分析
- [ ] ContextPlan、PromptCompiler、ToolRuntime、ProviderRuntime、ArtifactStore、Memory 和 Workspace 产生 observed edge。；[ ] 实现 purpose/scope/tenant/residency/data class/retention 的 edge policy。
- [ ] 实现 forward/backward/path/schema/residency/provider/subject/deletion/incident/cost impact query。；[ ] 查询返回 graph cursor、policy、redaction、confidence、gaps、blocked paths 和 evidence refs。
- [ ] provider send、tool side effect、artifact upload、remote object、cache、embedding、memory 和 export 具备可验证 receipt。
### P2：删除、DSAR、质量与漂移
- [ ] 实现 deletion plan、DSAR subject expansion、remote delete、cache/vector/backup/export propagation。；[ ] 实现 legal hold、retention/TTL、unknown/partial/blocked、deletion proof 和 reopen。
- [ ] 实现 schema、semantic、edge、scope、residency、freshness、quality、deletion、version drift。；[ ] 建立 lineage coverage、freshness、reconciliation、residency、deletion completeness SLO。
- [ ] 建立 backfill、dual-read、sample verification、graph rebuild 和 recovery runbook。
### P3：CI、发布与运营
- [ ] 建立 object/edge/schema/egress/deletion/quality/replay/incident/cost gates。；[ ] Provider、adapter、model、route、prompt、context、toolset、workspace、workflow、artifact 和 memory 变更触发 impact analysis。
- [ ] 建立 tenant/operator/privacy/security/legal 的分层 catalog、graph、export 和 audit 视图。；[ ] 建立 synthetic/canary/replay/fault injection/production sampled lineage testkit。
- [ ] 连接 Provider Incident、Data Quality、Privacy、Data Governance、Cost、Session Replay、Evaluation 和 Postmortem。
### P4：治理成熟度
- [ ] 所有 unknown high-risk edge 默认 block/quarantine/manual review。；[ ] observed、declared、inferred 的比例和质量进入 dashboard 与发布决策。
- [ ] 所有 deletion/DSAR/incident/forensic/export 具备最小必要、ACL、retention、legal hold 和证明。；[ ] 建立 lineage owner、data steward、system owner、privacy/security reviewer 和 on-call。
- [ ] 定期做跨 tenant、错误 region、provider incident、schema drift、DSAR、backup、restore 和 graph rebuild 演练。
## 五个参考项目的启发来源
### Pi
- session、message/part、tool loop、stream event、compaction、checkpoint 和可恢复 runtime 启发 lineage 应把 semantic object、transport event、tool result、context 重建和 replay 事实分开。；headless kernel 与 CLI/TUI/RPC 共用运行时启发 lineage collector 不应绑定 UI；同一事实应服务 Context、Prompt、State、Artifact、Evaluation 和 Host。
- session tree/fork 方向启发 branch、resume、replay 和子 Agent 产生新 object/version/edge，而不是覆盖原 graph。
### Grok Build
- actor、ChatState、Sampler、permission、folder trust、sandbox、工具并发和路径锁启发 producer/consumer scope、workspace file lineage、tool side effect 和资源 owner 必须由 runtime 强制。；sampler/permission/sandbox 分层启发 lineage catalog 只能提供 policy evidence，不能代替实际 sandbox、egress、文件和命令边界。
- 并行工具和结果归属启发多个 child/tool output 需要独立 object、attempt、edge、receipt 和 parent attribution。
### OpenCode
- client/server、session/message/part、event bus、projector、snapshot、patch/revert、provider、permission 和 MCP/LSP 启发 lineage 需要 append-only event、可投影 graph、可审计 artifact 和可回滚 materialization。；snapshot/patch 让 workspace file、repository baseline、generated output、test result 和 delivery artifact 可追溯。
- client/server 分离启发 graph query、raw payload、artifact fetch 和 runtime policy 必须分层，UI 不能成为 lineage truth。
### Claude Code
- permissions、hooks、skills、subagents、memory、计划、任务工作流和 coding agent 资源启发 Prompt/Context/Tool/Workspace/Memory/Artifact/Worker 都需要 provenance、scope、purpose 和删除传播。；memory 与用户控制启发 memory candidate、recall、confirmed record、embedding、edit、tombstone 和 DSAR 必须形成可解释 lineage。
- hooks/MCP/project-local config 启发不可信项目内容不能注册 owner、purpose、policy 或 provider egress。
### OpenClaw
- AgentHarness registry、agent-core、Gateway/channel、tool/sandbox/elevated、plugins、memory、后台任务和多 channel session 启发 lineage 必须跨 Host、Provider、Tool、Worker、Artifact、Delivery 和长期 Session 统一。；事务化注册和 scope/capability 装配启发 producer/consumer、extension、provider、workflow 和 route 变更需要 snapshot、兼容检查、失败回滚和 lineage 记录。
- background worker、delivery、queue、reconnect 和多租户 channel 启发异步 consumer、lease、cache、通知、export 和 cleanup 不能脱离 graph。
## Definition of Done
- [ ] 每个高价值 logical data object 有稳定 identity、版本、schema、owner、purpose、scope、tenant、residency、data class、retention 和 deletion policy。；[ ] 每个生产、复制、转换、选择、编译、外发、消费、缓存、索引、删除和恢复动作有 lineage edge 或明确 gap。
- [ ] source/producer/consumer/transformation/provenance 可反查，且 observed/declared/inferred 清晰区分。；[ ] Context/Prompt/Tool/State/Memory/Artifact/Workspace/Provider/Cost/Evaluation/Incident 形成统一 graph。
- [ ] forward/backward/subject/schema/provider/residency/deletion/incident/cost impact 可查询、可限流、可授权、可解释。；[ ] purpose/scope/tenant/residency/data class/retention 只能收紧或保持，不能由模型或 provider response 扩大。
- [ ] DSAR、retention、legal hold、remote delete、cache、vector、backup、artifact、export 和 deletion proof 可验证。；[ ] schema、semantic、scope、residency、freshness、quality、deletion 和 version drift 有检测、隔离、修复和回归门禁。
- [ ] catalog/graph 是可重建投影，原始 event/receipt/provenance immutable，查询不代替 runtime enforcement。；[ ] unknown lineage 不被伪装为 complete、deleted、observed 或 compliant。
- [ ] CI、发布、运行时和事故响应都有 lineage gate，并能在真实 Harness 中测试。；[ ] 文档完成标准不是“有一张图”，而是“能证明数据从哪里来、去哪里、为何去、版本为何、谁能看、如何删、何时漂移、如何恢复”。
