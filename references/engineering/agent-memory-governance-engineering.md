# Agent Memory Governance Engineering 细粒度工程设计

> 本文定义 Agent Memory 的治理控制面：它把 Memory Product、Memory Store、Privacy、Policy、State、Context、Provider Runtime、Queue 和 Harness 连接成可执行、可审计、可恢复的策略系统。
>
> 本文只基于当前目录已有的参考架构、本地 `agent-harness.md`、State & Memory、Agent Memory Product、Context、Prompt、Harness、Tool、Permission & Sandbox、Subagent、Event & Observability、Evaluation、Provider Schema Evolution、Durable Queue、Privacy、Agent Product、Workflow Orchestration 和五个参考项目源码归纳；不依赖 README，不进行网络搜索。
>
> 核心结论：Memory Governance 不是给 memory 表增加 `canRead`、`canWrite`、`expiresAt` 几个字段，而是 purpose limitation、scope、sensitivity、consent、provenance、policy decision、egress、retention、删除传播、审计和恢复组成的独立 control plane。

## 目录

1. [设计目标与非目标](#设计目标与非目标)
2. [四种 truth 与边界判断](#四种-truth-与边界判断)
3. [Memory Product、Store、Governance 与包布局](#memory-productstoregovernance-与包布局)
4. [威胁模型与治理不变量](#威胁模型与治理不变量)
5. [Policy Profile、Scope、Purpose 与 Consent](#policy-profilescopepurpose-与-consent)
6. [Sensitivity、DLP、Provenance 与 Authority](#sensitivitydlpprovenance-与-authority)
7. [数据模型与 TypeScript contracts](#数据模型与-typescript-contracts)
8. [Decision Receipt 与审计事实](#decision-receipt-与审计事实)
9. [Candidate、Confirmation 与 Write Policy](#candidateconfirmation-与-write-policy)
10. [Recall Policy 与 Context 投影](#recall-policy-与-context-投影)
11. [Revision、Conflict、Delete、DSAR 与 Retention](#revisionconflictdelete-dsar-与-retention)
12. [Index、Cache、Artifact、Backup 与 Provider Copy](#indexcacheartifactbackup-与-provider-copy)
13. [Poisoning、Injection 与 Provider Egress](#poisoninginjection-与-provider-egress)
14. [生命周期、端到端流程与集成](#生命周期端到端流程与集成)
15. [Queue、Subagent、Workflow、恢复与 Reconciliation](#queuesubagentworkflow恢复与-reconciliation)
16. [Policy Migration、Exception 与 Break-glass](#policy-migrationexception-与-break-glass)
17. [可观测性、测试与 Evaluation](#可观测性测试与-evaluation)
18. [反模式、实施清单与发布门禁](#反模式实施清单与发布门禁)
19. [五个参考项目的启发](#五个参考项目的启发)
20. [Definition of Done](#definition-of-done)

## 设计目标与非目标

### 目标

- 能说明某条 memory 为什么被观察、提取、保存、召回、修订、外发或删除。
- 把产品用户控制和 runtime 强制治理分开。
- 对 tenant、organization、user、workspace、project、session、branch、run、turn、subagent 建立最小 scope。
- 把 `memory_persistence`、`memory_recall`、`memory_edit`、`memory_delete`、`memory_export` 和 `memory_evaluation` 分为独立 purpose。
- 用 `public | internal | confidential | secret | regulated` 控制保存、召回、日志和外发。
- 区分用户直述、模型推断、工具事实、文件事实和人工确认的 provenance。
- 让 candidate、active、confirmed、stale、conflicted、expired、forgotten、quarantined 可恢复、可审计。
- 为 write、recall、edit、delete、export、egress、policy change 和 exception 生成 durable receipt。
- 用户关闭 memory 后停止写入、召回、索引、embedding、flush、export 和后台 job。
- 删除后清理 canonical record、revision、tombstone、index、embedding、cache、artifact、backup 和 provider copy。
- 对 provider fallback、embedding、rerank、shadow、hedge、subagent 和 worker 重新执行 egress policy。
- 对 poisoning、prompt injection、scope 混淆和 provenance 伪造 fail closed 或 quarantine。
- policy、schema、租户迁移和恢复不静默改变历史语义。
- 用 deterministic testkit、side-effect oracle、replay、fault injection 和 reconciliation 证明治理事实。

### 非目标

- 不代替 `SessionRepository` 保存完整 transcript。
- 不代替 `ContextCompiler` 选择全部上下文。
- 不代替 `MemoryStore` 实现向量、全文或 KV 技术细节。
- 不代替 `PolicyEngine` 处理所有工具、文件、进程、网络授权。
- 不用 prompt 文本强制 scope、TTL、删除、DSAR 或 tenant 隔离。
- 不把每条对话、工具结果或 compaction summary 自动升级为长期 memory。
- 不把 embedding 相似度当作 authority、consent 或事实正确性证明。
- 不把一次确认当作未来所有 scope、purpose、provider 的永久授权。
- 不用删除主表记录替代派生对象、备份、缓存和远端副本清理。
- 不把 exception 或 break-glass 变成普通自动写入路径。
- 不用最终模型文本证明 memory 已写入、已删除、已召回或未外发。

## 四种 truth 与边界判断

```text
Transcript Truth  session/branch 上发生过的语义事实
Memory Truth      经过治理、版本化和状态管理的跨任务资源
Context Truth     某次 ModelRequest 实际收到的 memory view
Governance Truth  某次策略、同意、外发、删除、例外的决策事实
```

四者不能混成一张聊天表或一个向量索引。

### Memory Product

产品层回答：用户保存了什么、为什么保存、来自哪里、谁能看到、哪些任务可能使用、何时过期、如何确认、编辑、修订、关闭、导出和删除。

产品层必须显示本次 recall 的 selected、dropped、filtered 和 reason codes。

产品层不能直接读取向量库表，也不能依据模型自述显示“已保存”或“已删除”。

### Memory Store

Store 层保存 canonical record、immutable revision、tombstone、scope、状态、版本和查询索引。

Store 层负责 CAS、幂等、重建、迁移、投影和 reconciliation。

Store 层不决定用户是否同意长期保存，不执行 extraction gate，不自行决定 provider egress。

### Memory Governance

Governance 层决定当前 purpose、principal、scope、sensitivity、provenance、consent、retention、hold 和 destination 是否允许动作。

Governance 还决定是否 notice、approval、confirmation、redaction、summary、artifact-only、quarantine 或 deny。

### 推荐控制流

```text
Product Command
  -> Governance Evaluation
  -> Decision Receipt
  -> Store / Index / Queue / Artifact
  -> Durable Event / Projector
  -> Product View
```

## Memory Product、Store、Governance 与包布局

### 职责矩阵

| 模块 | 负责 | 不负责 |
|---|---|---|
| `MemoryProductService` | 列表、详情、搜索、设置、确认、编辑、删除、导出 | 直接访问向量表 |
| `MemoryGovernance` | purpose、scope、sensitivity、consent、retention、egress、gate | UI 渲染 |
| `PolicyProfileResolver` | profile 合并、安全上限、快照和冲突诊断 | 执行 memory 写入 |
| `CandidateExtractor` | candidate、证据链、提取版本 | 直接激活 active |
| `ConfirmationService` | 用户确认、拒绝、编辑后确认、过期 | 绕过 policy |
| `RecallPlanner` | 过滤、排序、投影、解释、预算 | 修改 canonical record |
| `MemoryWriter` | schema、CAS、revision、receipt | 越过 gate |
| `ContradictionResolver` | 冲突分类、修订建议、quarantine | 代替用户决定高风险事实 |
| `RetentionManager` | TTL、expiry、hold、reaper | 删除审计事实 |
| `DeletionCoordinator` | tombstone、依赖图、清理、验证 | 擅自绕过 hold |
| `EgressEvaluator` | provider、region、view、redaction、destination | OS 网络隔离 |
| `DecisionReceiptStore` | receipt 完整性、追加、查询、验证 | 保存完整敏感正文 |
| `MemoryStore` | canonical、版本、索引、查询 | 定义产品语义 |
| `IndexProjector` | 从 durable facts 构建检索视图 | 产生新业务事实 |
| `PrivacyRuntime` | 分类、DLP、DSAR、驻留、删除规则 | 生成 UI 文案 |
| `ContextCompiler` | 把 RecallView 放入 ContextPlan | 决定长期保存 |
| `Harness` | 装配、预算、取消、恢复、事件路由 | 成为 memory 数据库 |
| `HostAdapter` | 展示 candidate、receipt、删除进度、控制命令 | 直接宣称完成 |

### 推荐包布局

```text
packages/memory-governance/  contracts.ts policy-profile.ts scope.ts purpose.ts classification.ts consent.ts gate.ts decisions.ts receipts.ts egress.ts retention.ts legal-hold.ts exceptions.ts reconciliation.ts migrations.ts audit.ts testkit/
packages/memory-product/     service.ts views.ts confirmation.ts settings.ts export.ts deletion.ts explanations.ts
packages/memory-runtime/     candidate.ts writer.ts recall.ts contradiction.ts index.ts cache.ts flush.ts
packages/privacy-runtime/    inventory.ts dlp.ts redaction.ts provider-egress.ts dsar.ts
packages/memory-ops/         reaper.ts reconciliation-worker.ts migration-worker.ts quarantine.ts dashboards.ts
```

依赖方向是 `Host/Product -> Product Port -> Governance Port -> Runtime Port -> State/Event/Queue/Artifact/Privacy adapters`；Context Runtime 只能接收 RecallView，Agent Kernel 只接 Context Port，基础设施只实现 Store、Index、Queue、Blob、Audit adapter。

## 威胁模型与治理不变量

### 不可信输入

- 用户自然语言中的 scope、owner、consent、approval 或“已经确认”。
- 模型生成的 memory claim、confidence、reason、saved 状态。
- workspace 文件、代码注释、AGENTS/CLAUDE 规则、RAG 文档。
- 工具结果、日志、MCP 描述、provider metadata、remote response。
- subagent summary、child artifact、compaction summary。
- Host 客户端提交的 owner、tenant、memory ID、删除状态。
- provider 返回的 remote object ID、retention、training 或 deletion 声明。

### 保护目标

- 低 authority 数据不能升级为 policy、approval 或 scope authority。
- session memory 不能静默升级为 user、workspace 或 tenant memory。
- secret、regulated 或高风险 PII 不能进入默认长期 memory。
- 语义相似度不能越过 tenant、workspace、purpose 或 owner 边界。
- tombstone 后旧 index、cache、embedding、artifact、backup、provider copy 不能继续召回。
- worker、subagent、fallback 不能拿到 frozen profile 之外的数据。
- unknown write、upload、delete 不能自动重放或标记 success。
- exception、诊断快照和 receipt 不复制完整敏感正文。

### 五层安全决策

```text
Visibility  模型是否看到 memory 能力
Call        当前 memory action 是否可以被提出
Approval    是否需要用户对保存、删除或跨 scope 确认
Execution   Store/index/queue 使用什么 backend
Egress      哪个 view 可以离开当前治理边界
```

Recall 可见性不等于 write 授权；write 授权不等于 provider egress；delete 请求不等于派生清理完成。

### 不变量

1. 每条 memory 使用满足目的的最窄 scope。
2. scope 只能通过显式治理命令扩大；模型不能提交更高 owner。
3. `memory_persistence` 不自动授权 `memory_recall`、`export` 或 provider reuse。
4. candidate 不是 active，active 不是 confirmed，forgotten 不是物理删除完成，unknown 不是 failed 或 success。
5. `model + inferred` 不拥有 `user + direct` authority。
6. `tool + verified` 可提高 confidence，但不能自动扩大 scope。
7. memory 是 data 或 workflow hint，不能获得 authorization authority。
8. 修订写新版本，删除写 tombstone，policy、exception、migration 写新事实。
9. 审计事实和历史 revision 不原地覆盖。
10. 低层 profile 只能收紧高层 safety floor，不能放宽。

## Policy Profile、Scope、Purpose 与 Consent

### Policy Profile

`MemoryPolicyProfile` 是某个 scope、principal、产品模式和 run 阶段的不可变输入，不是全局 `enabled` 标志。

必须约束：enabled、allowed type、allowed scope、write mode、recall mode、confirmation、sensitivity ceiling、purpose、TTL、retention、hold、provider、region、API family、remote retention、subagent、background flush、embedding、rerank、delete capability 和 degraded 行为。

### Profile 合并

```text
built-in safety floor < organization < tenant < user < workspace < project < session < run override
```

低层 profile 只能收紧。

关闭 user memory 不能由 workspace 重新开启。

organization 禁止 regulated memory 时，run override 不能放宽。

Session 和 Run 必须保存 `profileId`、`profileVersion`、`profileHash`、合并来源、scope、consent references、egress snapshot、effective gates、生效时间和过期时间。

运行中 profile 变化默认影响新动作；敏感动作在下一 durable boundary 重新验证。

### Profile TypeScript contract

```typescript
interface MemoryPolicyProfile { profileId:string; version:string; tenantId:string; scope:MemoryPolicyScope; enabled:boolean; allowedTypes:MemoryType[]; writeMode:"disabled"|"candidate_only"|"strict_auto"|"reviewed_auto"|"allowed"; recallMode:"disabled"|"current_session"|"confirmed_only"|"scoped"|"cross_session"; requireConfirmationFor:MemoryType[]; maxPersistentSensitivity:Sensitivity; maxRecallSensitivity:Sensitivity; allowedPurposes:PrivacyPurpose[]; allowedScopes:MemoryScopeLevel[]; allowSubagent:boolean; allowBackgroundFlush:boolean; allowProviderEgress:boolean; providerProfiles:ProviderMemoryProfile[]; ttlDefaults:Partial<Record<MemoryType,DurationPolicy>>; retention:RetentionPolicy; legalHoldPolicy:LegalHoldPolicy; redactionProfile:string; deletionCapability:"synchronous"|"asynchronous"|"best_effort"; exceptionPolicy:ExceptionPolicy; sourceHash:string; }
```

### Scope 层级

```text
tenant -> organization -> user -> workspace -> project -> session -> branch -> run -> turn -> subagent
```

`organization` 是 tenant 下的共享治理层，但必须显式 owner。

`working` 默认 run/turn；`episodic` 默认 session；`semantic` 默认 user/workspace/project；`procedural` 默认 workspace/project/user；tenant memory 只能由组织显式治理；subagent memory 默认 child run 且不直接激活到父 scope。

### ScopeRef 与 Owner

```typescript
interface MemoryScopeRef { level:MemoryScopeLevel; tenantId:string; organizationId?:string; userId?:string; workspaceId?:string; projectId?:string; sessionId?:string; branchId?:string; runId?:string; turnId?:string; subagentRunId?:string; scopeVersion:number; rootIdentityHash?:string; }
interface MemoryOwner { principalId:string; ownerKind:"user"|"organization"|"workspace"|"project"|"session"|"run"|"system"; createdBy:PrincipalRef; delegatedFrom?:PrincipalRef; editableBy:PrincipalRef[]; deletableBy:PrincipalRef[]; exportableBy:PrincipalRef[]; visibleTo:ScopeRef[]; }
```

owner 不等于 createdBy；创建主体不一定拥有编辑、删除、导出权。

有效访问是 `requested scope ∩ parent scope ∩ assignment resources ∩ owner visibility ∩ tenant policy ∩ workspace policy ∩ purpose policy ∩ sensitivity ceiling ∩ provider egress`。

scope 继承默认只读；扩大 scope 必须创建新的 governance command。

### Purpose

```typescript
type PrivacyPurpose = "task_execution"|"memory_persistence"|"memory_recall"|"memory_edit"|"memory_delete"|"memory_export"|"memory_evaluation"|"safety_detection"|"support_diagnostic"|"recovery"|"incident_forensics";
```

- task execution 不自动授权长期保存。
- recall 只能为当前 task 提供上下文。
- persistence 需要稳定性、未来价值和保存控制。
- export 必须限制 subject、scope、view、expiry。
- delete 先处理 legal hold、incident hold 和 unknown jobs。
- evaluation 使用脱敏、最小化、独立 retention。
- diagnostic 使用短 TTL、metadata-first view。
- forensics 只能由受控 operator 或 break-glass 使用。

派生 view 不能拥有比 source 更宽的 purpose；recall prompt view 不能自动成为 persistence source；episodic 汇总为 semantic candidate 必须重新过 write gate。

```typescript
interface PurposeEvaluation { decisionId:string; purpose:PrivacyPurpose; subject:PrincipalRef; scope:MemoryScopeRef; memoryIds:MemoryId[]; destination?:EgressDestination; decision:"allow"|"ask"|"deny"|"transform"; requiredTransform?:"redact"|"summarize"|"artifact_only"|"none"; policyVersion:string; consentRef?:string; legalBasisRef?:string; reasons:string[]; expiresAt:string; }
```

### Consent 与 Approval

Consent 是 purpose、data class、destination、retention 的治理依据；Approval 是具体 action、参数、scope、expiry 的授权事实，两者不能互相替代。

一次 `memory_confirm` 不授权未来跨 workspace recall；撤回 consent 不会让历史 event 自动消失，但会阻止新处理并触发再评估。

```typescript
interface MemoryConsentRecord { consentId:string; tenantId:string; principalId:string; purpose:PrivacyPurpose; dataClasses:Sensitivity[]; destinations:EgressDestination[]; scope:MemoryScopeRef; basis:"consent"|"contract"|"legitimate_interest"|"legal_obligation"|"configured_policy"|"unknown"; noticeRef?:string; version:string; capturedAt:string; expiresAt?:string; withdrawnAt?:string; evidenceHash:string; hostProof?:HostApprovalProof; }
```

Notice 至少说明：保存类型、建议 scope/owner、未来召回范围、TTL/复核、provider/embedding/rerank 外发、是否需确认、编辑/关闭/删除/导出/撤回方法，以及 provider 不支持删除时的限制。

用户必须能关闭所有长期 memory、按 type 关闭、禁止跨 session recall、只允许 confirmed、拒绝 candidate、编辑/修订/forget、导出 records 与 profile、发起 DSAR，并查看每次 recall 的 selected/dropped/reason codes。

## Sensitivity、DLP、Provenance 与 Authority

### 敏感度

```text
public < internal < confidential < secret < regulated
```

memory 默认继承来源最高 sensitivity；摘要不自动降级；合并 source 取更严格等级，除非有字段级可审计 redaction；不确定分类按更高等级。

### Data Tags

`pii`、`credential`、`financial`、`health`、`location`、`customer_data`、`source_code`、`legal_hold`、`biometric`、`child_data`、`security_sensitive`。

### DLP pipeline

```text
ingest -> size/decompression -> MIME/schema -> secret scan -> PII/regulated scan -> prompt-injection diagnostic -> purpose/scope classify -> redact/tokenize -> forbidden-field validation -> governance gate
```

必须扫描 structured fields、searchableText、evidence excerpt、artifact preview、embedding input、index metadata、export package、provider request view 和 audit payload，而不只是 `content.summary`。

scanner 不可用时敏感写入进入 candidate 或 deny；redactor 不可用时 provider egress deny 或 artifact-only；分类未知时提升 sensitivity；redaction 改变 schema 返回 `redaction_changed_schema`；检测到 secret 时阻断低信任 sink 并撤销 egress lease；派生对象已写但扫描未完成则从 recall 排除并 quarantine。

### Provenance

```typescript
interface ProvenanceChain { sourceKind:"user"|"model"|"tool"|"file"|"retrieval"|"human_review"|"system"; sourceRefs:ResourceRef[]; sourceVersions?:string[]; sourceHashes?:string[]; extractionVersion?:string; observedAt:string; recordedAt:string; userConfirmed:boolean; derivation:"direct"|"extracted"|"summarized"|"inferred"|"merged"; inferenceNotes?:string[]; }
interface AuthorityDescriptor { level:"highest"|"high"|"scoped"|"data"|"none"; basis:"product_policy"|"organization_policy"|"user_direct"|"human_review"|"trusted_tool"|"model_inferred"|"retrieval"; appliesTo:"instruction"|"fact"|"workflow_hint"|"identity"|"none"; expiresAt?:string; }
interface ConfidenceBreakdown { extraction:number; sourceReliability:number; freshness:number; confirmation:number; crossSourceAgreement:number; conflictPenalty:number; final:number; methodVersion:string; }
```

confidence 是排序和复核信号，不是事实保证；高 confidence 不能越过 scope、purpose、consent 或 egress deny。

### Memory Poisoning

攻击包括恶意文档要求写 global policy、模型推断用户属性并标 confirmed、工具要求保存 secret、child 伪造父级确认、旧 memory 覆盖新 direct claim、provider metadata 伪造 owner/consent/admin、用户输入要求所有 tenant 允许，以及把 memory 放进 system authority section。

防护包括：memory 只作为 data resource；provenance 贯穿 candidate/record/view/receipt；candidate 不能创建工具、policy、approval 或 secret binding；confirmation 由可信 Host 控制并绑定 candidate hash；scope/owner/purpose 由 trusted runtime 注入；view 标记 stale/conflicted/inferred/source；recall 不改变 active toolset；poisoning 触发 quarantine、incident signal 和审计。

## 数据模型与 TypeScript contracts

### 基础类型

```typescript
type MemoryId=string; type MemoryVersionId=string; type CandidateId=string; type RecallId=string; type GovernanceDecisionId=string; type TombstoneId=string; type PolicyProfileId=string; type Sensitivity="public"|"internal"|"confidential"|"secret"|"regulated"; type MemoryType="semantic"|"episodic"|"procedural"|"working"; type MemoryStatus="candidate"|"active"|"confirmed"|"stale"|"conflicted"|"expired"|"disabled"|"forgotten"|"quarantined"; type ConfirmationState="not_required"|"pending"|"confirmed"|"rejected"|"revoked";
```

### GovernedMemoryRecord

```typescript
interface GovernedMemoryRecord { id:MemoryId; versionId:MemoryVersionId; tenantId:string; owner:MemoryOwner; type:MemoryType; status:MemoryStatus; confirmation:ConfirmationState; content:MemoryContent; scope:MemoryScopeRef; purpose:PrivacyPurpose[]; provenance:ProvenanceChain; confidence:ConfidenceBreakdown; authority:AuthorityDescriptor; sensitivity:Sensitivity; tags:MemoryDataTag[]; createdAt:string; updatedAt:string; lastVerifiedAt?:string; expiresAt?:string; retention:RetentionPolicy; legalHold?:LegalHoldRef; incidentHold?:IncidentHoldRef; revisionOf?:MemoryVersionId; conflictSetId?:string; sourceHash:string; recordHash:string; policyProfileId:PolicyProfileId; deletionState:DeletionState; }
interface DeletionState { state:"active"|"requested"|"tombstoned"|"index_pending"|"cache_pending"|"derived_pending"|"provider_pending"|"verified"|"blocked"|"unknown"; requestId?:string; tombstoneId?:TombstoneId; pendingDependencies:DeletionDependency[]; verifiedAt?:string; limitationCodes?:string[]; }
```

### Candidate 与 RecallView

```typescript
interface GovernedMemoryCandidate { id:CandidateId; proposed:MemoryDraft; evidence:EvidenceRef[]; sourceEntryIds:EntryId[]; proposedScope:MemoryScopeRef; proposedPurpose:PrivacyPurpose[]; sensitivity:Sensitivity; tags:MemoryDataTag[]; provenance:ProvenanceChain; confidence:ConfidenceBreakdown; automaticWriteEligible:boolean; confirmationRequired:boolean; candidateHash:string; expiresAt:string; state:"pending"|"accepted"|"rejected"|"expired"|"superseded"|"quarantined"; createdByRunId:RunId; }
interface GovernedRecallView { recallId:RecallId; memoryId:MemoryId; versionId:MemoryVersionId; type:MemoryType; text?:string; structured?:Record<string,unknown>; presentation:"inline"|"summary"|"artifact_ref"|"metadata_only"; scopeLabel:string; sourceLabel:string; authority:number; confidence:number; freshness:number; conflict:"none"|"possible"|"confirmed"; stale:boolean; sensitivity:Sensitivity; providerEgress:EgressDecision; sourceRefs:ResourceRef[]; viewHash:string; expiresAt?:string; }
```

### Ports

```typescript
interface MemoryGovernancePort { resolveProfile(input:ProfileResolveInput):Promise<PolicyProfileSnapshot>; classify(input:MemoryClassificationInput):Promise<ClassificationResult>; evaluatePurpose(input:PurposeEvaluationInput):Promise<PurposeEvaluation>; evaluateWrite(input:MemoryWriteDecisionInput):Promise<GovernanceDecision>; evaluateRecall(input:MemoryRecallDecisionInput):Promise<GovernanceDecision>; evaluateMutation(input:MemoryMutationDecisionInput):Promise<GovernanceDecision>; evaluateDelete(input:MemoryDeleteDecisionInput):Promise<GovernanceDecision>; evaluateEgress(input:MemoryEgressInput):Promise<EgressDecision>; createException(input:ExceptionRequest):Promise<ExceptionReceipt>; explain(id:GovernanceDecisionId,audience:ExplanationAudience):Promise<GovernanceExplanation>; }
interface GovernedMemoryStore { get(scope:MemoryScopeRef,id:MemoryId,version?:MemoryVersionId):Promise<GovernedMemoryRecord|undefined>; list(scope:MemoryScopeRef,q:MemoryQuery):Promise<GovernedMemoryRecord[]>; append(input:MemoryAppendInput,expectedVersion?:number):Promise<MemoryAppendReceipt>; revise(input:MemoryRevisionInput):Promise<MemoryAppendReceipt>; tombstone(input:MemoryForgetInput):Promise<MemoryDeletionReceipt>; search(input:MemorySearchInput):Promise<MemorySearchHit[]>; rebuildIndex(input:IndexRebuildRequest):Promise<JobReceipt>; inspect(id:MemoryId):Promise<MemoryStorageView>; }
interface GovernedRecallPort { plan(input:RecallRequest):Promise<GovernedRecallPlan>; execute(plan:GovernedRecallPlan):Promise<GovernedRecallResult>; explain(id:RecallId,audience:ExplanationAudience):Promise<GovernanceExplanation>; }
interface GovernanceDecisionReceiptStore { append(r:GovernanceDecisionReceipt):Promise<ReceiptCommitResult>; get(id:GovernanceDecisionId,scope:MemoryScopeRef):Promise<GovernanceDecisionReceipt|undefined>; list(q:ReceiptQuery):Promise<GovernanceDecisionReceipt[]>; verify(id:GovernanceDecisionId):Promise<ReceiptVerification>; }
interface MemoryReconciliationPort { scan(scope:MemoryScopeRef,cursor?:string):Promise<ReconciliationBatch>; reconcile(input:ReconciliationInput):Promise<ReconciliationReceipt>; quarantine(input:QuarantineRequest):Promise<QuarantineReceipt>; }
```

## Decision Receipt 与审计事实

Receipt 是治理事实，不是 debug log，必须回答：谁、在什么 scope、针对什么 memory、服务什么 purpose、采用哪个 profile/policy/consent/DLP/redaction、观察到哪些 source/sensitivity、结果是什么、产生哪些 obligations、是否允许 index/cache/backup/subagent/provider 传播。

```typescript
interface GovernanceDecisionReceipt { decisionId:GovernanceDecisionId; action:"write"|"recall"|"edit"|"delete"|"export"|"egress"|"exception"|"migration"; subject:PrincipalRef; tenantId:string; scope:MemoryScopeRef; memoryIds:MemoryId[]; candidateIds?:CandidateId[]; purpose:PrivacyPurpose; decision:"allow"|"ask"|"deny"|"transform"|"quarantine"|"unknown"; reasons:DecisionReason[]; obligations:GovernanceObligation[]; profileId:PolicyProfileId; profileHash:string; policyVersion:string; consentRef?:string; legalBasisRef?:string; sensitivity:Sensitivity; egress?:EgressDecision; inputHash:string; outputHash?:string; causationEventId?:EntryId; correlationId?:string; createdAt:string; expiresAt?:string; integrity:ReceiptIntegrity; }
```

Receipt append-only；`inputHash` 覆盖 action、scope、purpose 和 relevant facts；`outputHash` 覆盖 decision、transformed view、obligations；policy/profile/consent/egress snapshot 变化时不能复用旧 receipt；receipt 默认不含完整正文；查询 receipt 仍需 tenant、owner、purpose、audit check；unknown receipt 必须进入 recovery 或 manual review。

## Candidate、Confirmation 与 Write Policy

### Candidate 原则

自动提取只能产生 candidate；candidate 不是事实确认，不是默认 recall 输入，不能改变 policy、toolset、approval、owner；source hash 变化后旧确认 token 失效。

允许来源：用户明确说“记住/以后都这样/保存这个偏好”、受控 turn extraction、trusted tool 稳定事实、经 project trust 审核的 workspace 规则、Memory Center 手工创建、compaction 前结构化 flush。

默认禁止直接 active：模型推断人格/健康/财务/敏感属性、未验证 RAG、单次情绪/临时偏好、工具错误/日志/中间推理、安全提示、child 未经父级转交的结论、provider metadata 中的用户事实。

### Confirmation

确认绑定 candidate ID/hash、type、scope、purpose、TTL、source refs、evidence、sensitivity、DLP、profile、consent、notice、policy version、approver、Host proof、expiry。

用户可 `confirm`、`edit_then_confirm`、`confirm_scope_narrower`、`confirm_ttl_shorter`、`reject`、`forget_candidate`；只能收紧 scope 和缩短 TTL，不能用确认 token 扩大授权。

### Auto-write Gate

自动 active 同时要求：明确持久化意图；type 在 allowlist；sensitivity 未超 ceiling；scope 不超过 source；provenance 可追溯；schema/业务校验通过；无 unresolved contradiction；TTL 明确且非无限；用户可查看/编辑/删除；index/audit/receipt 可 durable commit；extraction egress 允许；无 hold、pending deletion 或 profile 冲突。

任一失败则 candidate、quarantine 或 deny。

```text
disabled       只允许 working memory
candidate_only 长期 memory 全部需确认
strict_auto    低敏感、稳定来源、明确意图
reviewed_auto  组织审核来源后自动 active
allowed        仍受全部 privacy、scope、TTL、安全上限约束
```

### Write pipeline

```text
observe transcript/tool/artifact -> normalize claim -> classify type/scope/purpose -> attach provenance -> DLP/sensitivity -> duplicate/contradiction -> confidence/authority -> candidate/auto gate -> approval/confirmation -> append MemoryEntry -> index/cache job -> receipt/notification
```

禁止：模型 `saved:true` 直接写 active；模型提交任意 tenant/owner/scope/TTL；workspace 指令升级 global preference；session 自动复制到 user；secret/regulated 直接长期 active；index 成功但 canonical event 失败时显示已保存；profile 关闭后 flush；通过重试绕过确认。

成功 write 返回 memory/version、status/confirmation/scope、source/provenance/confidence、TTL/retention/verification、receipt、index 状态、egress 状态和用户下一步。

## Recall Policy 与 Context 投影

Recall 是治理后的 Context 投影，不是直接返回 MemoryRecord。

### Recall pipeline

```text
Task purpose -> resolve tenant/user/workspace/session scope -> frozen profile -> consent/legal basis -> discover -> status/owner/scope filter -> sensitivity/purpose/egress filter -> freshness/TTL/hold -> lexical/semantic ranking -> dedupe/conflict -> token/byte budget -> RecallView -> receipt -> ContextPlan
```

默认排除 expired、forgotten、disabled、quarantined、scope 不匹配、purpose 不允许、provider 不允许、未解决高风险冲突、child 未获 parent assignment 的 memory，以及 delete/export/incident job 正在处理的 raw view。

排序考虑 `relevance × scope fit × authority × freshness × provenance × confidence × task-stage fit - contradiction - sensitivity - redundancy - token cost`；相似度不能替代 scope 和 authority。

用户可选择本次不使用 memory、仅当前 session、仅 confirmed、仅指定 type、查看 selected、移除一条后继续、关闭未来跨 session recall。

Recall Receipt 记录 recall ID、profile/scope version、candidate/selected/dropped/filtered IDs、view version/hash/source/reason、redaction/summary/artifact-only/egress、provider/region/API family、预算、index version、freshness。

Context 编译顺序必须是 `tenant/scope -> purpose -> sensitivity -> consent -> egress -> freshness/authority -> relevance/ranking -> token budget`；memory view 永远不获得 instruction authority；compaction 不得丢 deletion request、hold、unknown outcome、candidate 或 receipt 引用。

## Revision、Conflict、Delete、DSAR 与 Retention

### Revision 与 Conflict

编辑不覆盖旧事实，创建新 `MemoryVersion`；旧版本保留 lineage，除非 retention/delete 清理；用户不能编辑 provenance、audit lineage、tenant owner、tombstone。

冲突包括同字段新旧值、不同 scope 规则、user direct 与 model inferred、tool verified 与旧 claim、procedural 与 organization policy、branch/config 变化、delete/revision/confirmation 并发。

```text
newer stronger source -> supersede
same authority/scope -> mark_review
different condition/time -> keep_both with validity
model inference vs user direct -> prefer user direct
policy conflict -> memory remains data, policy wins
sensitivity conflict -> higher sensitivity and quarantine if needed
```

procedural memory 不能覆盖 system、organization、tenant policy；recall 可显示“存在偏好但当前策略不允许执行”；policy conflict 不自动物理删除。

### Forget、Delete、Tombstone

- `forget`：立刻禁止 recall，状态变化。
- `delete`：清理 canonical、派生和远端对象。
- `disable`：停止使用但保留可恢复记录。
- `expire`：停止 active recall，可能保留最小治理事实。
- `revoke_confirmation`：撤回确认，不等于历史不存在。

```text
request -> authenticate/scope -> purpose/hold -> freeze write/recall -> enumerate dependencies -> append delete command -> tombstone -> immediate recall exclusion -> index/cache/derived/provider cleanup -> verify -> deletion receipt
```

```typescript
interface MemoryTombstone { tombstoneId:TombstoneId; memoryId:MemoryId; lastVersionId?:MemoryVersionId; tenantId:string; scope:MemoryScopeRef; reason:"user"|"retention"|"privacy"|"correction"|"incident"|"policy"; requestedBy:PrincipalRef; sourceHash?:string; createdAt:string; blockResurrectionUntil?:string; dependencies:DeletionDependency[]; verified:boolean; }
```

删除完成不能只检查主表；必须验证 recall index 不返回、cache 命中为 tombstone/miss、embedding 不参与召回、derived view/preview 清理或有 hold 解释、provider copy 删除/过期/limitation、backup reaper 登记、队列 job 取消/结算、receipt 包含 blocked/unknown/limitation。

### DSAR

DSAR 盘点 active、candidate、revision、conflict、tombstone、全文、structured fields、embedding、全文 index、rerank/recall cache、recall history、ContextPlan、compaction candidate、flush job、artifact raw/preview/summary/export/backup、subagent、background queue、notification、child result、provider remote object、request receipt、deletion capability，以及审计中的最小治理事实和 deletion proof。

### Retention、TTL、Hold

```text
never_persist | until_turn_end | until_run_end | until_task_end | until_session_end | ttl | until_file_changes | until_revalidated | legal_hold | incident_hold
```

working 默认 run end/短 TTL；episodic 默认天到月；semantic 可长但需 revalidation；procedural 在 workspace、branch、config、policy 变化时可能失效；TTL 到期停止 recall；定时任务不能静默延长；延长 TTL 是 mutation，需要重新评估 purpose、consent、sensitivity、owner。

legal hold 可阻止物理删除，但不自动允许 recall 或 egress；hold 只保护明确对象和 purpose；hold 变化写 durable entry；不保护无关 tenant/derived cache。

reaper 读取 status、expiresAt、retention、hold、active export/recovery/audit dependency、provider copy status，不能绕过 deletion plan。

## Index、Cache、Artifact、Backup 与 Provider Copy

依赖图是 `canonical -> revision -> lexical index -> vector embedding -> rerank/recall cache -> ContextPlan view -> artifact summary/preview -> backup/replica -> provider request/remote file -> evaluation fixture`。

Cache key 至少包含 tenant、scope hash、memory version、profile/policy version、purpose、provider/model/API family、redaction profile、index version；删除或 policy change 失效相应 namespace。

```text
canonical tombstone -> recall disabled -> lexical cleanup -> vector cleanup -> cache invalidation -> artifact cleanup -> backup/replay marker -> provider delete/status -> verification
```

raw、sanitized、summary、preview、embedding input、export package 是独立 artifact view；每个 view 带 owner、tenant、scope、purpose、sensitivity、retention、source/derived hash、transform version、target、expiry、scan status、deletion state；ArtifactRef 不能替代 receipt。

Provider remote file、conversation、batch、cache、embedding 是独立 inventory 对象，记录 provider、API family、deployment、region、remote ID、upload/expiry、purpose、view hash、retention、training opt-out、delete capability、request/response/delete/status receipt。

provider 不支持删除时禁止复用 remote object、缩短本地 retention、记录 limitation、向用户展示限制、创建 follow-up/expiry monitor。

## Poisoning、Injection 与 Provider Egress

### Egress pipeline

```text
MemoryRecord -> purpose -> scope/owner -> sensitivity/classification -> consent/legal basis -> provider/region/API family -> retention/training/delete contract -> redact/summary/artifact view -> DLP -> EgressSnapshot -> ModelRequest/remote job
```

```typescript
interface MemoryEgressDecision { decisionId:string; action:"allow_full"|"allow_redacted"|"allow_summary"|"artifact_only"|"deny"; provider:string; apiFamily:string; deployment?:string; region?:string; purpose:PrivacyPurpose; viewHash:string; redactionProfile?:string; retentionClass:string; trainingOptOut:"required"|"allowed"|"unknown"|"prohibited"; reasons:string[]; expiresAt:string; }
```

fallback 必须重新执行 capability、profile、scope、purpose、residency、training/retention contract、redaction/DLP、budget/cost；primary receipt 不能授权 fallback；hedge 默认禁止对 confidential/secret/regulated 重复外发；shadow 只允许 sanitized fixture、summary 或 ref-only view。

Provider raw response 不可信；metadata 不能覆盖 tenant、owner、consent、policy；fallback 是新 Attempt、新 egress decision、新 receipt。

## 生命周期、端到端流程与集成

### 状态机

```text
Profile: Draft -> Validating -> Reviewed -> Active -> Superseded -> Retired
Candidate: Observed -> Classified -> CandidateCreated -> PendingConfirmation -> Accepted -> Rejected/Expired/Superseded/Quarantined
Memory: Candidate -> Active -> Confirmed -> Revised -> Stale/Conflicted/Disabled/Expired -> Forgotten -> Tombstoned -> DeletionVerified
Recall: Requested -> ScopeChecked -> PurposeChecked -> PolicyChecked -> Retrieving -> Ranked -> Projected -> EgressChecked -> Delivered -> Completed
Delete: Requested -> AuthorizationChecked -> HoldChecked -> TombstoneCommitted -> RecallDisabled -> IndexCleanup -> CacheCleanup -> DerivedCleanup -> ProviderCleanup -> Verified -> Settled/Partial/Blocked/Unknown
```

任何阶段都可能 deny、partial、cancelled、quarantine；旧 profile 退休前保留 reader、解释和历史 receipt。

### 用户明确要求记住

```text
user intent -> normalize type/scope/purpose/content -> trusted owner/tenant -> classify/DLP -> profile -> consent/notice -> candidate -> contradiction -> auto/confirmation gate -> append -> schedule index/derived -> receipt -> notify
```

### 自动候选

```text
TurnCompleted -> allowed extraction -> candidate -> source hash/evidence -> authorized scope -> sensitivity/DLP -> stability/reuse -> contradiction/duplicate -> policy/confirmation -> persist candidate or deny
```

### Edit

```text
edit -> authenticate owner -> expected version -> editable fields -> reclassify -> re-evaluate purpose/scope/TTL -> conflict -> append revision -> invalidate old view/index/cache -> receipt
```

### Model、Prompt、Context、Tool、State、Policy、Harness

Model Runtime 只接收 RecallView、EgressSnapshot 和脱敏 ContextPlan；extraction model 与 task model 分离 purpose、usage、cost、provider receipt。

Prompt 只解释 memory 开关、可用 type/scope、confirmed/candidate/working/data summary、stale/conflicted/inferred，提示模型不能自行声明已保存；Prompt 不负责 owner、TTL、retention、egress、consent、DSAR 或 system authority。

建议工具：`memory_search`、`memory_get`、`memory_suggest`、`memory_confirm`、`memory_edit`、`memory_forget`、`memory_policy`；参数不能包含任意 tenant、owner、scope、policy override；工具可见不等于动作授权。

Session entries 保存 candidate、memory、recall、profile、consent、egress/DLP、delete/tombstone/verify、exception/quarantine、migration/reconciliation/recovery；transcript 只引用 ID、version、view hash、receipt，不复制完整 record。

Harness bootstrap 冻结 tenant/user/workspace/project/session scope、profile、flags、consent/legal basis、classification/DLP/redaction/egress version、provider/model/API/region、index/retention/delete capability、memory/recall/write/export/background budget；run 中监督 candidate、confirmation、flush、index、delete、export、migration、cancel、lease、checkpoint、durable event、provider cleanup、reconciliation。

## Queue、Subagent、Workflow、恢复与 Reconciliation

### Subagent

child memory scope 默认 child run；父级只传递最小 `MemoryRecallPackage`：

```typescript
interface MemoryRecallPackage { packageId:string; parentRunId:RunId; childRunId:RunId; memoryViews:GovernedRecallView[]; purpose:PrivacyPurpose; scope:MemoryScopeRef; expiresAt:string; packageHash:string; }
```

child 不能直接写 user/workspace/tenant active memory；child candidate 必须经过 parent fan-in、governance、schema、confirmation；父取消时停止 child write/index/export/provider egress job。

### Workflow

workflow definition 只能声明 memory capability requirement，不能内嵌用户 memory 内容；每个 model/tool/subagent/artifact step 重新做 egress；workflow version 不自动改变 frozen policy；resume 重新验证 profile、consent、scope、TTL、provider contract。

### Queue

job 类型至少包括 `memory-candidate`、`memory-index`、`memory-recall-cache`、`memory-forget`、`memory-derived-cleanup`、`memory-provider-delete`、`memory-export`、`memory-reconciliation`、`memory-policy-migration`、`memory-recovery`。

payload 只保存 ref、hash、snapshot、idempotency key、最小 assignment；queue visible 不表示 write 未发生；lease expiry 后查询 execution record、tombstone、provider status。

### Recovery invariants

- active 已写、index 未写：不能报告未保存。
- tombstone 已写、派生未清：不能报告已删除。
- provider upload unknown：不能盲目重传敏感 view。
- provider delete unknown：不能复用 remote object。
- profile 过期：不能恢复敏感 egress。
- stale consent：不能自动延长。
- unknown write：不能自动重放。
- cache/index/projection 落后：canonical truth 不改变。

### Reconciliation

```text
scan canonical -> scan index/cache/embedding/artifact/provider -> compare status/version/hash -> classify missing/orphan/stale/resurrected -> finding -> safe repair or quarantine -> verify counts/hashes -> receipt
```

Finding 必须有 finding ID、memory ID、object kind、expected/observed state、severity、safeRepair、repairPlan、evidence、createdAt。

重点注入 crash/timeout/duplicate/gap：candidate receipt 前后、canonical append/index 前后、tombstone/cache cleanup 前后、provider accepted/receipt 前后、provider delete/status 前后、export blob/manifest 前后、migration switch 前后、audit/notification 之间。

## Policy Migration、Exception 与 Break-glass

### Migration

Policy 变化可能改变 type、scope、sensitivity ceiling、purpose allowlist、consent、TTL、egress、retention、delete capability、subagent inheritance；因此不是改 boolean。

```typescript
interface MemoryPolicyMigrationPlan { migrationId:string; fromProfileId:PolicyProfileId; fromProfileHash:string; toProfileId:PolicyProfileId; toProfileHash:string; scopeSelector:ScopeSelector; classificationChanges:ClassificationRuleChange[]; writeChanges:WritePolicyChange[]; recallChanges:RecallPolicyChange[]; retentionChanges:RetentionChange[]; egressChanges:EgressChange[]; deletePlan:DeletionPlanRef[]; dryRunRequired:boolean; dualRead:boolean; rollbackWindow:DurationPolicy; }
```

流程：draft profile、impact inventory、affected classification、dry-run old/new decisions、比较 receipts、生成 candidate/quarantine/delete job、review high sensitivity、只对新 run 激活、按 bounded batch 迁移、reconcile index/cache/provider、保留 rollback reader、再 retire。

规则：新 profile 不能复活 forgotten/tombstoned；收紧 recall 立即阻止新 recall；收紧 retention 生成 deletion job 不删除 hold 对象；收紧 egress 失效旧 view cache；放宽 scope 必须 candidate/重新确认；旧 receipt 不修改，只产生 migration receipt；失败保留旧 reader/source snapshot；partial/blocked 对用户可解释。

### Exception

exception 是受控短期偏离，不是永久 allowlist；必须绑定 incident/原因、principal、tenant、scope、memory IDs、purpose、destination、sensitivity、具体动作、profile diff、obligation、expiry、max uses、approver、reviewer、事后复核。

```typescript
interface MemoryGovernanceException { exceptionId:string; reason:string; incidentId?:string; principal:PrincipalRef; scope:MemoryScopeRef; memoryIds:MemoryId[]; allowedActions:Array<"recall"|"write"|"export"|"delete"|"forensics">; purpose:PrivacyPurpose; destination?:EgressDestination; maxSensitivity:Sensitivity; obligations:GovernanceObligation[]; approvedBy:PrincipalRef[]; createdAt:string; expiresAt:string; maxUses:number; revokedAt?:string; }
```

### Break-glass

仅用于 privacy incident containment、deletion/retention recovery、provider remote status、forensic evidence preservation、legal hold reconciliation；默认 metadata-only、read-only、短 TTL、双人控制；不能扩大 provider egress、不能让 subagent 自动继承、不能保存为普通 profile；使用后立即 revoke 并 review。

## 可观测性、测试与 Evaluation

### Durable Events

`memory.policy.resolved`、`policy.changed`、`classified`、`purpose.evaluated`、`consent.checked`、`candidate.created/confirmed/rejected`、`write.decided`、`created`、`revised`、`conflict.detected`、`recalled`、`recall.filtered`、`egress.decided`、`redaction.applied`、`dlp.scanned`、`forget.requested`、`tombstone.committed`、`index.cleanup.completed`、`cache.invalidated`、`provider.delete.requested/completed`、`delete.verified`、`export.requested/completed`、`reconciliation.finding`、`policy.migrated`、`exception.created`、`break_glass.used`、`quarantined`、`recovery.required`。

### Trace 与字段

span 层级：`session -> run -> memory policy -> classification/purpose/consent -> candidate/write -> recall/egress -> index/cache/provider -> deletion/reconciliation -> migration/recovery`。

必备字段：trace/session/run/turn、memory/candidate/recall/decision ID、profile ID/hash、purpose、scope hash、sensitivity、provenance kind、source/view hash、provider/API/model/region、redaction、DLP/index version、retention/TTL/hold、job/lease、artifact refs、idempotency hash、outcome/unknown。

不得默认记录完整 memory content、tokenization map、secret/regulated 原文、完整 prompt、hidden reasoning、provider headers、其他 tenant 资源存在性。

### 指标与 SLO

写入指标：candidate rate、automatic active、confirmation/rejection/expiry、deny/quarantine/conflict、provenance coverage、false-positive。

召回指标：success、selected/filtered/dropped、stale/conflict/wrong-scope/unconfirmed recall、egress transform/deny、latency、index lag。

删除指标：tombstone latency、propagation completeness、index/cache/embedding lag、provider success/unknown/limitation、orphan derived、resurrection；resurrection 目标为零。

治理指标：receipt coverage、profile conflict、migration lag、exception expiry miss、break-glass usage、reconciliation severity、cross-tenant violation、secret/regulated egress escape；跨租户与未授权外发目标为零。

SLO 至少覆盖 durable active 查询率、forget 到 tombstone P95、recall success、deletion propagation、egress audit、DSAR manifest、unknown deletion resolution、migration reconciliation、cross-tenant violation、unauthorized egress。

### Testkit

```text
FakeMemoryStore FakePolicyProfileResolver FakeConsentStore FakeClassificationService FakeDlpScanner FakeRedactor FakeProviderEgress FakeIndexProjector FakeCache FakeArtifactStore FakeQueue FakeApprovalStore FakeRemoteStatus DeterministicClock DeterministicIds EventRecorder CrashInjector SideEffectRecorder ReconciliationOracle ReplayRunner
```

### 单元与组件测试

单元测试覆盖 profile merge/safety floor、scope intersection/owner、purpose/consent、sensitivity/DLP/redaction、candidate/confirmation、recall ranking/TTL/freshness/authority/conflict、revision/CAS/tombstone/resurrection、cache/index/egress、exception/break-glass、receipt hash/幂等/explain。

组件测试覆盖 Product API、Governance Port、ContextPlan/RecallView、Session/Event Store、Queue worker、Index/Delete/Reconciliation、Artifact/DSAR、Provider fallback、Subagent intersection、Migration dry-run/rollback reader。

### 安全场景

1. 模型伪造 tenant、owner、consent、admin role。
2. 恶意文档诱导 global memory。
3. child 请求父级全部 memory。
4. session 升级 user/workspace。
5. embedding 命中其他 workspace。
6. expired memory 被召回。
7. unconfirmed candidate 进入默认 ContextPlan。
8. secret 进入 provider request。
9. regulated 进入 embedding/trace。
10. fallback 跨 denied region。
11. delete 后 embedding/cache/preview/backup 可召回。
12. provider delete unknown 后复用 remote object。
13. tombstone 被旧 index resurrect。
14. export 混入其他 tenant。
15. migration 放宽 scope 自动 active。
16. break-glass 被普通 workflow 重放。
17. receipt 失败仍显示已保存。
18. lease 过期 worker 继续写 index。
19. duplicate delivery 重复 provider delete。
20. prompt injection 改变 memory policy。

每个 scenario 断言 decision/receipt、status、scope/owner/purpose/sensitivity、ContextPlan selected/dropped/reason、provider request、index/cache/artifact/remote state、deletion propagation、job/lease/idempotency/retry、unknown recovery、UI receipt 引用。

LLM judge 只评价 candidate 未来价值、解释清晰度、summary 忠实度和用户理解；不评价是否真实写入、删除、越权召回、发生外发或满足 DSAR/retention。

## 反模式、实施清单与发布门禁

### 反模式

1. 把治理实现为单表权限字段。
2. 只有 `enabled` 没有 type/scope/purpose/sensitivity/retention。
3. 全部聊天自动写长期 memory。
4. 模型“已记住”更新 active。
5. candidate 没 source hash/expiry/confirmation/rejection。
6. model inferred 和 user direct 使用同一 authority。
7. session 自动升级 user/workspace。
8. procedural memory 当 permission/system policy。
9. recall 只按 embedding 排序。
10. expired/conflicted/forgotten 仍默认召回。
11. RecallView 暴露 raw record。
12. memory 内容进入 system prompt 或工具注册。
13. fallback 复用旧 egress decision。
14. secret/regulated 只因摘要被降级。
15. delete 只删主表。
16. tombstone 不阻止旧 index resurrect。
17. provider delete unknown 后复用 remote object。
18. migration 直接改 profile。
19. exception 无 expiry/owner/review。
20. break-glass 成为普通 dangerous mode。
21. lease 过期 worker 继续清理。
22. audit 复制完整正文。
23. receipt 无 input hash/policy/scope。
24. 用最终文本证明已保存/删除/未外发。
25. DSAR 只处理 active 表。
26. 关闭只隐藏 UI。
27. legal hold 被当作 recall allow。
28. consent 被当作 action approval。
29. index freshness 被当 canonical durability。
30. 只测试 allow，不测 deny/quarantine/unknown/recovery。
31. metrics label 使用 memory text、path、tenant ID 等高基数值。
32. workspace profile 放宽 tenant safety floor。
33. migration 把外部 confirmed 静默标当前 confirmed。
34. governance 嵌入 Agent Kernel while loop。

### 实施清单

#### P0 治理契约

- [ ] 定义 `MemoryPolicyProfile`、`MemoryScopeRef`、`PurposeEvaluation`。
- [ ] 定义 sensitivity、tags、provenance、authority、confidence。
- [ ] 定义 `GovernanceDecisionReceipt`、完整性和 explanation。
- [ ] 定义 candidate/active/confirmed/stale/conflicted/forgotten/quarantined。
- [ ] 定义 write/recall/edit/delete/export/egress action。
- [ ] 建立 safety floor、profile merge、scope guard。

#### P1 Write、Recall 与用户控制

- [ ] candidate extractor、source hash、evidence、expiry。
- [ ] confirmation token、rejection suppression、strict auto-write gate。
- [ ] RecallPlanner、RecallView、filtered reason、token budget。
- [ ] type/scope/purpose/sensitivity 设置。
- [ ] revision、CAS、conflict view。
- [ ] 关闭 memory、按 type 禁用、当前 session-only。

#### P2 隐私、外发与删除

- [ ] PrivacyRuntime、DLP、redaction、provider egress。
- [ ] provider/API/region/retention/training contract。
- [ ] tombstone、index/cache/embedding/derived cleanup。
- [ ] provider remote status/delete/limitation。
- [ ] TTL、retention、legal hold、incident hold、reaper。
- [ ] DSAR、export manifest、加密、访问审计。
- [ ] deletion verification 和 partial/blocked/unknown。

#### P3 队列、恢复与运营

- [ ] candidate/index/delete/export/reconciliation/migration queue。
- [ ] idempotency、lease、heartbeat、fencing、checkpoint。
- [ ] reconciliation scanner、repair、quarantine、receipt。
- [ ] exception、break-glass、revoke、事后 review。
- [ ] migration dry-run、dual-read、rollback reader。
- [ ] audit、trace、metrics、SLO、dashboard、告警。

#### P4 评测与发布

- [ ] 双租户、跨 workspace、过期、冲突、删除复活、fallback fixture。
- [ ] synthetic secret、PII、regulated negative cases。
- [ ] Store、Index、Artifact、Queue、Provider、Host conformance。
- [ ] 每个 durable boundary crash injection。
- [ ] secret escape、cross-tenant、wrong-scope、unapproved egress、resurrection hard gate。
- [ ] candidate false positive、stale recall、explanation quality soft gate。
- [ ] profile snapshot、receipt manifest、migration report、rollback test、operator runbook。

### 发布门禁

- [ ] Governance 是独立 control plane，不是单表权限字段。
- [ ] 未确认 memory 不进默认 active recall。
- [ ] 关闭 memory 后 write、recall、flush、index、embedding、export 停止。
- [ ] secret/regulated 不进入禁止的 provider、trace、subagent、长期 store。
- [ ] scope escalation 必须显式 command、approval 或 confirmation。
- [ ] 删除后的 canonical、index、cache、embedding、artifact、provider 状态可验证。
- [ ] receipt、audit、projection、queue 可重放。
- [ ] unknown outcome 不盲目重放。
- [ ] migration 可 dry-run、暂停、恢复、回滚。
- [ ] break-glass 有短 TTL、最小范围、双人审批、事后复核。

## 五个参考项目的启发

### Pi

headless agent loop 与 Harness 分离说明治理不应塞入 Kernel；session tree、branch、compaction entry 启发 memory scope、source range、可恢复 flush；CLI/TUI/RPC 共用 runtime 启发 Memory Center、Host、Recall Explanation 消费 canonical events；provider message 与 session truth 分离支持独立 MemoryRecord；执行隔离较弱提醒 egress、scope、删除必须由 runtime 强制。

### Grok Build

Session/ChatState actor 启发 write、revision、index、delete 的状态所有权；permission、folder trust、sandbox、路径锁启发 scope、执行能力和资源锁分离；工具输出预算和上下文修剪启发 RecallView、summary、artifact-only、token budget；分层 sampler 启发 extraction/recall/embedding/provider attempt 成本归因；显式错误状态启发 unknown deletion、upload unknown、recovery queue。

### OpenCode

session/message/part 模型启发 Memory Center 与 Recall View 是 projector；durable event/projector 启发 receipt、deletion view、privacy view、reconciliation 可重建；snapshot/patch/revert 启发 revision、tombstone、base hash；client/server 分离启发 Product API 不绑定 UI；permission、MCP/LSP、状态迁移复杂度提醒 Store、Governance、Provider、Host 必须清晰边界。

### Claude Code

memory、skills、hooks、subagents、permission modes、计划工作流启发用户控制、candidate confirmation、最小委派；项目规则与 auto memory 并存说明 procedural memory 不能自动获得 system/policy authority；subagent 能力启发 child scope、evidence、预算、parent fan-in；用户可见关闭、确认、修订体验说明 receipt 必须可产品解释。

### OpenClaw

AgentHarness registry 启发 source、index、provider egress、policy profile 可装配；agent-core 与 Gateway/channel 分离启发 delivery、通知、后台 worker 解耦；tool、sandbox、elevated 分层启发 read、write、egress、break-glass 分开决策；compaction 前 flush 启发 candidate 而非无条件持久化；事务化插件注册启发 migration、index registration、cleanup worker 的失败回滚。

## Definition of Done

Memory Governance 只有同时满足以下条件才算完成：

- Profile 能表达 type、scope、purpose、sensitivity、consent、TTL、retention、egress、subagent、background。
- Product、Store、Governance 职责边界清晰。
- write、recall、edit、delete、export、egress 都生成可验证 receipt。
- candidate、confirmation、auto-write、conflict、revision、tombstone 可恢复。
- provenance、confidence、authority、source hash、sensitivity 可解释。
- poisoning、injection、scope escalation、provider metadata spoofing 有强制防护。
- deletion 覆盖 canonical、index、embedding、cache、artifact、backup、queue、provider。
- retention、TTL、legal hold、incident hold、DSAR 可执行可验证。
- migration 有 dry-run、dual-read、reconciliation、rollback、recovery。
- exception/break-glass 有最小 scope、短 TTL、审批、审计、review。
- subagent、workflow、queue、artifact、context、fallback 不绕过治理。
- unknown 不被伪装为 failed 或 success。
- 测试验证轨迹、状态、receipt、provider request、派生清理、真实副作用和负向结果。
- 决策流程必须按 purpose、scope、sensitivity、provenance、consent、policy、egress、retention 和用户控制顺序执行。
- 故障恢复必须区分 queue/index/provider/delete/export 的 unknown，先 reconciliation，再 retry、quarantine、manual 或 rollback。
- 测试策略必须同时覆盖 unit、component、integration、replay、fault injection、privacy、cross-tenant 和 adversarial memory poisoning。
- “模型说已记住”永远不能替代 MemoryEntry、scope、TTL、receipt、index 状态和 deletion path。
