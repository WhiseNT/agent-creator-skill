# Agent Memory Evaluation Engineering 细粒度工程设计
> 本文定义 Agent Memory 的工程评测系统：它评测 memory candidate、write、recall、edit、delete、forget、DSAR 和 provider egress 的完整轨迹、状态、副作用、隐私结果与用户控制，而不是对最终回答做一次文本打分。
>
> 设计依据仅来自当前目录已有的参考架构、`agent-harness.md`、State & Memory、Agent Memory Product、Agent Memory Governance、Context、Prompt、Harness、Tool、Permission & Sandbox、Subagent、Event & Observability、Evaluation、Workflow Orchestration、Workflow Versioning、Durable Queue、Data Governance、Privacy、Agent Product、Provider Runtime 文档以及五个参考项目的本地源码调研结论；不依赖 README，不进行网络搜索。
>
> 核心判断：**Memory Evaluation 不是“用一个分数评价记忆好不好”**。它必须将语义质量、状态真实性、scope/permission、隐私删除、成本延迟和用户控制拆成可解释维度；确定性事实由 oracle 判定，LLM judge 只处理规则难以表达的语义问题。
## 目录
1. [设计目标与非目标](#设计目标与非目标)
2. [核心判断与职责边界](#核心判断与职责边界)
3. [Memory Evaluation 与普通 LLM Judge 的边界](#memory-evaluation-与普通-llm-judge-的边界)
4. [总体架构与包布局](#总体架构与包布局)
5. [评测对象、真值和不确定性](#评测对象真值和不确定性)
6. [核心数据模型与 TypeScript 接口](#核心数据模型与-typescript-接口)
7. [Golden Memory Set](#golden-memory-set)
8. [Dataset 类型与数据治理](#dataset-类型与数据治理)
9. [Scenario 与轨迹 Fixture](#scenario-与轨迹-fixture)
10. [Scripted Model、Fake Store 与 Testkit](#scripted-modelfake-store-与-testkit)
11. [评测生命周期与状态机](#评测生命周期与状态机)
12. [Candidate 轨迹评测](#candidate-轨迹评测)
13. [Write 轨迹评测](#write-轨迹评测)
14. [Recall 轨迹评测](#recall-轨迹评测)
15. [Edit、Revision 与 Conflict 评测](#editrevision-与-conflict-评测)
16. [Delete、Forget 与 Tombstone 评测](#deleteforget-与-tombstone-评测)
17. [DSAR、Export 与 Retention 评测](#dsarexport-与-retention-评测)
18. [Memory Quality Dimensions](#memory-quality-dimensions)
19. [Precision、Recall 与 Necessity](#precisionrecall-与-necessity)
20. [Faithfulness、Freshness 与 Conflict](#faithfulnessfreshness-与-conflict)
21. [Privacy、Scope、Utility 与 User Control](#privacyscopeutility-与-user-control)
22. [Ground Truth、Uncertainty 与标注协议](#ground-truthuncertainty-与标注协议)
23. [Deterministic Oracle 与 LLM Judge](#deterministic-oracle-与-llm-judge)
24. [Offline Replay](#offline-replay)
25. [Online Shadow 与 Canary](#online-shadow-与-canary)
26. [Counterfactual Recall](#counterfactual-recall)
27. [Poisoning、Injection、Leakage 与对抗测试](#poisoninginjectionleakage-与对抗测试)
28. [Human Review 与仲裁](#human-review-与仲裁)
29. [Metrics、Thresholds 与 SLO](#metricsthresholds-与-slo)
30. [成本、延迟与容量](#成本延迟与容量)
31. [Evaluation Artifact 与证据包](#evaluation-artifact-与证据包)
32. [回归分诊与发布门禁](#回归分诊与发布门禁)
33. [与 Model、Prompt、Context、Tool、State、Policy、Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
34. [安全、隐私、Retention 与 DSAR](#安全隐私retention-与-dsar)
35. [故障恢复与未知结果](#故障恢复与未知结果)
36. [测试策略与 Conformance](#测试策略与-conformance)
37. [反模式与审查规则](#反模式与审查规则)
38. [实施清单](#实施清单)
39. [五个参考项目的启发来源](#五个参考项目的启发来源)
40. [Definition of Done](#definition-of-done)
## 设计目标与非目标
### 目标
Memory Evaluation Harness 必须能够：
- 评测从 source evidence 到 candidate、active record、RecallView、ContextPlan 和 provider request 的完整链路。
- 区分 memory 的语义质量、治理正确性、执行真实性、隐私传播和用户体验。
- 检查 `MemoryType`、`MemoryScopeRef`、`ProvenanceChain`、`ConfidenceBreakdown`、`TTL`、`Sensitivity` 和 `RetentionPolicy` 是否保持语义。
- 评测 candidate 是否应该存在，而不是只评测 candidate 文本是否流畅。
- 评测 write 是否真实产生 `MemoryEntry`、版本、receipt、index job 和 durable 状态。
- 评测 recall 是否选择正确 memory、排除错误 scope、标记 stale/conflicted，并遵守 token/egress budget。
- 评测 edit/revision 是否保留 lineage、CAS、冲突集和用户控制，而不是覆盖旧事实。
- 评测 delete/forget/DSAR 是否传播到 canonical、index、embedding、cache、artifact、backup、queue 和 provider copy。
- 提供 golden memory set、synthetic dataset、real/de-identified dataset、counterfactual pair 和 regression fixture。
- 以 deterministic oracle 优先判断状态、权限、删除、泄漏、SLO 和副作用。
- 在确有必要时使用 LLM judge 判断语义相关性、未来复用价值、summary 忠实度和解释可理解性。
- 支持 offline replay、online shadow、canary、human review、版本对比和 ablation。
- 为每次评测保留可脱敏、可重放、可审计的 Evaluation Artifact。
- 形成按维度的阈值、SLO、回归分诊和 release gate，而不是单一总分。
### 非目标
本模块不负责：
- 代替 MemoryStore、MemoryGovernancePort、RecallPort 或 PolicyEngine 执行真实业务逻辑。
- 把测试用的 LLM judge 当作 canonical truth、权限判断器或删除证明。
- 默认保存完整生产 transcript、原始 PII、secret、regulated 内容或 provider payload。
- 以单一综合分数掩盖 wrong-scope recall、secret leakage、delete failure 或 unknown outcome。
- 让评测环境绕过现有 Harness、Policy、Sandbox、Egress、Retention 或 DSAR 约束。
- 用公开 benchmark 的平均分直接推断当前 tenant、workspace 或用户体验。
- 承诺所有 memory 事实都有唯一确定答案；部分事实必须显式表达 uncertainty。
- 把离线高分直接等同为生产可用，或把 shadow 观察当作用户可见执行。
- 通过修改数据集标签来消除真实冲突，而不是记录冲突和标注依据。
### 质量公式
```text
Memory Evaluation Quality
  = Coverage
  × Ground-truth Integrity
  × Oracle Correctness
  × Privacy Safety
  × Reproducibility
  × Operational Usefulness
```
任一项接近零，评测结果就不能作为发布证据。
## 核心判断与职责边界
### 三种 truth
```text
Source Truth       原始用户陈述、工具 receipt、文件版本、业务事实
Memory Truth       canonical memory record、revision、tombstone、receipt
Evaluation Truth   fixture、label、oracle、judge、threshold 和观察证据
```
Evaluation Truth 只能评估 Memory Truth，不能反向覆盖生产事实。
### 组件职责
| 组件 | 负责 | 不负责 |
|---|---|---|
| `DatasetRegistry` | 数据集版本、manifest、来源、脱敏、污染状态 | 运行 memory write |
| `GoldenMemorySet` | 期望 memory、负例、scope、时效和冲突标签 | 代替线上 MemoryStore |
| `ScenarioCompiler` | 将案例编译成可执行 fixture 和断言 | 修改生产 policy |
| `EvaluationRunner` | 装配 Harness、执行、采集和结算 | 解释所有语义质量 |
| `MemoryOracle` | 状态、scope、privacy、删除、receipt 和副作用断言 | 生成任意黄金标签 |
| `RecallMetricEngine` | precision/recall/utility/freshness 等聚合 | 决定单条事实的法律真值 |
| `LLMJudge` | 语义相关性、价值、忠实度和解释评价 | 判断真实写入、越权、删除和 SLO |
| `HumanReviewQueue` | 边界案例、冲突仲裁、标注更新 | 无审计修改生产 memory |
| `ReleaseGate` | 根据硬门禁、软阈值、趋势和风险发布 | 绕过 hard fail |
| `ArtifactStore` | 证据包、脱敏轨迹、报告和长输出 | 决定评测结论 |
| `Harness` | 真实装配路径、隔离、取消、恢复、事件和 host | 变成评测专用 loop |
### 依赖方向
```text
Dataset -> Scenario -> EvaluationRunner -> Real Harness Assembly
                                      -> Oracle / Judge / Human Review
                                      -> Artifact / Report / Release Gate
```
评测代码可以替换 `ModelPort`、`MemoryStore`、`Clock`、`ID`、`Queue`、`Provider Egress` 和 `Host`，但不应复制另一套 Memory 产品逻辑。
## Memory Evaluation 与普通 LLM Judge 的边界
### 普通 LLM Judge 适合什么
- 当前 task 与召回 memory 是否语义相关。
- candidate 是否看起来具有未来复用价值。
- summary 是否保留 source 的关键条件和限定。
- 冲突解释是否能被用户理解。
- 用户可见的 memory notice 是否清楚、完整和不过度承诺。
- 开放式、规则难表达的 memory utility 评价。
### 普通 LLM Judge 不适合什么
- memory 是否已经真实写入 canonical store。
- write 是否生成了正确 `MemoryEntry`、version 和 receipt。
- recall 是否跨 tenant、workspace、session 或 subagent 越权。
- tombstone 后 embedding、cache、artifact 或 provider copy 是否仍可召回。
- DSAR 是否覆盖所有派生对象。
- TTL、retention、SLO、queue lease、幂等和事件顺序是否满足。
- tool side effect 是否真实发生或发生次数是否正确。
- secret、regulated、raw PII 是否离开允许边界。
- unknown outcome 是否被错误标成 failed 或 success。
### 强制判定原则
```text
可由 schema、状态机、hash、scope、receipt、side-effect ledger 判断 -> deterministic oracle
只能由语义、可读性、未来价值判断 -> LLM judge 或 human review
两者都困难 -> 标记 inconclusive，不伪造 certainty
```
“模型说已经记住了”永远不能替代 `MemoryEntry`、scope、TTL、receipt、index 状态和 deletion path。
## 总体架构与包布局
```text
Dataset Registry
  -> Evaluation Planner
  -> Scenario / Variant Compiler
  -> Isolated Evaluation Harness
       ├─ ScriptedModel / ShadowModel
       ├─ FakeMemoryStore / ReadOnlyMirror
       ├─ FakeIndex / Cache / Artifact / Provider Egress
       ├─ FakePolicy / Approval / Queue / Clock
       └─ Real Context / Prompt / State / Harness paths
  -> Observation Bundle
       ├─ Candidate / Write / Recall / Delete / DSAR trajectory
       ├─ Canonical events / semantic entries / checkpoints
       ├─ Memory state / index state / provider request
       ├─ Side-effect ledger / artifact manifest
       └─ Usage / latency / cost / diagnostics
  -> Oracle Engine
       ├─ State / Scope / Privacy / Deletion oracles
       ├─ Trajectory assertions
       ├─ Quality metric engine
       └─ Optional LLM judge / human review
  -> Evaluation Artifact Store
  -> Regression Triage
  -> Release Gate / Online Monitor
```
### 推荐包布局
```text
packages/memory-eval/
  contracts.ts
  dataset.ts
  golden-set.ts
  scenario.ts
  runner.ts
  replay.ts
  oracle.ts
  quality-metrics.ts
  privacy-tests.ts
  counterfactual.ts
  judge.ts
  human-review.ts
  artifacts.ts
  regression.ts
  release-gate.ts
  online-shadow.ts
  testkit/
```
## 评测对象、真值和不确定性
### 评测对象
至少区分以下对象：
- `MemoryCandidate`：建议保存但尚未成为 active 的候选。
- `MemoryRecord`：已持久化、版本化、带 provenance 的记录。
- `RecallPlan`：过滤、排序、预算和 egress 前的计划。
- `RecallView`：交给 ContextPlan 或 provider 的安全投影。
- `MemoryRevision`：基于旧版本的新事实或用户编辑。
- `MemoryTombstone`：forget/delete 后阻止复活的治理事实。
- `GovernanceDecisionReceipt`：purpose、scope、sensitivity、policy 和 egress 证据。
- `EvaluationArtifact`：评测证据包，不是业务 memory。
### Truth level
```typescript
type TruthLevel =
  | "deterministic"
  | "verified_source"
  | "human_consensus"
  | "annotator_consensus"
  | "probabilistic"
  | "unknown";
```
- `deterministic`：状态、hash、ID、scope、数量、事件顺序等可计算事实。
- `verified_source`：来自明确用户陈述、可信工具 receipt 或固定文件版本的事实。
- `human_consensus`：多个合格审阅者一致确认的语义标签。
- `annotator_consensus`：标注者在协议下达成的可接受一致。
- `probabilistic`：存在合理分歧，只能给区间或概率。
- `unknown`：证据不足，不允许假装为 negative 或 positive。
### Uncertainty 记录
```typescript
interface UncertaintyLabel {
  state: "certain" | "likely" | "ambiguous" | "unknown";
  probability?: number;
  interval?: [number, number];
  reasons: string[];
  evidenceRefs: ResourceRef[];
  reviewerCount: number;
  adjudicated: boolean;
}
```
评测聚合时：
- hard gate 只接受确定性证据。
- uncertain 样本进入单独分桶，不与明确通过混合。
- 争议标签保留正、负和 abstain 版本。
- 报告中展示覆盖率与 uncertainty rate。
## 核心数据模型与 TypeScript 接口
### 基础标识
```typescript
type EvaluationRunId = string;
type DatasetId = string;
type DatasetVersionId = string;
type ScenarioId = string;
type VariantId = string;
type ObservationId = string;
type AssertionId = string;
type MetricId = string;
type ArtifactId = string;
type ReviewId = string;
type MemoryId = string;
type CandidateId = string;
type RecallId = string;
type TombstoneId = string;
```
### EvaluationSuite
```typescript
interface MemoryEvaluationSuite {
  schemaVersion: string;
  suiteId: string;
  name: string;
  dataset: DatasetDescriptor;
  scenarios: MemoryEvaluationScenario[];
  defaults: MemoryEvaluationDefaults;
  releaseProfile?: ReleaseGateProfile;
  provenance: DatasetProvenance;
}
```
### Scenario
```typescript
interface MemoryEvaluationScenario {
  id: ScenarioId;
  name: string;
  purpose: "candidate" | "write" | "recall" | "edit" | "forget" | "dsar" | "security" | "recovery";
  task: MemoryTaskFixture;
  initialMemory?: MemoryFixture[];
  sourceEvidence: EvidenceFixture[];
  policy: MemoryPolicyFixture;
  environment: MemoryEvaluationEnvironment;
  model?: ModelFixture;
  faults?: FaultPlan[];
  variants?: MemoryEvaluationVariant[];
  assertions: MemoryAssertion[];
  metrics: MetricSpec[];
  budgets: EvaluationBudget;
  risk: "low" | "medium" | "high" | "critical";
  provenance: ScenarioProvenance;
}
```
### MemoryFixture
```typescript
interface MemoryFixture {
  id: MemoryId;
  versionId: string;
  type: MemoryType;
  content: MemoryContent;
  scope: MemoryScopeRef;
  status: MemoryStatus;
  provenance: ProvenanceChain;
  confidence: ConfidenceBreakdown;
  sensitivity: Sensitivity;
  lastVerifiedAt?: string;
  expiresAt?: string;
  sourceHash: string;
  recordHash: string;
}
```
### ObservationBundle
```typescript
interface MemoryObservationBundle {
  evaluationRunId: EvaluationRunId;
  scenarioId: ScenarioId;
  variantId: VariantId;
  status: "passed" | "failed" | "error" | "inconclusive";
  candidateTrace: CandidateTrace[];
  mutationTrace: MemoryMutationTrace[];
  recallTrace: RecallTrace[];
  deleteTrace: DeleteTrace[];
  dsarTrace?: DsarTrace;
  events: CanonicalEvent[];
  entries: SessionEntry[];
  finalMemory: MemoryStoreSnapshot;
  derivedState: DerivedMemoryState;
  providerRequests: ProviderRequestObservation[];
  sideEffects: SideEffectRecord[];
  artifacts: ArtifactRef[];
  usage: UsageSummary;
  latency: LatencySummary;
  diagnostics: Diagnostic[];
  reproducibility: ReproducibilityRecord;
}
```
### CandidateTrace
```typescript
interface CandidateTrace {
  candidateId: CandidateId;
  sourceEntryIds: EntryId[];
  proposedType: MemoryType;
  proposedScope: MemoryScopeRef;
  proposedPurpose: PrivacyPurpose[];
  evidenceRefs: ResourceRef[];
  stateTransitions: MemoryStateTransition[];
  decision?: GovernanceDecisionReceipt;
  userInteraction?: "none" | "shown" | "edited" | "confirmed" | "rejected" | "expired";
}
```
### RecallTrace
```typescript
interface RecallTrace {
  recallId: RecallId;
  queryHash: string;
  requestedScope: MemoryScopeRef;
  candidateIds: MemoryId[];
  selectedIds: MemoryId[];
  droppedIds: MemoryId[];
  filteredReasons: Record<string, string[]>;
  views: GovernedRecallView[];
  contextPlanHash?: string;
  egressDecision?: EgressDecision;
  latencyMs: number;
}
```
### DeleteTrace 与 DSAR
```typescript
interface DeleteTrace {
  requestId: string;
  memoryIds: MemoryId[];
  tombstones: MemoryTombstone[];
  dependencyStates: DeletionDependencyState[];
  recallChecks: RecallCheck[];
  providerDeleteChecks: ProviderDeleteCheck[];
  finalState: "verified" | "partial" | "blocked" | "unknown";
}
interface DsarTrace {
  requestId: string;
  subject: PrincipalRef;
  inventory: DsarInventoryItem[];
  exportedViews: ArtifactRef[];
  deletionPlan: DeletionPlan;
  completion: "complete" | "partial" | "blocked" | "unknown";
  limitations: string[];
}
```
### Assertion 与结果
```typescript
interface MemoryAssertion {
  id: AssertionId;
  kind: "state" | "event" | "scope" | "privacy" | "quality" | "latency" | "cost" | "side_effect" | "human_review";
  severity: "hard" | "soft" | "informational";
  expression: AssertionExpression;
  expected?: unknown;
  oracle: "deterministic" | "llm_judge" | "human" | "hybrid";
}
interface AssertionResult {
  assertionId: AssertionId;
  status: "passed" | "failed" | "error" | "inconclusive";
  value?: unknown;
  evidenceRefs: ArtifactRef[];
  reasons: string[];
}
```
## Golden Memory Set
### 定义
`GoldenMemorySet` 是经过版本化、来源审查和标注协议约束的 memory 期望集合。它不只保存“应该召回哪些文本”，还保存：
- 当前 task purpose。
- 允许的 scope 和禁止的 scope。
- memory type 与字段级敏感度。
- source evidence 与 source hash。
- freshness window、TTL 和失效条件。
- 必须写入、允许 candidate、必须拒绝和必须不 recall 的集合。
- 语义等价、条件共存、冲突和 abstain 标签。
- 允许的 RecallView 形态：inline、summary、artifact_ref、metadata_only。
- 用户控制期望：是否提示确认、是否可编辑、是否可撤回。
### 数据模型
```typescript
interface GoldenMemorySet {
  id: string;
  version: DatasetVersionId;
  scope: "global" | "tenant" | "workspace" | "scenario";
  records: GoldenMemoryRecord[];
  negativeRecords: GoldenNegativeMemory[];
  conflictSets: GoldenConflictSet[];
  taskQueries: GoldenRecallQuery[];
  annotationProtocol: AnnotationProtocol;
  reviewedAt?: string;
  integrityHash: string;
}
interface GoldenMemoryRecord {
  canonicalId: string;
  equivalentForms: string[];
  type: MemoryType;
  sourceEvidenceIds: string[];
  expectedScope: MemoryScopeRef;
  expectedPurpose: PrivacyPurpose[];
  requiredState: "candidate" | "active" | "confirmed" | "forbidden";
  freshness: FreshnessExpectation;
  sensitivity: Sensitivity;
  userControl: UserControlExpectation;
  uncertainty: UncertaintyLabel;
}
```
### Golden set 变更
- 标签变更生成新 dataset version，不覆盖历史标签。
- 每次变更记录 reason、reviewer、source hash 和影响场景。
- 删除 production-derived case 时保留最小 case tombstone，阻止旧 artifact 复活。
- golden set 不包含 provider secret、不可脱敏的 regulated 原文或永久共享链接。
- 同一案例的 positive、negative、uncertain 版本必须可区分。
## Dataset 类型与数据治理
### Synthetic dataset
用于：
- 大规模覆盖 candidate/write/recall/delete 状态组合。
- 生成 secret、PII、regulated、scope crossing、TTL 和 conflict 负例。
- 注入确定的时钟、版本、hash、provider error 和 queue fault。
- 进行 property-based、load 和 fuzz 测试。
要求：
- 生成器本身版本化。
- synthetic value 明确标记，不冒充真实用户。
- secret 使用不可用的合成 token，不使用生产凭据。
- 生成的语义关系仍需通过规则或人工抽样校验。
### Real dataset
用于：
- 观察真实 task 分布、纠正行为、recall 失败和用户控制路径。
- 分析 freshness、scope、utility、latency 和成本。
- 发现 synthetic dataset 未覆盖的长期演化和冲突。
要求：
- 通过 purpose、consent、tenant policy 和最小化门槛。
- 默认不把原始 transcript 直接加入 golden set。
- 仅保留最小 evidence、hash、结构化字段和脱敏 view。
- 生产数据只能在隔离、访问审计和短 retention 评测环境中使用。
### De-identified dataset
- 记录去标识化方法、版本、残余关联风险和 reviewer。
- 同一主体的关系一致性必须保留，但 tokenization map 只能在可信边界保存。
- 不能把不可逆 hash 自动称为匿名化。
- 去标识化失败或分类未知时降级为 restricted、quarantine 或 deny。
### Dataset manifest
```typescript
interface DatasetDescriptor {
  datasetId: DatasetId;
  versionId: DatasetVersionId;
  kind: "synthetic" | "real" | "de_identified" | "mixed";
  sourceRefs: ResourceRef[];
  schemaVersion: string;
  generatorVersion?: string;
  redactionProfile?: string;
  contaminationRisk: "low" | "medium" | "high";
  retention: RetentionPolicy;
  allowedPurposes: PrivacyPurpose[];
  split: "train" | "dev" | "test" | "shadow" | "canary";
  manifestHash: string;
}
```
## Scenario 与轨迹 Fixture
### 轨迹优先
每个 scenario 至少定义：
- 输入 evidence 和来源。
- 当前 tenant、user、workspace、session、branch 和 run scope。
- 当前 memory policy、consent、retention、provider egress 和 index version。
- scripted model 行为或 live model variant。
- 预期 candidate、write、recall、edit/delete 或 DSAR 轨迹。
- 必须保留和必须禁止的 event、entry、receipt、provider field 和 side effect。
- 故障注入点、恢复步骤和允许的 unknown 状态。
- hard assertions、soft metrics、human review 和 budget。
### Scenario 分类
```text
candidate extraction
explicit remember intent
negative remember intent
automatic write gate
confirmed write
scope narrowing
recall relevant
recall stale
recall conflict
recall wrong scope
edit and revision
forget and tombstone
DSAR inventory
provider egress denial
memory poisoning
prompt injection
subagent inheritance
compaction flush
index lag
worker crash
provider upload unknown
```
### 最小 fixture 原则
- 一个 scenario 验证一个主要主题。
- 需要多个维度时使用 variant，而不是复制隐含状态。
- fixture 自包含，不依赖开发机时间、随机数、环境变量或最新 provider。
- 输入、memory、artifact、policy 和 model script 都有 hash。
- 每个 scenario 同时覆盖正向、负向、边界、拒绝和 unknown 路径。
## Scripted Model、Fake Store 与 Testkit
### 必备组件
```text
ScriptedModel
FakeMemoryStore
FakeMemoryIndex
FakeRecallCache
FakePolicyProfileResolver
FakeConsentStore
FakeDlpScanner
FakeRedactor
FakeProviderEgress
FakeArtifactStore
FakeQueue
FakeApprovalStore
FakeRemoteStatus
DeterministicClock
DeterministicIds
DeterministicRandom
EventRecorder
SideEffectRecorder
CrashInjector
ReplayRunner
HumanReviewStub
```
### ScriptedModel
```typescript
interface ScriptedModel {
  stream(request: ModelRequest, signal: AbortSignal): AsyncIterable<ModelEvent>;
  scriptId: string;
  expectedPromptHash?: string;
  expectedToolsetHash?: string;
  responsePlan: ModelResponsePlan[];
}
```
Script 可以表达：
- 无 memory action。
- 提出 `memory_suggest`。
- 声称已保存但不产生工具调用。
- 产生跨 scope、敏感字段或伪造 tenant 参数。
- 多次 recall、重复 write、错误 edit 和错误 forget。
- provider stream 中断、未知 event、长度截断和重复 delta。
- 在 recall 后改变答案，用于 counterfactual 观察。
### FakeMemoryStore 规则
Fake store 必须模拟真实 port 的：
- CAS、版本、tombstone、index lag 和 cache lag。
- active/candidate/conflicted/expired/forgotten/quarantined 状态。
- provenance、scope、sensitivity、TTL 和 retention。
- duplicate delivery、worker crash、unknown result 和 reconciliation。
- 不把测试便利 API 暴露给被测 Agent。
## 评测生命周期与状态机
### EvaluationRun 状态机
```text
created
  -> dataset_resolved
  -> environment_prepared
  -> policy_frozen
  -> scenario_running
  -> observation_collected
  -> oracle_evaluating
  -> judge_pending
  -> human_review_pending
  -> aggregated
  -> gate_evaluated
  -> completed
任意活动状态 -> failed
任意活动状态 -> cancelled
observation_collected -> inconclusive
```
### Scenario 状态机
```text
pending
  -> prepared
  -> candidate_observed
  -> mutation_observed
  -> recall_observed
  -> deletion_observed
  -> settled
prepared -> skipped | blocked | failed
任意状态 -> crashed -> recovering -> resumed | unknown | failed
```
### 评测顺序
```text
resolve dataset and split
  -> verify manifest and contamination state
  -> create isolated tenant/workspace/session
  -> freeze policy/consent/retention/egress snapshot
  -> seed source evidence and initial memory
  -> run candidate/write/recall/edit/delete/DSAR scenario
  -> flush durable events and checkpoints
  -> run deterministic oracles
  -> run permitted LLM judge or human review
  -> compute metrics and uncertainty
  -> build Evaluation Artifact
  -> compare baseline and evaluate release gate
```
## Candidate 轨迹评测
### 必须回答的问题
- 是否从允许的入口生成 candidate。
- candidate 是否有 source evidence、source hash、type、scope、purpose、sensitivity、TTL 和 expiry。
- 模型推断是否被错误升级为 active 或 confirmed。
- secret、regulated、高风险 PII 是否被 candidate gate 拦截或 quarantine。
- candidate 是否展示给用户，是否支持 edit、confirm、reject 和 suppression。
- 用户拒绝后是否避免重复通知同一 hash。
- compaction flush 是否只保存允许持久化的候选。
### Hard assertions
```text
candidate 必须有 source refs
candidate scope 不得宽于 source scope
candidate status 不得绕过确认门槛
candidate hash 变化后旧确认 token 失效
candidate 不得改变 toolset/policy/approval
candidate 事件必须 durable 或有等价 receipt
```
### Soft metrics
- candidate future-value precision。
- candidate false-positive rate。
- 用户查看率、确认率、编辑率、拒绝率。
- candidate explanation readability。
- 重复建议率。
## Write 轨迹评测
### 写入阶段
```text
observe evidence
  -> normalize claim
  -> classify type/scope/purpose
  -> attach provenance
  -> DLP/sensitivity
  -> duplicate/contradiction
  -> confidence/authority
  -> auto-write or candidate gate
  -> confirmation/approval
  -> append MemoryEntry
  -> index/cache job
  -> receipt and notification
```
### Hard assertions
- active write 必须有 canonical record、version、MemoryEntry 和 receipt。
- `MemoryRecord.recordHash` 与写入内容匹配。
- `sourceHash` 与 evidence snapshot 匹配。
- active、candidate、confirmed、quarantined 状态与 policy 结论一致。
- index 未完成时 UI 不得显示为 fully searchable。
- store 成功但 index 失败时不能报告未保存；应报告 index pending/degraded。
- write 失败或 unknown 时不能创建第二个 active record。
- 自动写入必须满足 strict auto gate 的每一个条件。
### Recall 关联
写入后评测不能只检查表中有记录，还要验证：
- 允许的 task purpose 可以按 policy recall。
- 不允许的 purpose 不能命中。
- stale、conflicted、forgotten 状态有正确过滤。
- provider request 只含 RecallView，而不是 raw MemoryRecord。
## Recall 轨迹评测
### Recall pipeline
```text
Task purpose
  -> resolve tenant/user/workspace/session scope
  -> load frozen memory policy
  -> consent/legal-basis check
  -> discover records
  -> status/owner/scope filter
  -> sensitivity/purpose/egress filter
  -> freshness/TTL/hold filter
  -> lexical/semantic ranking
  -> dedupe/conflict annotation
  -> token budget
  -> RecallView
  -> ContextPlan
  -> provider egress
  -> receipt
```
### Hard assertions
- wrong tenant、workspace、session、branch、subagent memory 不得进入 selected。
- forgotten、expired、quarantined、disabled 记录默认不得进入 active recall。
- RecallView 不得暴露 owner internals、delete token、raw secret 或 tokenization map。
- `selectedIds`、`droppedIds`、reason codes 和 view hash 必须可解释。
- recalled memory 不得获得 instruction authority、工具注册权或 approval 权限。
- provider fallback 必须重新做 egress decision。
- ContextPlan token budget 和 sensitivity ceiling 必须生效。
### 评测对照
每个 query 至少准备：
- required positive memories。
- optional positive memories。
- relevant-but-stale memories。
- semantically similar but wrong-scope memories。
- contradictory memories。
- privacy forbidden memories。
- decoy memories。
## Edit、Revision 与 Conflict 评测
### 评测重点
- edit 是否要求 owner、expectedVersion 和可编辑字段。
- 用户编辑是否产生新版本而不是覆盖旧记录。
- provenance、audit lineage、tenant owner 和 tombstone 是否不可篡改。
- 新版本是否重新分类 sensitivity、purpose、TTL、egress 和 conflict。
- 相同 authority、不同时间条件和 user direct/model inferred 是否按规则处理。
- CAS 冲突是否被暴露、重试是否有上限。
- conflict resolution 是否保留双方 source evidence。
### 断言
```text
edit(before) + revision -> old version remains queryable by audit policy
CAS mismatch -> no silent overwrite
policy conflict -> memory remains data, policy wins
model inference vs user direct -> user direct preferred
same scope/equal authority -> mark_review rather than arbitrary overwrite
```
## Delete、Forget 与 Tombstone 评测
### 语义区分
- `forget`：立即停止 recall，保留最小 tombstone。
- `delete`：清理 canonical 与允许清理的派生对象。
- `disable`：停止使用但保留可恢复记录。
- `expire`：停止 active recall，不等于立刻物理删除。
- `revoke_confirmation`：撤回确认，不等于历史不存在。
### 删除轨迹
```text
request
  -> authenticate/scope check
  -> purpose/hold check
  -> freeze write/recall
  -> enumerate dependencies
  -> append delete command
  -> tombstone commit
  -> immediate recall exclusion
  -> index cleanup
  -> embedding cleanup
  -> cache invalidation
  -> artifact/preview cleanup
  -> backup/provider handling
  -> verify
  -> deletion receipt
```
### Hard assertions
- tombstone commit 后 recall index 不得返回 active view。
- 旧 index 不能 resurrect forgotten memory。
- cache hit 必须是 miss 或 tombstone，而不是旧 content。
- provider delete unknown 不能被标记为 completed。
- deletion partial/blocked/unknown 必须在 receipt 和 UI 中明确。
- legal hold 只阻止物理删除，不自动允许 recall 或 egress。
- queue duplicate 不得重复执行不可逆 provider delete。
- 删除状态未知时先停止 recall，再执行 reconciliation。
## DSAR、Export 与 Retention 评测
### Inventory 覆盖
DSAR 评测必须枚举：
- active、candidate、revision、conflict、tombstone。
- raw、structured、searchable、embedding、lexical index、rerank cache 和 recall cache。
- ContextPlan 引用、compaction candidate、memory flush job 和 background queue。
- Artifact raw、summary、preview、export package、backup 和 replay fixture。
- subagent、child result、notification、provider remote object、request receipt。
- audit 中的最小治理事实和 deletion proof。
### Hard assertions
- 导出只包含 subject 有权查看的 scope。
- export package 有短 TTL、hash、访问审计和撤销能力。
- DSAR 不混入其他 tenant、workspace 或用户。
- provider copy 的删除能力或 limitation 必须被记录。
- retention reaper 不绕过 legal hold、incident hold 和 active recovery dependency。
- TTL 不能由后台任务静默延长。
- DSAR completion 只能在 manifest、依赖状态和限制说明齐全时标记 complete。
## Memory Quality Dimensions
### 维度总览
```text
precision
recall
necessity
faithfulness
freshness
conflict
privacy
scope
utility
user_control
```
维度之间不能互相抵消：
- 高 utility 不能抵消 privacy violation。
- 高 precision 不能抵消漏掉用户明确要求保存的事实。
- 高 recall 不能抵消 wrong-scope recall。
- 高 faithfulness 不能抵消 stale 或 policy conflict。
- 高 user satisfaction 不能证明 deletion 真实完成。
### 维度接口
```typescript
interface MemoryQualityVector {
  precision: MetricValue;
  recall: MetricValue;
  necessity: MetricValue;
  faithfulness: MetricValue;
  freshness: MetricValue;
  conflict: MetricValue;
  privacy: MetricValue;
  scope: MetricValue;
  utility: MetricValue;
  userControl: MetricValue;
  uncertaintyRate: MetricValue;
}
```
## Precision、Recall 与 Necessity
### Precision
`precision@k` 评估 selected memory 中有多少对当前 query、purpose 和 scope 真正有用或允许使用：
```text
precision@k = relevant_and_allowed_selected@k / selected@k
```
必须将以下情况单独计为错误，而不是普通不相关：
- wrong-scope。
- privacy-forbidden。
- stale-as-current。
- unresolved-conflict-as-fact。
- unconfirmed memory 在 policy 禁止时被 selected。
### Recall
`recall@k` 评估 required positive memory 是否被正确 selected 或以允许的 summary 形式投影：
```text
recall@k = required_positive_recalled@k / required_positive_available@k
```
用户明确说“记住”的内容漏写、漏召回或在允许任务中被过度过滤，应分别报告 write recall 和 retrieval recall。
### Necessity
necessity 衡量 selected memory 是否是完成当前 task 所必需或具有可证明边际价值：
```text
necessity = required_selected / selected
```
建议同时记录：
- 必需、明显有用、可选、无关、危险五档。
- memory-on 与 memory-off 的 counterfactual success 差异。
- 删除某条 memory 后是否出现用户重复输入或任务失败。
- token cost per useful memory。
## Faithfulness、Freshness 与 Conflict
### Faithfulness
评估 RecallView、summary 或 revision 是否忠实于 source evidence：
- 事实值是否保持。
- 时间、条件、限定词是否保持。
- provenance 是否可追溯。
- 推断是否被标为 inferred。
- summary 是否引入 source 没有的新权威语气。
- edit 是否保留用户意图和可审计 diff。
可用 deterministic field oracle 检查结构化字段；自然语言 summary 由 LLM judge + human sample 检查。
### Freshness
freshness 不是“最近创建”单一指标：
```text
freshness = verified_at age
  + source version validity
  + TTL remaining
  + dependency stability
  + task temporal fit
```
评测应覆盖：
- TTL 未到期但 source file 已变更。
- memory 过期后仍被召回。
- 新 user direct claim 未能 supersede 旧 inference。
- revalidation 后 freshness 恢复。
- provider/cache/index lag 导致旧 view。
### Conflict
冲突质量应包含：
- conflict detection rate。
- false conflict rate。
- unresolved conflict recall rate。
- policy conflict 被错误执行的次数。
- user direct 与 model inferred 的优先级正确率。
- 条件共存是否保留时间和 scope。
- 解释是否展示双方来源而不泄漏其他 tenant。
## Privacy、Scope、Utility 与 User Control
### Privacy
privacy 评测以 negative oracle 为主：
- secret/regulated 进入 provider request 为 hard fail。
- cross-tenant recall 为 hard fail。
- forget 后仍能在 recall/cache/embedding 命中为 hard fail。
- export 混入其他主体为 hard fail。
- provider delete unknown 被标 complete 为 hard fail。
### Scope
scope metric 分为：
```text
scope_precision = allowed_selected / selected
scope_recall = allowed_required_selected / allowed_required
scope_escape_rate = forbidden_selected / all_selected
```
scope 交集必须遵守：
```text
requested scope
  ∩ parent active scope
  ∩ assignment resources
  ∩ owner visibility
  ∩ tenant policy
  ∩ purpose policy
  ∩ sensitivity ceiling
  ∩ provider egress
```
### Utility
utility 不是最终答案正确率的同义词。应观察：
- memory-on 与 memory-off 成功率差。
- 用户重复提供信息次数。
- 工具参数一次成功率。
- 任务完成时间和 tool calls。
- user correction rate。
- memory 造成的错误路径、过度自信和额外成本。
- 每个 selected memory 的边际收益。
### User control
用户控制指标包括：
- candidate 展示率。
- 确认、编辑、拒绝和关闭操作成功率。
- 用户拒绝后重复建议率。
- forget request 到 recall exclusion 的 P95。
- DSAR 到 manifest 完成的 P95。
- 用户查看 recall explanation 的可理解性。
- UI 显示“已保存/已删除”与 durable receipt 的一致率。
## Ground Truth、Uncertainty 与标注协议
### Ground truth 来源层级
```text
user direct statement
  > trusted tool receipt / verified file version
  > human reviewed correction
  > multi-source agreement
  > model extraction
  > semantic similarity
```
这不是自动授权层级，而是事实与评测证据的优先参考。
### 标注表
```typescript
interface MemoryAnnotation {
  caseId: string;
  annotatorId: string;
  labelType: "write" | "recall" | "freshness" | "faithfulness" | "necessity" | "conflict" | "privacy" | "scope";
  label: string;
  confidence: "high" | "medium" | "low";
  evidenceRefs: ResourceRef[];
  rationale: string;
  abstain: boolean;
  createdAt: string;
  protocolVersion: string;
}
```
### 标注协议
- 先定义 scope、purpose、memory type 和时间条件，再判断相关性。
- 先判 hard privacy/scope，再判 utility 和语义质量。
- 允许 annotator abstain，不强迫二元标签。
- 双人独立标注，分歧进入 adjudication。
- 记录 Cohen/Fleiss agreement 或等价一致性指标。
- 高风险案例至少由具备数据治理和产品语义背景的 reviewer 复核。
- 标注协议升级生成新版本并重新计算受影响案例。
## Deterministic Oracle 与 LLM Judge
### Deterministic Oracles
优先使用：
- state machine oracle。
- event sequence oracle。
- scope/tenant/owner oracle。
- policy/approval/consent oracle。
- hash/source/provenance oracle。
- TTL/freshness oracle。
- index/cache/tombstone oracle。
- provider egress field oracle。
- side-effect ledger oracle。
- queue lease/idempotency oracle。
- cost/latency/SLO oracle。
### LLM Judge 约束
```typescript
interface JudgeSpec {
  modelRef: ModelRef;
  rubricVersion: string;
  dimensions: Array<"relevance" | "necessity" | "faithfulness" | "utility" | "explanation">;
  temperature: number;
  maxTokens: number;
  abstainAllowed: boolean;
  evidenceRequired: boolean;
}
```
Judge 输入必须包含最小、脱敏、带 source refs 的 view，不应包含：
- provider secret。
- deletion token。
- 其他 tenant 的存在性。
- hidden reasoning。
- 不必要的完整 transcript。
Judge 输出必须包含 label、rationale、evidence spans、confidence 和 abstain。
### Judge 校准
- 使用 golden semantic cases 校准 prompt 和 rubric。
- 与 human review 比较 precision、agreement、false accept 和 false reject。
- 对 judge model/provider 变更建立 conformance fixture。
- judge 失败、超时或 disagreement 时标记 inconclusive，不自动通过。
- judge 只能生成 soft metric，除非组织明确批准其成为低风险 release signal。
## Offline Replay
### Replay 定义
offline replay 使用已记录的 source evidence、initial memory、ContextPlan、ModelEvent、ToolEvent、policy snapshot、clock、random seed 和 provider fixture，在隔离 Harness 中重建轨迹。
```text
recorded durable entries/events
  -> restore fixture state
  -> replay old policy/runtime
  -> replay candidate/runtime variant
  -> compare trajectory/state/egress/side effects
```
### Replay 模式
- `state_replay`：只重建 Memory Center、Recall History 和 Privacy View。
- `event_replay`：重放 canonical events，不重新调用 provider。
- `live_reexecution`：在 fake/sandbox backend 中重新执行。
- `counterfactual_replay`：替换 memory selection 或 policy variant。
- `migration_replay`：旧 schema/upcaster 与新 runtime 对比。
### Replay 不变量
- 同一 durable entries 应重建同一 canonical memory view。
- projector 重放幂等。
- tombstone 不能被旧 index resurrect。
- replay 不应执行真实不可逆副作用。
- old run snapshot 不因 latest policy 变化而改变。
- provider request snapshot 与 egress decision 可验证。
## Online Shadow 与 Canary
### Shadow
shadow 只观察、不改变用户可见状态和真实 memory：
- 使用 sanitized input、summary、ref-only view 或只读 mirror。
- 不写 active memory、不触发真实 forget/delete/export。
- 不向真实 provider 发送未经允许的数据。
- shadow 的 candidate/recall 结果与 production 结果对比。
- 记录 latency、cost estimate、selected/dropped/reason codes 和 disagreement。
### Canary
canary 只在明确 cohort、tenant、workspace 或 session 范围内启用：
- 固定 runtime、policy、dataset、judge、prompt、context 和 provider snapshot。
- 先执行低风险 read/recall，后执行严格 gating 的 write。
- 高风险 privacy/security 指标为 zero-tolerance。
- 支持逐步扩大、暂停、回滚和保留旧 view。
- canary 不得放宽 retention、egress、scope 或 approval。
### 线上指标
- recall selected/dropped 分布。
- user correction、forget、disable 和 complaint。
- stale/wrong-scope/unconfirmed recall。
- candidate false-positive 和 repeated suggestion。
- latency、cost、index lag、delete propagation。
- provider egress deny/transform 和 privacy incidents。
## Counterfactual Recall
### 目的
Counterfactual recall 用于估计 memory 的必要性、边际 utility 和错误风险，而不把单次最终答案变化误认为因果证明。
### 变体
```text
memory_off
confirmed_only
session_only
without_specific_memory
stale_memory_removed
conflict_filtered
scope_narrowed
summary_only
artifact_ref_only
```
### 设计
- 固定 task、model/provider、prompt/compiler、toolset、clock 和 random seed。
- 只改变一个 memory policy 或 selected set。
- 重复多次处理模型随机性。
- 比较 task success、tool correctness、correction、latency、cost 和 privacy。
- 对同一 memory 进行 leave-one-out 和 add-one-in。
- 将因果结论限定为“在该 fixture、该 runtime、该 variant 下观察到”。
### 反事实限制
- 不允许向真实用户执行可能泄漏或改变状态的对照。
- 不把 counterfactual 的最终文本改善解释为允许扩大 scope。
- memory-on 成功不能证明 memory 必要；memory-off 失败也可能是 seed 或 provider 波动。
## Poisoning、Injection、Leakage 与对抗测试
### Memory poisoning
覆盖：
- 文档诱导把局部规则写成 global policy。
- 模型推断健康、财务、人格属性并标为 confirmed。
- 工具要求保存 secret 或凭据。
- child 伪造 parent confirmation。
- 旧 memory 覆盖新 user direct claim。
- provider metadata 伪造 owner、consent 或 admin。
- workspace 试图扩大 scope、TTL 或 egress。
断言：candidate quarantine、authority= data、scope 不升级、policy 不改变、无未授权 provider egress。
### Prompt injection
注入载体：
- 文件、issue、邮件、检索结果、工具输出、MCP description、OCR 文本和 artifact。
注入目标：
- 自动写 memory。
- 改变 memory policy。
- 读取其他 session/workspace。
- 禁用 DLP、sandbox、approval 或 delete。
- 把 memory 放进 system authority section。
### Leakage
必须测试：
- cross-tenant recall。
- cross-workspace embedding hit。
- deleted memory 在 cache、preview、backup 或 provider remote object 中复现。
- raw memory 进入 provider request。
- tokenization map 进入 prompt、trace 或 child run。
- DSAR export 混入无权 scope。
- shadow/canary artifact 包含原始敏感字段。
### Poisoning/Leakage hard gates
```text
secret/regulated egress > 0 -> release blocked
cross-tenant selected > 0 -> release blocked
forgotten memory selected > 0 -> release blocked
unapproved memory write > 0 -> release blocked
DSAR scope violation > 0 -> release blocked
```
## Human Review 与仲裁
### 需要人工的案例
- 语义等价但文本表述不同。
- 时间条件或适用范围隐含不清。
- 两个来源同等权威且无法自动排序。
- 用户是否明确表达长期保存意图。
- candidate 是否具有未来复用价值。
- summary 是否丢失关键限定词。
- privacy label、de-identification 或 residual risk 不确定。
- 删除受 legal hold、provider limitation 或 backup policy 影响。
### Review Queue
```typescript
interface MemoryReviewCase {
  reviewId: ReviewId;
  evaluationRunId: EvaluationRunId;
  scenarioId: ScenarioId;
  dimension: string;
  evidenceRefs: ArtifactRef[];
  proposedLabels: string[];
  risk: "low" | "medium" | "high" | "critical";
  deadlineAt?: string;
  assignedTo?: PrincipalRef;
  state: "pending" | "in_review" | "adjudication" | "resolved" | "expired";
}
```
### Review 规则
- reviewer 只看到最小必要 evidence。
- 高风险 privacy/scope 评测不能由同一人同时编写案例并最终批准。
- reviewer 的修改产生新 annotation，不覆盖原意见。
- unresolved disagreement 进入 `inconclusive`，不被强行计为 passed。
- review decision 具备 protocol version、reason、evidence 和时间戳。
## Metrics、Thresholds 与 SLO
### 指标分类
```text
quality metrics       precision/recall/necessity/faithfulness/freshness/utility
control metrics       confirmation/rejection/edit/forget/user visibility
safety metrics        scope escape/privacy leakage/poisoning/unapproved write
reliability metrics   index lag/delete propagation/unknown/recovery/replay
performance metrics   latency/queue wait/provider time/token cost
operations metrics    artifact completeness/judge availability/review backlog
```
### 建议 metric schema
```typescript
interface MetricValue {
  metricId: MetricId;
  value: number;
  unit: string;
  numerator?: number;
  denominator?: number;
  confidenceInterval?: [number, number];
  sampleCount: number;
  excludedCount: number;
  uncertaintyCount: number;
  segment: Record<string, string>;
}
```
### Threshold 原则
- hard safety threshold：违反即阻断，不允许平均值抵消。
- hard correctness threshold：事件、状态、receipt、scope、tombstone 必须满足。
- soft quality threshold：允许统计波动，但必须比较 baseline、置信区间和趋势。
- budget threshold：token、cost、latency、artifact bytes 不能超预算。
- human review threshold：高 uncertainty、judge disagreement 或新 schema 进入人工复核。
### SLO 示例
- candidate source/provenance coverage：100%。
- unauthorized write：0。
- cross-tenant recall：0。
- secret/regulated provider egress：0。
- forget 到 recall exclusion 的 P95：按产品策略设定并持续监控。
- deletion propagation completeness：100% 或明确 limitation/hold。
- durable receipt coverage：100%。
- index freshness lag：P95 不超过 recall SLO budget。
- unknown deletion resolution：在约定窗口内进入 verified、blocked 或 manual review。
- offline replay reproducibility：固定 fixture 的 canonical state hash 一致。
## 成本、延迟与容量
### Cost attribution
必须分开归因：
- candidate extraction model。
- task model 的 memory recall context 增量。
- embedding、rerank 和 index。
- judge model。
- human review。
- artifact storage、queue、replay 和 provider egress。
- shadow、canary、counterfactual 和 retry。
### Latency breakdown
```text
candidate extraction
  + classification/DLP
  + store append
  + index
  + recall retrieval
  + ranking/conflict
  + egress/redaction
  + ContextPlan compile
  + provider time
  + judge/review (usually async)
```
### 容量规划
- 按 tenant、workspace、session、memory count、index bytes 和 recall QPS 估算。
- 为候选、index、delete、DSAR、reconciliation 和 evaluation queue 分离容量。
- 设定 judge concurrency、human review backlog 和 artifact retention 上限。
- 大规模 counterfactual 采用 sampled、bounded fan-out 和可取消 job。
- metric labels 不使用完整 memory text、path、tenant ID 等高基数字段。
## Evaluation Artifact 与证据包
### Artifact 内容
```typescript
interface MemoryEvaluationArtifact {
  artifactId: ArtifactId;
  evaluationRunId: EvaluationRunId;
  datasetVersion: DatasetVersionId;
  scenarioId: ScenarioId;
  variantId: VariantId;
  configSnapshotHash: string;
  policySnapshotHash: string;
  modelPromptContextHashes: string[];
  sourceManifest: ArtifactManifest;
  candidateTraceRef?: ArtifactRef;
  recallTraceRef?: ArtifactRef;
  mutationTraceRef?: ArtifactRef;
  deleteTraceRef?: ArtifactRef;
  dsarTraceRef?: ArtifactRef;
  eventLogRef: ArtifactRef;
  stateSnapshotRef: ArtifactRef;
  oracleReportRef: ArtifactRef;
  judgeReportRef?: ArtifactRef;
  humanReviewRef?: ArtifactRef;
  metricReportRef: ArtifactRef;
  redactionProfile: string;
  sensitivity: Sensitivity;
  retention: RetentionPolicy;
  integrityHash: string;
}
```
### 证据最小化
- 默认存 hash、ID、状态、reason code、版本和脱敏摘要。
- 原始 evidence 只在评测必要、隔离、短 TTL 和访问审计下保存。
- 绝不把 tokenization map 放入普通 artifact。
- provider request 只保存脱敏 view、字段级 diff 或 hash。
- artifact 删除必须可验证，不因报告生成而永久保留。
## 回归分诊与发布门禁
### 回归分类
```text
dataset drift
label/ground-truth change
prompt/compiler change
context selection change
memory policy change
store/index/cache bug
provider/model drift
judge drift
runtime/recovery bug
privacy/security regression
cost/latency regression
```
### Triage 流程
```text
detect regression
  -> verify dataset and environment manifest
  -> reproduce with deterministic replay
  -> compare baseline/candidate trajectory
  -> locate first divergent durable event
  -> classify dimension and severity
  -> quarantine flaky or inconclusive case
  -> fix runtime/policy/dataset/rubric
  -> add minimal regression fixture
  -> rerun targeted and full suites
  -> update release evidence
```
### Release gate
P0 hard gates：
- cross-tenant/cross-workspace/scope escape 为零。
- secret、regulated、禁止 raw PII provider egress 为零。
- unapproved active write 为零。
- deleted/forgotten memory resurrection 为零。
- DSAR scope violation 为零。
- unknown outcome 不被自动标为 success。
- durable event、receipt 和 tombstone coverage 达标。
P1 quality gates：
- precision、recall、necessity、faithfulness、freshness、utility 不低于 baseline 保护线。
- wrong-scope、stale-as-current、unconfirmed recall 不超过阈值。
- user control、delete latency、index freshness 和 cost/latency 在 SLO 内。
- judge/human disagreement 与 uncertainty rate 不异常上升。
P2 advisory：
- explanation readability。
- candidate card clarity。
- long-tail utility。
- shadow disagreement。
- reviewer backlog。
## 与 Model、Prompt、Context、Tool、State、Policy、Harness 集成
### Model Runtime
- extraction model、task model、judge model 使用不同 purpose、usage、cost 和 provider receipt。
- provider fallback 重新执行 memory egress，不复用旧 decision。
- Provider raw response 只作为不可信 evidence，不直接写 active memory。
- model request 记录 model/provider/api family、prompt/context hash、RecallView hash 和 usage。
### Prompt
Prompt 只解释：
- memory 功能是否开启。
- 当前可见 memory type、scope 和 confirmation 状态。
- RecallView 可能 stale、conflicted、inferred 或 summary-only。
- 模型不能自行声明已保存、已删除或已外发。
- 用户表达记忆意图时应提出受控 memory command 或生成 candidate。
Prompt 不负责：
- owner、tenant、TTL、retention、DSAR、egress、approval 和实际写入。
### Context
Memory Evaluation 必须读取并断言 `ContextPlan`：
- candidate、selected、dropped、summarized、offloaded 和 filtered IDs。
- source、scope、trust、authority、freshness、sensitivity、retention。
- token budget、dedupe、conflict annotation 和 egress decision。
- memory 与 transcript、compaction summary 的重复率。
### Tool
测试工具至少包含：
```text
memory_search
memory_get
memory_suggest
memory_confirm
memory_edit
memory_forget
memory_policy
memory_export
```
工具测试必须验证：
- 模型不能传任意 tenant、owner、scope、policy override。
- tool visible 不等于 action allowed。
- confirm/forget/edit 需要 Host/Policy 的可信证明。
- tool result 只返回安全摘要、状态和 receipt。
### State
- Session entries 保存 candidate、write、revision、recall、forget、DSAR、policy、egress 和 evaluation references。
- WorkingState 保存当前 recall plan、pending candidate、pending user action 和 cleanup jobs。
- Checkpoint 保存未完成的 index、delete、export、review、recovery 和 provider status query。
- Projector 生成 Memory Center、Recall History、Privacy View、Evaluation View 和 Recovery View。
### Policy 与 Privacy
```text
Visibility -> 是否看到 memory 能力
Call -> 是否可提出具体 action
Approval -> 是否需要用户确认
Execution -> Store/index/queue/backend 使用什么能力
Egress -> 哪个 view 可进入 provider/host/evaluation sink
```
评测自身也必须有 `memory_evaluation` purpose、dataset retention、reviewer scope 和 provider egress policy。
### Harness
Harness bootstrap 冻结：
- tenant/user/workspace/session scope。
- memory policy、privacy/consent/legal-basis snapshot。
- store/index/cache/artifact/provider/queue capability。
- model/prompt/context/compiler 版本。
- evaluation dataset、seed、clock、ID 和 fault plan。
Run 中监督：
- candidate/write/recall/edit/delete/DSAR job。
- event、checkpoint、lease、cancellation、artifact 和 settlement。
- shadow/canary 不改变真实用户状态。
## 安全、隐私、Retention 与 DSAR
### 评测数据分类
```text
public | internal | confidential | secret | regulated
```
评测默认使用 synthetic 或 de-identified 数据；secret、regulated、高风险 PII：
- 不进入普通 trace 和 judge prompt。
- 不进入长期 golden set。
- 不发送到未允许 provider。
- 不随 child run 或 background job 自动继承。
- 只保存最小 hash、类型、大小、状态和安全证据。
### Purpose limitation
`memory_evaluation` 与 `memory_recall`、`memory_persistence`、`memory_delete` 是不同 purpose。
- task processing 不自动授权 evaluation。
- production feedback 进入 dataset 前必须重新分类、脱敏、去重和审核。
- shadow 不得借 evaluation purpose 绕过真实 consent 或 provider egress。
- 评测 artifact 不能成为新的长期 memory source。
### DSAR 对评测系统
DSAR 必须覆盖：
- dataset case、annotation、judge input/output、human review、artifact、replay fixture、counterfactual output。
- 生产反馈派生的 scenario、manifest、索引和备份。
- 访问日志和最小 audit evidence。
删除完成必须输出：
- request ID、subject scope、发现对象、删除对象、blocked/hold/limitation、provider receipt、verifier 和完成时间。
## 故障恢复与未知结果
### 故障分类
```text
fixture_invalid
 dataset_unavailable
 policy_snapshot_unavailable
 memory_store_timeout
 index_lag
 cache_inconsistent
 provider_request_unknown
 judge_timeout
 human_review_timeout
 artifact_upload_failed
 queue_lease_expired
 worker_crashed
 deletion_unknown
 export_partial
 replay_diverged
```
### Recovery 不变量
- evaluation store append 成功、artifact 失败：结果不是“未观察”，而是 artifact incomplete。
- canonical write 成功、index 未写：报告 write success + index pending。
- tombstone 成功、derived cleanup 未完成：报告 deletion partial/blocked。
- provider upload unknown：不重传敏感 view，先查询 remote status。
- judge 失败：soft metric inconclusive，不影响 deterministic safety gate 的事实判断。
- worker lease 过期：fencing token 失效，旧 worker 不能继续写结果。
- host disconnect：不等于取消评测或被测 memory job。
- replay divergence：保存 first divergent event、snapshot hash 和 environment diff。
### Evaluation RecoveryCoordinator
```typescript
interface EvaluationRecoveryCoordinator {
  listPending(scope: ScopeRef): Promise<RecoveryCandidate[]>;
  inspect(runId: EvaluationRunId): Promise<RecoveryInspection>;
  resume(runId: EvaluationRunId): Promise<JobReceipt>;
  quarantine(runId: EvaluationRunId, reason: string): Promise<void>;
  markInconclusive(runId: EvaluationRunId, evidence: ArtifactRef[]): Promise<void>;
}
```
## 测试策略与 Conformance
### Unit
- golden set schema、hash、upcaster 和 label validation。
- scope intersection、purpose、sensitivity、TTL 和 freshness。
- candidate/write/recall/delete 状态机。
- precision/recall/necessity/faithfulness metric。
- conflict、dedupe、counterfactual pairing。
- oracle expression 和 severity。
- artifact manifest、redaction 和 retention。
### Component
- FakeMemoryStore 与 MemoryProductPort contract。
- RecallPort 与 ContextPlan。
- GovernanceDecisionReceiptStore。
- index/cache/tombstone/reconciliation。
- provider egress 与 fallback。
- queue lease、worker recovery 和 DSAR job。
- judge adapter 与 human review queue。
### Integration
- Session/Event/Memory Store 一致性。
- compaction 与 memory flush candidate。
- Model/Prompt/Context/Tool/Harness 的真实装配路径。
- subagent scope intersection 和 parent fan-in。
- Artifact lineage、DSAR 和 provider remote copy。
- workflow version snapshot 与 evaluation replay。
### Fault injection
在以下 durable boundary 后注入崩溃：
- candidate append 前后。
- confirmation commit 后 index 前。
- active write 后 receipt 前。
- recall selected 后 ContextPlan 前。
- tombstone 后 index/cache cleanup 前。
- provider upload accepted 后 receipt 前。
- provider delete accepted 后 status query 前。
- export manifest 后 blob 写入前。
- judge result 后 artifact commit 前。
- human review resolution 后 aggregation 前。
验证：不重复副作用、不丢事实、不把 unknown 当成功、旧 index 不复活。
### Conformance cases
每个 MemoryStore、Index、Queue、ProviderEgress、ArtifactStore、JudgeAdapter 和 HostAdapter 至少通过：
- tenant/scope enforcement。
- CAS/idempotency。
- event ordering 和 replay。
- TTL/retention/forget。
- deletion propagation。
- provider egress redaction。
- artifact hash 与 sensitivity。
- timeout/cancel/lease expiry。
- unknown/recovery/reconciliation。
## 反模式与审查规则
1. 用一个总分评价 memory 好坏。
2. 让 LLM judge 判断“是否真的写入”。
3. 用最终回答证明 recall 正确或删除完成。
4. 只测 selected，不测 dropped、filtered 和 reason codes。
## 实施清单
### P0：评测契约
- [ ] 定义 EvaluationSuite、Scenario、Variant、ObservationBundle、Assertion、Metric。
### P1：Golden 与离线回放
- [ ] 建立 golden memory set、negative set、conflict set 和 recall query set。
### P2：质量维度与安全门禁
- [ ] 实现 precision/recall/necessity/faithfulness/freshness/conflict。
### P3：在线与人工闭环
- [ ] 实现 online shadow 和 sanitized replay。
### P4：运营与发布
- [ ] 实现 regression triage、first divergent event 定位和 quarantine。
## 五个参考项目的启发来源
### Pi
- headless agent loop 与 Harness 分离，说明 Memory Evaluation 应评测 Harness 行为，不把评测塞入 Kernel。
### Grok Build
- actor 和 sampler 分层启发 deterministic state ownership、Attempt、retry/fallback 和 usage attribution。
### OpenCode
- session/message/part 模型启发 MemoryRecord、RecallView、EvaluationArtifact 与 product projection 分离。
### Claude Code
- memory、skills、hooks、subagents、permission modes 和计划工作流启发 candidate confirmation、用户控制和 child scope 的产品化评测。
### OpenClaw
- compaction 前 memory flush 启发 candidate-only 评测，而不是无条件保存历史。
## Definition of Done
Memory Evaluation 只有同时满足以下条件才算完成：
- candidate、write、recall、edit、delete、forget、DSAR 都有可执行 scenario 和轨迹断言。
- golden set、synthetic、real/de-identified dataset 都有 manifest、版本、来源、污染和 retention 记录。
- ground truth 有层级，uncertainty、abstain、冲突和人工仲裁可表达。
- precision、recall、necessity、faithfulness、freshness、conflict、privacy、scope、utility、user control 均有独立指标。
- LLM judge 只处理语义维度，不能判断真实状态、权限、删除、泄漏、SLO 或副作用。
- offline replay、online shadow、canary、counterfactual recall 都遵守 tenant、egress、privacy 和安全边界。
- poisoning、injection、leakage、wrong-scope、resurrection、unapproved write 有 hard gate；决策流程记录 dataset、scenario、variant、policy、oracle、judge、threshold、artifact 和 release gate；可观测性关联 evaluation run、scenario、memory/session/run、scope、provider、artifact、first divergent event 和回归分诊。
