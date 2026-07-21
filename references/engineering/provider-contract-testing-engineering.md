# Provider Contract Testing Engineering 细粒度工程设计
> 本文定义跨 Provider、ApiFamily、Model、Deployment 和 Adapter 的契约测试工程。
>
> 依据仅来自当前目录已有的参考架构、Agent Harness、Provider Runtime、Provider Runtime Conformance、Provider Security Contract、Provider Routing、Provider Schema Evolution、Evaluation、Event/Observability、Security Operations、Privacy、Data Governance、Durable Queue、Production Operations 与五个参考项目源码调研结论；不依赖 README，不新增网络搜索结论。
>
> **边界声明：** Provider Contract Testing 不是“为每个 SDK 写几个 happy-path 单测”。它验证的是 provider-neutral contract、能力声明、请求/响应/事件语义、工具和结构化输出边界、安全外发、版本兼容、未知结果、恢复行为与发布证据。
## 目录
1. [目标与非目标](#目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [职责边界](#职责边界)
4. [测试对象与总体架构](#测试对象与总体架构)
5. [Provider-neutral Contract](#provider-neutral-contract)
6. [Capability Matrix](#capability-matrix)
7. [核心数据模型](#核心数据模型)
8. [TypeScript 接口](#typescript-接口)
9. [Request Normalization](#request-normalization)
10. [Response 与 Event Normalization](#response-与-event-normalization)
11. [Streaming Contract](#streaming-contract)
12. [Tool Calling Contract](#tool-calling-contract)
13. [Structured Output Contract](#structured-output-contract)
14. [Multimodal Contract](#multimodal-contract)
15. [Usage、Error、Retry 与 Cancel](#usageerrorretry-与-cancel)
16. [Fixture、Golden 与 Record/Replay](#fixturegolden-与-recordreplay)
17. [Fake Transport 与 Testkit](#fake-transport-与-testkit)
18. [Adapter Conformance](#adapter-conformance)
19. [Security Contract Testing](#security-contract-testing)
20. [Schema 与 Version Compatibility](#schema-与-version-compatibility)
21. [Negative、Adversarial 与 Fault Injection](#negativeadversarial-与-fault-injection)
22. [Differential Test 与 Provider Drift](#differential-test-与-provider-drift)
23. [Live Smoke、Shadow 与 Quarantine](#live-smokeshadow-与-quarantine)
24. [CI、Release Gate 与发布流程](#cirelease-gate-与发布流程)
25. [测试数据隐私](#测试数据隐私)
26. [Flaky Test 处理](#flaky-test-处理)
27. [Incident Regression](#incident-regression)
28. [生命周期与状态机](#生命周期与状态机)
29. [决策流程](#决策流程)
30. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
31. [故障恢复与未知结果](#故障恢复与未知结果)
32. [安全、隐私与运行隔离](#安全隐私与运行隔离)
33. [可观测性、证据与报告](#可观测性证据与报告)
34. [测试策略矩阵](#测试策略矩阵)
35. [反模式](#反模式)
36. [实施清单](#实施清单)
37. [五个参考项目的启发来源](#五个参考项目的启发来源)
38. [Definition of Done](#definition-of-done)
## 目标与非目标
### 目标
Provider Contract Testing 必须能够：
- 用稳定的 provider-neutral contract 描述一次 `Attempt` 的输入、输出、事件、工具、schema、usage、错误和终止语义。
- 验证 `ProviderAdapter` 是否忠实实现 `ModelPort`，而不是验证某个 SDK 调用是否返回 200。
- 用 `CapabilityMatrix` 表达能力的强度、限制、投影模式、证据来源和新鲜度。
- 将 request normalization、response normalization 和 event normalization 分开测试。
- 覆盖同步、流式、工具调用、并行工具、structured output 和多模态输入。
- 区分 provider refusal、safety、length、cancelled、transport error、unknown outcome 和业务失败。
- 验证 usage 是 observed、estimated 还是 reconciled，并正确进入 `UsageLedger`。
- 验证 retry、fallback、hedge、cancel、timeout 和 circuit breaker 不破坏幂等与审计语义。
- 用 fixture、golden、record/replay、fake transport 和 deterministic clock 形成可重复证据。
- 对每个 adapter 运行通用 conformance suite，并允许 provider 特有扩展进入受控 metadata。
- 验证 security contract、egress、residency、credential scope 和 redaction 约束。
- 在 canonical schema、provider API、adapter、event 和 tool 版本变化时发现兼容性问题。
- 通过 negative、adversarial、fault injection、differential、drift 和 incident regression 覆盖失败路径。
- 将离线证据、scoped live smoke、quarantine、发布门禁和生产监控连接起来。
### 非目标
本文不负责：
- 选择 primary/fallback provider；选择属于 Provider Routing。
- 执行真实工具、文件、网络、支付、部署或其他业务副作用。
- 让不同 provider 对同一 prompt 产生相同文本、token、事件粒度或安全措辞。
- 用录制的成功响应证明实时 endpoint、配额、价格、区域或模型版本仍可用。
- 让 provider SDK 类型成为 Kernel、Harness 或 State 的公共契约。
- 把 provider safety filter 当成本地 Policy、DLP、Approval 或 Sandbox。
- 把 schema 能解析当作业务正确，把 tool call parsed 当作 tool executed。
- 以一条 `COUNT(*)`、一个 HTTP 200 或一组 happy-path snapshot 证明契约完整。
- 在没有隔离、凭据和副作用 oracle 时执行真实 provider 测试。
- 使用测试系统绕过 tenant、workspace、egress、retention、audit 或 deletion policy。
### 核心公式
```text
Contract Test Quality
  = Semantic Coverage
  × Capability Accuracy
  × Normalization Integrity
  × Failure Safety
  × Security Evidence
  × Reproducibility
  × Drift Detection
```
任一乘项接近零，跨 provider 迁移都可能在生产任务中失效。
## 核心判断与术语
### 核心判断
```text
Provider Runtime 负责调用和归一化。
Conformance Suite 负责证明 adapter 是否符合契约。
Routing 负责选择候选与 fallback 顺序。
Policy/Sandbox 负责允许、审批和真实执行边界。
Harness 负责冻结输入、监督生命周期和恢复。
State/Event Store 负责保存 durable truth。
Evaluation 负责轨迹、状态、副作用和回归 oracle。
```
- Contract testing 的比较单位是语义，不是原始 JSON 字节。
- `OpenAI-compatible` 只能作为 API shape 线索，不能自动证明 tool、stream、usage、error、file 和 safety 等价。
- 原始 provider metadata 要保留，但不能污染 canonical contract。
- unknown event 不能静默丢失；未知终止事件默认暂停或失败。
- `stream EOF` 不是 `completed` 的充分条件。
- `retry`、`fallback`、`hedge`、`shadow` 和 `canary` 都产生新的 `Attempt`。
- 每个测试结果都必须能追溯到 contract、adapter、capability、fixture、环境和版本。
### 稳定术语
- `Provider`：外部模型服务或兼容协议服务的逻辑提供方。
- `ApiFamily`：同一 provider 内的请求/响应协议族。
- `Model`：能力、版本、上下文和输出语义上的基础模型引用。
- `Deployment`：实际可调用的 deployment、endpoint、profile、ARN 或 publisher resource。
- `ModelRef`：调用方选择模型的 provider-neutral 引用。
- `ResolvedModel`：经过 catalog、deployment、region 和 capability 解析后的冻结目标。
- `ProviderAdapter`：理解某个 `ApiFamily` 并负责协议映射的边界实现。
- `Transport`：HTTP、SDK、SSE、WebSocket、chunked 或云签名连接层。
- `Attempt`：一次具体 provider/model/deployment 下的采样尝试。
- `CanonicalEvent`：内部可持久化、排序、投影和回放的事件。
- `Fixture`：固定输入、raw frame、错误、上下文或工具脚本样本。
- `Golden`：规范化后的期望结果、事件序列或诊断集合。
- `Evidence`：测试输出、receipt、hash、日志引用或 live smoke 证明。
- `Quarantine`：阻断或限制某 adapter/capability/route 的显式运行状态。
## 职责边界
### Contract Registry 负责
- 注册 canonical request、response、event、tool、structured、multimodal、error 和 usage schema。
- 维护 contract version、owner、reviewer、兼容范围、废弃状态和 hash。
- 维护通用 suite、provider profile、fixture manifest 和 golden manifest。
- 记录每项 contract 的必需、可选、降级和拒绝语义。
### Provider Runtime 负责
- 使用冻结的 `ResolvedModel`、`ContextPlan`、`PolicySnapshot` 和 `EgressSnapshot` 编译请求。
- 执行 transport、解析 raw response/stream、生成 normalized result/event。
- 提供 provider request receipt、raw response reference、usage evidence 和 error taxonomy。
- 不把失败测试修复为隐式 fallback，不改写 tenant 或 policy。
### Conformance Runner 负责
- 装配 adapter、fake transport、fixture、clock、ID、store 和 oracle。
- 运行通用 contract suite 与 provider-specific extension suite。
- 输出每个断言的 pass、fail、skip、error、inconclusive 和 evidence refs。
- 对能力声明、归一化、版本、隐私和安全门禁提供结果。
### Routing 负责
- 在 policy、egress、quota、health 和 capability 边界内选择 provider/model/deployment。
- 消费 conformance status、catalog freshness 和 quarantine state。
- 不为测试目的重新暴露被安全策略拒绝的候选。
### Policy、Privacy 与 Sandbox 负责
- 决定测试数据是否可以发往某 provider/region。
- 决定是否允许 live smoke、shadow、hedge 或 remote object 操作。
- 隔离工具、网络、文件、凭据和外部副作用。
### Evaluation 负责
- 提供 scripted model、fake tool、side-effect oracle、fault injection、replay 和 scenario 断言。
- 不能以模型文本替代真实 receipt、文件状态、事件顺序或权限事实。
### 强制边界
```text
Contract -> Fixture/Scenario -> Adapter Port -> Fake/Live Transport
-> Raw Provider Frame -> Normalizer -> Canonical Result/Event
-> Oracle -> Evidence -> Release/Routing/Operations
```
## 测试对象与总体架构
### 测试对象分层
```text
L0 纯数据模型与 schema validator
L1 Request/response/event normalizer
L2 Adapter + fake transport
L3 Provider Runtime + Harness contract
L4 Cross-adapter conformance
L5 Scoped live smoke
L6 Shadow/canary drift observation
L7 Incident regression in production-like replay
```
- L0 发现字段、类型、枚举和 hash 问题。
- L1 发现语义转换、顺序和终止边界问题。
- L2 发现 transport framing、重试、取消和 raw payload 解析问题。
- L3 发现 Kernel、Tool、State、Policy、Harness 集成问题。
- L4 发现 adapter 间 contract 不一致。
- L5 发现真实 endpoint、认证、区域和服务端行为问题。
- L6 发现未计划的 provider drift。
- L7 防止已修复的事故再次发生。
### 逻辑拓扑
```text
Contract Registry -> Capability Matrix -> Fixture Registry
  -> Conformance Planner
  -> Test Harness
      ├─ Provider Adapter
      ├─ Fake/Live Transport
      ├─ Deterministic Clock/ID/Random
      ├─ Policy/Privacy/Egress Fixture
      ├─ Session/Event/Artifact Recorder
      └─ Side-effect Sandbox
  -> Normalization Oracle
  -> Security/Schema/Usage Oracle
  -> Evidence Bundle
  -> CI Gate / Routing Catalog / Operations Dashboard
```
### 推荐包布局
```text
packages/provider-contract-testing/
  contracts.ts
  capability-matrix.ts
  fixture-registry.ts
  golden.ts
  record-replay.ts
  fake-transport.ts
  adapter-suite.ts
  normalizers.ts
  schema-compatibility.ts
  security-contract.ts
  fault-injection.ts
  differential.ts
  smoke.ts
  quarantine.ts
  release-gates.ts
  incident-regression.ts
  privacy.ts
  reporting.ts
  testkit/
```
### 依赖方向
```text
Harness -> ContractTestPort
Conformance -> ProviderRuntime contracts
Adapter -> Transport contracts
Oracle -> Canonical events/results
Evidence -> State/Event/Audit references
Routing/Operations -> Conformance status only
```
测试包不能 import TUI、业务 ORM、生产 secret 或未隔离的工具执行器。
## Provider-neutral Contract
### Contract 五层
1. `Input Contract`：messages、parts、tools、response format、sampling、attachments 和 budget。
2. `Capability Contract`：model/deployment/adapter 支持的能力与限制。
3. `Execution Contract`：timeout、cancel、retry、idempotency、attempt 和 unknown outcome。
4. `Output Contract`：message、part、tool call、structured result、usage、finish、warning。
5. `Event Contract`：started、delta、tool ready、usage、completed、failed、cancelled、unknown。
### Request 不变量
- 每个请求必须有 `requestId`、`attemptId`、`contractVersion` 和 `ResolvedModel`。
- `tenantId`、`workspaceId`、`runId` 和 `policySnapshotId` 只能来自受信控制面。
- `ContextPlan`、`ToolsetSnapshot` 和 `EgressSnapshot` 必须是冻结引用。
- message、part、tool、structured 和 multimodal 的顺序是语义事实。
- 不支持的强制能力必须在 transport 之前返回 typed capability error。
- request hash 覆盖 canonical payload、schema、model、context、toolset、policy、egress 和 projection hash。
- 不把短期 credential、随机 trace ID 或 UI cursor 放入 request hash。
### Output 不变量
- response 必须关联 `attemptId` 和 provider request receipt。
- 所有完整工具调用必须可由 `callId`、工具名、参数 hash 和序号定位。
- refusal、safety、length、cancelled、error 和 completed 不能合并为一个 stop 字符串。
- structured output 必须区分 parse、schema、business validation 和 provider refusal。
- usage 必须标注 observed、estimated、reconciled 或 missing。
- unknown provider field/event 进入 metadata、diagnostic 或 raw reference。
- terminal event 只能有一个，终态后不得出现新的业务事件。
### 语义等价性
- 允许不同 token 数、delta 粒度、provider ID 和文本措辞。
- 必须保持消息角色、part 类型、工具配对、完成边界、错误类别和安全信号。
- 允许 provider 扩展，但扩展必须标注 namespace、version、sensitivity 和 provenance。
- 不能把被删除的 required constraint 伪装为兼容。
## Capability Matrix
### 能力轴
```text
textInput
textOutput
imageInput
audioInput
videoInput
documentInput
fileReference
streaming
streamCancel
parallelToolCalls
toolCalling
strictToolSchema
structuredOutput
strictStructuredOutput
reasoningEvents
citation
grounding
safetyEvents
usageDetails
promptCaching
serverSideTools
remoteObjects
```
### 能力强度
- `native_strict`：provider 原生且满足 contract 的严格语义。
- `native_relaxed`：原生支持，但存在约束或验证差异。
- `emulated`：客户端投影或组合实现，必须带 warning。
- `prompt_only`：仅提示词约束，不得作为严格 schema 能力。
- `unsupported`：明确拒绝。
- `unknown`：没有足够新鲜证据，默认不能满足硬约束。
### Capability Matrix 数据列
- provider、apiFamily、model、deployment。
- capability name、mode、limit、constraint、known gaps。
- catalog version、adapter version、contract version。
- evidence source、fixture IDs、live smoke status。
- verifiedAt、expiresAt、freshness、quarantine state。
- supported input/output modalities。
- error behavior、usage behavior、cancel behavior。
- security/egress restrictions。
### 能力交集
```text
effective capability
= catalog capability
∩ deployment capability
∩ credential capability
∩ tenant policy
∩ workspace policy
∩ host capability
∩ egress policy
∩ conformance status
```
### 能力测试规则
- capability 声明为 `true` 必须至少有一个 fixture 或 live evidence。
- strict 能力必须有约束保持断言，而不只是请求成功断言。
- stream 能力必须验证 delta、terminal、usage 和断流。
- cancel 能力必须验证取消请求、停止事件和资源释放。
- usage 能力必须验证字段来源与账本归因。
- unknown 能力不能用于 primary route 的硬需求。
- failed conformance 必须更新 catalog 和 routing quarantine。
### Capability Matrix 接口
```typescript
interface CapabilityMatrixEntry {
  provider: string;
  apiFamily: string;
  model: string;
  deployment?: string;
  capability: string;
  mode: CapabilityMode;
  limits?: Record<string, number | string | boolean>;
  restrictions: string[];
  evidenceRefs: EvidenceRef[];
  contractVersion: string;
  adapterVersion: string;
  verifiedAt?: string;
  expiresAt?: string;
  status: "verified" | "degraded" | "unknown" | "quarantined";
}
```
## 核心数据模型
### ContractDescriptor
```typescript
interface ContractDescriptor {
  contractId: string;
  family: "request" | "response" | "event" | "tool" | "structured" | "multimodal" | "error" | "usage" | "security";
  version: string;
  schemaHash: string;
  semanticRules: SemanticRule[];
  compatibility: CompatibilityPolicy;
  owner: string;
  status: "draft" | "active" | "deprecated" | "retired";
}
```
### ContractCase
```typescript
interface ContractCase {
  caseId: string;
  suiteId: string;
  contractRefs: string[];
  adapterRef: AdapterRef;
  fixtureRef: string;
  risk: "low" | "medium" | "high" | "critical";
  tags: string[];
  assertions: ContractAssertion[];
  privacyProfile: string;
  sideEffectPolicy: "none" | "sandboxed" | "scoped_live";
}
```
### EvidenceBundle
```typescript
interface EvidenceBundle {
  evidenceId: string;
  runId: string;
  caseId: string;
  status: "passed" | "failed" | "skipped" | "error" | "inconclusive";
  inputHash: string;
  outputHash?: string;
  eventHash?: string;
  adapterVersion: string;
  contractVersions: Record<string, string>;
  capabilitySnapshotId: string;
  policySnapshotId: string;
  egressSnapshotId: string;
  diagnostics: Diagnostic[];
  artifactRefs: ArtifactRef[];
  createdAt: string;
}
```
### AttemptEvidence
```typescript
interface AttemptEvidence {
  attemptId: string;
  providerRequestId?: string;
  rawRequestRef?: RawPayloadRef;
  rawResponseRef?: RawPayloadRef;
  receipt?: ProviderReceipt;
  normalizedResult?: ModelResponse;
  normalizedEvents: CanonicalEvent[];
  usage?: Usage;
  error?: NormalizedError;
  outcome: "completed" | "refused" | "failed" | "cancelled" | "unknown";
}
```
### OracleResult
```typescript
interface OracleResult {
  assertionId: string;
  status: "pass" | "fail" | "skip" | "error" | "inconclusive";
  severity: "info" | "warning" | "blocking";
  reasonCodes: string[];
  observed?: unknown;
  expected?: unknown;
  evidenceRefs: ArtifactRef[];
}
```
## TypeScript 接口
### Adapter Port
```typescript
interface ProviderAdapter {
  describe(): AdapterDescriptor;
  capabilities(model: ResolvedModel): Promise<ModelCapabilities>;
  compile(request: ModelRequest): Promise<CompiledProviderRequest>;
  send(request: CompiledProviderRequest, signal: AbortSignal): AsyncIterable<ProviderFrame>;
  normalize(frame: ProviderFrame): ProviderEvent[];
  aggregate(events: ProviderEvent[]): Promise<ProviderResponse>;
  classifyError(error: unknown): NormalizedError;
}
```
### Contract Test Runner
```typescript
interface ContractTestRunner {
  runSuite(input: ConformanceInput): Promise<ConformanceReport>;
  runCase(input: ContractCaseInput): Promise<EvidenceBundle>;
  replay(recording: RecordingRef, options: ReplayOptions): Promise<EvidenceBundle>;
  compare(left: EvidenceBundle, right: EvidenceBundle): Promise<DifferentialReport>;
}
```
### Transport Test Double
```typescript
interface TestTransport {
  request(input: TransportRequest, signal: AbortSignal): AsyncIterable<TransportFrame>;
  script(plan: TransportScript): void;
  calls(): TransportCall[];
  reset(): void;
}
```
### Fixture Registry
```typescript
interface FixtureRegistry {
  register(fixture: FixtureDescriptor): Promise<void>;
  resolve(ref: string, version?: string): Promise<FixtureDescriptor>;
  list(filter: FixtureFilter): Promise<FixtureDescriptor[]>;
  redact(ref: string, profile: string): Promise<FixtureDescriptor>;
}
```
### Oracle
```typescript
interface ContractOracle {
  assertRequest(observed: CompiledProviderRequest, expected: RequestExpectation): OracleResult[];
  assertResponse(observed: ProviderResponse, expected: ResponseExpectation): OracleResult[];
  assertEvents(observed: CanonicalEvent[], expected: EventExpectation): OracleResult[];
  assertSecurity(observed: AttemptEvidence, policy: SecurityExpectation): OracleResult[];
  assertUsage(observed: Usage | undefined, expected: UsageExpectation): OracleResult[];
}
```
## Request Normalization
### 规范化顺序
```text
Host input
-> canonical Message/Part
-> ContextPlan validation
-> Toolset snapshot
-> Structured/Multimodal validation
-> Policy/Egress check
-> Capability negotiation
-> provider projection
-> request hash
-> raw request compile
```
### Message 规则
- 角色必须映射为 canonical role，不允许由 provider response 覆盖。
- `parts[]` 保留文本、图片、音频、视频、文档、tool call 和 tool result 顺序。
- 空 part、重复 tool result、缺失 call ID 和无效 MIME 在发送前拒绝。
- provider 不支持的 system/developer 语义必须进入 projection diagnostic。
- provider-specific instruction 只能位于 adapter projection，不能修改 canonical transcript。
- 不允许因 provider 限制静默删除 security instruction、tool result 或 approval context。
### Tool Request 规则
- 工具定义先 canonical schema 校验，再做 provider projection。
- tool name、description、input schema、effect、idempotency 和 owner 不能由 provider 返回值覆盖。
- required、enum、范围、数组边界和 additionalProperties 的丢失必须产生 warning 或拒绝。
- 并行工具支持必须在 capability matrix 与 event contract 中同时声明。
- tool choice `auto`、`none`、`required` 和具体工具名称必须有明确映射。
- 工具数量、参数字节数和 schema 深度超过 deployment limit 时返回 typed error。
### Structured Request 规则
- canonical structured schema 带 schema ID、version、hash 和 validation version。
- strict 要求不能被静默降为 prompt-only。
- provider subset analysis 必须列出 dropped constraints。
- fallback 必须重新投影 schema，不能复用不兼容 projection。
- request hash 覆盖 schema hash 与 projection hash。
### Multimodal Request 规则
- source 为 inline、artifact 或 URL 时必须分别检查大小、MIME、TTL、SSRF 和 egress。
- artifact view 必须显式是 raw、sanitized、preview、summary 或 ref-only。
- provider remote object ID 不能替代本地 ArtifactRef。
- provider 不支持某 MIME 时返回 capability mismatch。
- 上传成功而模型请求失败时，remote object 进入独立对账流程。
### Request Golden
Golden 不比较 provider 原始字段顺序，而比较：
- canonical message 语义。
- provider projection mode。
- 保留和丢弃字段。
- request hash、schema hash 和 capability snapshot。
- egress view、region、credential scope 和 timeout。
- raw request 的脱敏结构摘要。
## Response 与 Event Normalization
### 响应规范化顺序
```text
raw frame
-> provider parser
-> provider event
-> event sequence validation
-> canonical event
-> response aggregation
-> schema/tool/safety validation
-> usage extraction
-> terminal settlement
```
### Response 规则
- response ID、provider request ID 和 attempt ID 分开保存。
- message item、content part、tool call 和 provider metadata 分开保存。
- refusal 不转换为空字符串。
- truncated output 不转换为完整 JSON 或完整 tool call。
- provider safety block 进入 safety metadata 和 typed finish state。
- missing finish reason 必须是 warning 或 incomplete，不能默认 stop。
- raw response 只以 receipt/reference 形式保存，受 redaction 和 retention 约束。
### Event 规范化规则
- 每个 event 有 eventId、schemaVersion、layer、durability、sequence、correlation 和 security。
- provider sequence gap 必须记录 diagnostic。
- unknown event 进入 `provider.event.unknown`，保留 raw reference 和 parser version。
- unknown critical terminal event 阻止成功结算。
- delta 合并不能改变 canonical sequence、call ID 和最终 content hash。
- terminal event 唯一且必须给出 outcome、finish reason、usage status 和 diagnostics。
### Event Golden
Golden 断言：
- 事件 kind、顺序、attempt、turn 和 tool call 关联。
- text/reasoning/tool argument delta 是否完整。
- usage update 是否在允许的边界出现。
- safety、citation、grounding 和 provider extension 是否保留。
- completed、failed、cancelled、unknown 是否互斥。
- event durability 和 sensitivity 是否正确。
## Streaming Contract
### 流式阶段
```text
AttemptStarted
-> ContentPartStarted
-> Text/Reasoning/ToolArgumentsDelta*
-> ToolCallReady?
-> UsageUpdated?
-> AttemptCompleted | AttemptFailed | AttemptCancelled | Unknown
```
### 流式必须覆盖
- 单一文本 delta。
- 空 delta、重复 delta、乱序 delta。
- 多个 content part 交错。
- reasoning 与 text 分离。
- 多个 tool call 交错增量。
- tool arguments 被拆成任意边界。
- usage 在末尾、增量中或缺失。
- safety update、citation、grounding 和 unknown event。
- provider EOF、网络断开、解析失败、超时和 abort。
- terminal 之前或之后出现非法事件。
### Tool 参数增量
- 只在 `ToolCallReady` 或 provider 明确 complete 后解析 JSON。
- 增量 buffer 按 call ID 隔离，不能按全局字符串拼接。
- Unicode、转义、嵌套对象和大参数必须覆盖。
- JSON parse error 不能执行工具。
- call ID 缺失或变化时返回 protocol error。
- completed 后继续到达的 delta 进入 late event diagnostic，不改变结果。
### Cancel 断言
- abort signal 传入 transport、adapter、normalizer 和 worker。
- cancel 后不再产生新的 tool execution。
- 已经有 provider request 的 cancel 必须记录 provider cancel outcome 或 unknown。
- cancel 不是 failed；terminal reason 必须是 cancelled 或 unknown。
- 连接、reader、timer、lease 和 quota 必须释放或进入恢复队列。
## Tool Calling Contract
### 工具调用阶段
```text
model emits call
-> call completeness check
-> canonical JSON parse
-> schema validation
-> business validation
-> policy/approval
-> sandbox execution
-> receipt
-> tool result projection
-> next model request
```
### Contract 断言
- 每个 call ID 只对应一个 canonical tool call。
- 并行调用按 call ordinal 保留模型提出顺序。
- 执行顺序可以不同，但回传必须保持明确 call/result 关联。
- provider tool name 不得覆盖本地 canonical tool identity。
- provider schema 通过不等于本地 business schema 通过。
- tool result status、error code、artifact ref 和 truncation state 必须可表达。
- tool execution 不在 provider contract test 中产生真实副作用。
### Tool Result
- 小结果可以 inline，大结果通过 ArtifactRef offload。
- 结果 view 必须包含 sensitivity、purpose、retention 和 egress decision。
- truncated result 必须带 `truncated=true`、原始大小和 artifact reference。
- tool failure 作为结构化结果回传，不能伪装为模型输出。
- provider 不支持 tool result content type 时使用显式 projection diagnostic。
### 重试与幂等测试
- provider retry 不应重复 tool execution。
- agent retry 必须保留原 call ID 与新的 attempt ID 的关系。
- tool retry 使用独立 execution ID 和稳定业务幂等键。
- unknown provider outcome 时不得直接重发含有已执行写工具的请求。
- replay 只能在无副作用 fake 或 receipt-aware oracle 中进行。
## Structured Output Contract
### 校验层级
```text
provider finish/safety
-> byte decoding
-> JSON parse
-> canonical schema validation
-> business validation
-> redaction validation
-> durable result
```
### 测试矩阵
- 合法最小对象。
- 缺 required 字段。
- 多余字段与 additionalProperties。
- enum、数值范围、字符串长度和数组边界。
- 深层嵌套、Unicode 和大对象。
- provider 返回 markdown fence。
- provider 返回半截 JSON。
- provider refusal、安全拦截和 length truncation。
- redaction 导致 schema 变化。
- schema version 不匹配。
- native strict、native relaxed、emulated 和 prompt-only 四种投影。
### 失败策略
- parse failure 可有限 `retry_modified`，必须记录新 attempt。
- schema failure 不能无限自修复。
- business validation failure 不能由 provider strict mode 覆盖。
- refusal 与 validation failure 分开计量。
- fallback 必须确认新 provider 支持相同 schema 或显式降级。
## Multimodal Contract
### 输入维度
- MIME 类型、编码、大小、页数、时长、分辨率和 part 顺序。
- inline、artifact、URL、remote object 的 source 语义。
- raw、sanitized、preview、summary、range、ref-only view。
- sensitivity、content hash、purpose、region、retention 和 delete path。
### 测试用例
- 支持的文本+图片组合。
- 不支持的 MIME。
- 空附件、损坏编码、超限文件和错误 content type。
- URL redirect、私网地址、过期 URL 和跨区地址。
- artifact scan pending、scan failed 和 remote upload unknown。
- provider 返回图片、音频、视频或文档引用。
- 多 part 顺序、重复 part、缺失 part 和 provider reorder。
- 附件被 redaction 或 summary 后的 hash 与 lineage。
### 安全断言
- live smoke 不读取生产文件。
- URL 测试只访问 fake transport 或明确 allowlist。
- remote object delete、expiry 和 reuse 都有 receipt。
- provider 返回的 URI 不能绕过本地 ArtifactStore scope。
- 跨区域 fallback 必须重新做 egress 与 residency 检查。
## Usage、Error、Retry 与 Cancel
### Usage Contract
Usage 至少区分：
- input tokens。
- output tokens。
- cached input tokens。
- reasoning tokens 或 provider-specific usage。
- tool call/remote operation usage。
- latency、first event、total duration。
- observed、estimated、reconciled、missing。
- attempt、turn、run、session、tenant 归因。
### Usage 断言
- provider usage 字段映射到 canonical Usage。
- missing usage 不得生成 exact cost。
- retry、fallback、compaction 和 shadow 分别计量。
- stream 中间 usage 与最终 usage 不重复入账。
- usage ledger 写失败不能被测试结果吞掉。
- 价格版本、catalog version 和 evidence ref 必须保存。
### Error Taxonomy
```text
invalid_request
schema_error
capability_mismatch
authentication_error
authorization_error
rate_limited
capacity_unavailable
context_overflow
network_error
protocol_error
provider_safety_refusal
provider_server_error
cancelled
timeout
unknown_outcome
```
### 错误断言
- 参数错误不重试原请求。
- 认证/授权错误停止并返回缺失范围。
- 429、容量和暂时性 5xx 按 retry-after、指数退避和 jitter 处理。
- 网络错误只对安全请求有限重试。
- 写请求 unknown outcome 先查询 receipt/status。
- provider safety refusal 不是 transport failure。
- context overflow 交给 Context/Harness 处理，而不是无限重试。
### Retry Contract
- transport retry、agent retry、fallback、tool retry 产生不同原因码。
- retry attempt 有新的 attempt ID，但有 parent attempt reference。
- retry budget、deadline、quota 和 cost 计量必须冻结。
- retry 不应复制不可重放的工具或 remote upload。
- circuit open 时测试必须验证提前拒绝，不是继续打 endpoint。
## Fixture、Golden 与 Record/Replay
### Fixture 类别
- canonical request fixture。
- provider raw request fixture。
- provider raw response fixture。
- provider stream frame fixture。
- error payload fixture。
- tool schema and result fixture。
- structured output fixture。
- multimodal metadata fixture。
- capability catalog fixture。
- security/egress/policy fixture。
- incident regression fixture。
### Fixture Manifest
每个 fixture 至少记录：
- fixture ID、version、owner、source、createdAt。
- contract versions、adapter version、provider/api family。
- sensitivity、redaction status、retention class。
- input/output/event hash。
- expected outcome、tags、risk 和 compatibility range。
- 是否允许 live replay、是否包含 remote object reference。
- 关联 issue、incident、release 和 evidence。
### Golden 规则
- Golden 保存 canonical semantic result，不保存无必要的完整 secret/raw payload。
- provider metadata 可使用 hash、结构摘要和受控 artifact ref。
- delta 粒度差异不应造成无意义 golden churn。
- 终态、工具配对、错误类型、usage 来源和安全状态必须 exact assert。
- provider wording 不作为默认 hard assertion。
- golden 更新必须有 diff review、owner、reason 和 compatibility report。
### Record/Replay
```text
live/provider frame
-> sanitize
-> hash/redact
-> record manifest
-> replay fake transport
-> normalize
-> compare golden
```
- replay 不证明实时可用性。
- replay 不得再次执行真实工具或网络副作用。
- 录制包含 raw payload 时必须独立加密、最小访问和短 TTL。
- replay 必须固定 clock、ID、random、scheduler 和 adapter version。
- 记录 provider status、headers 中的敏感字段和 credential 必须清除。
## Fake Transport 与 Testkit
### Fake Transport 能力
- 按 frame、byte、event、delay 和 connection boundary 脚本化响应。
- 注入 429、5xx、timeout、EOF、malformed JSON、TLS/网络错误。
- 模拟 retry-after、rate limit headers、provider request ID 和 usage。
- 支持 abort 竞态、重复 frame、乱序 frame 和 late frame。
- 记录 request headers/body 的脱敏摘要。
- 模拟 remote object upload、status query、delete 和 unknown outcome。
### Deterministic Runtime
- deterministic clock。
- deterministic ID generator。
- seeded random。
- deterministic scheduler。
- fake credential broker。
- fake policy/egress resolver。
- in-memory event recorder。
- durable event store test double。
- side-effect sandbox。
### Testkit 断言
- 每次 test 结束必须 assert transport calls exhausted 或显式允许多余调用。
- 每个 request 都要 assert tenant、attempt、model、policy 和 egress snapshot。
- 每个 event 都要 assert correlation、sequence 和 durability。
- fake transport 不允许忽略 abort、timeout 和 lease fence。
- testkit 资源必须在 finally 中释放。
## Adapter Conformance
### 通用套件
每个 adapter 至少运行：
1. descriptor 与 capability declaration。
2. request normalization。
3. response aggregation。
4. stream event normalization。
5. tool call 增量和结果反馈。
6. structured output projection/validation。
7. multimodal projection。
8. usage extraction。
9. error classification。
10. retry/cancel/timeout。
11. unknown field/event 保留。
12. security/egress enforcement。
13. schema version compatibility。
14. raw receipt 与 provenance。
### Conformance Level
- `L0`：类型、schema、静态 contract。
- `L1`：fake transport request/response。
- `L2`：stream、tool、structured、usage、error。
- `L3`：Harness、State、Policy、Event、Evaluation 集成。
- `L4`：scoped live smoke。
- `L5`：生产 drift、incident regression 和 rollout evidence。
### 通过条件
- L0-L2 的 blocking case 全部通过。
- L3 不得有 terminal、tool pairing、scope 或 usage blocking failure。
- L4 必须在允许的 region、credential 和 data class 下通过。
- L5 的漂移指标在 error budget 内，且无未处置安全问题。
- skip 必须有 capability reason，不能用 skip 掩盖实现失败。
### Adapter Compliance 报告
报告必须包含：
- provider、api family、model/deployment、adapter version。
- suite、contract、capability、fixture 和 environment version。
- passed、failed、skipped、error、inconclusive 数量。
- blocking failures、known gaps、degraded projection。
- raw receipt、golden diff、security evidence 和 drift signal。
- recommendation：active、degraded、quarantine、retire。
## Security Contract Testing
### 安全测试轴
- tenant、workspace、session、run、attempt scope 绑定。
- credential scope、短 lease、rotation、revocation。
- allowed provider、api family、model、deployment 和 region。
- data class、purpose、retention、training、egress view。
- DLP、secret、PII、regulated 检测和 redaction。
- remote file、URL、artifact、cache 和 provider object。
- refusal、safety metadata、abuse signal 和 audit evidence。
- live smoke 的 sandbox、network、credential 和 data minimization。
### Security Contract 断言
- provider response 不能覆盖 tenantId、workspaceId、purpose、consent 或 region。
- adapter 不能读取或修改 tenant policy。
- denied egress 在 request compile 前失败。
- unknown classification 对敏感数据 fail-closed。
- secret 不进入 request body、raw recording、trace、log、artifact preview 或 golden。
- provider remote object 有单独 inventory、expiry、delete receipt 和 reconciliation。
- contract revoke 后新 attempt 被阻断。
- fallback/hedge/shadow/canary 都重新评估安全合同。
### 负向安全案例
- 错误 tenant ID 注入 request metadata。
- provider 返回伪造的 higher-privilege tool。
- URL 指向私网或跨区 endpoint。
- raw fixture 含 API key、cookie 或 tokenization map。
- adapter 将 `training=false` 当作全部 egress 许可。
- safety refusal 被转换为空成功文本。
- live smoke 使用不匹配的 credential scope。
- quarantine adapter 仍被 routing 选中。
## Schema 与 Version Compatibility
### 版本维度
```text
contractVersion
canonicalSchemaVersion
providerApiVersion
adapterVersion
capabilityVersion
projectionVersion
eventSchemaVersion
toolSchemaVersion
structuredValidationVersion
pricingVersion
```
### 兼容级别
- `byte_compatible`：字节兼容，仅适用于原始 fixture 层。
- `parse_compatible`：旧 parser 可以读取。
- `semantic_compatible`：canonical 语义不变。
- `projection_compatible`：目标 provider 仍可安全投影。
- `replay_compatible`：旧 recording 可以重放。
- `operationally_compatible`：监控、账本、恢复和发布仍可工作。
- `breaking`：需要迁移、门禁或新 contract。
### Schema Diff 规则
- 增加 optional metadata 通常为 additive。
- 增加 required field、改变 role、顺序或 tool pairing 通常 breaking。
- strict -> relaxed 是降级，不是等价兼容。
- 改变 finish reason、terminal boundary、unknown handling 是 event breaking。
- 改变 usage 字段或计费口径至少是 semantic change。
- 改变 redaction、residency、retention 或 provider remote object 语义必须安全审查。
### Compatibility Gate
- 新 adapter 必须通过旧 canonical fixture。
- 新 canonical schema 必须回放旧 recording 或提供 upcaster。
- provider API version 改变必须有 projection diff 和 live smoke。
- 旧 event projector 必须声明支持的 event schema range。
- migration 不能重写 immutable audit fact。
- incompatible case 必须阻断发布或明确 quarantine。
## Negative、Adversarial 与 Fault Injection
### Negative Case 类别
- 缺少必需字段。
- 错误类型、枚举、编码、MIME 和大小。
- 空值、null、missing、duplicate 和未知字段。
- 非法角色、tool call、tool result 和顺序。
- provider response 假造 tenant、run、artifact 或 tool ID。
- schema parse success 但 business invalid。
- usage 字段为负数、溢出或重复累计。
- terminal event 缺失、重复或迟到。
- retry-after 非法、rate limit header 缺失。
- context overflow、quota、auth、policy 和 egress deny。
### Adversarial Case 类别
- prompt injection 伪装成 system/provider metadata。
- tool schema 注入高风险默认值。
- provider event 携带恶意 URL、script 或 path。
- raw payload 诱导 recorder 绕过 redaction。
- 大量 unknown event 消耗解析、队列和 artifact 预算。
- 无限 tool call、重复 call ID、doom loop。
- 断线后伪造 completed 或重复写入 ledger。
- provider fallback 把 confidential 数据发送到 denied region。
- live smoke 返回错误 tenant 的 remote object。
### Fault Injection
- transport 在首事件前、中间 delta、tool ready 前和 terminal 前断开。
- event store 在 attempt started、usage、terminal 时失败。
- usage ledger 提交超时或重复提交。
- cancel 与 response frame 同时发生。
- lease expiry 与 provider response 同时发生。
- adapter version 与 fixture version 不匹配。
- capability catalog 过期、空、冲突或被撤销。
- DLP/redactor unavailable。
- remote delete receipt unknown。
### Fault Result 规则
- 每个 fault case 断言 terminal outcome、retry count、side-effect count、event sequence 和 audit evidence。
- `inconclusive` 不能计为 passed。
- unknown outcome 必须进入 recovery path。
- 非幂等写操作不能盲目自动重放。
- fault injection 不得接触生产凭据或真实业务系统。
## Differential Test 与 Provider Drift
### Differential 比较轴
- canonical request 保留字段。
- projection mode 和 dropped constraints。
- message/part/tool/structured 语义。
- stream sequence、terminal 和 usage。
- error taxonomy、retryability、cancel 和 unknown。
- safety/refusal/citation/grounding metadata。
- latency、cost、capacity 和 rate-limit evidence。
- egress、residency、retention 和 remote object 行为。
### 比较规则
- 不比较 provider-specific wording、token count 和 delta 粒度作为 hard failure。
- 对 semantically equivalent events 做 canonical comparison。
- 对 capability difference 使用 expected degradation，不把差异伪装成 pass。
- 结果按 hard contract、degraded contract、provider extension 三层呈现。
- 差异必须引用 fixture、adapter、catalog 和 policy version。
### Drift Detection
- raw field 新增、删除或类型变化。
- event 顺序、终止、tool arguments 边界变化。
- finish reason、safety、usage 和 error code 变化。
- model alias、deployment、region 或 API version 变化。
- structured subset、多模态 MIME 或 remote object 生命周期变化。
- live smoke 与录制 golden 的语义差异。
### Drift 处置
```text
observe -> classify -> reproduce -> impact assess
-> update fixture/contract or quarantine
-> canary -> release/rollback -> incident regression
```
## Live Smoke、Shadow 与 Quarantine
### Live Smoke 原则
- 只使用最小 synthetic fixture。
- 使用专用低权限 credential 和允许的 region。
- 禁用真实工具、文件写入、网络副作用和持久 remote object，除非有独立测试合同。
- 每次 smoke 记录 provider、api family、deployment、region、adapter、contract 和 catalog snapshot。
- smoke 失败不能自动切换业务 policy；要更新 health/conformance 状态。
- 采样与数据保留必须是短 TTL、metadata-first。
### Smoke 分层
- `probe`：认证、基本请求、终止和 usage。
- `stream`：delta、terminal、cancel 和断流。
- `tool`：只返回 scripted tool call，不真实执行。
- `structured`：固定 schema 的 parse/schema validation。
- `multimodal`：小型 synthetic asset 或 ref-only。
- `security`：deny/egress/credential scope 验证。
### Shadow
- shadow 使用 sanitized request、summary、fixture 或 artifact reference。
- shadow 不返回用户可见结果，不执行真实副作用。
- shadow 失败只影响观察指标，不改写 primary attempt。
- shadow attempt 仍需新的 usage、cost、egress 和 audit 归因。
- shadow data 不能跨 tenant 复用，除非明确合成或脱敏。
### Quarantine 状态
- `none`：正常参与已批准 route。
- `degraded`：仅允许满足的低风险能力。
- `smoke_failed`：暂停 live smoke 或相关 capability。
- `contract_failed`：禁止新 route。
- `security_hold`：立即阻断涉及数据外发的 attempt。
- `retired`：从 catalog 移除但保留历史证据。
## CI、Release Gate 与发布流程
### CI 层级
1. lint、typecheck、schema compile。
2. L0 canonical unit。
3. L1 normalizer fixture。
4. L2 adapter fake transport。
5. L3 Harness integration。
6. cross-provider conformance matrix。
7. security negative suite。
8. compatibility/replay suite。
9. differential suite。
10. scoped live smoke（受保护凭据与环境）。
### Blocking Gate
- contract schema 解析失败。
- required capability 被错误声明为支持。
- terminal、tool pairing、scope、egress 或 usage blocking failure。
- 未知 critical event 被静默丢弃。
- secret 出现在 fixture、golden、trace 或 recording。
- incompatible schema 无迁移或回滚计划。
- quarantine adapter 仍被 active route 使用。
- unknown outcome 被结算为 success。
### Non-blocking Gate
- provider wording 变化。
- delta 粒度变化但 canonical content 一致。
- provider extension 新增且已安全保留。
- 估算 usage 与实时账单小范围差异，前提是标注 estimated。
- 允许的 capability degradation 且 owner 已确认。
### 发布流程
```text
Draft
-> Review
-> Fixture-backed
-> Fake conformance
-> Security review
-> Replay compatibility
-> Scoped live smoke
-> Canary
-> Active
-> Observe
-> Supersede or Rollback
```
### Rollback 规则
- rollback 只切换 config/adapter/catalog snapshot，不重写历史 attempt。
- 已开始的 attempt 使用自己的 frozen snapshot。
- 新 attempt 不能使用 revoked contract。
- rollback 需要记录原因、影响 scope、evidence 和后续 regression case。
## 测试数据隐私
### 数据分类
- synthetic：纯合成，不含真实主体。
- tokenized：受控 token，map 留在可信边界。
- redacted：敏感字段被删除或替换。
- restricted：必要的真实案例，强访问与短 TTL。
- production-derived：经脱敏、最小化、审核和 provenance 处理的回归数据。
### 最小化规则
- 优先合成最小 request，而不是复制整段生产 transcript。
- fixture 只保留测试断言必需字段。
- raw provider payload 默认不进入 git、普通 artifact 或 CI 日志。
- golden 使用 hash、结构摘要和受控 ref。
- provider remote object、上传文件、缓存和 batch job 必须有删除路径。
- 录制数据必须有 owner、purpose、retention、access scope 和 expiry。
- live smoke 不使用用户 prompt、生产文件、真实 secret 或 regulated 数据。
### 隐私失败策略
- DLP、redactor、classification 或 access broker 不可用时，敏感 live test fail-closed。
- 发现 secret 时立即阻断上传、撤销 credential、隔离 recording 并生成 incident signal。
- 录制内容无法确认删除时，标记 deletion unknown，不声称已清理。
- privacy contract 改变时重新运行 security、egress、retention 和 replay gate。
## Flaky Test 处理
### Flaky 定义
- 相同 fixture、版本和环境的结果非确定性变化。
- 非确定性来自 provider 服务质量、时序、并发、网络、随机采样或测试污染。
- flaky 不能简单重跑后标记 passed。
### 分类
- `product_flake`：adapter、normalizer、state 或 race bug。
- `provider_flake`：实时 endpoint 行为波动。
- `infrastructure_flake`：CI、网络、credential、quota 或 store 波动。
- `fixture_flake`：数据或预期不稳定。
- `unknown_flake`：证据不足，必须保持 inconclusive。
### 处理策略
- 固定 clock、ID、random、scheduler 和 transport 后先重现。
- 保存每次 attempt、event、retry、provider receipt 和环境 hash。
- hard contract flaky 不得自动降级为非阻塞。
- live smoke 可有限重试，但必须记录原始失败和重试结果。
- quarantine flaky case/adapter/capability，而不是整个 suite 静默跳过。
- 每个 quarantine 有 owner、expiry、影响范围和解除条件。
- 删除或更新 flaky golden 必须有 review 和 regression evidence。
### 统计规则
- 报告首次失败、重试后结果、总运行次数和 confidence。
- `pass_after_retry` 不等于 clean pass。
- flaky rate 进入 quality SLI 与 release decision。
- 没有足够运行样本时标记 inconclusive。
## Incident Regression
### 事故 case 必须保存
- 症状、发现时间、影响 provider/api family/model/deployment。
- 最小 reproduction request、stream、error 或事件片段。
- tenant、region、policy、egress 和 credential scope 的脱敏摘要。
- 预期 terminal state、tool side effect、usage 和 audit evidence。
- 根因、修复版本、adapter/schema/config 变更。
- 回滚或 containment 行动。
### 回归层级
- parser unit reproduction。
- fake transport frame replay。
- adapter conformance case。
- Harness state/event replay。
- security/egress negative case。
- live smoke or canary observation case。
- production metric guard。
### 回归要求
- 原始事故 case 必须 immutable。
- 新 case 通过后才允许关闭 incident 的技术回归项。
- 修复不能只让一个 sample 通过；必须覆盖边界和相邻 capability。
- 有真实副作用的事故使用 receipt-aware oracle，不重放副作用。
- regression case 进入长期保留但按 privacy policy 最小化。
## 生命周期与状态机
### Contract Test Run 状态
```text
Created
  -> Planned
  -> Prepared
  -> Running
  -> Normalizing
  -> Asserting
  -> EvidenceCommitted
  -> Passed | Failed | Skipped | Inconclusive | Error
  -> Quarantined | Released
```
### Adapter 状态
```text
Draft
  -> Registered
  -> FixtureReady
  -> ConformancePending
  -> Conformant
  -> Degraded
  -> Quarantined
  -> Revalidated
  -> Active
  -> Deprecated
  -> Retired
```
### 状态不变量
- `Running` 前必须冻结 contract、fixture、capability、policy、egress 和 environment snapshot。
- `EvidenceCommitted` 前必须保存断言结果和关键引用。
- `Failed` 不能自动变成 `Passed`，除非新的 run 有独立 evidence。
- `Skipped` 必须有 capability 或环境 reason code。
- `Inconclusive` 不能进入 active release gate 的 passed 集合。
- `Quarantined` 必须传播到 routing/catalog/operations。
- `Retired` 仍可 replay 历史 evidence，但不能接新 attempt。
### 状态转换事件
- `contract.test.created`。
- `contract.test.started`。
- `contract.test.normalized`。
- `contract.assertion.failed`。
- `contract.evidence.committed`。
- `adapter.quarantined`。
- `adapter.revalidated`。
- `provider.drift.detected`。
- `contract.release.approved`。
## 决策流程
### 运行前决策
```text
resolve contract versions
-> resolve adapter/api family
-> resolve fixture and privacy profile
-> resolve capability snapshot
-> validate policy/egress/credential
-> choose fake or scoped live transport
-> freeze test environment
```
### 运行中决策
```text
send request
-> capture raw frame reference
-> normalize event
-> validate sequence and terminal
-> validate tool/structured/multimodal semantics
-> classify error/retry/cancel
-> record usage and receipts
-> run deterministic oracles
```
### 运行后决策
```text
aggregate evidence
-> compare golden/compatibility/differential
-> classify pass/fail/skip/inconclusive
-> update conformance status
-> update quarantine/routing/catalog
-> publish dashboard/audit evidence
-> create regression or release gate
```
### 失败决策表
| 观察 | 结论 | 动作 |
|---|---|---|
| schema parse failure | blocking | 阻断并修复 contract/adapter |
| unsupported optional field | warning | 保留 diagnostic，可发布 |
| missing required capability | blocking | 排除候选 |
| provider wording changed | non-blocking | 更新 semantic diff |
| unknown critical terminal | blocking | quarantine 或暂停 |
| provider 429 | retryable | 按 budget 重试 |
| provider write unknown | unknown | 查询 receipt，禁止盲重放 |
| live smoke credential expired | infrastructure error | 修复环境，不改 contract |
| secret detected in recording | security failure | 隔离、撤销、incident |
| allowed degradation | degraded | 写 warning，限制 route |
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### Model Runtime
- Contract suite 使用 `ModelPort`，不直接让 Kernel 识别 SDK 类型。
- `ResolvedModel`、adapter version、capability snapshot 和 contract version 写入 Attempt。
- Provider metadata 保留在 `ProviderMetadata`，不污染 canonical message。
- usage、cost、retry、fallback 和 unknown outcome 进入 UsageLedger。
### Prompt
- Prompt compiler 的 system、developer、user、tool 和 safety section 以 canonical Message/Part 验证。
- 测试 provider projection 是否保留 authority、边界和输出契约。
- 不把 prompt 文案通过 provider wording snapshot 断言为完全固定。
- prompt injection fixture 进入 security negative suite。
### Context
- `ContextPlan` 的资源、视图、token/byte budget、sensitivity、purpose 和 hash 是 request contract 输入。
- context overflow 测试验证 typed error、compaction hint 或 Harness recovery。
- provider adapter 不能自行删除任意 context 资源。
- context minimization 与 egress snapshot 必须进入 request golden。
### Tool
- testkit 提供 fake tool、schema validator、approval 和 side-effect oracle。
- 验证 provider tool projection、增量参数、call/result 对齐和错误回传。
- provider contract 不能替代 tool business validation、policy 或 sandbox。
### State
- durable event、attempt、checkpoint、usage、receipt 和 conformance evidence 有明确 source of truth。
- 重放不能改变 immutable audit fact。
- provider response 与 tool result 的提交顺序必须可恢复。
- replay fixture 应验证 session projector、event sequence 和 terminal settlement。
### Policy 与 Security
- test run 使用 frozen PolicySnapshot、EgressSnapshot、CredentialLeaseRef。
- denied provider、region、data class、remote object 和 capability 必须 fail-closed。
- live smoke 的 approval、DLP、redaction 和 audit 不得被测试 bypass。
### Harness
- Harness 装配真正的 runtime，只替换 ModelPort、Transport、Clock、Store、Tool backend 和 Host recorder。
- Harness 控制 max attempts、timeouts、cancel、budget、queue lease 和 recovery。
- 测试结果同时有 event stream、final result、evidence bundle 和 diagnostics。
## 故障恢复与未知结果
### Provider unknown outcome
发生 timeout、EOF、连接断开或 ack 丢失时：
1. 停止自动重发可能有副作用的请求。
2. 查询 provider receipt/status（若 contract 支持）。
3. 检查 durable attempt、event sequence、usage ledger 和 remote object 状态。
4. 将结果标为 `unknown`、`completed` 或 `not_started`，不能猜测。
5. 只有 policy 明确允许且幂等键稳定时才重试。
6. 创建 recovery event、diagnostic 和 incident signal。
### Test runner crash
- 运行前保留 test run manifest。
- 运行中写入 attempt started、frame observed 和 checkpoint。
- 重启后读取 execution record、lease、evidence partial 和 event cursor。
- 未完成断言标为 recovery pending，不当作 pass。
- recorder、artifact 和 temporary remote object 进入清理/对账队列。
### Queue/Worker 恢复
- 测试任务使用 durable queue 时继承 lease、heartbeat、fencing token 和 retry budget。
- lease expiry 不代表 adapter 未执行。
- worker 不能在 lease 失效后提交新 evidence。
- recovery worker 需使用相同 fixture hash 和 run scope。
### Store 不可用
- event/audit store 失败时，关键 contract evidence 不得声称已提交。
- 可缓存的 ephemeral trace 可以丢弃，但 blocking evidence、security 和 terminal 不能静默丢失。
- store 恢复后通过 outbox/replay 补写并校验 hash。
## 安全、隐私与运行隔离
### 隔离层
```text
Test Host
  -> Test Tenant/Workspace Scope
  -> Policy/Egress Snapshot
  -> Credential Lease
  -> Adapter/Transport Sandbox
  -> Fake Tool/Network/File Boundary
  -> Recorder/Audit Boundary
```
### 凭据规则
- live smoke 使用专用低权限 credential。
- credential scope 绑定 provider、api family、region、operation、tenant class 和 expiry。
- 测试日志、fixture、golden、trace 和 crash dump 不包含 secret。
- credential 轮换、撤销和失效是可测试的 lifecycle case。
### 网络与副作用
- fake transport 默认 deny 外网。
- scoped live 仅 allow provider endpoint 和必要的 status/delete endpoint。
- tool、MCP、URL、文件和 remote object 使用 fake 或隔离 sandbox。
- shadow/canary 禁止真实业务副作用。
- 任何未知外部副作用都进入 unknown outcome 和 incident path。
### 数据生命周期
- fixture、recording、golden、evidence、artifact、remote object 和 backup 分开管理。
- retention、deletion、DSAR、legal hold 和 export 都有独立 contract case。
- 删除完成需有 per-copy receipt；不能因本地删除就声称 provider 远端已删。
- privacy review 失败时 live test fail-closed。
## 可观测性、证据与报告
### 必备关联字段
- tenant、workspace、session、run、turn、attempt。
- contract、suite、case、fixture、golden 和 dataset version。
- provider、api family、model、deployment、region。
- adapter、transport、normalizer、schema、capability 和 policy version。
- request hash、projection hash、event stream ID、trace ID。
- retry、fallback、quarantine、release、incident 和 regression references。
### 事件
```text
contract.test.started
contract.request.compiled
contract.provider.frame.observed
contract.event.normalized
contract.assertion.failed
contract.usage.recorded
contract.security.denied
provider.drift.detected
adapter.quarantined
contract.evidence.committed
contract.release.gated
```
### 指标
- suite pass/fail/skip/error/inconclusive rate。
- blocking failure count。
- adapter conformance level。
- capability false-positive/false-negative rate。
- normalization unknown event rate。
- stream terminal integrity rate。
- tool call pairing failure rate。
- structured schema validation failure rate。
- usage missing/estimated/reconciled rate。
- retry、unknown outcome、cancel 和 quarantine rate。
- live smoke availability、drift detection latency。
- flaky rate、first-pass rate、pass-after-retry rate。
- privacy/security violation count。
- evidence commit latency、replay success rate。
### 报告视图
- 开发者视图：fixture、golden diff、raw reference、stack 和最小复现。
- Operator 视图：provider health、drift、quarantine、release gate、SLO。
- Security/Privacy 视图：egress、credential、redaction、remote object、incident。
- Routing 视图：candidate conformance、capability freshness、allowed degradation。
- Audit 视图：谁在何时基于什么 snapshot 运行了什么测试。
### 证据完整性
- evidence bundle append-only 或 content-addressed。
- 原始 payload 引用要记录 hash、retention、access scope 和 redaction state。
- 报告不能把 telemetry span 当作业务成功证明。
- audit 事实不能被 coalesce、采样或普通 retention 删除。
## 测试策略矩阵
| 维度 | Unit | Component | Integration | Live Smoke | Production Feedback |
|---|---:|---:|---:|---:|---:|
| request normalization | 必须 | 必须 | 必须 | 选择性 | drift |
| response normalization | 必须 | 必须 | 必须 | 必须 | drift |
| event sequence | 必须 | 必须 | 必须 | 必须 | SLO |
| tool calling | 必须 | 必须 | 必须 | scripted | incident |
| structured output | 必须 | 必须 | 必须 | 必须 | regression |
| multimodal | metadata | fake | sandbox | synthetic | incident |
| usage | parser | ledger | settlement | reconcile | cost |
| retry/cancel | fake | transport | Harness | scoped | outage |
| security egress | rules | adapter | Harness | restricted | incident |
| schema compatibility | diff | replay | migration | canary | regression |
| provider drift | fixture | differential | shadow | canary | production |
| privacy/deletion | metadata | store | lifecycle | scoped | DSAR |
### Coverage 规则
- 每个硬能力至少有 positive、boundary、negative、fault、recovery 五类 case。
- 每个 provider/API family 至少有一个 stream、tool、structured、usage、error、cancel 和 unknown case。
- 每个适配器的 provider-specific extension 至少有 preserve、redact、unknown 三类 case。
- 每次 provider/schema/adapter 版本变更必须执行 replay compatibility。
- 每次安全合同变更必须执行 egress、credential、retention、remote object 和 fallback case。
- 每次事故修复必须增加最小回归并覆盖邻近路径。
### 通过标准
- blocking hard assertions 全部通过。
- 无 secret、跨租户、未授权 egress 或未知成功结算。
- Evidence committed 且可重放或有明确 inconclusive 原因。
- 适配器状态、catalog、routing 和 dashboard 已更新。
- 失败、降级、quarantine、rollback 和 incident owner 明确。
## 反模式
### 把契约测试当 SDK happy path
表现：每家 SDK 只测一次同步文本响应。
后果：stream、tool、usage、refusal、cancel、schema 和真实错误全部缺失。
修复：使用通用 contract matrix、negative、fault、replay 和 live smoke。
### 直接比较 raw JSON
表现：因字段顺序、provider ID 或 delta 粒度变化频繁改 golden。
后果：无法区分 harmless drift 与语义 breaking。
修复：先 canonicalize，再比较语义、事件、terminal、tool pairing 和安全信号。
### 只测最终文本
表现：最终文本正确就通过。
后果：可能有错误工具副作用、丢失 approval、usage 未入账或跨租户外发。
修复：轨迹、事件、状态、副作用和 audit 全量断言。
### 把 stream EOF 当成功
表现：连接关闭就发 completed。
后果：截断结果、半截 JSON 和未知写操作被伪造成成功。
修复：要求 terminal、finish reason、receipt 和 settlement 证据。
### 把 provider strict 当本地校验
表现：provider 接受 schema 就执行工具。
后果：绕过业务约束、policy、approval 和 sandbox。
修复：parse、canonicalize、schema、business、policy、approval、sandbox、execute 分层。
### 把 replay 当实时健康
表现：录制响应通过就认为 provider 可用。
后果：掩盖认证、配额、区域、容量和版本漂移。
修复：replay 与 scoped live smoke、health 和 drift 分开。
### 失败后无限重试
表现：任何错误都重试或 fallback。
后果：成本爆炸、重复写操作、retry storm 和安全边界扩大。
修复：typed error、retry budget、idempotency、receipt query 和 circuit breaker。
### 用 quarantine 隐藏失败
表现：所有失败都标为 skipped 或长期 quarantine。
后果：路由继续使用失效 adapter，质量债务不可见。
修复：quarantine 必须有原因、owner、expiry、影响范围和 release gate。
### 测试数据复制生产数据
表现：直接上传生产 prompt、文件和日志做 smoke。
后果：隐私、驻留、保留、DLP 和跨租户风险不可控。
修复：synthetic 优先，最小化、脱敏、tokenize、短 TTL 和独立审批。
### 用 telemetry 代替 audit
表现：只看 trace/log 推断请求、审批和副作用。
后果：采样、丢失、重排和 retention 使事实不可证明。
修复：durable canonical event、receipt、audit 和 side-effect oracle。
## 实施清单
### 契约与模型
- [ ] 建立 canonical request/response/event/tool/structured/multimodal/error/usage schema。
- [ ] 定义 contract、schema、adapter、provider API 和 capability 版本轴。
- [ ] 注册 `CapabilityMatrixEntry`、`ContractDescriptor` 和 `EvidenceBundle`。
- [ ] 定义 hard、degraded、unknown、unsupported 和 provider extension 语义。
- [ ] 定义 request、response、event、tool、usage 和 error invariant。
### Testkit
- [ ] 实现 fake transport、scripted stream、deterministic clock、ID、random 和 scheduler。
- [ ] 实现 fake credential、policy、egress、event store、artifact store 和 side-effect recorder。
- [ ] 支持任意 delta 切分、unknown event、EOF、abort、timeout、429、5xx 和 malformed frame。
- [ ] 支持 remote object status/delete unknown 与 receipt-aware recovery。
### Adapter Conformance
- [ ] 为每个 ApiFamily 接入通用 adapter port。
- [ ] 建立 request/response/event normalizer fixture。
- [ ] 覆盖 streaming、tool calling、structured output、multimodal、usage、error、retry、cancel。
- [ ] 覆盖 unknown field/event、finish、safety、citation、grounding 和 provider metadata。
- [ ] 生成 L0-L5 conformance report 并同步 catalog/routing。
### 安全与隐私
- [ ] 建立 synthetic、redacted、tokenized、restricted fixture 分类。
- [ ] 在 live smoke 前冻结 EgressSnapshot、CredentialLeaseRef 和 PolicySnapshot。
- [ ] 实现 DLP、redaction、remote object inventory、retention 和 deletion receipt。
- [ ] 为 secret、PII、regulated、跨区、跨租户和 denied provider 建立 blocking cases。
### 发布与运营
- [ ] 将 blocking gate 接入 CI 和 release pipeline。
- [ ] 建立 golden diff、replay、compatibility、differential 和 drift dashboard。
- [ ] 建立 live smoke、shadow、canary、quarantine 和 rollback 机制。
- [ ] 建立 flaky triage、owner、expiry、pass-after-retry 统计。
- [ ] 将事故最小复现自动转为 immutable incident regression fixture。
- [ ] 让 adapter quarantine 影响 routing candidate 与 provider health。
## 五个参考项目的启发来源
### Pi
- headless agent loop 说明测试应围绕 Kernel、统一事件和可恢复 session，而不是围绕 UI snapshot。
- provider event 归一化启发 canonical stream、tool call 边界和 replay fixture。
- session tree 与 compaction 启发 attempt、checkpoint 和 incident regression 的恢复断言。
### Grok Build
- Rust actor 与显式 permission decision 启发 deterministic scheduler、并发工具和 policy negative test。
- 路径锁、folder trust、sandbox 说明 contract test 必须验证 execution boundary，而非只验证模型文本。
- 复杂状态机提醒 conformance runner 要区分 running、waiting、cancelled、unknown 和 recovered。
### OpenCode
- client/server 分离和 session/message/part 模型启发 canonical event、host projection 与 durable evidence 分层。
- event bus、projector、snapshot/patch/revert 启发 record/replay、状态 oracle 和 rollout rollback。
- MCP/LSP 与扩展集成启发 provider metadata、tool schema 和未知事件的 provenance 检查。
### Claude Code
- 权限模式、hooks、subagents、skills、memory 和 MCP 说明测试不能只测模型调用，必须测试 Harness policy、approval、context 和 extension 边界。
- 计划与任务工作流启发 contract test 的阶段性 evidence、失败恢复和 incident regression。
- 其非权威源码性质提醒本地实现判断仍应服从 canonical contract 和可验证 evidence。
### OpenClaw
- AgentHarness registry、独立 agent-core、provider runtime 和 channel gateway 启发 adapter registry、testkit 装配和 host-independent contract。
- tool/sandbox/elevated 分层启发安全合同、credential scope 和 live smoke 隔离。
- 事务化插件注册启发 adapter registration、quarantine、rollback 和版本化 evidence。
## Definition of Done
- [ ] 两个以上 ApiFamily 可通过同一 provider-neutral suite。
- [ ] request、response、stream、tool、structured、multimodal、usage、error、retry、cancel 均有 hard contract。
- [ ] capability matrix 与实际 adapter 行为有 fixture 或 live evidence 支撑。
- [ ] raw metadata、unknown event、provider extension 和 receipt 可审计且受隐私约束。
- [ ] security contract、egress、credential、residency、retention 和 deletion 有 blocking negative test。
- [ ] fake transport、record/replay、differential、drift、quarantine 和 release gate 可运行。
- [ ] flaky、unknown outcome、incident regression 和 rollback 有明确状态与 owner。
- [ ] 测试结果能进入 Routing、Operations、Evaluation、State/Event 和 Audit，而不另建平行事实系统。
