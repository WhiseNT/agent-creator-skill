# Lineage Quality Engineering 细粒度工程设计
> 本文定义 Agent Harness 中 Data Lineage 的质量控制面、验证运行面、证据模型、质量预算、隔离恢复和影响分析可信度。
> 本设计只使用本地已有参考架构与工程文档的术语和调研结论，包括 `SKILL.md`、`agent-reference-architecture.md`、`agent-harness.md`、`data-lineage-engineering.md`、`data-governance-engineering.md`、`data-quality-operations-engineering.md`、`privacy-engineering.md`、`artifact-engineering.md`、`event-observability-engineering.md`、`evaluation-engineering.md`、`workflow-orchestration-engineering.md`、`provider-runtime-engineering.md`、`provider-recovery-engineering.md`、`session-replay-engineering.md`、`workspace-isolation-engineering.md` 和 `multi-tenant-engineering.md`；不依赖 README，不进行网络搜索。
> **边界声明：** Lineage Quality 不是“检查是否存在 from/to”。它必须验证边的语义、时间、版本、schema、租户、region、purpose、删除义务、provenance confidence、覆盖范围和上下游影响；不能用一条存在的边证明影响分析可信。标题映射约定：`Impact-analysis Trust` 即“影响分析可信度”，`Provenance Confidence` 即“来源证明置信度”，`Quality Gates` 即“质量门禁”，`Deletion Proof` 即“删除证明”。
## 目录
1. [目标与非目标](#目标与非目标)
2. [核心原则与术语](#核心原则与术语)
3. [职责边界](#职责边界)
4. [Lineage 图与质量域](#lineage-图与质量域)
5. [质量维度](#质量维度)
6. [质量预算与质量 SLO](#质量预算与质量-slo)
7. [核心数据模型](#核心数据模型)
8. [TypeScript 接口](#typescript-接口)
9. [Lineage Edge 生命周期](#lineage-edge-生命周期)
10. [Edge Validation](#edge-validation)
11. [Orphan、Ambiguous 与 Cyclic Lineage](#orphanambiguous-与-cyclic-lineage)
12. [Schema/Contract Alignment](#schemacontract-alignment)
13. [Provenance Confidence](#provenance-confidence)
14. [Sampling、Ground Truth 与标注](#samplingground-truth-与标注)
15. [Incremental 与 Batch Verification](#incremental-与-batch-verification)
16. [Backfill、Rebuild 与版本迁移](#backfillrebuild-与版本迁移)
17. [Quality Gates](#quality-gates)
18. [Impact-analysis Trust](#impact-analysis-trust)
19. [DSAR、Deletion Proof 与 Residency Evidence](#dsar删除-proof-与-residency-evidence)
20. [Drift Detection](#drift-detection)
21. [Quality Incident、Quarantine 与 Replay](#quality-incidentquarantine-与-replay)
22. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
23. [可观测性、Dashboard 与 Alerts](#可观测性dashboard-与-alerts)
24. [测试策略与 Test Matrix](#测试策略与-test-matrix)
25. [反模式](#反模式)
26. [实施清单](#实施清单)
27. [五个参考项目启发来源](#五个参考项目启发来源)
28. [Definition of Done](#definition-of-done)
## 目标与非目标
### 目标
Lineage Quality 必须：
- 以 `LineageGraph`、`LineageNode`、`LineageEdge`、`EvidenceRef`、`QualityObservation` 和 `QualityIncident` 表达来源、转换、消费、物化、删除和区域事实。
- 对 completeness、correctness、timeliness、freshness、consistency、uniqueness、coverage 建立可计算指标、预算、SLO、阈值和告警。
- 在边写入、图投影、批量扫描、DSAR、residency、artifact、workflow 和 provider recovery 边界执行验证。
- 识别 orphan、ambiguous、cyclic、stale、duplicate、contradictory、cross-tenant、cross-region 和 schema-incompatible lineage。
- 将 schema/contract、ModelRef、ResolvedModel、ContextPlan、PromptPlan、ToolContract、ArtifactRef、CanonicalEvent、UsageLedger、PolicySnapshot 和 EgressSnapshot 对齐到 lineage。
- 给每条边和每个影响分析结果计算 provenance confidence，并明确直接观察、推断、采样和人工确认的差异。
- 支持增量校验、批量重扫、backfill、rebuild、replay、quarantine、repair proposal 和人工复核。
- 让 DSAR/deletion proof、retention、legal hold、residency evidence 和 provider remote object 状态可追溯。
- 让 quality gate 能阻止不完整或不可信 lineage 进入影响分析、artifact materialization、memory、cache、delivery 或合规结论。
### 非目标
- 不把 lineage 图作为授权系统；Policy、Permission、Egress、Sandbox 和 Privacy 仍是决策权威。
- 不因为边存在就推断数据实际被读取、复制、发送、训练或删除。
- 不把 trace span、日志搜索或 prompt 文本当作完整 lineage 事实。
- 不静默修复历史事实；修复必须新增 correction event、evidence 和版本。
- 不以单一全局分数掩盖高敏感租户、受限 region、关键 artifact 或删除义务的失败。
- 不允许自动 backfill 触发真实工具、外部写操作或未经批准的 provider egress。
## 核心原则与术语
### 三类事实
```text
Observed fact      由 runtime、store、provider receipt、artifact manifest 或业务系统直接观察
Derived relation   依据稳定 key、schema、event、transform、时间和契约推导
Declared intent    由配置、policy、workflow、prompt 或 operator 声明的预期关系
```
影响分析和删除证明优先使用 observed fact；derived relation 必须带规则版本；declared intent 不能冒充实际发生。
### Lineage 关系
- `source`：输入、文件、消息、用户内容、外部数据集、provider response 或工具结果。
- `transform`：prompt 编译、context 投影、模型采样、解析、摘要、清洗、聚合、压缩或版本迁移。
- `consumer`：模型、工具、workflow step、memory、cache、artifact view、通知或外部业务系统。
- `materialization`：把逻辑数据持久化为 event、session、artifact、memory、index、queue payload 或业务记录。
- `deletion`：删除、撤回、过期、匿名化、quarantine 或 tombstone 关系。
- `residency`：数据、备份、provider remote object、日志、缓存和派生视图的区域证据。
### 核心不变量
1. 每条 lineage edge 有稳定 `edgeId`、版本、方向、时间、scope、purpose、证据和 confidence。
2. `from`/`to` 的存在不是 edge validity；两端必须满足 node identity、schema、scope、contract 和生命周期条件。
3. lineage 允许暂时缺边，但必须显式标记 expected、missing、unknown、quarantined 或 waived。
4. 任何 correction、backfill、rebuild、merge、split 或删除都不能覆盖原始 edge evidence。
5. 跨 tenant、跨 workspace、跨 region 和跨 purpose 的边必须有显式 policy/egress evidence。
6. graph cycle 可能是合法反馈回路，也可能是错误的 self-reference；必须依赖 edge kind 和 workflow semantics 判定。
7. 影响分析结果必须绑定 quality snapshot、coverage、confidence、freshness 和 unresolved findings。
8. DSAR/deletion proof 必须能证明 source、materialization、consumer、backup、remote object 和 tombstone 的覆盖范围。
## 职责边界
| 组件 | 负责 | 不负责 |
|---|---|---|
| `LineageRecorder` | 在事件、artifact、tool、provider、workflow 边界发出事实 | 推断所有隐藏读取 |
| `LineageStore` | append-only edge/node、版本、证据、查询 | 自动授权 egress |
| `LineageValidator` | edge/node/schema/scope/time/contract 验证 | 修改原始事实 |
| `LineageQuality` | 质量指标、预算、SLO、incident、gate | 替代 Policy 决策 |
| `ImpactAnalyzer` | downstream/upstream reachability、影响集合和证据 | 在低质量图上宣称确定 |
| `DataGovernance` | purpose、retention、residency、DSAR、legal hold | 解析全部 runtime frame |
| `DataQuality` | completeness、freshness、consistency、quarantine、repair | 绕过 lineage evidence |
| `ArtifactStore` | hash、size、view、scan、retention、delete receipt | 宣称业务消费发生 |
| `ProviderRuntime` | provider request/response/usage/receipt | 维护全局 lineage 图 |
| `ToolRuntime` | tool input/output、execution、business receipt | 假设调用一定成功 |
| `WorkflowOrchestrator` | step dependency、checkpoint、compensation | 修改 lineage evidence |
| `SessionReplay` | recorded/forked replay 和 divergence | 直接执行真实副作用 |
| `Harness` | scope、policy、context、prompt、state、delivery | 代替质量扫描器 |
## Lineage 图与质量域
### 图结构
```text
Node = source | dataset | event | artifact | view | prompt | context | model | tool | step | run | output | deletion | residency
Edge = reads | derives | transforms | emits | materializes | consumes | references | copies | deletes | quarantines | verifies
```
图应支持有向多重边、版本化节点、时间有效区间、租户/工作区 scope 和不同 evidence class。不能将所有边压扁为 `from -> to`。
### 质量域
- 运行时域：Provider、Model、Prompt、Context、Tool、State、Artifact、Workflow、Delivery。
- 数据域：源数据集、用户输入、文件、缓存、索引、memory、派生视图。
- 治理域：purpose、consent、retention、residency、training、DSAR、legal hold。
- 运营域：quality snapshot、budget、incident、quarantine、backfill、rebuild、alert。
### Graph Scope
```typescript
interface LineageScope {
  tenantId: string;
  organizationId?: string;
  workspaceId?: string;
  projectId?: string;
  region?: string;
  purpose: string;
  sensitivity: Sensitivity;
  retentionClass: string;
}
```
查询必须带 scope；跨 scope 影响分析需要显式授权、聚合化结果或 privacy-preserving existence semantics。
## 质量维度
### Completeness
衡量应记录的节点和边中，实际存在且可验证的比例。分母必须来自 contract、event registry、artifact manifest、workflow plan、provider receipt、tool invocation 和 governance obligation，而不是仅来自已存在的图。
```text
completeness = valid_expected_edges / expected_edges
```
分别计算 node completeness、edge completeness、evidence completeness、deletion completeness 和 residency completeness。
### Correctness
边的方向、kind、subject、source/target identity、transform、时间、schema、scope、purpose、version 和 evidence 与事实一致。存在 edge 但方向反了仍是 incorrect。
### Timeliness
从事实发生到 edge durable 的延迟。区分 producer lag、queue lag、store lag、projector lag、backfill lag 和 observation lag。
### Freshness
lineage 证据相对于有效时间、source version、artifact version、policy version 和 provider state 的新鲜程度。freshness 不等于写入时间近；旧 source 的即时 edge 仍可能 stale。
### Consistency
不同投影、事件、artifact manifest、usage ledger、workflow checkpoint、policy snapshot、region evidence 和 provider receipt 对同一关系的结论一致。
### Uniqueness
同一逻辑关系不产生无法解释的重复 node/edge、重复 attempt、重复 materialization 或重复 deletion proof。合法多次 attempt 必须用 attemptId/causation 区分。
### Coverage
在 tenant、workspace、region、data class、provider、artifact kind、workflow kind、tool kind、retention class 和 lifecycle phase 上的代表性。全局 99% coverage 不能掩盖某个关键 region 为零。
### 维度组合
质量报告必须同时展示维度、scope、时间窗、分母、样本、confidence、unresolved 和 budget 消耗；不能只给单一百分比。
## 质量预算与质量 SLO
### Quality Budget
```typescript
interface LineageQualityBudget {
  budgetId: string;
  scope: LineageScope;
  window: TimeWindow;
  maxMissingEdges: number;
  maxInvalidEdges: number;
  maxOrphans: number;
  maxAmbiguity: number;
  maxCycles: number;
  maxStaleEvidenceMs: number;
  maxDeletionProofGaps: number;
  maxResidencyUnknown: number;
  maxUnresolvedImpact: number;
  maxRepairRate: number;
  consumed: QualityBudgetConsumption;
  policyVersion: string;
}
```
### Budget 原则
- 合规、删除、residency、跨租户和安全边的 budget 通常为零。
- 交互输出可以允许短暂 timeliness lag，但不能放宽 correctness 或 scope violation。
- 可接受的 orphan 必须有 TTL、owner、expected reason 和 quarantine policy。
- repair 自动化本身有预算，避免错误规则无限修改历史图。
- backfill/rebuild 消耗独立计算和写入预算，不与生产质量预算混淆。
### Quality SLO
| SLO | 含义 |
|---|---|
| edge completeness | 预期边在目标窗口内被记录并可验证 |
| correctness | 通过 schema、scope、时间和 evidence 验证的边比例 |
| timeliness | 事实到 durable edge 的 p95/p99 延迟 |
| freshness | 活跃图中证据未超过允许 age 的比例 |
| consistency | event/store/projector/artifact/policy 对账一致率 |
| uniqueness | 无法解释的重复 edge/node/obligation 比例 |
| coverage | 关键 scope、region、data class 的非零有效覆盖 |
| deletion proof | DSAR/retention 对象具有完整证明的比例 |
| impact trust | 达到 gate 的影响分析结果比例 |
### SLO 违约处理
SLO 违约生成 quality incident 或 budget burn event；不能只调高阈值。应区分 producer bug、schema drift、store lag、validator bug、真实缺失和观测盲区。
## 核心数据模型
```typescript
interface LineageNode {
  nodeId: string;
  nodeType: LineageNodeType;
  canonicalKey: string;
  version?: string;
  scope: LineageScope;
  schemaRef?: string;
  contractRef?: string;
  sourceSystem: string;
  validFrom: string;
  validTo?: string;
  observedAt: string;
  status: "active" | "deleted" | "quarantined" | "unknown";
  identityEvidence: EvidenceRef[];
}
type LineageNodeType = "source" | "dataset" | "event" | "artifact" | "view" | "prompt" | "context" | "model" | "tool" | "step" | "run" | "output" | "deletion" | "residency";
interface LineageEdge {
  edgeId: string;
  edgeKind: LineageEdgeKind;
  fromNodeId: string;
  toNodeId: string;
  scope: LineageScope;
  purpose: string;
  transformRef?: string;
  schemaMapRef?: string;
  contractRef?: string;
  attemptId?: string;
  workflowStepId?: string;
  validFrom: string;
  validTo?: string;
  recordedAt: string;
  sourceVersion?: string;
  targetVersion?: string;
  evidenceRefs: EvidenceRef[];
  provenance: ProvenanceInfo;
  status: "proposed" | "observed" | "validated" | "quarantined" | "superseded" | "rejected";
}
type LineageEdgeKind = "reads" | "derives" | "transforms" | "emits" | "materializes" | "consumes" | "references" | "copies" | "deletes" | "quarantines" | "verifies";
```
### Evidence
```typescript
interface EvidenceRef {
  evidenceId: string;
  kind: "canonical_event" | "artifact_manifest" | "provider_receipt" | "tool_receipt" | "workflow_checkpoint" | "policy_snapshot" | "egress_snapshot" | "schema_contract" | "audit_record" | "sample_observation" | "operator_attestation";
  locator: string;
  contentHash?: string;
  observedAt: string;
  validUntil?: string;
  sensitivity: Sensitivity;
  redactionState: "none" | "redacted" | "tokenized";
}
interface ProvenanceInfo {
  confidence: number;
  method: "direct_observation" | "contract_inference" | "event_join" | "sampling" | "replay" | "manual";
  ruleVersion: string;
  supportingEvidence: EvidenceRef[];
  contradictingEvidence: EvidenceRef[];
  lastVerifiedAt: string;
}
```
## TypeScript 接口
```typescript
interface LineageQualityPort {
  recordNode(node: LineageNode): Promise<void>;
  recordEdge(edge: LineageEdge): Promise<void>;
  validateEdge(input: EdgeValidationInput): Promise<EdgeValidationResult>;
  evaluate(input: QualityEvaluationInput): Promise<QualitySnapshot>;
  impact(input: ImpactAnalysisInput): Promise<ImpactAnalysisResult>;
  quarantine(input: QuarantineLineageInput): Promise<QuarantineReceipt>;
  reconcile(input: LineageReconciliationInput): Promise<LineageReconciliationResult>;
}
interface EdgeValidationInput {
  edge: LineageEdge;
  source?: LineageNode;
  target?: LineageNode;
  expectedContract?: LineageContract;
  graphSnapshotId: string;
  policySnapshotId: string;
}
interface EdgeValidationResult {
  status: "valid" | "invalid" | "unknown" | "quarantine";
  findings: LineageFinding[];
  normalizedEdge?: LineageEdge;
  confidence: ProvenanceInfo;
}
interface QualitySnapshot {
  snapshotId: string;
  scope: LineageScope;
  window: TimeWindow;
  graphVersion: string;
  dimensions: QualityDimensionResult[];
  budgets: LineageQualityBudget[];
  unresolved: LineageFinding[];
  gate: "pass" | "warn" | "fail" | "unknown";
  generatedAt: string;
}
interface ImpactAnalysisResult {
  analysisId: string;
  rootNodes: string[];
  affectedNodes: string[];
  affectedEdges: string[];
  confidence: number;
  coverage: CoverageReport;
  qualitySnapshotId: string;
  unresolved: LineageFinding[];
  trust: "trusted" | "conditional" | "untrusted";
}
```
## Lineage Edge 生命周期
```text
Expected -> Proposed -> Observed -> Validating -> Validated
                         |              |
                         v              v
                       Unknown       Quarantined
Validated -> Superseded | Deleted | Reconciled
```
### Expected
由 workflow plan、tool contract、artifact manifest、provider adapter、policy obligation、schema contract 或 deletion plan 产生预期边。Expected 不是事实，但用于 completeness 分母。
### Proposed
producer 根据 event、runtime callback 或 batch inference 生成边；必须带 causation、scope、purpose 和 evidence candidate。
### Observed
至少有一个可引用的直接事实，例如 `CanonicalEvent`、`ToolReceipt`、`ArtifactRef`、`WorkflowCheckpoint`、provider receipt 或删除回执。
### Validating
执行节点存在、方向、时间、schema、contract、scope、region、purpose、version、duplicate、cycle 和 evidence freshness 检查。
### Validated
满足当前 quality policy；validated edge 仍可能过期，需重新验证。
### Quarantined
证据冲突、跨域不明、schema drift、敏感 egress 未证明、hash mismatch、orphan 超 TTL 或循环风险时隔离。
### Superseded/Deleted
新版本替代旧边或 deletion/tombstone 证明边的生命周期；原始 edge 保留审计，不物理擦除历史事实。
## Edge Validation
### 验证顺序
```text
parse schema
  -> node identity and existence
  -> scope/tenant/workspace
  -> edge kind and direction
  -> valid time and observed time
  -> source/target schema and contract
  -> transform/version compatibility
  -> purpose/egress/residency
  -> evidence freshness and integrity
  -> uniqueness and causation
  -> cycle policy
  -> provenance confidence
  -> quality gate
```
### Identity 检查
- `nodeId`、canonical key、version 和 sourceSystem 必须一致。
- artifact 使用 content hash、size、manifest version 和 view identity。
- event 使用 eventId、sequence、run/session scope 和 payload hash。
- provider attempt 使用 requestId、attemptId、providerRequestId、route snapshot 和 usage reference。
- tool 使用 toolCallId、toolExecutionId、business operation id 和 receipt。
- workflow 使用 workflow version、step id、checkpoint id 和 dependency cursor。
### 时间检查
验证 validFrom/validTo、observedAt、recordedAt、source version time、checkpoint time 和 policy effective time。未来边、逆序 transform 或已过期 credential 需要 finding。
### Scope 检查
比较 source、target、edge、policy、egress、credential、workspace 和 region scope。scope unknown 不能默认通过；存在跨 tenant 组合时进入 quarantine。
### Evidence 检查
证据 locator 可解析、hash 未变化、redaction 不影响验证、validUntil 未过期、主体和边匹配。日志中出现关键词不能代替 evidence ref。
### EdgeValidationResult 规则
invalid 表示有确定冲突；unknown 表示证据不足；quarantine 表示继续传播可能造成安全、合规或错误影响分析风险；warn 不能用于关键删除/residency 边。
## Orphan、Ambiguous 与 Cyclic Lineage
### Orphan
source 或 target node 不存在、已删除但 edge 仍 active、edge 证据指向不存在的 artifact/event、expected edge 超过 TTL 未观察。orphan 分为 producer lag、store lag、真实缺失、历史迁移和恶意/错误引用。
### Orphan 处理
1. 查询 canonical event、artifact manifest、checkpoint、provider/tool receipt 和 schema registry。
2. 判断是否为 ingestion/projector lag。
3. 若可补齐 node，新增 node event，不改 edge 原文。
4. 若超过 TTL，进入 quarantine 或 quality incident。
5. 影响分析遇到 orphan 时降低 coverage/confidence，不能静默跳过。
### Ambiguous
一个 source 可能映射多个 node、同一 canonical key 多版本无时间界限、edge kind 不明确、provider attempt 与业务 operation 不可区分、多个 artifact view 可能代表同一内容。必须保存 candidate set、匹配规则、置信度和 unresolved reason。
### Ambiguous 处理
- 先用 immutable id、content hash、version、causation 和 scope 收窄。
- 再用 schema/contract、time window、workflow cursor 和 receipt 关联。
- 无法唯一确定时生成 ambiguity finding，不选择任意一条边。
- 关键 DSAR、residency 和 destructive impact 必须人工确认。
### Cyclic
合法 cycle 例：memory feedback、workflow loop、retry attempt graph、streaming transform；非法 cycle 例：删除边回指活跃源、同一 transform 自引用、跨租户反馈无授权。cycle detector 要按 edge kind、workflow version、时间窗口和 causation 判断。
### Cycle 处理
- 记录 strongly connected component、cycle path、edge kinds 和 first observed time。
- 合法 cycle 需有 loop contract、最大迭代、终止条件和 owner。
- 非法 cycle quarantine 相关边和下游 materialization。
- 影响分析不能把 cycle 展开成无限集合；使用 visited set、bounded depth 和 trust downgrade。
## Schema/Contract Alignment
### 对齐对象
- Lineage node/edge schema version。
- ModelRef、ResolvedModel、ModelCapabilities。
- PromptPlan、ContextPlan、ToolContract、ArtifactManifest。
- Provider contract、route snapshot、usage schema、workflow schema。
- PolicySnapshot、EgressSnapshot、TenantContext、WorkspaceSnapshot。
### Contract
```typescript
interface LineageContract {
  contractId: string;
  version: string;
  allowedNodeTypes: LineageNodeType[];
  allowedEdgeKinds: LineageEdgeKind[];
  requiredEvidenceKinds: string[];
  requiredFields: string[];
  scopeRules: ScopeRule[];
  timeRules: TimeRule[];
  deletionRules?: DeletionRule[];
  residencyRules?: ResidencyRule[];
}
```
### Alignment 规则
- contract breaking change 必须先更新 expected edges 和 validator fixture。
- schema compatible 不等于 semantic compatible；例如 output schema 相同但 provider capability/region 改变仍需重新验证。
- adapter、prompt compiler、context compiler、tool registry、artifact view 和 workflow version 都必须进入 lineage transform/version。
- unknown schema field 不得直接丢弃；保存 raw evidence 并标记 schema drift。
- contract 迁移需要 dual-read/dual-write、backfill window、quality comparison 和 rollback。
## Provenance Confidence
### Confidence 分级
| 级别 | 证据 | 用途 |
|---|---|---|
| 1.0 | 直接 receipt/event/manifest 且 hash/sequence 可验证 | 删除、审计、关键影响分析 |
| 0.8–0.99 | 多个独立 event join 且 schema/时间一致 | 生产影响分析 |
| 0.5–0.79 | contract inference、采样、replay 支持 | 条件性分析、质量修复 |
| 0.2–0.49 | declared intent 或弱时间/弱 identity 关联 | 仅提示和补采样 |
| <0.2 | 猜测、冲突或缺证据 | 不得作为合规结论 |
### 计算原则
confidence 不是任意平均；可使用 evidence independence、freshness、identity certainty、schema alignment、scope certainty、contradiction penalty 和 method prior。相互复制的日志不算独立证据。
```typescript
interface ConfidenceFactors {
  identity: number;
  direction: number;
  temporal: number;
  schema: number;
  scope: number;
  evidenceIntegrity: number;
  freshness: number;
  contradictionPenalty: number;
}
```
### Confidence 传播
沿 downstream 传播时取瓶颈或带宽度的组合，不能让大量低置信边平均成高置信。遇到 orphan、ambiguous、quarantine、stale、cycle 或跨域 unknown 时必须降级并记录原因。
### Confidence 反事实
影响分析报告显示 `confirmed affected`、`likely affected`、`possible affected` 和 `unknown`; 不把 possible 当 confirmed，也不把 unknown 从结果中删除。
## Sampling、Ground Truth 与标注
### Sampling 目的
采样用于发现遗漏、校准 inference、估计 coverage、评估 freshness 和测试实际运行路径；不能用采样比例代替关键 edge 的完整记录。
### Sampling 策略
- 按 tenant、region、provider、model、tool、artifact kind、workflow、sensitivity 和 lifecycle 分层。
- oversample high-risk、quarantine、orphan、ambiguous、跨域和最近 schema 变更。
- 保留 deterministic sample key，支持重复验证和审计。
- 明确 sample frame、抽样概率、未覆盖范围、置信区间和时间窗口。
### Ground Truth
ground truth 来源包括：业务系统 receipt、provider status、artifact hash、event sequence、workflow checkpoint、operator adjudication 和受控 replay。ground truth 也可能过期或冲突，必须带时间、scope、版本和可信度。
### 标注流程
1. 生成去敏 sample case。
2. 展示 source、target、edge、evidence、schema、scope 和时间线。
3. 由双人或规则引擎标记 valid/invalid/unknown/ambiguous。
4. 冲突进入 adjudication，记录 rationale 和 rule version。
5. 更新 validator、confidence calibration、quality budget 和回归集。
### 采样指标
precision、recall、false orphan、false complete、edge validity agreement、ground-truth age、sampling coverage 和 adjudication latency。
## Incremental 与 Batch Verification
### Incremental
在 event、artifact、tool receipt、provider receipt、checkpoint、policy change、schema publish、DSAR 或 residency change 时验证受影响的节点和边。使用 dependency index、causation、content hash、version 和 scope 限定集合。
### Incremental 优点
低延迟、可阻止坏边传播、适合 quality gate、成本低；缺点是依赖索引、可能漏掉历史孤立问题、无法发现全图 cycle 或跨分区冲突。
### Batch
按时间、tenant、region、provider、data class、artifact、workflow、schema 或 quality incident 扫描全图/分区，执行 orphan、duplicate、cycle、consistency、freshness、coverage、deletion 和 residency 检查。
### Batch 优点
能发现历史累积问题和全局图性质；缺点是成本高、结果滞后、需要 snapshot、分区和 backpressure。
### 混合策略
```text
incremental gate on write
  + nearline verification on hot paths
  + daily/weekly batch scan
  + monthly deep graph and deletion/residency audit
  + incident-triggered targeted scan
```
### Snapshot
batch 使用 immutable `LineageGraphSnapshot`、node/edge high-water mark、event watermark、schema registry version、policy version 和 evidence cutoff。扫描期间的新事实进入下一窗口，不产生时间旅行。
## Backfill、Rebuild 与版本迁移
### Backfill
backfill 从 canonical events、artifact manifests、workflow checkpoints、provider/tool receipts 和历史 logs 的合法 evidence 重建缺失边。每个 backfill job 带 source range、rule version、scope、owner、budget、dry-run 和 rollback marker。
### Rebuild
rebuild 重建 projection、索引、confidence、quality snapshot 或 impact cache，不修改原始事实。rebuild 可按 tenant/region/time partition 分区，并在发布前做 old/new comparison。
### 迁移步骤
1. 读取旧 schema/contract 和历史质量基线。
2. 定义 mapping、不可映射字段和默认值；默认值不能伪造 observed fact。
3. dry-run 生成 proposed edges 和 findings。
4. 小 scope shadow compare。
5. 批量写入新版本，保留 old version links。
6. 执行 incremental catch-up，比较 high-water mark。
7. 通过 quality gate 后切换 read path。
8. 观察窗口后再清理过期 projection；原始 evidence 仍保留。
### Rollback
rollback 回退读取/投影版本，不删除已写的新 evidence。若新规则错误产生边，使用 correction/rejection event 标记，不物理覆盖。
## Quality Gates
### Gate 层次
- **Write gate**：阻止明显 invalid、跨 scope、无 required evidence、错误 schema 的边落入 active。
- **Materialization gate**：阻止低 confidence、quarantine 或 deletion/residency 未满足的节点进入 context、memory、cache、artifact view 或 delivery。
- **Impact gate**：只有 coverage、freshness、consistency、confidence 和 unresolved 在阈值内才允许输出 trusted impact。
- **Compliance gate**：DSAR、retention、legal hold、residency、training 和 egress 证据不足时 fail closed。
- **Release gate**：schema、adapter、provider、tool、workflow、prompt/context compiler 变更必须通过 lineage regression。
### Gate 结果
```typescript
type QualityGateResult = "pass" | "warn" | "fail" | "blocked" | "unknown";
interface QualityGateDecision {
  gateId: string;
  result: QualityGateResult;
  scope: LineageScope;
  snapshotId: string;
  violatedBudgets: string[];
  requiredRemediation: string[];
  expiresAt?: string;
  approver?: string;
}
```
### Fail-open/closed
- correctness、scope、security、residency、deletion、cross-tenant 和 destructive impact 默认 fail closed。
- timeliness/freshness 可在低风险、明确 TTL 和用户可见 degraded 下 warn。
- unknown 不等于 warn；关键对象的 unknown 必须 blocked 或 manual。
## Impact-analysis Trust
### 信任输入
impact analysis 必须输入：graph snapshot、quality snapshot、edge confidence、coverage report、freshness window、unresolved findings、schema/contract version、policy/egress version 和 query scope。
### Trust 级别
| Trust | 条件 | 用途 |
|---|---|---|
| trusted | 关键路径边 direct/validated，coverage 高，无关键 unresolved | 自动影响通知、删除计划建议 |
| conditional | 存在低风险 inference、轻微 stale 或限定 orphan | 人工确认后执行 |
| untrusted | 关键边缺失、跨域 unknown、cycle/ambiguity、residency/deletion gap | 只能扩大扫描和人工处理 |
### 影响算法
- upstream 用 source/reads/derives/transforms 路径。
- downstream 用 materializes/consumes/references/copies 路径。
- deletes、quarantines 和 verifies 是治理路径，不应混入普通数据传播计数。
- 使用 bounded depth、visited set、SCC collapse、version/time predicate 和 scope filter。
- 返回 confirmed/likely/possible/unknown 四类集合和每条路径证据。
### Trust 降级条件
关键 source 或 consumer 缺失；edge freshness 超 TTL；schema contract 不匹配；residency evidence 无效；delete proof 未闭环；cycle 未解释；confidence 低于 policy；质量 snapshot 过期；projection 与 event 不一致。
### 影响输出
输出必须包含 query intent、root nodes、time window、scope、quality snapshot、coverage、confidence、unknown、excluded/quarantined、路径样本、policy assumptions 和 expiry。没有这些字段不能称为“完整影响分析”。
## DSAR、Deletion Proof 与 Residency Evidence
### DSAR 图路径
```text
subject/source
  -> context/prompt/model/tool
  -> event/session/checkpoint
  -> artifact/view/memory/cache/index
  -> provider remote object/backup
  -> delivery/business record
```
DSAR 查询不仅按文本搜索，还要按 subject identity、artifact hash、event association、tool/business key、tenant scope 和 derived relation 搜索。
### Deletion Proof
```typescript
interface DeletionProof {
  proofId: string;
  requestId: string;
  subjectRefs: string[];
  obligations: DeletionObligation[];
  coveredNodes: string[];
  coveredEdges: string[];
  remoteReceipts: EvidenceRef[];
  backupEvidence: EvidenceRef[];
  exceptions: DeletionException[];
  verifiedAt: string;
  status: "complete" | "partial" | "blocked" | "unknown";
}
```
### 删除验证
- 删除 intent、authorization、policy、retention 和 legal hold 必须可见。
- source 与所有 materialization/downstream consumer 要有覆盖关系。
- cache、memory、artifact view、backup、queue/DLQ、session replay 和 provider remote object 分开证明。
- provider delete accepted 不等于 remote delete confirmed；需要 status/settlement evidence。
- 发现 orphan、ambiguous、unknown、跨 region 或低 confidence 时，proof 为 partial/blocked。
- 删除后的 tombstone 保留最小 non-content evidence，避免重新暴露内容。
### Residency Evidence
记录 data node、artifact/view、provider request、remote object、backup、log、cache、region、jurisdiction、policy effective time、credential scope 和 provider receipt。跨区复制、fallback、replay、backfill、support export 和 incident bundle 都需要单独 edge 和 egress evidence。
### Residency 失败
未知或冲突的 region evidence 进入 quarantine；不能用 provider 默认 region、UI locale 或请求发起地推断实际存储位置。
## Drift Detection
### Drift 类型
- schema drift：字段、类型、required/optional、enum 或 version 改变。
- contract drift：允许的 node/edge、evidence、scope、time 或 deletion 规则改变。
- topology drift：source/consumer/transform 连接模式异常变化。
- provenance drift：confidence、evidence method、rule version 或 contradiction 增加。
- freshness drift：延迟、stale ratio、event-to-edge lag 变差。
- coverage drift：某 tenant、region、provider、tool 或 data class 的记录消失。
- semantic drift：同一 edge kind 的真实业务含义或 provider/tool 行为变化。
- policy/residency drift：purpose、retention、region、training、egress 或 credential scope 改变。
### 检测方法
使用 schema registry diff、contract fixture、历史基线、分位数、change point、graph motif、edge kind distribution、node degree、SCC、sample ground truth 和 incident correlation。drift 需要区分正常版本发布、流量结构变化和真实错误。
### Drift 响应
低风险 drift 可 warn 并增加采样；关键 schema/contract/residency drift 触发 release gate、quarantine、双写比较或 rollback。drift event 必须链接变更、affected scope、first observed、last known good 和验证计划。
## Quality Incident、Quarantine 与 Replay
### Quality Incident
```typescript
interface QualityIncident {
  incidentId: string;
  severity: "low" | "medium" | "high" | "critical";
  scope: LineageScope;
  dimensions: string[];
  firstObservedAt: string;
  lastObservedAt: string;
  affectedSnapshots: string[];
  suspectedCause?: string;
  budgetBurn: QualityBudgetConsumption;
  containment: string[];
  owner: string;
  status: "open" | "containing" | "repairing" | "verifying" | "closed";
}
```
### Incident 分类
- 缺边/孤立节点导致影响分析不完整。
- 错边、schema mismatch、scope crossing 导致影响分析错误。
- stale/freshness lag 导致治理决策过期。
- duplicate/cycle/ambiguity 导致路径和删除证明不可信。
- DSAR/deletion/residency evidence gap。
- provider/tool/artifact/workflow 变更造成 lineage drift。
### Quarantine
quarantine 可以作用于 edge、node、subgraph、tenant partition、artifact view、provider surface、backfill job 或 impact result。必须有 reason、TTL、owner、entry evidence、解除条件、下游阻断范围、可读 forensic view 和 audit。
### Repair 与 Replay
repair 分为：补 node、补 edge、reclassify、reject、supersede、merge、split、补 evidence、降低 confidence、重建 projection。replay 使用 recorded event、受控 provider/tool fake、固定 snapshot 和 side-effect deny；不能在生产图中直接写 repair 结果，先写 proposed/candidate，再经过 gate。
### Incident 关闭条件
根因已定位或接受 residual risk；关键 quality budget 恢复；受影响图完成 incremental/batch verification；impact/deletion/residency 结果重新计算；quarantine 解除或转 permanent；runbook、fixture、alert 和 owner 已更新。
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### Model/Provider
ModelRef、ResolvedModel、ModelCapabilities、ProviderSurface、Attempt、UsageLedger、RouteSnapshot 和 Provider Recovery Receipt 都是 lineage nodes/evidence。模型请求的 reads/derives/emits/materializes 边必须区分 prompt input、context view、output、usage 和 tool proposal。
### Prompt
PromptPlan 保存模板版本、role、变量来源、tool instructions、output schema、policy notice、source hash 和 compiler version。prompt 不是最终事实；应通过 event/artifact/context edges 记录实际发送的可验证版本。
### Context
ContextPlan 记录 source、priority、freshness、resource version、visibility、token estimate、compaction、artifact view 和 egress。被压缩、摘要、截断、引用或 offload 的关系必须有 transforms/derives edges。
### Tool
ToolContract、ToolCall、ToolExecution、Sandbox、Approval、ToolReceipt、business operation id 和 result artifact 构成完整工具 lineage。只有 Proposed 不代表 consumed，只有 receipt 才能证明执行结果。
### State/Session
CanonicalEvent、SessionEntry、Checkpoint、Projector、UsageLedger 和 DeliveryReceipt 分别记录事实、聚合、恢复、投影、成本和用户/渠道交付。lineage validator 对齐 sequence、causation、correlation 和 version。
### Policy/Privacy
PolicySnapshot、EgressSnapshot、TenantContext、CredentialLease、ResidencyEvidence、Retention、DSAR 和 legal hold 是治理边。quality gate 不得替代 policy enforcement，但必须阻止不可信 lineage 支撑合规结论。
### Harness/Workflow
Run、Turn、Step、workflow dependency、subagent child scope、queue job、artifact、recovery checkpoint 和 final settlement 作为图节点。workflow 失败、retry、fallback、compensation 和 replay 产生新边，不能覆盖原路径。
## 可观测性、Dashboard 与 Alerts
### 指标
- `lineage_node_total{type,status,scope_class}`。
- `lineage_edge_total{kind,status,confidence_band}`。
- `lineage_quality_dimension{dimension,scope_class}`。
- completeness、correctness、timeliness、freshness、consistency、uniqueness、coverage 分数。
- orphan、ambiguous、cycle、duplicate、stale、quarantine、unknown、schema mismatch 数量。
- edge write latency、validation latency、batch scan duration、backfill lag、rebuild lag。
- evidence age、confidence distribution、ground-truth agreement、impact trust ratio。
- deletion proof completeness、residency unknown、DSAR backlog、remote receipt lag。
- quality budget burn、incident MTTD/MTTR、repair rejection、replay divergence。
### Dashboard
1. 全局质量：各维度、分母、样本数、预算、SLO、趋势和关键 scope。
2. 图健康：node/edge 状态、orphan、ambiguity、cycle、duplicate、SCC 和高风险路径。
3. 证据：confidence、evidence kind、freshness、contradiction、provider/tool/artifact receipt。
4. 治理：DSAR、deletion proof、residency、retention、legal hold、cross-tenant findings。
5. 变更：schema/contract/provider/tool/workflow/prompt/context 版本与 drift。
6. 运营：quality incident、quarantine、backfill、rebuild、queue、replay、repair 和 owner。
### Alerts
- 关键 source/consumer 的 completeness 或 coverage 突降。
- correctness、scope crossing、schema mismatch、residency unknown 或 deletion proof gap。
- orphan/ambiguous/cycle 超预算或持续增长。
- freshness/timeliness 超 SLO，尤其是 DSAR、provider receipt 和 artifact manifest。
- impact trust 从 trusted 降为 conditional/untrusted。
- 版本发布后 topology/provenance drift。
- quality gate 被绕过、quarantine edge 被消费或 repair 直接写 active。
- backfill/rebuild 与增量 high-water mark 不一致。
### 查询安全
Dashboard 默认聚合和脱敏；下钻需要 scope authorization、purpose、audit、TTL 和最小 evidence view。错误消息不泄露其他 tenant 的 node/edge existence。
## 测试策略与 Test Matrix
### 单元测试
覆盖 canonical key、edge direction、valid time、scope、purpose、schema/contract、evidence hash、freshness、confidence、duplicate、orphan、ambiguity、SCC、budget 和 gate。
### Property-based 测试
随机生成 DAG、合法 cycle、版本分支、duplicate edge、时间倒流、跨 scope、missing node、schema drift、事件重复和 correction event，验证 validator 不崩溃、visited set 终止、confidence 不越界、原始事实不被覆盖。
### Contract 测试
对 Provider Runtime、Tool Runtime、ArtifactStore、EventStore、Workflow、Policy、Egress、Credential、Data Governance 和 Data Quality 的事件/接口 schema 做兼容与语义测试。
### Test Matrix
| 类别 | 输入/故障 | 期望结果 |
|---|---|---|
| completeness | expected edge 未产生 | finding、budget burn、gate 依据分级 |
| correctness | from/to 反向、错误 kind | invalid，不进入 active |
| timeliness | queue/store/projector 延迟 | lag 分段、SLO/incident，不伪造 freshness |
| freshness | source version 已过期 | stale edge、impact trust 降级 |
| consistency | event/artifact/checkpoint 冲突 | reconcile/quarantine，不覆盖事实 |
| uniqueness | 同 key 重复 edge | dedup 或合法 attempt 解释 |
| coverage | 某 region/tenant 无样本 | coverage gap、不可宣称全局可信 |
| orphan | 缺 source/target node | expected lag、补 node 或 quarantine |
| ambiguous | 多个 candidate node | unresolved，不任意选择 |
| cyclic | 非法 self-loop/跨域 cycle | SCC finding、quarantine |
| schema | contract breaking change | release gate fail、迁移计划 |
| provenance | 只有 declared intent | low confidence，不用于删除证明 |
| sampling | ground truth 冲突 | adjudication、校准规则 |
| incremental | 新 event 局部影响 | 只扫描依赖集合且不漏关键 edge |
| batch | 全图历史 orphan/cycle | snapshot 一致、结果可重放 |
| backfill | 缺边重建 | proposed -> validated，经 gate 才生效 |
| rebuild | projector/index 重建 | old/new comparison，不改原事实 |
| impact | 关键路径低置信 | conditional/untrusted 和 unknown 输出 |
| DSAR | artifact/cache/remote 未证明删除 | proof partial/blocked |
| residency | cross-region evidence 冲突 | quarantine、禁止合规结论 |
| drift | schema/topology/contract 变化 | alert、gate、rollback 或采样 |
| quarantine | 下游请求隔离 edge | 阻断 materialization/impact，保留 forensic |
| replay | recorded/forked replay | 不污染生产图，记录 divergence |
| multi-tenant | cross-tenant edge | policy finding，不泄露 existence |
### Integration 测试
使用 fake provider、fake tool、deterministic event store、artifact manifest、policy fixture、clock、replay runner 和 synthetic tenants，验证完整 run -> context -> provider/tool -> artifact -> workflow -> delivery -> deletion 图。
### 回归基线
保存每次 schema/provider/tool/workflow/prompt/context 变更的 quality snapshot、sample set、ground truth、impact result、deletion proof 和 drift report，发布前比较维度、budget、confidence、coverage 和 unresolved。
## 反模式
1. 只检查 `from` 和 `to` 存在就认为 lineage valid。
2. 用日志关键词推断实际读取、复制或删除。
3. 把 declared intent 当作 observed fact。
4. 把一个 global completeness 分数当作所有 tenant/region 的质量。
5. 忽略 schema、contract、version、scope、purpose 和时间。
6. 将合法 retry/attempt 重复错误合并成一个 edge，丢失副作用语义。
7. 删除 orphan/ambiguous/cyclic 边而不保留 correction evidence。
8. 只做 incremental，不做 batch 全图扫描。
9. backfill 直接写 validated/active，跳过 proposed、证据和 gate。
10. rebuild projection 时修改 canonical events。
11. 用低置信 inference 支撑 DSAR、residency、删除或安全结论。
12. 把 provider delete accepted 当作 delete confirmed。
13. 把实时写入时间当作 source freshness。
14. 忽略 projector lag、queue lag、artifact lag 和 provider settlement lag。
15. 影响分析不返回 coverage、confidence、unknown 和质量 snapshot。
16. cycle detector 不区分合法 workflow loop 与非法自引用。
17. quality gate 只报警不阻止高风险 materialization。
18. quarantine 后仍允许 context、memory、cache 或 delivery 消费。
19. dashboard 直接展示跨 tenant 的 node/edge existence。
20. 质量 incident 关闭后不更新 validator、fixture、runbook、SLO 和 owner。
## 实施清单
### 数据与事件
- [ ] 定义 LineageNode、LineageEdge、EvidenceRef、ProvenanceInfo、Scope、Contract 和 QualitySnapshot。
- [ ] 为 Provider、Model、Prompt、Context、Tool、State、Workflow、Artifact、Memory、Cache、Delivery、Deletion 和 Residency 建立 node/edge contract。
- [ ] 所有 producer 发出 canonical event、causation、correlation、version、scope 和证据引用。
- [ ] 保证原始事实 append-only，correction/supersede/reject 使用新事件。
### 验证与质量
- [ ] 实现 identity、direction、time、schema、contract、scope、purpose、region、evidence、duplicate 和 cycle validation。
- [ ] 实现 completeness/correctness/timeliness/freshness/consistency/uniqueness/coverage 指标。
- [ ] 实现 quality budget、SLO、snapshot、分母定义、置信区间和关键 scope 分层。
- [ ] 实现 orphan、ambiguous、cyclic、stale、conflict、quarantine 和 unresolved findings。
- [ ] 实现 provenance confidence、evidence independence、contradiction penalty 和校准。
### 运行与治理
- [ ] 实现 write/incremental/nearline/batch/deep audit 多层验证。
- [ ] 实现 backfill、rebuild、dual-read/dual-write、dry-run、comparison、rollback 和 high-water mark。
- [ ] 实现 quality gate，阻止不可信图进入 impact、materialization、DSAR、residency 和 deletion proof。
- [ ] 接入 ArtifactStore、ProviderRuntime、ToolRuntime、Workflow、Policy、Egress、Credential、Privacy 和 Data Governance。
- [ ] 实现 DSAR/deletion proof、retention、legal hold、remote delete、backup 和 residency evidence。
### 影响与运营
- [ ] 影响分析输出 trust、coverage、confidence、freshness、quality snapshot、unknown 和 exclusions。
- [ ] 建立 quality incident、quarantine、repair、replay、manual adjudication 和关闭条件。
- [ ] 建立 dashboard、alerts、quality SLO、budget burn、MTTD/MTTR 和 on-call runbook。
- [ ] 建立 sampling、ground truth、标注、adjudication、回归集和 drift detection。
### 测试
- [ ] 完成单元、property-based、contract、integration、batch/incremental、DSAR/residency、multi-tenant 和 replay 测试。
- [ ] 建立 schema/provider/tool/workflow/prompt/context 变更的 quality release gate。
- [ ] 每次质量 incident 生成 fixture、postmortem、validator/contract 更新和 game day action。
## 五个参考项目启发来源
### Pi
session tree、headless agent loop、compaction entry 和事件化运行边界启发 lineage 记录 prompt/context/tool/model/output 的实际生命周期，而不是只从最终 transcript 猜关系。
### Grok Build
actor、工具运行时、权限决策、路径锁和 sandbox 分层启发 lineage edge 必须带 owner、scope、execution、resource lock、permission 和 side-effect evidence。
### OpenCode
client/server、session/message/part、durable event、projector、snapshot/patch/revert 和多客户端事件流启发 canonical lineage 与 projection、replay、repair 分离。
### Claude Code
permissions、hooks、subagents、skills、memory、MCP 和 workflow 启发 lineage 需要覆盖工具、审批、子代理、记忆、插件、计划和交付，而不是只覆盖模型输入输出。
### OpenClaw
AgentHarness registry、agent-core、Gateway、provider runtime、tool/sandbox/elevated 和插件注册启发多 provider、多渠道、多插件环境下的 scope、residency、credential、quarantine 和版本 lineage。
这些启发仅归纳本地参考材料中的工程模式，不把任一项目当作现成 Lineage Quality 规范。
## Definition of Done
- [ ] 已明确 Lineage Quality 不是简单检查 from/to。
- [ ] 已覆盖 completeness、correctness、timeliness、freshness、consistency、uniqueness、coverage、quality budget 与 quality SLO。
- [ ] 已覆盖 edge validation、orphan、ambiguous、cyclic、schema/contract alignment、provenance confidence、sampling、ground truth、incremental/batch verification、backfill/rebuild 和 quality gates。
- [ ] 已覆盖 impact-analysis trust、DSAR/deletion proof、residency evidence、drift、quality incident、quarantine、replay、dashboard、alerts 和 test matrix。
- [ ] 关键结论均绑定 evidence、scope、时间、版本、confidence、coverage、unresolved findings 和 quality snapshot。
- [ ] 文档可直接拆分为数据模型、validator、scanner、budget、gate、impact analyzer、governance proof、incident、metrics、runbook 与测试任务。
