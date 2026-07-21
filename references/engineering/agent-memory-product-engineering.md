# Agent Memory Product Engineering 细粒度工程设计
> 本文定义面向用户的 Memory Product，而不是底层 `MemoryStore` 的索引或向量数据库实现。
>
> 设计依据仅来自当前目录已有的参考架构、`agent-harness.md`、Prompt、Context、Tool、State/Memory、Permission/Sandbox、Subagent、Event/Observability、Evaluation、Provider Runtime、Provider Routing、Artifact、Multi-tenant、Workspace Isolation、Session Replay、Privacy、Production Operations、Agent Product 文档，以及其中归纳的五个参考项目源码结论。
>
> 明确边界：Memory Product 不是“自动把聊天写入 memory”。它是用户可查看、可解释、可确认、可编辑、可删除、可关闭、可迁移、可评测的数据产品；底层 Memory Store 只提供受策略约束的持久化、索引、版本和查询端口。
## 目录
1. [设计目标与非目标](#设计目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [Memory Product 与 Memory Store 的边界](#memory-product-与-memory-store-的边界)
4. [职责边界与包布局](#职责边界与包布局)
5. [用户可见的产品能力](#用户可见的产品能力)
6. [四类 Memory 的产品语义](#四类-memory-的产品语义)
7. [Scope、Owner、Provenance、Confidence 与 TTL](#scopeownerprovenanceconfidence-与-ttl)
8. [核心数据模型](#核心数据模型)
9. [TypeScript 接口](#typescript-接口)
10. [候选记忆与用户确认](#候选记忆与用户确认)
11. [自动写入门槛](#自动写入门槛)
12. [Recall 控制与上下文投影](#recall-控制与上下文投影)
13. [冲突、修订与版本](#冲突修订与版本)
14. [跨 Session、Workspace 与 Subagent 隔离](#跨-sessionworkspace-与-subagent-隔离)
15. [Memory Flush 与 Compaction](#memory-flush-与-compaction)
16. [与 Model、Prompt、Context、Tool、State、Policy、Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
17. [生命周期与状态机](#生命周期与状态机)
18. [决策流程](#决策流程)
19. [通知、解释与用户信任](#通知解释与用户信任)
20. [导入、导出、迁移与兼容](#导入导出迁移与兼容)
21. [故障恢复与未知结果](#故障恢复与未知结果)
22. [安全、隐私、Retention 与 DSAR](#安全隐私retention-与-dsar)
23. [多租户、权限与执行隔离](#多租户权限与执行隔离)
24. [可观测性、指标与 SLO](#可观测性指标与-slo)
25. [评测与实验策略](#评测与实验策略)
26. [测试策略](#测试策略)
27. [反模式与审查规则](#反模式与审查规则)
28. [实施清单](#实施清单)
29. [五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
Memory Product 必须使用户能够：；查看系统当前保存了哪些 memory。；按内容、类型、scope、来源、时间和状态搜索 memory。；查看每条 memory 的来源、解释、置信度、更新时间和过期时间。；编辑可编辑字段，而不是只能删除后重新生成。；确认或拒绝模型提取的候选 memory。；单条删除、批量删除、按类型删除和按 scope 删除。；关闭长期 memory、关闭某一 memory type，或仅允许 working memory。；了解某条 memory 是否被 recall 到当前任务以及影响了什么上下文。；在冲突时查看旧版本、新版本和建议修订。；导入、导出、迁移和恢复自己的 memory 数据。；对敏感信息获得明确的保存、外发和保留解释。
Memory Product 必须使系统能够：；以统一语义表达 semantic、episodic、procedural、working memory。；把 memory 写入、recall、修订、忘记、导出和删除变成可审计事实。；将候选 memory 与 active memory 分开。；让每条 memory 具备 scope、owner、provenance、confidence、TTL、sensitivity 和 retention。；在跨 session、workspace、branch、run、turn、subagent 和 tenant 场景中强制隔离。；在 Context Compiler 中只注入经过 visibility、privacy、policy 和预算检查的 memory view。；在 compaction 前执行受控 memory flush，而不是默认保存全部聊天。；在 provider、embedding、index、queue 或 projector 故障时保留可恢复状态。；让评测能够检查记忆的准确性、必要性、用户控制和泄漏风险。
### 非目标
Memory Product 不负责：；代替 `SessionRepository` 保存完整 transcript。；代替 `ContextCompiler` 决定全部模型上下文。；代替 `MemoryStore` 实现具体向量、全文或 KV 存储。；通过 prompt 文本强制权限、删除、TTL 或 tenant 隔离。；把每条用户消息、每个工具结果或每个摘要自动变成长期 memory。；把模型推断的偏好直接当作用户确认的事实。；以自然语言摘要替代结构化任务状态、审批状态或外部 receipt。；将语义相似度当作授权证明、来源证明或事实正确性证明。；让 workspace 文件、RAG 内容、工具结果或 subagent 自行扩大 memory scope。；让“关闭 memory”只隐藏 UI，而不停止写入、recall、索引和派生缓存。；让导出文件成为永久公共 URL。；将删除主记录等同于删除 embedding、cache、artifact、backup 和 provider remote copy。
### 核心公式
```text
Memory Product Quality
  = User Control
  × Recall Utility
  × Provenance Quality
  × Scope Isolation
  × Privacy Safety
  × Durability
  × Explainability
  × Evaluation Coverage
```
任一乘项接近零，memory 越多不代表产品越好。
## 核心判断与术语
### 核心判断
```text
Memory 是可治理的跨任务资源。
Context 是一次模型请求的工作集。
Transcript 是 session/branch 上的语义历史。
Working State 是当前 run 的可恢复执行视图。
Artifact 是大内容和可交付内容的受控引用。
```
### 关键判断；Memory Product 不是聊天记录设置页。；Memory Product 不是 embedding 搜索页。；Memory Product 不是隐藏的 prompt 拼接器。；Memory Product 必须给用户一个可操作的控制面。；自动提取只能产生候选，不能自动证明用户同意。；用户确认是产品动作，不能只修改向量索引。；Recall 是一次经过权限和隐私检查的投影，不是直接返回原始记录。；Memory 的高相似度不等于高权威性。；新鲜度、来源和 scope 与相似度同等重要。；删除必须覆盖 active record、索引、缓存、派生 view 和后台任务。
### 术语；`Memory Product`：用户可见、可控、可解释的记忆产品服务和交互契约。；`Memory Store`：保存 canonical memory record、版本、索引、状态和查询端口的底层设施。；`Memory Candidate`：尚未成为 active memory 的提取或用户建议结果。；`Active Memory`：经过门槛、策略和必要确认后可被 recall 的记忆。；`Recall View`：面向当前 purpose、scope、provider 和 token budget 的记忆投影。；`Memory Revision`：对同一逻辑 memory 的新版本，不覆盖旧事实。；`Forget Tombstone`：记录删除、关闭或禁止 recall 的最小 durable 事实。；`Memory Flush`：在 compaction 或 run 边界前，把允许持久化的 working facts 转为候选或 active memory。；`Owner`：对 memory 的用户、组织、workspace、session 或系统责任主体。；`Provenance`：memory 来自用户、模型、工具、文件、人工确认或系统规则的来源链。；`Confidence`：对提取或验证结果的置信描述，不等于授权。；`TTL`：memory 可继续被 recall 或保留的时间边界。；`Retention`：包含 TTL、删除、legal hold、归档和派生对象的生命周期策略。
## Memory Product 与 Memory Store 的边界
### 产品层回答的问题；用户保存了什么。；为什么保存。；来自哪里。；谁可以看到。；何时会被使用。；何时过期。；如何修改、确认和删除。；关闭后哪些行为停止。；导出和删除是否完成。
### Store 层回答的问题；如何以版本化记录保存 memory。；如何按 scope、状态和类型查询。；如何维护全文、向量和结构化索引。；如何做 CAS、幂等、重建和迁移。；如何保留 tombstone、revision 和 lineage。；如何在 worker 崩溃后继续索引、删除或 compact。
### 明确禁止的耦合；Product UI 不直接读取向量数据库表。；`MemoryStore` 不决定用户是否同意长期保存。；`MemoryStore` 不自行调用模型提取候选。；`Memory Product` 不绕过 `PolicyEngine` 写入 secret。；`Memory Product` 不把 store 的相似度分数直接显示成事实置信度。；`Memory Product` 不把删除按钮映射为单一 SQL delete。；Store 查询结果必须经过 scope、purpose、sensitivity 和 egress 投影。
### 推荐端口
```text
Memory Product API
  -> Memory Governance
  -> Candidate Extractor / Confirmation Service
  -> Recall Planner
  -> Memory Store Port
  -> Index / Blob / Event / Queue Adapters
```
### 读写原则；Product 写入先创建 command，再由 governance 决定是否允许。；Store 写入必须带 `expectedVersion` 或稳定幂等键。；Recall 只能返回 `RecallView`，不能暴露未经投影的 raw record。；删除先写 durable command，再异步清理派生对象。；用户看到的“已保存”“已删除”“已关闭”必须对应 durable receipt。
## 职责边界与包布局
### 职责矩阵
| 模块 | 负责 | 不负责 |
|---|---|---|
| `MemoryProductService` | 用户 API、列表、搜索、编辑、确认、删除、关闭、解释 | 具体向量算法 |
| `MemoryGovernance` | purpose、scope、privacy、retention、阈值和决策 | UI 渲染 |
| `CandidateExtractor` | 从 turn、tool、working state 提取候选 | 直接激活长期 memory |
| `ConfirmationService` | 用户确认、拒绝、批量确认和过期 | 修改任意未授权记录 |
| `RecallPlanner` | 召回候选、排序、冲突标注和 projection | 改写 memory |
| `MemoryWriter` | 规范化、校验、版本化和写入 | 绕过 policy |
| `ContradictionResolver` | 冲突检测、修订建议和状态 | 代替用户做高风险事实决定 |
| `MemoryStore` | canonical record、索引、CAS、tombstone | 定义产品语义 |
| `MemoryIndexProjector` | 从事实构建检索视图 | 产生新的业务事实 |
| `ContextCompiler` | 将 recall view 放入 ContextPlan | 决定长期保存 |
| `SessionRepository` | transcript、checkpoint、compaction entry | 维护长期 memory 目录 |
| `PolicyEngine` | visibility、call、approval、execution、egress | 提取偏好 |
| `PrivacyRuntime` | classification、purpose、retention、DSAR | 生成用户文案 |
| `HostAdapter` | 展示卡片、控制命令、通知和交付 | 推断删除已完成 |
| `Harness` | 装配、预算、队列、恢复和事件路由 | 变成 memory 数据库 |
### 推荐包布局
```text
packages/memory-product/
  contracts.ts
  product-service.ts
  views.ts
  search.ts
  confirmation.ts
  settings.ts
  notifications.ts
  export.ts
  deletion.ts
  migration.ts
  explanations.ts
packages/memory-runtime/
  store.ts
  writer.ts
  recall.ts
  candidate.ts
  contradiction.ts
  revision.ts
  flush.ts
  retention.ts
  privacy.ts
  projections.ts
  index.ts
packages/memory-testkit/
  fake-store.ts
  scripted-extractor.ts
  deterministic-clock.ts
  recall-fixtures.ts
  deletion-oracle.ts
```
### 依赖方向
```text
Host/Product -> Memory Product ports
Memory Product -> Governance/Recall/Writer ports
Memory Runtime -> State/Event/Artifact/Policy/Privacy ports
Infrastructure -> Store/Index/Queue/Blob adapters
Context Runtime -> Recall View only
Agent Kernel -> Context port only
```
## 用户可见的产品能力
### Memory Center
产品应提供独立的 Memory Center 或等价设置入口，至少包含：；按类型分组的 active memory。；待确认候选 memory。；最近使用和最近修订的 memory。；已过期、被关闭和已删除的状态视图。；当前 session、workspace、user 和 organization scope 的筛选。；搜索框与结构化筛选。；单条详情、来源链和使用记录。；删除、编辑、确认、拒绝和关闭控制。；导出和迁移入口。；隐私和 retention 摘要。
### Search
搜索必须支持多种入口：；关键词搜索。；语义搜索。；类型过滤。；scope 过滤。；owner 过滤。；source/provenance 过滤。；active、candidate、expired、forgotten 状态过滤。；创建时间、验证时间和过期时间范围。；sensitivity 和 retention 过滤。
搜索结果必须显示：；memory 标题或安全摘要。；类型和 scope。；来源及其 trust/authority。；confidence 与 freshness。；TTL 和 retention 状态。；是否存在冲突。；是否在当前 session 被 recall。；可用操作。
### 查看详情
详情页不得只显示一段自然语言文本，还应显示：；canonical memory ID 和当前版本。；内容的结构化字段。；`provenance` 链。；原始来源的安全引用。；生成、确认、验证和修订时间。；confidence 的组成和解释。；scope、owner 和授权继承关系。；TTL、retention 和删除依赖。；当前版本与历史版本差异。；最近 recall 的 task purpose。；redaction、敏感度和 provider egress 限制。
### 编辑
编辑操作应区分：；修改内容。；修改类型。；收紧 scope。；延长或缩短 TTL。；修改是否可被 recall。；添加用户注释。；标记为不再适用。
编辑不得允许用户通过普通字段修改：；tenant owner。；audit lineage。；原始 provenance。；系统写入的安全状态。；其他用户或组织的 scope。；删除 tombstone。
### 关闭 Memory
关闭选项至少有：；关闭所有长期 memory 写入。；关闭自动候选提取。；关闭 semantic memory。；关闭 episodic memory。；关闭 procedural memory。；关闭跨 session recall。；仅保留当前 run 的 working memory。；停止后台 memory flush。
关闭必须改变运行时 policy snapshot，并写入 durable settings entry。
## 四类 Memory 的产品语义
### Semantic Memory
semantic memory 表达相对稳定、可复用的事实或偏好，例如：；用户明确声明的偏好。；用户确认的工作方式。；workspace 的稳定约定。；已验证的项目事实。
产品规则：；默认需要用户确认，或满足严格自动写入门槛。；需要清晰的来源和最近验证时间。；需要 conflict 状态，而不是静默覆盖。；对敏感个人属性采用更严格 ceiling。；recall 时显示为“根据已保存偏好”或等价解释。
### Episodic Memory
episodic memory 表达过去发生的、可能对未来任务有帮助的事件，例如：；某次任务已完成的决策。；某次部署失败的原因。；某次用户明确拒绝的方案。；某个 session 的重要上下文摘要。
产品规则：；必须有明确时间和事件来源。；默认 scope 较窄，不能自动推广为全局事实。；过期速度通常快于 semantic memory。；recall 时带事件时间和来源。；不能代替当前业务系统的真实状态查询。
### Procedural Memory
procedural memory 表达“如何做”的工作流偏好或步骤约定，例如：；用户要求先运行测试再编辑。；workspace 的验证命令和审批顺序。；用户偏好的输出格式。；经确认的项目操作流程。
产品规则：；不能升级为 system policy 或安全规则。；必须标记来源和适用范围。；运行时只作为 workflow hint，不是 authorization。；若与组织 policy 冲突，以高层 policy 为准并产生 diagnostic。；复杂 procedural memory 应指向 artifact 或版本化 workflow，而不是一段无版本文本。
### Working Memory
working memory 表达当前 run 的临时工作集，例如：；当前目标和未完成项。；最近工具结果摘要。；当前审批等待。；当前文件、测试和失败原因。；当前 memory candidate。
产品规则：；默认仅 run/turn scope。；默认不进入长期 Memory Center。；可在 compaction 前转为 candidate，但必须重新过门槛。；run 结束后按 retention 清理或转成 episodic candidate。；不得用 working memory 伪造已验证完成状态。
### 类型转换；working -> episodic：需要事件来源、时间和任务价值。；working -> semantic：需要稳定性、验证和确认。；episodic -> semantic：需要用户确认或多次独立验证。；procedural -> system policy：禁止自动转换。；semantic -> working：只能生成当前 run 的投影视图。
## Scope、Owner、Provenance、Confidence 与 TTL
### Scope 层级
```text
tenant
  -> organization
    -> user
      -> workspace
        -> project
          -> session
            -> branch
              -> run
                -> turn
                  -> subagent
```
推荐默认 scope：；working memory：run 或 turn。；episodic memory：session 或 workspace。；semantic memory：user、workspace 或 project。；procedural memory：workspace、project 或 user。；tenant scope 仅用于组织明确治理的共享知识。
### Owner
Owner 不是 `createdBy` 的别名。记录：；逻辑 owner。；创建主体。；代理主体。；delegatedFrom。；可编辑主体。；可删除主体。；可导出主体。；组织管理员是否可见。
### Provenance
Provenance 至少应包含：；source kind：user、model、tool、file、retrieval、human_review、system。；source reference：entry、artifact、tool call、event 或外部记录。；source version/hash。；extraction method/version。；observedAt 与 recordedAt。；是否被用户确认。；是否存在未解决推断。
### Confidence
confidence 应拆成：；extraction confidence。；source reliability。；freshness confidence。；confirmation state。；conflict penalty。；final recall confidence。
产品显示“置信度”时必须能解释组成，不得把单一模型概率伪装成事实保证。
### TTL 与验证
每种 memory type 应有默认 TTL，但必须允许 policy 收紧：；working：run end 或短 TTL。；episodic：天到月，按事件重要性决定。；semantic：较长 TTL，但需要 revalidation。；procedural：版本或 workspace 变更即失效。
TTL 到期后：；停止 active recall。；保留必要 tombstone 或 metadata。；可进入 revalidation candidate。；不得静默延长。
## 核心数据模型
### 标识与枚举
```typescript
type MemoryId = string;
type MemoryVersionId = string;
type CandidateId = string;
type RecallId = string;
type MemoryEntryId = string;
type MemoryType = "semantic" | "episodic" | "procedural" | "working";
type MemoryStatus = "candidate" | "active" | "conflicted" | "expired" | "disabled" | "forgotten" | "quarantined";
type ConfirmationState = "not_required" | "pending" | "confirmed" | "rejected" | "revoked";
```
### MemoryRecord
```typescript
interface MemoryRecord {
  id: MemoryId;
  versionId: MemoryVersionId;
  tenantId: string;
  owner: MemoryOwner;
  type: MemoryType;
  status: MemoryStatus;
  confirmation: ConfirmationState;
  content: MemoryContent;
  scope: MemoryScope;
  provenance: ProvenanceChain;
  confidence: ConfidenceBreakdown;
  sensitivity: Sensitivity;
  purpose: MemoryPurpose[];
  createdAt: string;
  updatedAt: string;
  lastVerifiedAt?: string;
  expiresAt?: string;
  retention: RetentionPolicy;
  revisionOf?: MemoryVersionId;
  conflictSetId?: string;
  sourceHash: string;
  recordHash: string;
}
```
### MemoryContent
```typescript
interface MemoryContent {
  summary: string;
  structured?: Record<string, unknown>;
  searchableText?: string;
  redactedFields?: string[];
  artifactRefs?: ArtifactRef[];
  language?: string;
  schemaVersion: string;
}
```
### Scope 与 Owner
```typescript
interface MemoryScope {
  level: "tenant" | "organization" | "user" | "workspace" | "project" | "session" | "branch" | "run" | "turn" | "subagent";
  tenantId: string;
  userId?: string;
  workspaceId?: string;
  projectId?: string;
  sessionId?: string;
  branchId?: string;
  runId?: string;
  subagentRunId?: string;
  scopeVersion: number;
}
interface MemoryOwner {
  principalId: string;
  ownerKind: "user" | "organization" | "workspace" | "project" | "session" | "run" | "system";
  editableBy: string[];
  deletableBy: string[];
}
```
### Provenance 与 Confidence
```typescript
interface ProvenanceChain {
  sourceKind: "user" | "model" | "tool" | "file" | "retrieval" | "human_review" | "system";
  sourceRefs: SourceRef[];
  extractionVersion?: string;
  observedAt: string;
  recordedAt: string;
  userConfirmed: boolean;
  inferenceNotes?: string[];
}
interface ConfidenceBreakdown {
  extraction: number;
  sourceReliability: number;
  freshness: number;
  confirmation: number;
  conflictPenalty: number;
  final: number;
  methodVersion: string;
}
```
### Candidate
```typescript
interface MemoryCandidate {
  id: CandidateId;
  proposed: MemoryRecordDraft;
  evidence: EvidenceRef[];
  reasons: CandidateReason[];
  automaticWriteEligible: boolean;
  confirmationRequired: boolean;
  expiresAt: string;
  state: "pending" | "accepted" | "rejected" | "expired" | "superseded";
  createdByRunId: string;
}
```
### RecallView
```typescript
interface RecallView {
  recallId: RecallId;
  memoryId: MemoryId;
  versionId: MemoryVersionId;
  type: MemoryType;
  text: string;
  structured?: Record<string, unknown>;
  scopeLabel: string;
  sourceLabel: string;
  confidence: number;
  freshness: number;
  conflict: "none" | "possible" | "confirmed";
  presentation: "inline" | "summary" | "artifact_ref";
  providerEgress: EgressDecision;
  expiresAt?: string;
}
```
## TypeScript 接口
### MemoryProductPort
```typescript
interface MemoryProductPort {
  list(input: MemoryListRequest): Promise<MemoryListView>;
  search(input: MemorySearchRequest): Promise<MemorySearchView>;
  get(input: MemoryGetRequest): Promise<MemoryDetailView>;
  edit(input: MemoryEditRequest): Promise<MemoryMutationReceipt>;
  confirm(input: MemoryConfirmRequest): Promise<MemoryMutationReceipt>;
  reject(input: MemoryRejectRequest): Promise<MemoryMutationReceipt>;
  forget(input: MemoryForgetRequest): Promise<MemoryDeletionReceipt>;
  setPolicy(input: MemoryPolicyUpdateRequest): Promise<MemoryPolicyReceipt>;
  export(input: MemoryExportRequest): Promise<ExportReceipt>;
  import(input: MemoryImportRequest): Promise<ImportReceipt>;
}
```
### MemoryStorePort
```typescript
interface MemoryStorePort {
  get(scope: ScopeRef, id: MemoryId, version?: MemoryVersionId): Promise<MemoryRecord | undefined>;
  list(scope: ScopeRef, query: MemoryQuery): Promise<MemoryRecord[]>;
  append(input: MemoryAppendInput, expectedVersion?: number): Promise<MemoryAppendReceipt>;
  revise(input: MemoryRevisionInput): Promise<MemoryAppendReceipt>;
  tombstone(input: MemoryForgetInput): Promise<MemoryDeletionReceipt>;
  search(input: MemorySearchInput): Promise<MemorySearchHit[]>;
  rebuildIndex(input: IndexRebuildRequest): Promise<JobReceipt>;
  inspect(id: MemoryId): Promise<MemoryStorageView>;
}
```
### RecallPort
```typescript
interface RecallPort {
  plan(input: RecallRequest): Promise<RecallPlan>;
  execute(plan: RecallPlan): Promise<RecallResult>;
  explain(recallId: RecallId, audience: ExplanationAudience): Promise<RecallExplanation>;
}
```
### Policy
```typescript
interface MemoryPolicy {
  enabled: boolean;
  allowedTypes: MemoryType[];
  automaticWrite: "disabled" | "strict" | "reviewed" | "allowed";
  requireConfirmationFor: MemoryType[];
  maxSensitivity: Sensitivity;
  allowedScopes: MemoryScopeLevel[];
  allowCrossSessionRecall: boolean;
  allowWorkspaceRecall: boolean;
  allowSubagentRecall: boolean;
  defaultTtlMs: Partial<Record<MemoryType, number>>;
  retention: RetentionPolicy;
  redactionProfile: string;
}
```
### Control Commands
```typescript
interface MemoryControlCommand {
  commandId: string;
  tenantId: string;
  principal: PrincipalRef;
  memoryId?: MemoryId;
  candidateId?: CandidateId;
  kind: "confirm" | "reject" | "edit" | "forget" | "disable" | "enable" | "export" | "import";
  payload: unknown;
  expectedVersion?: number;
  idempotencyKey: string;
}
```
## 候选记忆与用户确认
### Candidate 生成入口
候选只能来自明确的受控入口：；用户明确说“记住”“以后都这样”“保存这个偏好”。；turn 完成后的受控提取任务。；tool 返回已验证的稳定业务事实。；workspace 配置经过 trust gate 和 policy 审核后的稳定规则。；用户在 Memory Center 手工创建。；compaction 的 memory flush 产生的结构化候选。
以下内容默认不得直接成为 active memory：；模型自由推断的人格、健康、财务或敏感属性。；未验证的 RAG 内容。；单次情绪或临时偏好。；工具错误、日志噪声和中间推理。；其他 subagent 未经父级转交的结论。；provider metadata 或安全提示中的用户事实。
### Candidate 卡片
候选卡片应显示：；“建议保存什么”。；memory type。；建议 scope。；来源和证据。；为什么未来可能有用。；预计保存多久。；可能被哪些任务 recall。；敏感度和隐私影响。；接受、编辑、拒绝和永久关闭此类建议。
### 确认语义；`confirm` 将 candidate 转为 active 或进入 conflict resolution。；`reject` 产生 durable rejection，不删除原始 session 事实。；`edit_then_confirm` 以用户编辑后的内容创建新版本。；`confirm_scope_narrower` 只能收紧 scope。；`confirm_ttl_shorter` 只能缩短 TTL，除非另有明确二次确认。；确认必须绑定 candidate hash，防止批准后内容被替换。；过期 candidate 不能通过旧 UI 请求直接确认。
### 批量确认
批量操作必须：；展示数量、类型和 scope 分布。；拒绝包含 secret、regulated 或未分类敏感数据的隐式批量升级。；为每条 candidate 保留独立确认结果。；允许部分成功。；对冲突 candidate 单独进入人工处理。
## 自动写入门槛
### 默认原则
```text
自动写入不是默认能力。
默认先 candidate，再确认。
只有低风险、稳定、可验证、可删除的内容才可能自动 active。
```
### 严格门槛
自动 active 至少同时满足：；用户或 trusted tool 明确表达了持久化意图。；memory type 在 policy 的 automatic allowlist 中。；sensitivity 不超过长期 memory ceiling。；scope 不超出用户或 workspace 明确范围。；provenance 可追溯且不是单纯模型猜测。；结构化字段通过 schema 和业务校验。；不存在未解决冲突。；TTL 明确且不为无限期。；用户可在产品中查看和删除。；写入和索引都能产生 durable receipt。；目标 provider 不需要额外发送原文才可完成写入。
### 建议分级；`disabled`：只保留 working memory。；`candidate_only`：所有长期 memory 需要确认。；`strict_auto`：仅明确用户指令和低敏感度 procedural/semantic。；`reviewed_auto`：组织审核规则后允许指定来源自动写入。；`allowed`：仍受 privacy、scope、TTL 和安全上限约束，不代表无条件写入。
### 不可绕过条件
以下任一条件成立，必须 candidate 或 deny：；source 是模型单次推断。；scope 试图从 session 升级到 user/workspace。；content 可能包含 secret、regulated 或高风险 PII。；provenance 无法定位到原始 entry、tool receipt 或 artifact。；contradiction resolver 无法判断关系。；user memory policy 已关闭。；DLP、分类、索引或审计不可用。；即将发送给 provider 的 extraction prompt 不符合 egress policy。
## Recall 控制与上下文投影
### Recall 不是全文检索
Recall 必须按顺序执行：
```text
receive task purpose
  -> resolve tenant/user/workspace/session scope
  -> load frozen memory policy
  -> discover eligible records
  -> ownership and status filter
  -> privacy/purpose/egress filter
  -> type and freshness filter
  -> semantic/lexical ranking
  -> deduplicate and conflict annotate
  -> token budget allocation
  -> build RecallView
  -> ContextPlan projection
  -> emit recall explanation
```
### 排序因素
```text
recall score
  = relevance
  × scope fit
  × authority
  × freshness
  × provenance quality
  × confirmation weight
  × task-stage weight
  - conflict penalty
  - sensitivity penalty
  - redundancy penalty
  - token cost
```
不要只按 embedding cosine distance 排序。
### Recall 过滤
默认排除：；expired、forgotten、disabled、quarantined。；与当前 tenant、workspace 或 session 不匹配。；当前 purpose 不允许使用的 memory。；provider egress 不允许发送的 memory。；与当前任务明显冲突且未解决的旧版本。；已被用户明确标记为不相关的记录。；child scope 未被父 assignment 授予的记录。
### 用户控制
产品应提供：；本次任务不使用 memory。；仅使用当前 session memory。；仅使用已确认 memory。；仅使用某一类型。；查看本次 recall 清单。；从本次 recall 中移除一条并继续。；关闭未来跨 session recall。
### ContextPlan 记录
每次 recall 应记录：；recallId、policyVersion、scopeVersion。；candidate IDs、selected IDs、dropped IDs。；每条 memory 的版本、view hash 和来源。；被过滤的原因码。；token/byte budget。；redaction、summary 和 artifact projection。；provider target 和 egress decision。；recall latency、index version 和 freshness。
## 冲突、修订与版本
### 冲突类型；同一字段的新旧值冲突。；不同 scope 的规则冲突。；用户明确陈述与工具事实冲突。；procedural memory 与 system/organization policy 冲突。；同一事件的不同来源冲突。；当前 workspace 与旧 workspace 的路径或命令冲突。
### 冲突分级；`compatible_update`：新值补充旧值。；`supersedes`：新值明确替代旧值。；`coexists`：作用域或条件不同，可并存。；`needs_review`：无法自动判断。；`policy_conflict`：memory 只能降级为 data，不能覆盖 policy。；`unsafe_conflict`：涉及敏感或高风险事实，默认不 recall。
### 修订原则；不覆盖旧版本事实。；以新 `MemoryRevision` 表达变更。；保留 revisionOf、原因、操作者和证据。；对用户编辑保留 before/after 的安全 diff。；冲突解决后更新 conflict set，而不是删除旧证据。；重新计算 confidence、freshness 和 TTL。；修订可能触发 recall cache 和 embedding 的失效。
### 用户体验
冲突卡片应说明：；两个值各自来源。；适用的 scope 和时间。；为什么系统不能自动选择。；建议选“保留旧值”“使用新值”“同时保留条件”“删除两者”。；是否会影响未来任务。
### CAS 与幂等；编辑和确认必须带 expectedVersion。；同一 idempotency key 重放返回原 receipt。；版本冲突不能静默覆盖其他客户端修改。；删除与修订并发时以 durable sequence 和 tombstone 规则决定。
## 跨 Session、Workspace 与 Subagent 隔离
### 默认隔离；session memory 不自动成为 user memory。；workspace memory 不自动跨 workspace 共享。；branch memory 默认继承只读 ancestor view，不共享可变 active record。；run memory 默认只属于当前 run。；subagent 默认没有父级全部 memory。；tenant memory 只能由组织策略和明确 owner 管理。
### Scope 交集
```text
child recall scope
  = requested scope
  ∩ parent active scope
  ∩ assignment resources
  ∩ tenant policy
  ∩ workspace policy
  ∩ privacy/egress boundary
```
### Subagent 规则；父级只传递最小的 `MemoryRecallPackage`。；package 包含 memory ID、view hash、用途和 expiry，不包含未授权 raw record。；child 产生的 memory candidate 默认归 child/run scope。；child 不得直接写 user/workspace active memory。；child 的候选必须通过父级 fan-in、schema、policy 和必要确认。；child event 与 parent transcript 分离，但保留 parentRunId 和 evidence refs。；父取消时停止 child 的 memory write、index 和 export job。
### Workspace 变化
以下事件使 workspace memory view 失效：；root identity 变化。；branch 或 commit 变化。；project trust 撤销。；policy、toolset 或 config hash 变化。；文件或配置 hash 变化。；workspace 被删除、迁移或换租户。
## Memory Flush 与 Compaction
### Memory Flush 的目的
Memory flush 只负责在上下文压缩或 run 边界前识别“是否存在值得进入未来上下文的候选”，不负责无条件保存历史。
### Flush 输入；当前 working state。；已完成的 turn 和 durable tool result。；当前任务目标、约束和验收。；已有 memory 的冲突和版本。；用户 memory policy。；privacy、retention 和 scope snapshot。；将被 compaction 覆盖的 entry range。
### Flush 输出
```typescript
interface MemoryFlushResult {
  coveredFrom: EntryId;
  coveredTo: EntryId;
  candidates: MemoryCandidate[];
  retainedWorkingState: StructuredTaskState;
  droppedReasons: DroppedMemoryReason[];
  policySnapshotId: string;
  sourceHash: string;
}
```
### Compaction 顺序
```text
capture structured task state
  -> run memory flush
  -> validate candidate privacy and scope
  -> persist candidate entries
  -> build compaction summary
  -> append CompactionEntry
  -> invalidate covered recall cache
  -> rebuild ContextPlan
```
### 失败处理；flush 失败不应阻止保存原始 transcript 和 compaction checkpoint。；candidate 写入失败必须记录 `memory_flush_partial`。；compaction 成功但 candidate 不确定时，不得声称“已记住”。；后台摘要使用 sourceHash，原文变化后不能直接复用。；flush 不得把 approval、unknown outcome、删除请求或 retention hold 丢入摘要。
## 与 Model、Prompt、Context、Tool、State、Policy、Harness 集成
### Model Runtime；Model Runtime 只接收经过 EgressSnapshot 的 RecallView。；extraction model 与 task model 的调用必须区分 purpose、usage 和 cost。；provider fallback 需要重新检查 memory egress。；provider request 不应直接携带 MemoryRecord 的内部 owner 和删除字段。；provider raw response 如产生候选，必须回到 CandidateExtractor 验证。
### Prompt
Prompt 只解释：；当前 memory 是否开启。；当前可用 memory 类型。；这次收到的是已确认 memory、候选摘要还是 working state。；memory 可能过期、冲突或不准确。；模型不能自行声明“已保存”。；用户明确要求记忆时应调用 memory command 或返回候选。
Prompt 不负责：；授权 recall。；选择 tenant/workspace。；通过文字删除 memory。；强制 TTL 和 retention。；防止模型把 retrieved memory 当 system instruction。
### Context
Memory 是 ContextResource 的一种：；kind 为 `memory`。；带 source、scope、trust、authority、freshness、sensitivity 和 retention。；先 privacy 过滤，再 relevance 排序。；通过 `RecallView` 投影，不直接插入 raw record。；必须记录 selected、summarized、offloaded、dropped。；与 compaction summary 和 transcript 去重。
### Tool
可提供受策略控制的工具：；`memory_search`：搜索可见 memory。；`memory_get`：读取详情或安全 view。；`memory_suggest`：创建 candidate。；`memory_confirm`：仅在用户明确授权 token 下执行。；`memory_forget`：创建删除命令。；`memory_policy`：读取或请求当前设置。
工具规则：；工具名称可见不代表动作已授权。；模型不能传入任意 tenant、owner 或 scope。；`memory_confirm` 和 `memory_forget` 必须经过 approval/host control 或等价证明。；工具结果只返回安全摘要和 receipt。
### State；Session entries 保存 memory candidate、confirmation、revision、forget、policy 和 recall facts。；WorkingState 保存当前候选、recall plan 和 pending user action。；Checkpoint 保存未完成的索引、删除、导出和确认任务。；Projector 生成 Memory Center、Recall History、Privacy View 和 Recovery View。；Transcript 不复制完整 MemoryRecord，只引用 memory ID/version/view hash。
### Policy 与 Privacy
```text
Visibility -> 模型是否看见 memory 能力
Call -> 当前 memory action 是否可提出
Approval -> 是否需要用户确认保存/删除/跨 scope
Execution -> Store/index/queue 在何处运行
Egress -> 哪个 memory view 可送往 provider/host
```
### Harness
Harness 在 bootstrap 时冻结：；tenant、user、workspace 和 session scope。；memory policy 和 feature flags。；privacy/consent/legal-basis snapshot。；index version、retention 和 deletion capability。；当前 model/provider/egress。；memory budget、recall budget 和 background queue capacity。
Harness 在 run 中监督：；recall、candidate、confirmation、flush、index 和 deletion task。；取消传播和 worker lease。；durable event、checkpoint 和 terminal settlement。；UI delivery 与通知。
## 生命周期与状态机
### MemoryRecord 状态机
```text
candidate
  -> active
  -> conflicted
  -> expired
  -> disabled
  -> forgotten
candidate -> rejected | superseded | expired
active -> revised | conflicted | disabled | forgotten | expired
conflicted -> active | revised | disabled | forgotten
expired -> revalidated | forgotten
```
### Candidate 状态机
```text
created
  -> pending_confirmation
  -> accepted
  -> rejected
  -> expired
  -> superseded
```
### Recall 状态机
```text
requested
  -> scope_checked
  -> policy_checked
  -> retrieving
  -> ranked
  -> projected
  -> delivered
  -> completed
requested/retrieving/ranked -> denied
requested/retrieving -> cancelled
retrieving -> partial
```
### Mutation 状态机
```text
requested
  -> validated
  -> awaiting_approval
  -> committed
  -> indexed
  -> notified
  -> settled
validated -> rejected
committed -> index_pending
committed -> unknown
```
### 删除状态机
```text
forget_requested
  -> authorization_checked
  -> tombstone_committed
  -> recall_disabled
  -> index_cleanup_pending
  -> cache_cleanup_pending
  -> derived_cleanup_pending
  -> deletion_verified
  -> settled
```
删除若无法完成所有派生清理，必须显示 `partial` 或 `blocked`，不能显示已删除。
## 决策流程
### 用户明确要求记住
```text
用户请求
  -> 解析 memory intent
  -> 规范化 type/scope/content
  -> DLP 与敏感度分类
  -> 检查 memory policy
  -> 生成 candidate
  -> 判断是否需要 confirmation
  -> 展示确认卡片或自动写入
  -> 写入 active/revision
  -> 建立索引
  -> 发送通知
  -> 返回 receipt 与解释
```
### 自动候选
```text
TurnCompleted
  -> 选择允许提取的字段
  -> 提取 candidate
  -> 限制 scope
  -> 验证 provenance
  -> 评估稳定性与未来价值
  -> 检查 conflict
  -> 评估 privacy/retention
  -> candidate store
  -> 通知用户
```
### Recall
```text
任务输入
  -> purpose/context scope
  -> memory policy snapshot
  -> candidate query
  -> ownership/status/privacy filter
  -> relevance/freshness/authority ranking
  -> conflict and redundancy resolution
  -> token/egress projection
  -> ContextPlan
  -> ModelRequest
```
### Forget
```text
用户点击删除
  -> authentication and scope check
  -> action hash
  -> approval if required
  -> append forget command
  -> write tombstone
  -> invalidate recall/cache
  -> queue index/derived cleanup
  -> verify references
  -> emit deletion receipt
```
## 通知、解释与用户信任
### 通知类型；`memory_candidate_created`。；`memory_confirmed`。；`memory_rejected`。；`memory_revised`。；`memory_conflict_detected`。；`memory_expiring`。；`memory_expired`。；`memory_recalled`。；`memory_forget_started`。；`memory_deleted`。；`memory_delete_partial`。；`memory_disabled`。；`memory_export_ready`。；`memory_import_partial`。
### 解释的三种受众
用户解释：；保存了什么。；来源是什么。；用于什么。；保存多久。；如何关闭或删除。
Operator 解释：；policy、scope、decision ID。；index、queue、worker 和 retry 状态。；redaction、egress 和版本。
Audit 解释：；最小必要治理事实。；action hash、principal、time、policy version。；不复制完整敏感内容。
### Recall 解释
在用户可见 UI 中可显示：；“本次使用了 2 条已确认偏好”。；“1 条旧记忆因过期未使用”。；“1 条 workspace 记忆因 scope 不匹配未使用”。；“本次只向 provider 发送了脱敏摘要”。
不得显示：；其他租户存在但被拒绝的 memory。；完整 policy 内部规则。；hidden reasoning 或 secret。
## 导入、导出、迁移与兼容
### 导出范围
导出应支持：；active memory。；candidate memory。；revision history。；provenance 和 evidence refs。；scope、owner、TTL、retention。；policy settings。；deletion tombstone 的最小证明。
默认不导出：；provider secret。；tokenization map。；内部索引结构。；全部 session transcript。；受 legal hold 或其他主体权限限制的数据。
### Export Package
```typescript
interface MemoryExportPackage {
  packageId: string;
  schemaVersion: string;
  tenantId: string;
  subject: PrincipalRef;
  memories: MemoryExportRecord[];
  policies: MemoryPolicySnapshot[];
  lineage: ExportLineage[];
  redactionProfile: string;
  createdAt: string;
  expiresAt: string;
  integrityHash: string;
}
```
导出文件必须：；短 TTL。；受控下载。；带访问审计。；可撤销。；不能通过不可信 URL 共享。
### 导入
导入流程：
```text
receive package
  -> authenticate owner
  -> verify signature/hash
  -> parse schema
  -> classify and redact
  -> map source scopes
  -> validate provenance
  -> detect conflicts
  -> create candidates or staged records
  -> user preview
  -> commit selected records
  -> index
```
导入不得默认 active 全部外部 memory。
### Schema 迁移；canonical schema 与 provider/import schema 分开。；minor 版本可兼容读取。；major 版本使用 upcaster 或显式 migration。；migration 先 dry-run，再 dual-read 或 staged write。；迁移失败保留旧版本和 migration receipt。；不修改历史 audit/event 事实。；embedding/index 可异步重建，但 recall 在不完整时必须显示 degraded。
### 跨产品迁移；将 scope、owner 和 provenance 映射为最小权限。；无法映射的 scope 降级到 candidate 或 quarantine。；不把原系统的“confirmed”盲信为当前系统 confirmed。；记录 source product、source version、mapping rules 和 operator/user。
## 故障恢复与未知结果
### 失败分类；extraction failed：不创建 active memory。；candidate write failed：保留 session evidence，允许重新提取。；confirmation timeout：candidate 过期，不自动接受。；store unavailable：暂停写入，recall 可按 policy 使用已验证缓存。；index lag：record 已 durable，recall 标记可能不完整。；delete unknown：禁止继续 recall，等待清理验证。；export interrupted：保留 job checkpoint，不重复泄露内容。；provider extraction unknown：查询 provider request/remote object 状态，不盲目重发敏感原文。；worker crash：依据 lease、checkpoint、idempotency 和 side-effect receipt 恢复。
### RecoveryCoordinator
```typescript
interface MemoryRecoveryCoordinator {
  listCandidates(scope: ScopeRef): Promise<RecoveryCandidate[]>;
  inspect(candidate: RecoveryCandidate): Promise<RecoveryInspection>;
  resume(input: RecoveryResumeRequest): Promise<JobReceipt>;
  quarantine(input: RecoveryQuarantineRequest): Promise<void>;
  settleUnknown(input: SettleUnknownRequest): Promise<void>;
}
```
### 恢复不变量；未知的写入不自动重放。；删除未知时先停止 recall，再查询清理状态。；active record 已写但 index 未写，不能报告“未保存”。；index 已写但 durable event 未写，必须进入一致性修复队列。；UI 断线不等于取消后台 memory job。；取消后仍完成的事实按 durable sequence 保留。
## 安全、隐私、Retention 与 DSAR
### 数据分类
Memory 默认继承来源敏感度，不因摘要而自动降级：
```text
public | internal | confidential | secret | regulated
```
secret、regulated、高风险 PII 默认：；不写长期 memory。；不进入普通 trace。；不进入 subagent。；不发送给不允许的 provider。；需要更强的确认和 retention policy。
### Purpose Limitation
memory persistence 与 memory recall 是两个不同 purpose：；`memory_persistence`：保存未来可复用内容。；`memory_recall`：为当前 task 提供上下文。；`memory_export`：生成用户数据包。；`memory_delete`：执行主体请求。；`memory_evaluation`：脱敏评测。
当前 task 的允许处理不自动授权长期保存。
### DSAR
DSAR 需要覆盖：；active、candidate、revision、tombstone。；全文、向量、embedding、rerank cache。；recall history 和 ContextPlan 引用。；artifact、export package 和 backup。；provider remote object 或删除能力限制。；subagent 和 background job 派生记录。；audit 中的最小治理事实。
删除流程应产生：；request ID。；subject scope。；发现对象数量。；已删除对象与 blocked 依赖。；provider/delete receipt。；retention/legal hold 解释。；完成时间与 verifier。
### 关闭与删除的区别；关闭：停止新写入、recall 或某类型行为。；删除：移除记录及允许移除的派生对象。；过期：自动停止 active 使用，但不一定立即删除所有审计事实。；撤回确认：改变 confirmation state，不等于历史不存在。
### 访问控制；用户只能看到自己有权访问的 scope。；workspace memory 需要 workspace membership。；organization memory 需要角色和 purpose。；operator 只能看最小诊断视图。；subagent 通过显式 assignment 授权。；host adapter 不得以客户端传来的 owner 替代服务器 scope。
## 多租户、权限与执行隔离
### Tenant 不变量；`memory.tenantId` 必须等于 session、run、artifact、event 和 queue job 的 tenant。；cache key 必须包含 tenant、scope hash、policy version 和 record version。；worker lease 必须带 fencing token。；provider fallback 不能跨越 tenant egress boundary。；organization memory 不能被普通 user scope 修改。；delete/export job 不得读取其他 tenant。
### 五层决策
```text
Visibility: 模型是否看到 memory 工具
Call: 当前 memory action 是否可提出
Approval: 是否需要用户确认
Execution: Store/index/queue 使用何种 backend
Egress: 哪个 view 可进入 provider/host
```
### Workspace 隔离；workspace memory 绑定 workspace root identity 和 config hash。；project trust revoke 后暂停项目 memory recall。；branch 变化可使 procedural memory 失效。；workspace 删除触发 memory、artifact、cache 和 index cleanup。；不能用路径字符串作为 workspace ownership 证明。
### Provider Egress
```text
MemoryRecord
  -> classification
  -> purpose
  -> scope
  -> provider/region policy
  -> redaction/summary
  -> RecallView
  -> ModelRequest
```
provider 只能看到允许的 view；不得看到 deletion token、owner internals 或 tokenization map。
## 可观测性、指标与 SLO
### Durable 事件
建议事件：；`memory.candidate.created`。；`memory.candidate.confirmed`。；`memory.candidate.rejected`。；`memory.created`。；`memory.revised`。；`memory.conflict.detected`。；`memory.recalled`。；`memory.recall.filtered`。；`memory.forget.requested`。；`memory.forget.tombstoned`。；`memory.index.completed`。；`memory.delete.completed`。；`memory.export.completed`。；`memory.policy.changed`。；`memory.flush.completed`。；`memory.recovery.required`。
### Ephemeral 事件；recall progress。；extraction token delta。；index progress。；UI spinner。；heartbeat。
### Trace 关联
每次 memory 操作至少关联：
```text
trace_id
session_id
run_id
turn_id
memory_id
candidate_id
recall_id
policy_version
scope_hash
index_version
provider/model/api_family
artifact_ref
idempotency_key_hash
```
### 产品指标；memory candidate 展示率。；candidate 确认率。；candidate 拒绝率。；用户编辑率。；用户主动创建率。；forget/delete 成功率。；memory policy 关闭率。；recall 使用率。；recall 后用户纠正率。；recall 后任务成功率。；冲突发现率与解决时延。；过期 memory 命中率。；memory leakage 负向案例率。；每次成功任务的 memory 成本。；DSAR 完成率和逾期率。
### 质量指标；precision@k。；recall@k。；stale recall rate。；wrong-scope recall rate。；unconfirmed recall rate。；provenance coverage。；deletion propagation completeness。；index freshness lag。；candidate false-positive rate。；user trust calibration。
### SLO 示例；用户确认后的 durable commit 可查询率。；forget 请求进入 tombstone 的延迟。；recall plan 成功率。；index lag 的 P95。；deletion propagation 完成率。；cross-tenant recall 违规数必须为零。；未授权 memory provider egress 数必须为零。
## 评测与实验策略
### 评测原则
评测不能只问“模型回答是否更好”，还要检查：；是否创建了不该创建的 memory。；是否漏掉用户明确要求保存的内容。；是否在 recall 时越过 scope。；是否向 provider 发送了禁止内容。；是否能解释来源、TTL 和用户控制。；删除后是否仍出现在 recall、cache、embedding 或 artifact。；compaction 后是否保留关键状态。；subagent 是否越权继承 memory。
### Scenario 类型；明确“记住我的偏好”并确认。；明确“不要记住这件事”。；模型推断敏感属性。；同一偏好在两个 session 中冲突。；workspace procedural memory 与组织 policy 冲突。；memory 过期后任务 recall。；删除后立即 recall。；provider egress 只允许 summary。；subagent 请求父级 memory。；index 写入成功但 event commit 失败。；worker crash 发生在 tombstone 后。；import 包含不可信 scope。
### Oracles
确定性 oracle 优先判断：；状态机。；scope 和 owner。；policy decision。；event sequence。；active/candidate 状态。；TTL 和 deletion propagation。；provider request 是否含禁用字段。；side-effect ledger。
LLM judge 只用于：；语义相关性。；候选是否值得未来复用。；解释是否清晰。；用户可理解性。
LLM judge 不得判断：；是否已删除。；是否越权。；是否真的写入。；是否发生跨租户泄漏。；是否满足 TTL、SLO 或幂等。
### Ablation
比较以下变体：；无 recall。；仅 semantic recall。；仅 confirmed memory。；包含 candidate 但不 active。；有冲突过滤与无冲突过滤。；有 freshness weighting 与无 weighting。；有用户解释与无解释。；不同 TTL、scope 和 token budget。
## 测试策略
### Unit；schema validation。；candidate threshold。；confidence calculation。；TTL calculation。；scope intersection。；conflict classification。；recall scoring。；redaction projection。；export/import upcaster。；policy merge。
### Component；fake MemoryStore。；fake index。；scripted extractor。；deterministic clock。；deterministic ID。；fake approval。；fake provider egress。；fake queue and lease。；deletion oracle。
### Integration；Session/Event/Memory Store 一致性。；ContextPlan 与 RecallView 集成。；compaction 与 memory flush。；Host card 与 durable receipt。；subagent capability intersection。；provider fallback 与 egress。；artifact lineage 与 DSAR。
### Fault Injection；store timeout。；index lag。；queue duplicate delivery。；worker crash。；CAS conflict。；provider 429/5xx/断流。；redaction failure。；key broker unavailable。；deletion partial failure。；host disconnect。；stale approval。
### Security Matrix；prompt injection 诱导写 memory。；tool 参数伪造 tenant。；cross-session recall。；cross-workspace recall。；subagent 越权。；cache key 丢 tenant。；provider request 泄漏 raw memory。；export URL 重放。；delete 后 embedding 仍命中。；expired memory 被召回。
### Replay
使用 `EventRecorder`、`ReplayRunner` 和 `CrashInjector` 验证：；同一 durable entries 可重建同一 Memory Center view。；projector 重放幂等。；tombstone 不会被旧 index resurrect。；migration 后旧 record 仍可解释。；live re-execution 与 recorded replay 明确区分。
## 反模式与审查规则
1. 把每条聊天消息写入长期 memory。
2. 把 embedding 命中直接当作用户偏好。
3. 让模型返回“我已经记住了”就更新 UI。
4. 只有 `enabled: boolean`，没有按类型、scope 和 purpose 的 policy。
5. candidate 没有确认、过期和拒绝状态。
6. memory record 没有 provenance、confidence 和 source hash。
7. semantic memory 覆盖组织 policy。
8. procedural memory 被当作 permission。
9. session memory 静默升级为 user memory。
10. subagent 自动继承父级全部 memory。
11. recall 只按向量相似度排序。
12. 过期 memory 仍可被索引命中。
13. 删除只删主表，不删 embedding/cache/preview。
14. 关闭 memory 只隐藏 UI，不停写入和 recall。
15. 导出包是永久公共链接。
16. 将 tokenization map 放入 prompt 或普通日志。
17. compaction 直接丢失 memory candidate 和 deletion request。
18. index 成功但没有 durable event。
19. 未知删除结果自动重试危险操作。
20. 用 trace 或最终答案证明 memory 已保存。
21. 不记录 recall 的过滤原因。
22. 不区分 user-confirmed 与 model-inferred。
23. 用单一总分掩盖 wrong-scope recall。
24. 让低层 workspace 配置放宽 tenant memory policy。
25. 将 provider remote file 当作本地 memory 已删除。
26. 迁移时默认把所有外部记录标为 confirmed。
27. 将高敏感数据摘要后自动降级为 public。
28. 用户拒绝一次 candidate 后仍重复通知同一 candidate。
29. 通过定时任务无限延长 TTL。
30. 把 Memory Product 误实现为“给 while loop 加几个 if”。
## 实施清单
### 第一阶段：最小可控产品；[ ] 定义四类 memory 的 canonical schema。；[ ] 实现 Memory Product 与 Memory Store port。；[ ] 实现 active/candidate/forgotten 状态。；[ ] 实现列表、详情、搜索、确认、拒绝、编辑和删除。；[ ] 实现 memory policy 和关闭开关。；[ ] 实现 scope、owner、provenance、confidence、TTL。；[ ] 实现 Memory Center 的 durable receipt。；[ ] 实现 fake store、event recorder 和 deterministic clock。
### 第二阶段：Recall 与 Harness；[ ] 实现 RecallPlanner 和 RecallView。；[ ] 接入 ContextCompiler 的 memory resource。；[ ] 接入 Prompt Compiler 的 memory 状态说明。；[ ] 接入 Model Runtime 的 egress view。；[ ] 接入 State/Session 的 candidate、revision 和 recall entry。；[ ] 接入 Policy、Privacy 和 Artifact ports。；[ ] 实现 recall explanation 和过滤诊断。；[ ] 实现 working memory 与 compaction flush。
### 第三阶段：一致性与隔离；[ ] 实现 CAS、幂等和 conflict resolver。；[ ] 实现 index projector 与 lag/degraded 状态。；[ ] 实现跨 session/workspace/subagent scope intersection。；[ ] 实现 queue、lease、checkpoint 和 recovery。；[ ] 实现 tombstone、cache invalidation 和派生清理。；[ ] 实现 multi-tenant storage partition。；[ ] 实现 provider egress 和 residency re-check。；[ ] 实现 Session Replay 的 memory reconstruction。
### 第四阶段：隐私与运营；[ ] 实现 retention、DSAR、导入、导出和迁移。；[ ] 实现 DLP、secret/PII/regulated 分类。；[ ] 实现 delete receipt、provider delete binding 和 limitation report。；[ ] 实现审计、trace、指标、SLO 和告警。；[ ] 实现 privacy incident containment。；[ ] 实现数据集版本、online feedback 和回归门禁。；[ ] 进行备份恢复与灾备演练。
### 发布门禁；[ ] 未确认 memory 不会进入默认 active recall。；[ ] memory 关闭后写入和 recall 都停止。；[ ] cross-tenant recall 测试为零违规。；[ ] secret/regulated memory 不进入 provider request。；[ ] 删除后 active、index、cache 和 view 均不可 recall。；[ ] compaction 不丢失 candidate、approval、unknown outcome 和 retention hold。；[ ] worker crash 不重复未知副作用。；[ ] host 展示状态引用 durable receipt。；[ ] 迁移和导出有 schema、TTL、访问审计和回滚路径。
## 五个参考项目的启发来源
### Pi；headless agent loop 与 harness 分离，说明 Memory Product 不应塞进 Kernel。；session tree 和可恢复 compaction 说明 memory flush 必须拥有切点、source hash 和恢复语义。；CLI、TUI、RPC 共用 runtime，说明 Memory Center 和 Host Adapter 应消费同一 canonical event。；session 事实与 provider message 分离，支持 memory record 独立于 transcript。；默认执行隔离较弱，提醒 memory egress 不能只依赖产品提示。
### Grok Build；actor 与状态所有权说明 memory write、conflict 和 index projector 可串行化。；permission decision、folder trust、sandbox 与路径锁说明 memory scope 不等于执行权限。；并行工具和资源锁经验可用于 memory flush、index 和删除任务的并发协调。；上下文修剪可能丢失旧工具结果，说明 memory 不能替代结构化 working state。；对失败和状态边界的显式建模可用于 unknown deletion 和 recovery。
### OpenCode；session/message/part 数据模型说明用户看到的是 projection，不是底层表。；durable event/projector 说明 Memory Center、Recall History 和 Privacy View 应可重建。；client/server 分离说明 Memory Product API 不应绑定单一 UI。；permission、snapshot、patch/revert 说明 memory edit/delete 需要可审查变更和版本。；状态模型迁移复杂，提醒 memory schema 和 index 迁移必须有兼容窗口。
### Claude Code；memory、skills、hooks、subagents 与任务工作流的产品化说明用户需要显式的记忆控制体验。；记忆与项目规则同时存在，说明 procedural memory 不能自动拥有 system/policy authority。；subagent 产品能力说明 child memory 必须有独立上下文、预算和结果契约。；用户可见的工作流控制说明确认、关闭和删除不能隐藏在后台。；公开结构只作辅助参考，安全与能力边界仍由本地 Policy/Sandbox/Harness 强制。
### OpenClaw；AgentHarness registry 说明 memory source 应作为可装配能力，并记录 provenance。；agent-core 与 gateway/channel 分离说明跨渠道 memory delivery 应通过 Host Adapter。；tool、sandbox、elevated 分层说明 memory read、memory write 和 provider egress 需要分开决策。；插件事务化注册说明 memory source/index 插件失败时必须回滚，不能留下半注册状态。；多渠道与 provider 组合复杂，强化了 scope key、tenant isolation、通知和 retention 的必要性。
### 综合结论
```text
Memory Product = 用户控制面
  + 候选/确认门槛
  + 版本化事实
  + 受策略约束的 Recall View
  + scope/provenance/confidence/TTL
  + compaction flush
  + privacy/deletion/export
  + durable event/projector
  + evaluation and operations
```
它不是“自动把聊天写入 memory”，也不是单独的向量检索服务。
