# Agent Evaluation Engineering 详细设计
> Agent Evaluation 不是对最终回答做一次文本打分，而是验证模型—工具闭环的完整行为：输入、上下文、模型动作、权限、工具、持久状态、真实副作用、恢复、交付与最终结果。
>
> 本文偏重 Runner、Testkit、Assertion、Oracle 执行、Fault/Crash、CI 和生产评测闭环；测评集分类、case authoring、ground truth、grader 校准、统计设计、污染防护与生命周期见 [Agent Evaluation Dataset Engineering](agent-evaluation-dataset-engineering.md)。
## 目录
1. [设计目标](#设计目标)
2. [职责边界](#职责边界)
3. [评测分层](#评测分层)
4. [总体架构](#总体架构)
5. [核心数据模型](#核心数据模型)
6. [Scenario 与 Task Fixture](#scenario-与-task-fixture)
7. [Scripted Model 与 Fake Tools](#scripted-model-与-fake-tools)
8. [评测生命周期与状态机](#评测生命周期与状态机)
9. [Trajectory 与 Event Assertions](#trajectory-与-event-assertions)
10. [Final State 与 Side-effect Oracle](#final-state-与-side-effect-oracle)
11. [Deterministic Tests](#deterministic-tests)
12. [LLM Judge 边界](#llm-judge-边界)
13. [Provider Conformance](#provider-conformance)
14. [Fault Injection 与可靠性](#fault-injection-与可靠性)
15. [Crash Recovery 评测](#crash-recovery-评测)
16. [安全评测](#安全评测)
17. [性能与成本评测](#性能与成本评测)
18. [Ablation 与因果比较](#ablation-与因果比较)
19. [指标与聚合](#指标与聚合)
20. [数据集版本与污染防护](#数据集版本与污染防护)
21. [兼容 evals/evals.json 的扩展 Schema](#兼容-evalsevalsjson-的扩展-schema)
22. [CI Gates](#ci-gates)
23. [在线评测与生产反馈闭环](#在线评测与生产反馈闭环)
24. [故障与恢复](#故障与恢复)
25. [测试策略](#测试策略)
26. [反模式](#反模式)
27. [实施清单](#实施清单)
28. [项目启发来源](#项目启发来源)
## 设计目标
评测系统应满足：
- **多层**：覆盖 unit、component、integration、scenario、online。
- **多目标**：覆盖质量、安全、可靠性、性能、成本和可恢复性。
- **轨迹优先**：检查模型和 Harness 的动作过程，而非只看最终文本。
- **状态可证**：检查 durable state、checkpoint、projection 和恢复状态。
- **副作用可证**：检查文件、数据库、网络、消息和外部业务动作。
- **确定性优先**：能用规则、fake、schema、oracle 判断的，不先交给 LLM judge。
- **可重复**：固定 fixture、时钟、ID、随机种子、provider script 和环境。
- **可归因**：记录 model/prompt/context/tool/policy/config/dataset 版本。
- **可比较**：支持 baseline、candidate、ablation、重复样本和统计置信。
- **可治理**：数据集版本、污染防护、隐私、访问和保留策略明确。
- **可门禁**：CI 对关键回归 fail build，对波动指标分层处理。
- **可闭环**：生产反馈经筛选、脱敏、去重、最小化和审核后进入数据集。
```text
Agent evaluation
  != final text grading only
Agent evaluation
  = trajectory + event protocol + state transition
  + policy decision + tool behavior + real side effect
  + final result + cost + latency + recovery
```
### 非目标
本文不定义模型排行榜，不用单一总分替代所有维度，不使用生产凭据运行危险测试，不让 LLM judge 裁决权限、支付、删除、事件顺序或真实副作用，也不把离线高分直接等同于生产可用。
## 职责边界
### Evaluation Spec
定义 scenario、fixture、variant、assertion、oracle、metric、budget、环境、依赖版本、随机性、敏感性和通过规则。
### Evaluation Runner
解析 spec，装配测试 Harness，准备隔离环境，执行 scenario/variant，采集事件、轨迹、状态、artifact、side-effect ledger、usage/cost/latency，运行断言并生成不可变结果。
### Harness Testkit
提供 scripted provider/model、fake tool、fake approval、deterministic clock/ID/random/scheduler、in-memory/durable store、event recorder、fault/crash injector、replay runner 和 side-effect sandbox。
### Oracle
把观察事实与期望比较，不修改被测系统；给出结构化证据，区分 hard failure、soft score、error 和 inconclusive；副作用以外部事实为准，不以模型自述为准。
### LLM Judge
仅评估规则难表达的语义相关性、解释完整性、开放式方案质量和可读性；不得判断工具是否真的执行、权限是否生效、文件是否修改、成本是否超限或 crash 是否重复副作用。
### CI Gate 与生产反馈
CI 执行受控可重复集合并比较 baseline；生产反馈系统负责收集用户信号、错误、人工接管和业务 outcome，经脱敏与审核后形成候选 case，不直接把原始 transcript 当黄金答案。
## 评测分层
### 离线、在线与回归
- 离线评测在受控 fixture 上验证 prompt/context、工具、轨迹、最终状态、副作用、安全、成本和恢复，适合 CI 与 ablation。
- 在线评测在真实或 shadow 流量上观察 completion、纠正、接管、latency、cost、policy、tool failure 和业务 outcome；安全策略不得因实验放宽。
- 回归评测保存原始症状、最小复现、期望轨迹/状态/副作用、修复版本和失败分类，防止已修复问题复发。
### 安全、可靠性、性能与成本
- 安全：prompt/tool/retrieval injection、project trust、approval bypass、sandbox、data egress、secret、cross-tenant。
- 可靠性：429/5xx/断流、tool timeout/crash、session conflict、event delivery、process crash、retry/fallback、idempotency、replay。
- 性能：TTFE/TTFT、总延迟、吞吐、并发、tool queue、backpressure、projector、context compile、资源占用。
- 成本：主模型、retry/fallback、compaction、memory、embedding/rerank、subagent、tool compute、storage/egress、每成功任务成本。
### Provider Conformance
验证 provider adapter 的 message/content 转换、tool calling、stream normalization、finish reason、usage、安全/拒答、取消、error taxonomy、capability detection 和未知字段保留。
## 总体架构
```text
Dataset Registry -> Evaluation Planner -> Variant Matrix
  -> Evaluation Runner -> Test Harness
      ├─ Scripted/Live Model
      ├─ Fake/Real Tool Backend
      ├─ Policy/Approval/Sandbox
      ├─ Session/Event Store
      └─ Host/Event Recorder
  -> Observation Bundle
      ├─ Trajectory / Events / Final State
      ├─ Side-effect Ledger / Artifacts
      └─ Usage / Cost / Latency / Diagnostics
  -> Oracle Engine
      ├─ Deterministic Assertions
      ├─ State / Side-effect Oracles
      ├─ Metrics
      └─ Optional LLM Judge
  -> Result Store / Report / CI Gate
```
### 推荐包边界
```text
packages/
  eval-schema/       # suite/scenario/assertion/result
  eval-runner/       # planning, isolation, execution, settlement
  eval-testkit/      # scripted model, fake tools, clocks, IDs
  eval-assertions/   # event, trajectory, state, side effect
  eval-oracles/      # deterministic and judge adapters
  eval-metrics/      # aggregation, confidence, cost/latency
  eval-datasets/     # manifests, versions, contamination controls
  eval-reporting/    # JSON, JUnit, artifacts
  eval-online/       # shadow and feedback ingestion
```
Evaluation Harness 应调用真实产品装配路径，只替换 ModelPort、Tool backend、Clock、IDs、Host、Store 等端口；不得为测试维护另一套简化 Agent loop。
## 核心数据模型
```typescript
interface EvaluationSuite {
  schemaVersion: string;
  skillName: string;
  dataset: DatasetDescriptor;
  defaults?: EvaluationDefaults;
  scenarios: EvaluationScenario[];
}
interface EvaluationScenario {
  id: string;
  name?: string;
  description?: string;
  tags?: string[];
  risk?: "low" | "medium" | "high" | "critical";
  task: TaskFixture;
  environment?: EnvironmentFixture;
  model?: ModelFixture;
  tools?: ToolFixture[];
  policy?: PolicyFixture;
  session?: SessionFixture;
  faults?: FaultPlan[];
  variants?: EvaluationVariant[];
  assertions: EvaluationAssertion[];
  metrics?: MetricSpec[];
  budgets?: EvaluationBudget;
  judge?: JudgeSpec;
  provenance?: ScenarioProvenance;
}
```
### Observation 与 Result
```typescript
interface ObservationBundle {
  evaluationRunId: string;
  scenarioId: string;
  variantId?: string;
  status: EvaluationExecutionStatus;
  trajectory: TrajectoryStep[];
  events: CanonicalEvent[];
  finalResult?: HarnessResult;
  finalState?: SessionProjection;
  sideEffects: SideEffectRecord[];
  artifacts: ArtifactRef[];
  usage: UsageSummary;
  cost?: CostSummary;
  latency: LatencySummary;
  diagnostics: Diagnostic[];
  environmentSnapshot: EvaluationEnvironmentSnapshot;
}
interface EvaluationResult {
  evaluationRunId: string;
  scenarioId: string;
  variantId?: string;
  status: "passed" | "failed" | "error" | "skipped" | "inconclusive";
  assertionResults: AssertionResult[];
  metricValues: MetricValue[];
  judgeResults?: JudgeResult[];
  evidenceRefs: ArtifactRef[];
  reproducibility: ReproducibilityRecord;
}
```
`passed` 表示所有 hard assertion 通过；`failed` 表示明确产品失败；`error` 是评测基础设施或 fixture 错误；`skipped` 是显式能力条件不满足；`inconclusive` 是观察不足。后三者不能计为 passed。
## Scenario 与 Task Fixture
```typescript
interface TaskFixture {
  prompt: string;
  expectedOutput?: string;
  inputMessages?: Message[];
  files?: FixtureFile[];
  attachments?: FixtureAttachment[];
  initialArtifacts?: ArtifactFixture[];
  acceptanceCriteria?: string[];
  completionContract?: JsonSchema;
}
interface EnvironmentFixture {
  workingDirectory?: string;
  operatingSystem?: "windows" | "linux" | "macos" | "any";
  environmentVariables?: Record<string, SecretRef | string>;
  clock?: FixedClockFixture;
  randomSeed?: number;
  network?: NetworkFixture;
  sandbox?: SandboxFixture;
  repository?: RepositoryFixture;
  tenant?: TenantFixture;
}
```
`prompt`、`expectedOutput`、`files` 与现有 `evals/evals.json` 兼容。
Fixture 应最小、自包含，不依赖开发机隐式状态，不使用生产凭据；文件使用 hash，真实仓库固定 commit，网络使用录制/mock，平台差异显式声明。
一个 scenario 验证一个主要主题，如多工具顺序、审批、流式参数拆分、sandbox fail-closed、crash 后不重复发送；每项能力覆盖正常、边界、无权限、非法参数、依赖失败、取消、恢复和未知事件。
```typescript
interface ScenarioProvenance {
  source: "synthetic" | "regression" | "production" | "security_research";
  sourceRef?: string;
  createdBy?: string;
  reviewedBy?: string[];
  introducedInVersion?: string;
  fixedByVersion?: string;
  redactionStatus: "not_required" | "redacted" | "tokenized" | "restricted";
  contaminationRisk?: "low" | "medium" | "high";
}
```
## Scripted Model 与 Fake Tools
### ScriptedModel
```typescript
interface ScriptedModel {
  stream(request: ModelRequest, signal: AbortSignal): AsyncIterable<ModelEvent>;
  calls(): RecordedModelCall[];
  assertExhausted(): void;
}
type ScriptStep =
  | { type: "expect_request"; assertion: ModelRequestAssertion }
  | { type: "emit"; event: ModelEvent; delayMs?: number }
  | { type: "emit_raw"; providerEvent: unknown; delayMs?: number }
  | { type: "fail"; error: ScriptedProviderError }
  | { type: "wait_for_abort" }
  | { type: "branch"; when: ScriptPredicate; then: ScriptStep[]; otherwise?: ScriptStep[] };
```
Scripted Model 能任意切分 tool arguments、交错多调用、插入 unknown event、模拟 usage/429/5xx/EOF/abort，并断言下一次 model request 是否包含正确 tool result。不能只脚本最终文本，必须覆盖 `request -> stream -> tool call -> result feedback -> next request -> final`。
### FakeTool 与 SideEffectRecorder
```typescript
interface FakeTool<I = unknown, O = unknown> {
  spec: ToolSpec<I, O>;
  execute(input: I, context: FakeToolContext): Promise<O> | AsyncIterable<ToolEvent>;
  calls(): RecordedToolCall<I>[];
  sideEffects(): SideEffectRecord[];
}
interface SideEffectRecorder {
  record(effect: SideEffectRecord): Promise<void>;
  query(filter?: SideEffectFilter): Promise<SideEffectRecord[]>;
  snapshot(): Promise<SideEffectSnapshot>;
}
```
Fake Tool 支持固定/分支结果、delay/progress、timeout、retryable error、部分副作用后失败、忽略 abort、大输出、artifact、resource lock 和 idempotency receipt。Side effect 包括文件、数据库、HTTP、邮件、订单、部署、Git 和权限变化。
### Approval 与 Deterministic Runtime
```typescript
interface ScriptedApprovalProvider {
  resolve(request: ApprovalRequest): Promise<ApprovalDecision>;
  requests(): ApprovalRequest[];
}
interface EvaluationRuntimeControls {
  clock: DeterministicClock;
  ids: DeterministicIdGenerator;
  random: SeededRandom;
  scheduler?: DeterministicScheduler;
}
```
Approval 脚本支持 allow once/scoped、deny、expire、disconnect 和 pending 时 crash。
## 评测生命周期与状态机
```text
Suite: Discovered -> Validating -> Planned -> Running -> Aggregating -> Reported
Scenario: Created -> PreparingFixture -> Ready -> Executing
          -> Collecting -> Evaluating
          -> Passed | Failed | Error | Skipped | Inconclusive
```
### 执行流程
1. 读取 suite 和 dataset manifest，校验 schema、版本、引用与安全策略。
2. 展开 model/prompt/context/tool/policy variants，固定 seed、clock、ID 和环境。
3. 创建隔离 workspace/sandbox，装载 fixture、recorder 和 side-effect snapshot。
4. 通过真实 Harness 入口执行，采集 terminal result 或 timeout。
5. Flush durable events，加载 final projection、artifact 和 side-effect ledger。
6. 运行 deterministic assertions，再按允许范围运行 LLM judge。
7. 计算 metric，清理环境，写不可变 result 和 evidence。
拿到 final text 后不能立即结束；必须等待 tool tasks、durable terminal、projector、side-effect recorder、artifact 和必要 delivery settle。
Timeout 分为 scenario、model、tool、approval、settlement、judge；不能全部记成“答案错误”。
## Trajectory 与 Event Assertions
```typescript
type TrajectoryStep =
  | { type: "model_request"; request: SanitizedModelRequest }
  | { type: "model_event"; event: ModelEvent }
  | { type: "tool_call"; call: ToolCall }
  | { type: "policy_decision"; decision: PolicyDecision }
  | { type: "approval"; request: ApprovalRequest; decision?: ApprovalDecision }
  | { type: "tool_result"; result: ToolResult }
  | { type: "state_commit"; entries: SessionEntryRef[] }
  | { type: "delivery"; state: DeliveryState }
  | { type: "terminal"; result: HarnessResult };
type EvaluationAssertion =
  | EventSequenceAssertion | EventPresenceAssertion | EventAbsenceAssertion
  | EventCountAssertion | TrajectoryPatternAssertion | ToolCallAssertion
  | PolicyAssertion | ApprovalAssertion | FinalStateAssertion
  | SideEffectAssertion | OutputAssertion | SchemaAssertion
  | BudgetAssertion | RecoveryAssertion | CustomAssertion;
```
### Sequence
```typescript
interface EventSequenceAssertion {
  type: "event_sequence";
  mode: "exact" | "subsequence" | "partial_order";
  expected: EventMatcher[];
  allowAdditional?: boolean;
  severity: "hard" | "soft";
}
```
`exact` 用于协议单元测试，`subsequence` 允许额外 progress，`partial_order` 用于并行工具。并行示例：每个 call 必须满足 Ready < Started < Completed，所有依赖工具 Completed < NextModelRequest，但不强制 A/B 完成先后。
### 必查轨迹
- 正确/全部工具、无不存在工具，参数符合 schema 与业务规则。
- 高风险操作前 approval；deny 后不执行；参数变化后旧 approval 失效。
- Tool result 对应 call ID；并发、串行、资源锁和模型反馈顺序正确。
- Retry 不重复副作用；max turns/tools、cancel、fallback、compaction 生效。
- Doom-loop 被停止；未知 provider event 和截断调用产生正确状态。
失败报告包含 expected matcher、actual window、event ID/sequence、脱敏 payload diff、causation chain 和 artifact reference。轨迹断言读取 canonical events，不解析终端日志文案。
## Final State 与 Side-effect Oracle
```typescript
interface FinalStateOracle {
  evaluate(expected: FinalStateExpectation, actual: SessionProjection): Promise<OracleResult>;
}
interface SideEffectOracle {
  snapshotBefore(): Promise<SideEffectSnapshot>;
  snapshotAfter(): Promise<SideEffectSnapshot>;
  evaluate(
    before: SideEffectSnapshot,
    after: SideEffectSnapshot,
    ledger: SideEffectRecord[],
  ): Promise<OracleResult>;
}
```
Final State 检查 session/run terminal、semantic entries、pending approval、model/toolset、checkpoint、compaction、retry/fallback、usage/cost、delivery、artifact 和业务状态。
Side-effect 证据优先级：
```text
external receipt / database fact
  > sandbox filesystem diff
  > tool execution ledger
  > canonical tool result event
  > model final text claim
```
模型说“订单已取消”不能证明订单真的取消。
### Oracle 类型
- 文件：存在、内容/hash、允许/禁止路径、只应用一次、保留用户初始修改。
- 数据库：目标行、affected rows、commit/rollback、idempotency、tenant isolation。
- 网络/消息：endpoint、method/body hash、次数、idempotency header、receipt、unknown outcome。
- Negative：未批准/deny/read-only/dry-run/crash recovery 时没有不允许的副作用。
无法确认外部副作用时不能判 passed；按风险标记 inconclusive 或 failed，保存查询证据并触发人工审查。
## Deterministic Tests
固定 model/tool script、clock、IDs、random seed、scheduler、filesystem、env、capabilities、prompt/context/resources 和 pricing version。
```text
protocol/unit                 最多、完全确定
component/contract            多、确定
scripted scenario             多、确定
recorded provider replay      中等、近确定
live provider smoke           少、允许波动
online experiment             持续、统计判断
```
Snapshot 适合 CompiledPrompt section/hash、ContextPlan、normalized events、provider request shape、projection 和 report schema，但必须配合语义断言。
Recorded replay 保存 raw frames、安全 headers、provider/model/api family、SDK/adapter version、finish reason、usage 和 capture time；用于 adapter/normalizer 回归，不证明在线 provider 未变化。
每个结果记录 seed；允许字段如 event ID、绝对时间、provider request ID 做归一化；固定相对顺序、工具次数、状态、副作用和预算。Flaky 不自动算 pass，不能无限重跑直到通过。
## LLM Judge 边界
适合评估最终解释覆盖、开放式方案质量、可读性、引用支持和摘要保真；不适合 schema、tool 参数、event ordering、side effect、policy/approval、secret、cost/latency、filesystem/database 或 duplicate execution。
```typescript
interface JudgeSpec {
  enabled: boolean;
  modelRef: string;
  promptVersion: string;
  rubric: JudgeRubric;
  inputPolicy: "final_only" | "final_and_summary" | "selected_evidence";
  samples?: number;
  temperature?: number;
  requireRationaleCodes?: boolean;
  failOpen?: boolean;
}
```
Judge 输入先脱敏，不提供 secret，不允许调用生产工具；judge prompt/model/rubric 全部版本化；judge 失败不能覆盖 deterministic hard assertion；高风险安全默认 fail-closed。
偏差控制：随机交换候选顺序，隐藏系统身份，使用结构化 rubric，多样本/多 judge，监控 position/verbosity/style bias，与人工 anchor 校准并保存 disagreement。
`expected_output` 是标准摘要或参考，不做字面匹配；优先拆成 required concepts、forbidden claims、trajectory/state/side-effect requirements 和 optional rubric。
## Provider Conformance
```typescript
interface ProviderConformanceSuite {
  provider: string;
  apiFamily: string;
  capabilities: ModelCapabilities;
  cases: ProviderConformanceCase[];
}
```
必测普通文本、多 content parts、单/多 tool call、arguments 任意分片、tool result、structured output、已声明模态、usage、refusal/safety、finish reason、429/5xx、abort、unknown event、context truncation。
断言 ModelRequest 规范、canonical ModelEvent、provider metadata 保留、不完整 call 不 ready、usage source、error taxonomy、capability mismatch 提前失败、cancel 释放 transport。
同厂商不同 API family 使用独立 profile；“OpenAI-compatible”不能免测 stream、schema 子集、usage、error、file/resource、safety 和 metadata。
少量 live smoke 使用非生产账户、最小 token、无危险工具，不作为唯一 conformance 证据，并记录 provider/model/deployment 和执行时间。
## Fault Injection 与可靠性
```typescript
interface FaultPlan {
  id: string;
  target: "provider" | "normalizer" | "tool" | "session_store"
    | "event_router" | "projector" | "sandbox" | "approval"
    | "host" | "process";
  trigger: FaultTrigger;
  effect: FaultEffect;
  once?: boolean;
}
```
Trigger 包括某事件前后、第 N 次调用、side effect 后、durable commit 前后、经过时间、queue depth、abort；Effect 包括 throw、429/5xx、hang、delay、drop/duplicate frame、corrupt delta、close stream、crash、append failure、version conflict、disconnect、sandbox unavailable。
可靠性断言：retry 有限且 backoff 可验证；fallback 只在允许错误触发；事件记录完整；有副作用调用不盲目重放；pending approval 可恢复；abort 传播；critical consumer 失败可见；terminal 与 durable store 一致；资源释放。
### Doom-loop
构造相同 tool+arguments、轻微变体、错误后无进展重复、父子 Agent 递归；断言 duplicate detector、max tool/turn、无重复副作用、明确 terminal/diagnostic。
## Crash Recovery 评测
在以下 durable boundary 前后模拟 crash：user input、assistant item、tool call ready、approval request/resolve、side effect、tool result commit、checkpoint、compaction、terminal、delivery send/ack。
```typescript
interface RecoveryExpectation {
  resumeStatus: "continued" | "waiting_for_approval" | "requires_manual" | "terminal";
  duplicateSideEffects: number;
  requiredRecoveredEntries?: string[];
  forbiddenReexecutions?: string[];
  finalState?: FinalStateExpectation;
}
```
执行前 crash 只有在无 receipt、确认未执行、policy 仍允许且 approval 有效时可安全重试。执行后 commit 前 crash 必须查询外部状态/idempotency receipt；确认成功则补写结果，确认失败才按策略重试，未知则 `UnknownOutcome`，绝不盲目执行。
Compaction recovery 检查 source hash、call/result 成对、structured task state、pending approval、usage 不重复和失败摘要不覆盖有效状态。
恢复完成标准必须检查 durable sequence、projection、side-effect count、receipt、budget、pending work 和 terminal，不只比较最终文本。
## 安全评测
威胁覆盖 prompt/tool/retrieval injection、恶意 workspace/skill/hook/plugin/MCP、schema bypass、path/command/SQL/URL injection、SSRF/data egress、secret、approval spoofing、sandbox fail-open、cross-tenant、资源耗尽。
每个安全 scenario 明确攻击者能力、不可信输入位置、目标资产、禁止动作、安全替代、期望 policy/approval/sandbox 事件、负副作用 oracle 和证据脱敏。
### Injection 与 Trust
外部内容不得提升 authority、注册工具、改变 approval、泄露 system/secret 或向攻击 URL 外发。未信任 workspace 不执行 hook，不启动 MCP/LSP，不加载插件/env loader，非交互环境不自动信任，并产生 trust diagnostic/audit。
### Approval 与 Sandbox
测试 action summary、参数变化、scoped approval、deny、timeout、pending recovery 和 decision actor。Sandbox 测试文件/网络/进程、symlink/path traversal、unavailable、fail-closed、elevated 分离和 attestation。
### Secret 与 Tenant
使用 synthetic canary secret 扫描 prompt、events、logs/traces、artifacts、final、tool result、snapshot 和 judge input；禁止真实密钥。Cross-tenant 断言 state/event/artifact/replay 全部隔离。
关键安全使用 hard assertion：一次未授权副作用即失败，不能用平均文本质量抵消。
## 性能与成本评测
```typescript
interface LatencySummary {
  totalMs: number;
  timeToFirstEventMs?: number;
  timeToFirstTextMs?: number;
  timeToFirstToolCallMs?: number;
  contextCompileMs?: number;
  modelMs?: number;
  toolQueueMs?: number;
  toolExecutionMs?: number;
  approvalWaitMs?: number;
  settlementMs?: number;
}
```
Benchmark 分 micro、component、scenario、soak、load、recovery、cost。记录 CPU/内存、OS/runtime、provider/region、网络、并发、warm/cold cache、dataset version 和 code/config commit；不同环境绝对 latency 不直接比较。
```typescript
interface CostSummary {
  currency: string;
  total: number;
  byOperation: Record<string, number>;
  byProviderModel: Record<string, number>;
  estimated: number;
  reconciled?: number;
  pricingVersion?: string;
}
interface BudgetAssertion {
  type: "budget";
  maxTurns?: number;
  maxToolCalls?: number;
  maxTokens?: number;
  maxCost?: number;
  maxDurationMs?: number;
  maxArtifactsBytes?: number;
  severity: "hard" | "soft";
}
```
指标包括 cost/run、cost/pass、cost/successful side effect、retry waste、fallback/compaction/subagent overhead、cache savings、tool/compute/storage/egress。性能回归用稳定环境、分位数、绝对+相对阈值，并检查成功率和隐藏 retry。
## Ablation 与因果比较
```typescript
interface EvaluationVariant {
  id: string;
  description?: string;
  modelOverride?: Partial<ModelFixture>;
  promptOverride?: PromptVariant;
  contextOverride?: ContextVariant;
  toolOverride?: ToolVariant;
  policyOverride?: PolicyVariant;
  harnessOverride?: HarnessVariant;
}
```
Prompt ablation 比较 section、版本、工具描述、mode、example、output contract；Context 比较 project rules、memory、retrieval、recent turns、summary、budget、rerank、compaction；Tool 比较 visibility、schema、粒度、truncation、artifact、concurrency、MCP/local；Policy 在隔离环境比较 visibility、approval、allowlist、sandbox、fail-open/closed 后果。
同一 scenario/seed/environment 对 baseline/candidate 配对，计算 success、policy violation、tool calls、tokens、cost、latency 差异。若同时改变模型、prompt、context、tools，不能把结果归因于单一因素。
## 指标与聚合
### 指标
- 成功：scenario/task/hard assertion pass、final-state、side-effect、trajectory、conformance、recovery。
- 轨迹：tool precision/recall、invalid/unnecessary/duplicate call、argument failure、approval compliance、policy violation、turns/tools per success。
- 最终：schema validity、required concepts、unsupported claims、citation、可读性、judge score。
- 状态/副作用：durable terminal、checkpoint、duplicate/unauthorized effect、unknown outcome、cross-tenant contamination。
- 可靠性：retry/fallback/abort/recovery、sequence violation、replay mismatch、resource leak、flaky rate。
- 性能/成本：p50/p95/p99、TTFE/TTFT、tool latency、token/cost per run/pass、cache、event throughput/projector lag。
### 聚合
Hard safety failure 单独报告，不被平均分隐藏；按 risk/tag/provider/model/host 分层；宏/微平均同时报告；重复样本给置信区间；缺失不填零；skipped/error/inconclusive 单列；dataset version 变化时不直接比较总分。
如必须总分，先应用 hard gates，再对通过安全底线的结果加权；未授权副作用、secret、cross-tenant、重复付款/发送/删除不可被文本高分抵消。
## 数据集版本与污染防护
```typescript
interface DatasetDescriptor {
  id: string;
  version: string;
  createdAt?: string;
  description?: string;
  manifestHash?: string;
  split?: "dev" | "validation" | "test" | "canary" | "production_shadow";
  visibility?: "public" | "internal" | "restricted";
  license?: string;
  provenance?: string[];
}
```
Major 表示任务分布/scoring/split 大改；Minor 表示新增 scenario 或 optional assertion；Patch 表示不改变行为的修复。Manifest 记录 scenario/fixture hash、oracle/judge version、provenance、split、sensitivity、contamination risk 和 allowed environments。
污染包括训练数据含题、prompt/skill 泄漏 expected answer、反复针对 test 调参、regression 进入示例、judge 看到系统身份、生产反馈与验证集重复、文件名暴露答案。
防护：dev/validation/test 分离，held-out 限制访问，canary 轮换，prompt/context 泄漏扫描，hash/语义去重，评测访问审计，restricted case 不完整公开，regression/generalization 分开报告。
生产数据进入数据集流程：
```text
collect -> consent/retention check -> redact/tokenize -> deduplicate
-> classify -> minimize reproduction -> deterministic oracle
-> privacy/security review -> assign split/version -> publish manifest
```
Golden 更新必须解释旧期望为何错误、有评审、更新 dataset version 并重跑 baseline，不能只为 candidate 通过而降低标准。
## 兼容 evals/evals.json 的扩展 Schema
当前格式：
```json
{
  "skill_name": "agent-creator-skill",
  "evals": [
    { "id": 1, "prompt": "...", "expected_output": "...", "files": [] }
  ]
}
```
扩展必须保留 `skill_name`、`evals`、number/string `id`、`prompt`、`expected_output`、`files`；旧条目无需迁移即可运行；新字段 optional 或有安全默认值。
```typescript
interface LegacyCompatibleEvalFile {
  skill_name: string;
  schema_version?: string;
  dataset?: DatasetDescriptor;
  defaults?: EvalDefaults;
  evals: LegacyCompatibleEvalCase[];
}
interface LegacyCompatibleEvalCase {
  id: number | string;
  prompt: string;
  expected_output?: string;
  files?: LegacyEvalFileRef[];
  name?: string;
  description?: string;
  tags?: string[];
  risk?: "low" | "medium" | "high" | "critical";
  mode?: "offline" | "live" | "shadow";
  task?: Partial<TaskFixture>;
  environment?: EnvironmentFixture;
  model?: ModelFixture;
  tools?: ToolFixture[];
  policy?: PolicyFixture;
  session?: SessionFixture;
  faults?: FaultPlan[];
  variants?: EvaluationVariant[];
  assertions?: EvaluationAssertion[];
  metrics?: MetricSpec[];
  budgets?: EvaluationBudget;
  judge?: JudgeSpec;
  provenance?: ScenarioProvenance;
  ci?: CiGateSpec;
}
```
### Legacy Adapter
```typescript
function normalizeLegacyCase(input: LegacyCompatibleEvalCase): EvaluationScenario {
  return {
    id: String(input.id),
    name: input.name,
    tags: input.tags ?? ["legacy"],
    risk: input.risk ?? "medium",
    task: {
      prompt: input.prompt,
      expectedOutput: input.expected_output,
      files: normalizeLegacyFiles(input.files ?? []),
      ...input.task,
    },
    environment: input.environment,
    model: input.model,
    tools: input.tools,
    policy: input.policy,
    session: input.session,
    faults: input.faults,
    variants: input.variants,
    assertions: input.assertions ?? legacyDefaultAssertions(input),
    metrics: input.metrics,
    budgets: input.budgets,
    judge: input.judge,
    provenance: input.provenance,
  };
}
```
仅有 `expected_output` 时生成 soft semantic output assertion，并报告 `coverage_gap`；不得自动声称轨迹、状态和副作用通过。包含工具、审批、安全的 legacy case 应补 hard assertions。
### 推荐扩展示例
```json
{
  "skill_name": "agent-creator-skill",
  "schema_version": "2.0",
  "dataset": {
    "id": "agent-creator-core",
    "version": "1.1.0",
    "split": "validation",
    "visibility": "internal"
  },
  "defaults": {
    "mode": "offline",
    "seed": 7,
    "budgets": { "max_turns": 8, "max_tool_calls": 12, "max_duration_ms": 30000 }
  },
  "evals": [
    {
      "id": 1,
      "prompt": "请设计一个跨 provider 的客服 Agent。",
      "expected_output": "明确 API family、审批、幂等、流式事件与测试。",
      "files": [],
      "tags": ["provider", "tools", "approval", "streaming"],
      "risk": "high",
      "model": { "kind": "scripted", "script_ref": "scripts/customer-agent.json" },
      "tools": [
        { "name": "cancel_order", "fake": { "effect": "external", "result": { "status": "cancelled" } } }
      ],
      "assertions": [
        {
          "type": "event_sequence",
          "mode": "subsequence",
          "severity": "hard",
          "expected": [
            { "kind": "tool.call.ready", "tool_name": "cancel_order" },
            { "kind": "approval.requested" },
            { "kind": "approval.resolved", "decision": "allow" },
            { "kind": "tool.execution.completed", "status": "success" }
          ]
        },
        { "type": "side_effect", "severity": "hard", "effect": "order.cancelled", "count": 1 },
        { "type": "budget", "severity": "hard", "max_tool_calls": 2 },
        {
          "type": "output_semantic",
          "severity": "soft",
          "required_concepts": ["API family", "人工确认", "幂等", "流式事件"]
        }
      ]
    }
  ]
}
```
JSON 保持 snake_case，运行时转 camelCase。Assertion type 建议支持 output_contains/not_contains/semantic/schema、event present/absent/count/sequence、trajectory、tool、policy、approval、final_state、side_effect、budget、recovery、custom。
`files` 支持 string 或 `{path, content, source, hash, mode}`；`mode` 可为 input/expected/forbidden_to_modify。Unknown optional 字段保留；unknown assertion 拒绝该 case；duplicate ID 拒绝 suite；critical case 必须有 deterministic safety/side-effect assertion；live mode 必须声明 credential 和 side-effect policy；judge-only 高风险 case 不得做 hard gate。
## CI Gates
### 分层
- Presubmit：protocol/unit、scripted deterministic、prompt/context snapshot+semantic、recorded replay、安全核心。
- Merge：完整回归、fault injection、crash 子集、conformance、成本预算、并发/backpressure。
- Scheduled：全数据集、多 seed、live smoke、load/soak、judge calibration、污染扫描、完整 recovery matrix。
- Release：关键业务、安全、迁移和生产配置快照对应的验收集合。
```typescript
interface CiGateSpec {
  enabled?: boolean;
  tier?: "presubmit" | "merge" | "scheduled" | "release";
  hard?: boolean;
  requiredTags?: string[];
  thresholds?: GateThreshold[];
  baselineRef?: string;
  allowInconclusive?: boolean;
}
```
Hard gate 用于 deterministic contract、unauthorized side effect、secret、schema、event/state invariant、duplicate execution、critical recovery 和明确 budget；Soft gate 用于 judge 风格、live provider 波动、开放式质量和观察期指标。
Baseline 保存 code commit、dataset/scenario hash、provider/model/config、prompt/context/tool/policy/judge version、environment 和 metric distribution。
```text
schema/infra invalid -> error
critical hard assertion failed -> fail
significant quality regression -> fail/review
cost/latency threshold exceeded -> fail/warn by policy
judge-only small drift -> warn/manual review
```
Flaky 记录首次和全部重跑，不允许自动重跑直到通过；关键安全 case 不可永久 quarantine。报告至少包含版本、状态、hard failures、baseline delta、metric、cost、top regressions、复现配置和 evidence refs。
## 在线评测与生产反馈闭环
在线信号包括赞踩、纠正、重复说明、人工接管、放弃、rollback、approval deny、policy violation、error/retry/fallback、业务 completion、latency/cost 和 support ticket。
单一用户反馈不是事实真值；应联合用户信号、durable state、side-effect receipt、业务 outcome、policy/audit 和抽样人工审查。
### Shadow 与 Canary
```text
production request -> primary executes
-> sanitized fixture -> shadow candidate with fake/dry-run tools
-> compare trajectory/final state/cost
```
Shadow 不执行真实副作用。Canary 使用小流量、低风险任务、相同或更严格安全策略、hard safety monitoring、自动回滚条件和可审计分流。
```typescript
interface ProductionFeedbackRecord {
  runIdHash: string;
  feedbackType: string;
  value?: number | string;
  businessOutcome?: string;
  sideEffectRefs?: ArtifactRef[];
  userCorrectionCount?: number;
  policySignals?: string[];
  redactionState: string;
  consentScope?: string;
}
```
未授权/重复副作用、纠正多次、recovery 失败、provider drift、安全漏报、高成本、新型 tool misuse 和多客户端不一致进入候选回归队列。
```text
observe -> triage -> reproduce -> minimize fixture
-> deterministic oracle -> regression case -> fix
-> CI gate -> canary -> monitor
```
不要用生产文本调参后又在同一文本上报告提升。
## 故障与恢复
评测基础设施错误包括 invalid fixture、runner crash、sandbox/artifact/judge/provider 不可用、timeout、result conflict；标记 `error`，保存复现配置和 evidence，清理资源，有限重试，不覆盖第一次结果。
Runner checkpoint 保存已完成 scenario/variant、当前 fixture、seed、observation artifact、judge pending 和 aggregation cursor；恢复不得重复执行 live side-effect case。
Result 不可变；rerun 使用新 evaluationRunId；aggregate 指向明确样本；baseline 不原地变化；judge 重评形成新结果层。
Judge failure 保留 deterministic assertions，结果可 inconclusive/soft warning，高风险不 fail-open。Cleanup failure 标记 dirty environment、不复用 workspace、记录孤儿资源并通过 TTL/后台任务清理。
关键 evidence 丢失时 hard assertion 不能假设通过；side effect 重新查询外部事实，无法恢复则 error/inconclusive。
## 测试策略
### 评测系统自身
- Schema、legacy adapter、matcher、partial order、budget、metric、manifest/hash、污染去重、judge parser、gate decision。
- Runner fixture/cleanup、variant、seed、timeout、abort、settlement、artifact、crash resume、并行隔离。
- Scripted Model request expectation、exhaustion、branch、chunking、failure、abort、usage、unknown event。
- Fake Tool call recording、progress、timeout、partial effect、idempotency、ignored abort、artifact、resource lock。
- Assertion exact/subsequence/partial order、absence/count、payload、state diff、negative effect、evidence、hard/soft。
### Contract 与 End-to-end
所有 provider、tool backend、session store、host adapter、sandbox backend 运行各自 conformance suite。
至少覆盖：普通回答、单工具、多工具、非法工具/参数、approval allow/deny/timeout、tool timeout/error、429/5xx/断流、截断 arguments、retry/fallback、doom-loop、cancel、compaction、subagent、crash recovery、多客户端 resume、prompt injection、sandbox unavailable、secret、unknown provider event、性能成本预算。
### Meta-evaluation 与 Mutation
用人工 anchor 校准 judge 和 oracle；验证 scenario 能区分 known-good/known-bad；做 mutation testing：跳过 approval、重复工具、错 call ID、丢 terminal、漏计 retry usage、sandbox fail-open、projector 忽略事件、final text 谎称成功。评测必须抓住这些缺陷。
每个工具型 scenario 至少有一个 trajectory/event assertion、一个 final-state 或 side-effect oracle、一个 budget/termination assertion；高风险动作再加 policy/approval/safety hard assertion。最终文本只能是其中一部分。
## 反模式
1. 只比较最终文本与 `expected_output` 的字符串相似度。
2. 模型说“已完成”就判真实任务完成。
3. 不检查 tool call、policy、approval、state 和 side effect。
4. 只 mock 最终回答，不脚本流式与工具循环。
5. 使用生产凭据和不可逆工具跑测试。
6. Unit test 依赖实时付费 provider。
7. Conformance 只测文本，不测 tool stream。
8. 把所有 provider 当同一兼容语义。
9. 缺失 tool arguments 任意分片/截断 case。
10. 使用 sleep 和真实时间导致不稳定。
11. ID、seed、scheduler 不可控。
12. Snapshot 替代语义断言。
13. LLM judge 裁决 schema、权限和真实副作用。
14. Judge model/prompt/rubric 不版本化。
15. Judge 看到候选身份和固定顺序。
16. 安全失败被平均总分稀释。
17. error/skipped/inconclusive 计为 passed。
18. 无限重跑 flaky 直到通过。
19. Recovery 只看最终文本，不查重复副作用。
20. Retry/fallback/compaction/subagent 成本遗漏。
21. 同时改变多个因素却声称单因素提升。
22. Dataset 无版本、manifest、hash、provenance。
23. Dev 与 held-out test 混用。
24. Prompt 或 fixture 文件名泄漏答案。
25. 生产 transcript 未经同意和脱敏直接入库。
26. Golden 只为 candidate 通过而更新。
27. Online experiment 放宽安全 policy。
28. Shadow candidate 执行真实副作用。
29. Evaluation Harness 使用另一套简化 loop。
30. 报告缺少 code/config/model/dataset 版本。
31. 不测 event store、projector、多客户端和恢复。
32. 不做 mutation testing，无法证明评测有效。
## 实施清单
### Schema、数据集与 Testkit
- [ ] 定义 Suite/Scenario/Observation/Result 和状态语义
- [ ] 保持 `skill_name/evals/id/prompt/expected_output/files` 兼容
- [ ] 实现 legacy adapter，legacy 文本断言标记 coverage gap
- [ ] Dataset version/manifest/hash/provenance/sensitivity/split
- [ ] 污染、泄漏、hash 和语义近重复扫描
- [ ] ScriptedModel 支持 raw/normalized stream 与 request assertion
- [ ] FakeTool 支持 progress/error/effect/idempotency/resource lock
- [ ] ScriptedApproval、DeterministicClock/IDs/Random/Scheduler
- [ ] EventRecorder、SideEffectRecorder、Fault/CrashInjector、ReplayRunner
### Assertions、Oracle 与 Conformance
- [ ] Event presence/absence/count/exact/subsequence/partial-order
- [ ] Trajectory、tool schema、policy、approval assertions
- [ ] Final-state 和 positive/negative side-effect oracle
- [ ] Output schema/semantic、budget、recovery assertions
- [ ] 结构化 evidence 和脱敏 diff
- [ ] Provider/tool/store/host/sandbox conformance suites
- [ ] Arguments 任意分片、safety/refusal/usage/finish/abort/unknown event
- [ ] Retry/fallback、doom-loop、session conflict、critical consumer failure
### Recovery、安全、性能与 Ablation
- [ ] 每个 durable boundary 前后 crash matrix
- [ ] Side effect 后 commit 前、receipt 查询和 UnknownOutcome
- [ ] Pending approval、compaction、terminal/delivery recovery
- [ ] Prompt/tool/retrieval injection、project trust、approval scope
- [ ] Path/command/SQL/URL、SSRF、sandbox、secret、cross-tenant
- [ ] TTFE/TTFT、p50/p95/p99、load/soak/replay/projector
- [ ] Token/cost by operation 和 cost per passed scenario
- [ ] Prompt/context/tool/policy 单因素 paired ablation
### Judge、CI 与生产闭环
- [ ] Judge 只处理开放式语义，输入脱敏且无生产工具
- [ ] Judge model/prompt/rubric 版本化并用人工 anchor 校准
- [ ] Deterministic hard failure 不被 judge 覆盖
- [ ] Presubmit/Merge/Scheduled/Release gates
- [ ] Hard/soft threshold、baseline、flaky policy、JSON/JUnit/artifact report
- [ ] Shadow/dry-run、Canary、安全监控和自动回滚
- [ ] 生产反馈脱敏、去重、最小复现、版本化回归
- [ ] 工具型 case 同时评轨迹、状态、真实副作用和最终结果
## 项目启发来源
- **Pi**：headless loop、统一 provider event、EventStream 与最终结果并存、AgentSession/session tree、compaction entry、steering/follow-up；启发脚本化完整 loop、断言事件轨迹，并验证 session/compaction/replay。
- **Grok Build**：Session/ChatState/Sampler actor、分层 sampler、permission decision、并行工具与路径锁、folder trust、sandbox、输出限制；启发 provider conformance、partial-order、资源锁、permission/sandbox fault injection 和状态恢复评测。
- **OpenCode**：client/server、session/message/part、event bus、durable event/projector、permission、snapshot/patch/revert、MCP/LSP；启发 final-state projector oracle、event replay、多客户端一致性和文件副作用检查。
- **Claude Code**：permission modes、hooks、skills、subagents、memory、MCP、计划与任务工作流；启发覆盖模式、审批、扩展、子 Agent、memory 和任务状态；公开能力与安全语义应以 Anthropic 官方文档为准。
- **OpenClaw**：AgentHarness registry、agent-core、Gateway/channel、provider runtime、tool/sandbox/elevated、事务化插件、后台运行与 memory；启发 channel delivery、后台恢复、插件回滚、分层安全评测和多来源成本归因。
