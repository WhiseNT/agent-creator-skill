# Provider Incident Response Engineering 细粒度工程设计
> 本文定义 Provider Incident Response（提供商事故响应）的控制面、数据面、事件分类、隔离、取证、恢复与回归工程。
>
> 依据仅来自当前目录已有的参考架构、Agent Harness、Provider Runtime、Provider Security Contract、Provider Routing、Provider Runtime Conformance、Provider Contract Testing、Provider Schema Evolution、Security Operations、Production Operations、Event/Observability、Privacy、Data Governance、Data Quality Operations、Artifact、Multi-tenant、Workspace Isolation、Session Replay、Cost Governance 与五个参考项目源码调研结论；不依赖 README，不进行网络搜索。
>
> **边界声明：** Provider Incident Response 不是“把 500 错误加到 Slack 告警”。它必须判断 provider incident 与普通 API error、业务 error、工具 error 和用户取消的边界；把信号关联到 provider/API family/model/deployment/region/tenant/route/credential/data view；在需要时停止外发、隔离路由、撤销凭据、保全证据、协调供应商、恢复并对账；最后把事故转成 contract/conformance gate、回归 fixture、SLO/error budget 调整和可验证的 postmortem。
## 目录
1. [目标与非目标](#目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [职责边界](#职责边界)
4. [Provider Incident 与普通错误的边界](#provider-incident-与普通错误的边界)
5. [事故分类学](#事故分类学)
6. [总体架构与故障域](#总体架构与故障域)
7. [核心数据模型](#核心数据模型)
8. [TypeScript 接口](#typescript-接口)
9. [Signal Detection 与 Correlation](#signal-detection-与-correlation)
10. [Severity、Blast Radius 与影响评估](#severityblast-radius-与影响评估)
11. [Tenant/Region/Model/Route Isolation](#tenantregionmodelroute-isolation)
12. [Containment、Quarantine 与流量控制](#containmentquarantine-与流量控制)
13. [Credential Rotation、Revocation 与 Egress Stop](#credential-rotationrevocation-与-egress-stop)
14. [Provider Communication 与外部协作](#provider-communication-与外部协作)
15. [Forensics、Evidence 与 Timeline](#forensicsevidence-与-timeline)
16. [Incident Command、状态更新与沟通](#incident-command状态更新与沟通)
17. [Recovery、Reconciliation 与恢复验证](#recoveryreconciliation-与恢复验证)
18. [Postmortem、回归与发布门禁](#postmortem回归与发布门禁)
19. [SLO、Error Budget 与运营控制](#sloerror-budget-与运营控制)
20. [Break-glass 与 Privacy/Legal Coordination](#break-glass-与-privacylegal-coordination)
21. [生命周期与状态机](#生命周期与状态机)
22. [端到端决策流程](#端到端决策流程)
23. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
24. [故障恢复与 Unknown Outcome](#故障恢复与-unknown-outcome)
25. [安全、隐私与多租户](#安全隐私与多租户)
26. [可观测性与审计](#可观测性与审计)
27. [测试策略](#测试策略)
28. [反模式](#反模式)
29. [实施清单](#实施清单)
30. [五个参考项目的启发来源](#五个参考项目的启发来源)
31. [Definition of Done](#definition-of-done)
## 目标与非目标
### 目标
Provider Incident Response 必须能够：
- 将 provider、api family、model、deployment、region、credential、adapter、route 和 tenant 绑定到同一份 IncidentScope。
- 识别 outage、degraded service、capability drift、data exposure、safety、regional、credential、billing、schema 和 adapter 事故。
- 区分单请求可重试错误、请求编译错误、工具业务失败、模型输出拒答、provider incident 和本地平台事故。
- 通过多信号 correlation 发现影响，而不是依赖单个状态码或单个日志。
- 用 severity、blast radius、confidence、data sensitivity 和副作用风险决定响应级别。
- 按 provider、api family、deployment、region、model class、route、tenant class 和 credential class 隔离故障。
- 支持 traffic stop、route quarantine、circuit open、fallback restriction、hedge stop、shadow stop 和 canary rollback。
- 支持 credential lease revoke、key rotation、egress stop、remote object quarantine 与 provider status query。
- 保存不可变的 evidence、timeline、decision、命令、状态变化、receipt 和受控原始引用。
- 支持 incident commander、operations、security、privacy、legal、provider support、tenant support 和 communications 协作。
- 处理 stream、tool call、structured output、usage、cost、remote file 和 unknown outcome 的恢复与对账。
- 将根因转成 Provider Contract、Conformance、Schema Evolution、Routing、Security、Privacy、Data Quality 和 Evaluation 回归门禁。
- 让 provider incident 进入 SLO/error budget、容量、告警分级、runbook 和发布决策。
### 非目标
本文不负责：
- 代替 Provider Runtime 的协议解析、错误分类或 adapter 实现。
- 代替 Provider Routing 进行普通候选排序；Incident Response 只提供健康、隔离和禁止使用的控制事实。
- 把所有 provider 4xx/5xx 都升级为事故。
- 让 provider safety filter 代替本地 Policy、DLP、Approval 或 Sandbox。
- 通过 retry、fallback 或更大 worker 池掩盖真实 blast radius。
- 让 incident commander 直接手工改数据库、删除证据或绕过审计。
- 以 Slack、短信、dashboard 或 trace 单独证明副作用、删除、恢复或未外发。
- 默认保存完整 prompt、hidden reasoning、原始 tool args、secret、regulated 原文或全部 provider payload。
- 将 provider status page、客户支持回复或模型文字自述当作唯一事实。
- 在没有明确 scope、TTL、双人审批和自动回收的情况下扩大 break-glass。
### 核心公式
```text
Provider Incident Response Quality
  = Detection Coverage
  × Classification Accuracy
  × Blast Radius Control
  × Containment Speed
  × Evidence Integrity
  × Recovery Correctness
  × Regression Closure
  × Communication Accuracy
```
任一乘项接近零，系统就可能“看起来恢复”但仍在继续外发、重复副作用或丢失事故证据。
## 核心判断与术语
### 核心判断
```text
Provider Runtime reports attempt facts.
Routing chooses only healthy and policy-approved candidates.
Incident Response declares and controls provider risk.
Policy/Security/Privacy enforce hard boundaries.
Harness freezes, supervises and recovers runs.
State/Event/Audit preserve durable truth.
Evaluation turns incidents into regression evidence.
```
- incident 的最小单位不是 HTTP response，而是受影响的 **Provider Surface**。
- 一个 500 可能是单次 provider server error，也可能是持续 outage；持续性、关联性和影响面决定是否声明 incident。
- 一个 200 也可能是 data exposure、capability drift、错误 region、错误 billing 或 adapter 误解析事故。
- API error 的处理目标是让当前请求安全结束；incident response 的目标是阻止影响继续扩散、证明影响范围并恢复系统级安全边界。
- 事故过程中新的 retry、fallback、hedge、shadow、canary 都是新的 Attempt，必须重新检查 Contract、Egress、Region、Budget 和 Capability。
- `unknown outcome` 是恢复状态，不是失败理由；请求可能已经被 provider 接受，不能按未执行处理。
- status update 是沟通投影，timeline 和 durable event 才是事实来源。
### 稳定术语
- `ProviderSurface`：Provider、ApiFamily、Model、Deployment、Region、Endpoint、CredentialClass、AdapterVersion 的组合。
- `ProviderSignal`：来自 runtime、health、routing、security、privacy、billing、quality、tenant support 或 provider communication 的观测。
- `ProviderIncident`：经关联、影响评估和声明后，需要跨请求或跨租户控制的 provider 风险事件。
- `IncidentScope`：受影响 tenant、workspace、session、run、attempt、route、region、model、credential、artifact 和时间窗。
- `BlastRadius`：影响对象集合、敏感度、外发路径、持续时间、可传播副本和未知范围。
- `ContainmentAction`：停止、隔离、熔断、撤销、路由收紧、egress stop、降级、暂停或 quarantine。
- `Quarantine`：将 provider surface、adapter、capability、remote object、credential、artifact 或 run 从正常路径移除，同时保留调查和恢复所需事实。
- `EvidenceBundle`：支持检测、影响、决策、恢复和关闭结论的受控证据集合。
- `IncidentCommand`：由授权 operator 或 commander 执行、具备 scope、TTL、reason、approval 和 audit 的控制动作。
- `RecoveryReceipt`：恢复、状态查询、删除、rotation、reconciliation 或 canary 验证的可引用回执。
## 职责边界
| 组件 | 负责 | 不负责 |
|---|---|---|
| Provider Runtime | attempt、stream、usage、error、receipt、raw ref | 声明全局 incident、切换租户策略 |
| Provider Health | liveness、readiness、stream、capacity、settlement 观测 | 代替 incident commander |
| Provider Routing | candidate filter、circuit、fallback compatibility | 绕过 Policy/Egress 或自行声明恢复 |
| Provider Security Contract | capability、credential、residency、retention、revocation 约束 | 解析所有原始 frame |
| Contract/Conformance | fixture、golden、schema、adapter 语义验证 | 生产 containment |
| Security Operations | secret、egress、cross-tenant、supply-chain 事件 | 直接修改业务事实 |
| Privacy/Data Governance | purpose、classification、lineage、retention、DSAR | 代替 provider transport |
| Production Operations | SLO、容量、队列、部署、DR、on-call | 解释业务授权 |
| Incident Commander | severity、scope、指挥、行动、沟通、关闭证据 | 直接绕过审计 |
| Harness/RunSupervisor | run scope、cancel、checkpoint、recovery、delivery | 修改 provider contract |
| State/Event/Audit | durable facts、timeline、replay、完整性 | 生成健康判断 |
| Host/Status Adapter | 用户和 operator 状态投影 | 推断真实影响范围 |
| Provider Support/Legal | 外部事实、合同、通知和监管协调 | 修改本地路由或证据 |
### 强制边界
```text
Runtime signal
  -> correlation and classification
  -> incident declaration
  -> scope and severity
  -> containment command
  -> route/credential/egress enforcement
  -> forensic preservation
  -> recovery and reconciliation
  -> regression and postmortem
```
## Provider Incident 与普通错误的边界
### 普通 API error
普通 API error 通常具有以下属性：
- 只影响单个 request 或有限的独立 attempt。
- 可以由 canonical request、policy、schema、credential 或 context 自身解释。
- 不需要阻止同一 surface 上的其他安全请求。
- 可以由有界 retry、modified request、tool result 或 user correction 安全结束。
- 不产生跨租户、跨 region、持续外发或 adapter-wide 语义风险。
例子：
- `provider_invalid_request`：tool schema 不符合 provider 子集。
- `provider_context_overflow`：ContextPlan 超过 frozen model limit。
- 单个用户 credential scope 不匹配。
- 用户选择了不允许的模型。
- structured output 本地业务校验失败。
- 工具返回业务错误或用户取消。
### Provider incident
满足以下任一组合时应进入 incident candidate：
- 同一 ProviderSurface 在时间窗口内出现超出基线的 transport、5xx、EOF、timeout 或 usage settlement 失败。
- 发生跨 tenant、跨 region、错误 deployment 或错误 credential 的数据外发。
- provider/API family/model/deployment 的能力或 schema 语义漂移，导致 ToolCall、Structured Output、Safety、Usage 或 terminal integrity 失真。
- provider 返回错误 safety、refusal、grounding、citation 或 region policy 信号，影响产品安全要求。
- provider remote file、conversation、cache、batch 或 delete 状态不可控，并可能继续传播敏感数据。
- provider billing、usage 或 pricing 事实大面积不一致，影响 hard cap、chargeback 或安全资源控制。
- adapter、SDK、schema projector 或 normalizer 的变更使多个租户产生相同错误语义。
- 事故范围无法确定，且未知本身足以构成高敏感度或高副作用风险。
### 边界决策表
| 观察 | 普通错误 | Incident candidate | 必要动作 |
|---|---|---|---|
| 单次 500 | 是 | 否 | 有界 retry、记录 attempt |
| 5 分钟内同 surface 5xx 持续超基线 | 否 | 是 | 健康降级、circuit、关联 |
| 单个用户 401 | 是 | 否 | lease 失效、重新授权 |
| 多 tenant credential 401 且 rotation 后仍失败 | 否 | 是 | credential incident、停止新 lease |
| 一个 schema 400 | 是 | 否 | contract diagnostic |
| 多模型 tool call 解析边界同时变化 | 否 | 是 | adapter/capability quarantine |
| provider response 指向错误 region | 否 | 是 | egress stop、region isolation |
| provider safety refusal | 通常是 | 若分类/范围大面积漂移则是 | typed outcome；必要时 safety incident |
| tool business error | 是 | 否 | Tool Runtime recovery |
| remote upload ack 丢失 | unknown | 若敏感内容可能重复外发则是 | status query、禁止盲重传 |
| provider 账单差异 | 通常是 | 大面积影响 cap/chargeback 时是 | provisional settlement、reconcile |
## 事故分类学（incident taxonomy）
### `outage`
Provider surface 无法接受请求、建立连接、返回有效 terminal 或完成可验证 settlement。包括完全不可用和区域性不可用。
检测重点：request acceptance、TTFE、EOF、5xx、DNS/TLS、circuit、queue backlog。
### `degraded`
请求仍部分成功，但延迟、容量、错误率、stream 完整性、usage 可见性或完成率显著下降。
检测重点：分位延迟、retry amplification、first event timeout、unknown outcome、settlement lag。
### `capability_drift`
Provider 实际行为与 Catalog、Contract、CapabilityMatrix 或 Conformance evidence 不一致。
典型信号：tool call completion boundary、strict structured output、multimodal MIME、parallel tool calls、reasoning/citation/safety event、context limit 改变。
### `data_exposure`
数据进入未批准 provider、region、deployment、remote object、日志、trace、backup、support channel 或错误 tenant scope。
即使 provider response 是 200，也必须作为安全/隐私事故处理。
### `safety`
provider safety、refusal、moderation、abuse、grounding 或内容政策行为发生影响产品安全边界的异常。
不能把 provider safety 当本地 Policy；需要检查本地 Egress、Tool、Approval、Sandbox 和交付。
### `regional`
实际 endpoint、deployment、remote object、backup 或 support path 与允许的 region/jurisdiction/residency 不一致。
### `credential`
API key、bearer、cloud role、signer、lease、rotation epoch 或 revocation version 暴露、过期、错绑、过宽或被拒绝。
### `billing`
usage、price、minimum unit、currency、discount、provider receipt 或账单对账异常，导致预算、quota、chargeback 或成本安全控制失真。
### `schema`
provider request/response/event/error/usage schema 变化，旧 parser、projector、ledger、replay 或 contract 无法安全解释。
### `adapter`
本地 adapter、SDK、transport、normalizer、projection、credential binding 或配置实现错误，造成跨 provider surface 的系统性影响。
### 复合分类
事故可以同时属于多个 taxonomy；主分类用于指挥，辅分类用于控制。例如：
```text
schema + adapter + capability_drift
credential + data_exposure
regional + privacy
outage + billing
safety + provider_contract
```
## 总体架构与故障域
### 逻辑拓扑
```text
Provider Runtime / Routing / Health / Contract
  -> Signal Normalizer
  -> Correlation Engine
  -> Incident Detector
  -> Incident Command Plane
       -> Scope/Severity/Blast Radius
       -> Route/Circuit/Quarantine Controller
       -> Credential/Egress Controller
       -> Evidence/Timeline Store
       -> Communications/Provider Liaison
       -> Recovery/Reconciliation Controller
  -> State/Event/Audit/Artifact
  -> SLO/Dashboard/Evaluation/Release Gate
```
### 故障域
```text
provider + apiFamily + deployment + region + credentialClass
provider + modelClass + adapterVersion
route + tenantClass + workspaceClass
remoteObject + egressProfile
controlPlane + dataPlane + storage + workerPool
```
一个故障域不能自动扩大为整个 Provider，除非 correlation evidence 表明 provider-wide 影响或安全风险无法隔离。
### 控制面与数据面
控制面保存：
- Provider Surface registry、health snapshot、circuit、quarantine、incident、contract、conformance、routing 和 credential 状态。
- policy、egress、residency、retention、break-glass、communications 和 runbook 版本。
- incident command、timeline、evidence manifest、provider case reference 和 recovery plan。
数据面只使用：
- frozen RouteSnapshot、ContractSnapshot、EgressSnapshot、CredentialLeaseRef、PolicySnapshot、AdapterAttestationRef。
- 当前 run 的 ContextPlan、ToolsetSnapshot、WorkspaceView、BudgetReservation 和 ArtifactRef。
## 核心数据模型
### Incident 类型
```typescript
type ProviderIncidentId = string;
type IncidentSignalId = string;
type IncidentActionId = string;
type IncidentEvidenceId = string;
type IncidentSeverity = "SEV0" | "SEV1" | "SEV2" | "SEV3" | "SEV4";
type IncidentStatus =
  | "detected"
  | "acknowledged"
  | "declared"
  | "investigating"
  | "contained"
  | "recovering"
  | "validated"
  | "communicated"
  | "closed";
type IncidentTaxonomy =
  | "outage"
  | "degraded"
  | "capability_drift"
  | "data_exposure"
  | "safety"
  | "regional"
  | "credential"
  | "billing"
  | "schema"
  | "adapter";
```
### ProviderSurface
```typescript
interface ProviderSurface {
  provider: ProviderRef;
  apiFamily: ApiFamilyRef;
  modelClass?: string;
  deployment?: DeploymentRef;
  region?: string;
  endpointHash?: string;
  credentialClass?: string;
  adapterVersion: string;
  contractVersion: string;
  capabilityVersion?: string;
  attestationRef?: string;
}
```
### IncidentScope
```typescript
interface IncidentScope {
  scopeId: string;
  surfaces: ProviderSurface[];
  tenantClasses: string[];
  tenantIds?: string[];
  workspaceIds?: string[];
  sessionIds?: string[];
  runIds?: string[];
  attemptIds?: string[];
  routeIds?: string[];
  artifactIds?: string[];
  remoteObjectIds?: string[];
  credentialLeaseIds?: string[];
  regionClasses?: string[];
  dataClasses: Sensitivity[];
  startAt: string;
  endAt?: string;
  confidence: number;
  scopeHash: string;
}
```
### BlastRadius
```typescript
interface BlastRadius {
  affectedAttempts: number;
  affectedRuns: number;
  affectedTenants: number;
  affectedRegions: string[];
  affectedModels: string[];
  affectedRoutes: string[];
  affectedCredentials: string[];
  dataClasses: Sensitivity[];
  externalDestinations: string[];
  knownSuccessfulRequests: number;
  knownFailedRequests: number;
  unknownOutcomeCount: number;
  potentialExposureCount: number;
  confidence: number;
  limitations: string[];
}
```
### ProviderIncident
```typescript
interface ProviderIncident {
  incidentId: ProviderIncidentId;
  title: string;
  primaryTaxonomy: IncidentTaxonomy;
  secondaryTaxonomies: IncidentTaxonomy[];
  severity: IncidentSeverity;
  status: IncidentStatus;
  commander?: PrincipalRef;
  deputy?: PrincipalRef;
  scope: IncidentScope;
  blastRadius?: BlastRadius;
  hypotheses: IncidentHypothesis[];
  signals: IncidentSignalRef[];
  actions: IncidentActionRef[];
  timeline: TimelineEntryRef[];
  communications: CommunicationRef[];
  evidenceBundleRef?: ArtifactRef;
  providerCaseRef?: string;
  legalPrivacyReviewRef?: string;
  openedAt: string;
  updatedAt: string;
  closedAt?: string;
  rootCause?: RootCauseSummary;
}
```
### Signal
```typescript
interface ProviderSignal {
  signalId: IncidentSignalId;
  kind:
    | "request_error"
    | "stream_integrity"
    | "health_probe"
    | "circuit_transition"
    | "capability_mismatch"
    | "schema_drift"
    | "egress_violation"
    | "credential_failure"
    | "usage_variance"
    | "billing_variance"
    | "quality_breach"
    | "tenant_report"
    | "provider_notice"
    | "security_detector"
    | "privacy_detector";
  observedAt: string;
  source: EventSource;
  surface?: ProviderSurface;
  scope?: ScopeRef;
  category?: string;
  code: string;
  severityHint: IncidentSeverity;
  confidence: number;
  count?: number;
  window?: TimeWindow;
  evidenceRefs: EvidenceRef[];
  redactionState: string;
}
```
### IncidentAction
```typescript
interface IncidentAction {
  actionId: IncidentActionId;
  incidentId: ProviderIncidentId;
  type:
    | "open_circuit"
    | "quarantine_route"
    | "stop_traffic"
    | "restrict_fallback"
    | "stop_shadow"
    | "rollback_canary"
    | "revoke_credential"
    | "rotate_credential"
    | "stop_egress"
    | "quarantine_remote_object"
    | "pause_run"
    | "cancel_safe_retry"
    | "query_provider_status"
    | "preserve_evidence"
    | "notify_provider"
    | "notify_tenant"
    | "restore_traffic";
  actor: PrincipalRef;
  scope: IncidentScope;
  reason: string;
  policyVersion: string;
  approvalRef?: string;
  breakGlassRef?: string;
  commandHash: string;
  expiresAt?: string;
  status: "planned" | "issued" | "applied" | "partial" | "failed" | "rolled_back";
  receiptRefs: EvidenceRef[];
  issuedAt: string;
}
```
### Timeline 与 Evidence
```typescript
interface TimelineEntry {
  timelineId: string;
  incidentId: ProviderIncidentId;
  occurredAt: string;
  observedAt: string;
  actor?: PrincipalRef;
  kind: "signal" | "decision" | "action" | "communication" | "receipt" | "hypothesis" | "scope_change";
  summary: string;
  sourceEventIds: string[];
  evidenceRefs: EvidenceRef[];
  immutableHash: string;
}
interface IncidentEvidenceBundle {
  bundleId: string;
  incidentId: ProviderIncidentId;
  scope: IncidentScope;
  eventRefs: string[];
  auditRefs: string[];
  artifactRefs: ArtifactRef[];
  requestHashes: string[];
  responseHashes: string[];
  providerReceiptRefs: string[];
  routeSnapshotRefs: string[];
  contractSnapshotRefs: string[];
  credentialRefs: string[];
  timelineRefs: string[];
  retentionClass: string;
  legalHold?: string;
  redactionState: string;
  integrityHash: string;
  collectedBy: PrincipalRef;
  collectedAt: string;
}
```
## TypeScript 接口
### Detection 与 Correlation
```typescript
interface ProviderIncidentDetector {
  ingest(signal: ProviderSignal): Promise<SignalReceipt>;
  correlate(input: CorrelationInput): Promise<CorrelationResult>;
  assess(input: IncidentAssessmentInput): Promise<IncidentAssessment>;
  declare(input: IncidentDeclaration): Promise<ProviderIncident>;
}
interface CorrelationInput {
  signals: ProviderSignal[];
  lookback: TimeWindow;
  dimensions: ("provider" | "apiFamily" | "model" | "deployment" | "region" | "route" | "tenantClass" | "credentialClass" | "adapter")[];
  baselineRefs: string[];
}
interface CorrelationResult {
  clusters: SignalCluster[];
  deduplicated: ProviderSignal[];
  crossSignals: CorrelationLink[];
  missingEvidence: EvidenceRequirement[];
}
```
### Incident Controller
```typescript
interface ProviderIncidentController {
  declare(input: IncidentDeclaration): Promise<ProviderIncident>;
  addSignal(incidentId: string, signal: ProviderSignal): Promise<void>;
  updateSeverity(incidentId: string, severity: IncidentSeverity, reason: string): Promise<void>;
  updateScope(incidentId: string, scope: IncidentScope, reason: string): Promise<void>;
  planContainment(incidentId: string): Promise<ContainmentPlan>;
  applyAction(action: IncidentAction, signal?: AbortSignal): Promise<ActionReceipt>;
  createEvidenceBundle(incidentId: string): Promise<ArtifactRef>;
  transition(incidentId: string, status: IncidentStatus, reason: string): Promise<void>;
  close(input: IncidentClosure): Promise<void>;
}
```
### Route 与 Credential 控制
```typescript
interface ProviderRiskController {
  quarantineSurface(input: QuarantineSurfaceRequest): Promise<QuarantineReceipt>;
  openCircuit(input: CircuitOpenRequest): Promise<CircuitReceipt>;
  stopTraffic(input: TrafficStopRequest): Promise<TrafficStopReceipt>;
  restrictFallback(input: FallbackRestrictionRequest): Promise<void>;
  stopEgress(input: EgressStopRequest): Promise<EgressStopReceipt>;
  revokeCredential(input: CredentialRevocationRequest): Promise<RevocationReceipt>;
  rotateCredential(input: CredentialRotationRequest): Promise<RotationReceipt>;
  restore(input: RestoreTrafficRequest): Promise<RestoreReceipt>;
}
```
### Recovery 与 Reconciliation
```typescript
interface ProviderIncidentRecovery {
  enumerate(input: RecoveryScopeRequest): Promise<RecoveryCandidate[]>;
  queryProvider(input: ProviderStatusQuery): Promise<ProviderStatusReceipt>;
  reconcile(input: ProviderReconciliationRequest): Promise<ReconciliationReport>;
  recover(input: RecoveryPlan, signal: AbortSignal): Promise<RecoveryReport>;
  verify(input: RecoveryVerificationRequest): Promise<VerificationReport>;
}
```
### Communication
```typescript
interface ProviderCommunicationPort {
  openCase(input: ProviderCaseRequest): Promise<ProviderCaseReceipt>;
  sendStatus(input: ProviderStatusMessage): Promise<CommunicationReceipt>;
  requestTimeline(input: ProviderTimelineRequest): Promise<ProviderTimelineReceipt>;
  requestDeletionOrRevoke(input: ProviderRemoteActionRequest): Promise<ProviderRemoteActionReceipt>;
  closeCase(input: ProviderCaseClosure): Promise<CommunicationReceipt>;
}
```
## Signal Detection 与 Correlation
### 信号来源
信号必须来自多层 source：
- Provider Runtime：error category、provider code、request ID、stream sequence gap、EOF、finish、usage、receipt。
- Provider Health：liveness、readiness、capability readiness、first-event、settlement、quota、circuit。
- Routing：candidate removed、fallback rate、sticky invalidation、canary rollback、route quarantine。
- Contract/Conformance：fixture mismatch、unknown event、schema diff、projection unsafe、capability false positive。
- Security/Privacy：wrong region、secret detector、DLP、cross-tenant、remote object、credential anomaly。
- Data Quality：usage reconciliation、lineage gap、provider copy orphan、deletion unknown、billing variance。
- Production Operations：queue age、worker saturation、error budget burn、deployment version、config change。
- Tenant/Host：用户报告、错误交付、模型能力变化、数据驻留疑问。
- Provider Communication：服务通知、support case、区域或 API 变更说明。
### Detection 不变量
- 单一 500 只能形成 signal，不能自动形成高严重度 incident。
- 多个相互独立的 signal 需要以 provider surface、scope、时间窗和版本 correlation。
- `unknown`、`inconclusive`、`skipped` 不计为 healthy。
- 安全、隐私、区域和 credential signal 的置信度低，也不能仅凭低置信度自动降级为无害。
- detector 版本、baseline、窗口、阈值和 sampling 必须记录。
- detector 不能直接重试或切换 provider；它只能提出 `IncidentCandidate`。
### Correlation 维度
```text
provider + apiFamily
  + modelClass/deployment
  + region/location
  + adapter/transport version
  + credentialClass
  + route strategy
  + tenant class
  + data sensitivity
  + time window
```
### 典型关联规则
1. **Outage cluster**：同 surface 的 request acceptance、TTFE、5xx、EOF 和 circuit signal 在窗口内同时异常。
2. **Capability cluster**：多个 fixture、live smoke、生产 Attempt 观察到同一 tool/structured/event 语义变化。
3. **Exposure cluster**：EgressSnapshot 与实际 endpoint、region、remote object 或 provider receipt 不一致。
4. **Credential cluster**：多个 tenant class 或 deployment 同时出现 auth failure，且与 rotation、scope 或 provider notice 相关。
5. **Billing cluster**：UsageLedger、provider receipt、PriceCatalog 和账单 line item 出现系统性差异。
6. **Adapter cluster**：错误集中在同一 adapter/SDK/normalizer version，而其他 adapter 正常。
7. **Regional cluster**：一个 region/deployment 异常，其他 region 同 surface 正常。
## Severity、Blast Radius 与影响评估
### Severity
| 级别 | 触发示例 | 首要目标 |
|---|---|---|
| SEV0 | 跨 tenant data exposure、secret 泄漏、错误 region 持续外发、sandbox/egress fail-open | 立即停止传播并建立统一指挥 |
| SEV1 | provider-wide outage、关键能力漂移、credential compromise、未知副作用大面积存在 | 快速 containment、影响确认和外部沟通 |
| SEV2 | 单区域/单 API family/单模型重要退化，具备安全 workaround | 限制范围、恢复兼容路线 |
| SEV3 | 非关键 capability、usage、billing 或 schema 漂移，有明确 workaround | 修复并加入发布门禁 |
| SEV4 | 低影响 diagnostic drift、单次 provider notice、非关键指标异常 | 记录、排期、观察 |
### Severity 计算轴
```text
severity = max(
  availability impact,
  data sensitivity impact,
  side-effect risk,
  scope breadth,
  propagation potential,
  uncertainty penalty,
  contractual/privacy/legal impact
)
```
- `secret`、`regulated`、跨 tenant 和错误 region 具有硬提升规则。
- 影响范围未知但潜在高敏感度时按较高级别处理。
- 低 confidence 不能抵消高 impact。
- severity 变化必须追加 timeline 和 actor。
### Blast Radius 计算
至少统计：
- provider、api family、model、deployment、region 和 endpoint。
- adapter、SDK、schema、projection、routing 和 config version。
- tenant class、tenant 数量、workspace、session、run、attempt。
- 成功、失败、拒答、取消、unknown outcome 的请求数量。
- request/response/tool/artifact/remote object 的数据敏感度。
- credential lease、rotation epoch、provider remote copy、日志/trace/backup 传播。
- 起止时间、最后已知健康点、恢复点和证据缺口。
### 影响评估状态
```text
unknown -> bounded -> confirmed -> reconciled
```
`bounded` 表示有保守上界；`confirmed` 具有可验证 receipt；`reconciled` 表示各副本与 ledger、route、event 已完成对账。
## Tenant/Region/Model/Route Isolation
### 隔离优先级
1. 先阻断受影响 ProviderSurface 的新发送。
2. 再隔离错误 region、deployment、model 或 adapter。
3. 再按 credential class、tenant class 和 route partition 精细隔离。
4. 只在 evidence 证明 provider-wide 时扩大 provider 级停止。
5. 不得用 sticky、cache、旧 route snapshot 或 background worker 绕过 quarantine。
### Tenant 隔离
- TenantContext 来自认证，不由 incident signal 或 provider response 覆盖。
- 以 tenant class、data class、residency class 和 policy version 建安全分桶。
- 如只有少数 tenant 受影响，优先停止这些 scope，不全局拒绝无关租户。
- 跨 tenant correlation 只使用脱敏聚合；forensics 查询重新授权。
- 一个 tenant 的 credential failure 不应污染其他 tenant，除非共享 credential class 已被证明暴露。
### Region 隔离
- region、location、jurisdiction、endpoint 和 remote object destination 分开记录。
- region 事故期间禁止自动跨境 fallback，除非已有独立 Egress/Provider Security Contract。
- 备份、日志、trace、support diagnostic、shadow 和 provider cache 也要纳入 region 影响。
- region 恢复必须用低敏感 synthetic probe 验证 endpoint 与声明一致。
### Model/Route 隔离
- 按 model class、deployment、API family、adapterVersion 和 capability fingerprint 拆分 circuit。
- route quarantine 只影响新 Attempt；历史 Attempt 不被改写。
- fallback 必须重新做 capability、schema、egress、residency、budget 和 safety 检查。
- shadow、canary、hedge 不能复制受限 payload；事件期间默认停止。
- route restore 需要 canary、health、conformance、quality 和 usage reconciliation evidence。
## Containment、Quarantine 与流量控制
### Containment Plan
```typescript
interface ContainmentPlan {
  incidentId: string;
  stopNewAttempts: boolean;
  stopProviderEgress: boolean;
  affectedSurfaces: ProviderSurface[];
  affectedScopes: IncidentScope;
  circuitActions: CircuitOpenRequest[];
  routeActions: QuarantineSurfaceRequest[];
  fallbackPolicy: "disabled" | "same_region_only" | "approved_candidates_only" | "none";
  credentialActions: CredentialRevocationRequest[];
  remoteObjectActions: ProviderRemoteActionRequest[];
  runActions: ("pause" | "cancel_safe_retry" | "quarantine" | "continue_to_boundary")[];
  evidencePlan: EvidenceCollectionPlan;
  expiresAt?: string;
}
```
### Traffic stop 层次
```text
candidate filter
  -> circuit open
  -> route quarantine
  -> model capability disable
  -> API family stop
  -> provider egress stop
  -> credential revoke
  -> tenant/region pause
  -> provider-wide deny
```
优先使用最小有效停止范围；安全事故或未知外发不能为了可用性保留不受控路径。
### Quarantine 对象
可 quarantine：
- ProviderSurface、RouteCandidate、ModelCapability、Adapter、SDK version、Schema Projection。
- Credential、CredentialLease、RemoteObject、Artifact、Cache namespace、Run、Worker pool。
- Conformance fixture、Canary cohort、Shadow plan、Deployment、Region。
quarantine 必须有 reason、owner、scope、createdAt、expiry、解除条件和传播目标。
### Fallback restrictions
- `disabled`：任何新 provider route 都禁止。
- `same_region_only`：只允许相同 jurisdiction/region 的兼容候选。
- `approved_candidates_only`：只允许预先通过 Contract/Conformance/Privacy 的候选。
- `safe_text_only`：禁用 tools、files、remote objects、structured strict 和高敏感度数据。
- `queue_or_pause`：保留请求但不发送，等待 incident 解除。
### Run 控制
- 对安全可继续的低风险 Attempt，可运行到当前授权 boundary。
- 对可能受污染的 Context、Toolset、Provider response 或 Artifact，转 quarantine/read-only。
- 对 stream 已产生完整 ToolCall 但 incident 在执行前发生，重新执行 Policy、Egress 和 Approval。
- 对 provider-side unknown action，停止自动 retry/fallback，先 query receipt。
## Credential Rotation、Revocation 与 Egress Stop
### 何时 revoke
- API key、token、cloud role 或 signer 暴露、错绑、scope 过宽、region 错误或 rotation epoch 不一致。
- provider 返回 secret-like 内容并无法确认传播范围。
- adapter/worker/plugin 可能读取了不应访问的 credential。
- incident command 要求停止所有新请求。
### Revocation 流程
```text
incident signal
  -> freeze new lease
  -> mark credential class suspect
  -> revoke active leases
  -> invalidate worker/provider caches
  -> stop affected route/egress
  -> issue staged replacement
  -> health/conformance smoke
  -> canary new lease
  -> expand or quarantine
```
旧 lease 不能因为 run 尚未结束就无限延长；高风险动作在 revoke 后停止或进入 unknown/recovery。
### Rotation 规则
- 新 credential 使用新 version/epoch，旧 audit 不覆盖。
- 轮换验证使用 synthetic/public 数据和低权限 probe。
- provider、region、deployment、purpose、tenant class、adapter attestation 必须重新绑定。
- 轮换期间同一旧 key 的 retry 不得继续放大流量。
- rotation receipt、旧 lease revoke、缓存失效和 worker 通知必须可查询。
### Egress stop
Egress stop 是数据面控制，不只是 dashboard 标记：
- Provider Runtime 在 send boundary 检查 EgressSnapshot 和 revoke version。
- Transport 拒绝创建新连接或发送 body；已连接 stream 进入安全关闭。
- Artifact provider upload、URL fetch、remote file reuse、shadow、canary 和 telemetry export 同时检查 stop state。
- raw payload、tokenization map、secret、regulated 内容不得进入 incident channel 或普通日志。
- egress stop 失败时升级 severity，并将相关 route/credential quarantine。
## Provider Communication 与外部协作
### Provider liaison 责任
由指定 provider liaison 负责：
- 建立 provider case，引用脱敏 request ID、provider request ID、region、deployment、时间窗和错误类别。
- 请求确认 outage、容量、API/schema 变化、region、safety、billing、remote object 或 credential 状态。
- 不发送用户 prompt、secret、完整工具参数或不必要 regulated payload。
- 记录 provider 回复时间、联系人、case ID、声明范围、限制和验证方式。
- 将 provider communication 作为 signal/evidence，不作为本地恢复的唯一条件。
### Provider Case 数据
```typescript
interface ProviderCaseRecord {
  caseId: string;
  incidentId: string;
  provider: string;
  apiFamily?: string;
  surfaces: ProviderSurface[];
  timeWindow: TimeWindow;
  requestIds: string[];
  safeErrorSummaries: string[];
  questions: string[];
  sentAt: string;
  receivedAt?: string;
  providerClaims: string[];
  verificationPlan: string[];
  limitations: string[];
}
```
### 不同意 provider 结论时
- 保留 provider claim 与本地 observed evidence 的差异。
- 不能因为 provider 说“已恢复”就立即恢复全部流量。
- 继续以 local health、conformance、security、privacy、billing 和 reconciliation gate 验证。
- 若合同、隐私或法律风险仍未澄清，维持 quarantine 或 restricted mode。
## Forensics、Evidence 与 Timeline
### Evidence 分层
1. **Runtime evidence**：request/response ID、错误分类、stream frame hash、finish、usage、receipt。
2. **Control evidence**：RouteSnapshot、ContractSnapshot、Policy/Egress、CredentialLease、AdapterAttestation、ConfigSnapshot。
3. **State evidence**：Attempt、ToolCall/Result、ArtifactRef、RemoteObject、Event cursor、Checkpoint、UsageLedger。
4. **Operational evidence**：health、circuit、queue、worker、deployment、rollout、canary、dashboard snapshot。
5. **External evidence**：provider case、status message、billing receipt、regional notice、legal/privacy review。
### Forensic 原则
- 先冻结 scope、时间窗、retention/incident hold，再收集。
- 原始 event、audit、receipt 和 immutable artifact 不原地修改。
- raw payload 使用受控 ArtifactRef、加密、短 TTL、最小访问和 redaction。
- 解释、假设和结论写入附加 timeline，不写回原始事实。
- evidence collection 自身具有 actor、purpose、scope、命令 hash 和审计。
- 对不能确认的内容保存 `unknown`，不填充成功或失败。
### Timeline 规范
每条 timeline entry 必须区分：
- `occurredAt`：事实发生时间。
- `observedAt`：系统收到信号时间。
- `recordedAt`：写入 durable store 时间。
- `monotonicDuration`：本地耗时。
- `actor`：自动检测器、worker、operator、commander、provider liaison。
- `sourceEventIds`、`causationEventId`、`evidenceRefs`。
### 最小 timeline
```text
first observed signal
last known good
incident candidate created
incident declared
commander assigned
scope bounded
traffic/circuit action issued
credential/egress action issued
provider contacted
tenant status updated
first containment verified
recovery probe passed
traffic restored
reconciliation completed
postmortem accepted
regression gate passed
incident closed
```
## Incident Command、状态更新与沟通
### Incident Command 角色
- `Incident Commander`：最终协调、优先级、severity、scope、行动批准和关闭标准。
- `Operations Lead`：provider health、queue、worker、route、deployment、rollback。
- `Runtime Lead`：adapter、normalizer、schema、contract、unknown outcome。
- `Security Lead`：credential、egress、cross-tenant、forensics、containment。
- `Privacy/Legal Lead`：data class、residency、retention、DSAR、通知义务输入。
- `Provider Liaison`：外部 case、状态、证据和恢复确认。
- `Tenant/Communications Lead`：用户状态、影响摘要、下一次更新时间。
- `Scribe`：timeline、decision log、action receipt、未决问题。
### 状态更新内容
每次更新尽量包含：
- 当前状态和绝对时间。
- 受影响的 provider surface 和已确认范围。
- 用户可见影响：不可用、延迟、功能受限、结果可能延迟或数据处理暂停。
- 已执行 containment，不公开 secret、内部 endpoint 或其他租户信息。
- 当前 workaround/fallback 是否可用及限制。
- unknown 范围和下一步验证。
- 下一次更新时间或恢复条件。
### 沟通不变量
- 不把“错误率下降”写成“所有请求恢复”。
- 不把 provider claim 写成已验证事实。
- 不在公共状态中暴露租户、凭据、敏感数据或安全检测细节。
- 安全/隐私事故由 Security/Privacy/Legal 决定通知范围，不能只由 SRE 判断。
- 所有沟通消息引用 incident、scope、时间窗和 evidence 版本。
## Recovery、Reconciliation 与恢复验证
### Recovery 阶段
```text
containment verified
  -> repair/config/adapter/credential change
  -> conformance and security regression
  -> low-risk probe
  -> canary route
  -> bounded traffic
  -> full route restoration
  -> reconcile historical attempts
  -> close residual unknowns
```
### 恢复前门禁
- Contract/Schema/Capability evidence 新鲜且通过。
- Adapter/SDK/transport 配置与 attestation 正确。
- Credential rotation/revoke 传播完成。
- Egress/region/residency、DLP、retention 和 remote object 状态可解释。
- Circuit half-open probe 成功，且非仅一条成功请求。
- Canary 的 error、latency、tool、structured、safety、usage、cost 和 unknown 指标在阈值内。
- 关键 durable event、audit、ledger、artifact 和 checkpoint 能正常提交。
### Reconciliation 对象
- Provider request ID、Attempt、RouteSnapshot、ModelChange 和 usage。
- stream sequence、terminal、ToolCall/ToolResult、structured result、safety/refusal。
- Artifact upload、本地 ref、provider remote object、status/delete receipt。
- Credential lease、rotation epoch、revoke event、worker cache。
- Provider billing receipt、UsageLedger、PriceCatalog、BudgetReservation。
- tenant/region/model/route exposure、日志/trace/backup/forensics copy。
### RecoveryReport
```typescript
interface RecoveryReport {
  incidentId: string;
  scope: IncidentScope;
  recoveredSurfaces: ProviderSurface[];
  verifiedAttempts: number;
  unknownAttempts: number;
  reconciledUsageEntries: number;
  reconciledRemoteObjects: number;
  unresolvedFindings: ReconciliationFinding[];
  canaryEvidenceRefs: EvidenceRef[];
  residualRisk: string[];
  verifiedAt: string;
}
```
### 恢复失败
恢复失败时：
- 保持 route quarantine 或 degraded，不循环扩大 fallback。
- 保留旧 evidence、旧 config 和恢复尝试的新增 evidence。
- 将未解决范围升级 severity 或创建 follow-up incident。
- 不删除失败版本；必要时 rollback adapter/config，但不重写历史 Attempt。
## Postmortem、回归与发布门禁
### Postmortem 必须回答
1. 发生了什么，哪些事实已确认，哪些仍 unknown。
2. provider surface、tenant、region、model、route、credential 和数据副本的影响范围。
3. 为什么检测到、为什么没有更早检测到。
4. 为什么 containment 能或不能阻止继续传播。
5. 哪些动作、retry、fallback、hedge、shadow、canary 产生了额外成本或副作用。
6. 哪些 contract、schema、adapter、policy、egress、SLO、runbook 或人机流程需要改变。
7. 哪些回归 fixture、conformance case、fault injection 和 dashboard 已新增。
8. 哪些残余风险、owner、截止日期和验证证据仍未完成。
### Incident Regression Case
```typescript
interface IncidentRegressionCase {
  caseId: string;
  incidentId: string;
  taxonomy: IncidentTaxonomy[];
  minimalRequestRef?: ArtifactRef;
  rawFrameRefs?: ArtifactRef[];
  expectedEvents: EventExpectation[];
  expectedState: string;
  forbiddenActions: string[];
  expectedContainment: string[];
  expectedRecovery: string[];
  privacyProfile: string;
  contractVersions: Record<string, string>;
  owner: string;
  status: "draft" | "active" | "retired";
}
```
### 发布门禁
阻断发布：
- 新 adapter、schema、projection 或 capability 声明无法通过受影响事故回归。
- unknown critical event、terminal、ToolCall pairing、usage 或 scope 失败。
- quarantine surface 仍进入 active route。
- revoke/rotation/egress stop 无法传播到 worker、cache、provider transport。
- provider response 可覆盖 tenant、region、approval、policy 或 artifact owner。
- provider unknown outcome 被结算为 success 或被盲目重放。
- incident evidence、timeline、audit 或 privacy/legal hold 丢失。
可观察但不一定阻断：
- provider wording、delta 粒度或非关键 metadata 变化。
- 允许的低风险 capability degradation，且已更新用户可见限制。
- 估算 usage 与账单小范围差异，且仍标记 provisional/reconciled。
## SLO、Error Budget 与运营控制
### Provider SLI
- request acceptance rate。
- first event / first text / first tool call latency。
- stream terminal integrity rate。
- normalized completion rate。
- provider 5xx、429、capacity、auth、capability、schema、safety、EOF、timeout 比例。
- unknown outcome rate。
- usage settlement completeness。
- route fallback、retry amplification、circuit open duration。
- data egress decision completeness、region correctness、remote object reconciliation。
- incident detection latency、containment latency、recovery latency、reopen rate。
### SLO 分母
分母必须包括：
- 成功、失败、拒答、取消、unknown、retry、fallback、shadow、canary 和后台 run。
- provider request、remote upload、status query、delete、billing import 等不同操作类型。
- 高敏感度 egress、credential rotation、audit commit 和 terminal settlement 的 hard invariant。
### Error Budget 动作
错误预算接近耗尽时：
- 停止非必要 canary、shadow、hedge 和实验流量。
- 降低 background、subagent、compaction 或高成本 route 并发。
- 限制 fallback 次数和 retry amplification。
- 要求更严格的 contract/conformance、人工审批或 queue。
- 不得为了恢复 availability 关闭 audit、DLP、egress、approval、sandbox 或 tenant isolation。
### 事故与错误预算
事故关闭前必须把：
- 受影响 SLI、消耗的 error budget、恢复时间、影响范围和成本。
- 是否触发 provider route pause、canary rollback、credential rotation、privacy/legal review。
- 是否新增 SLO、阈值、detector、runbook、fixture 和 owner。
写入 durable incident 与 postmortem。
## Break-glass 与 Privacy/Legal Coordination
### Break-glass 使用条件
只用于：
- 正在持续的高风险外发或副作用 containment。
- 正常控制面故障而无法停止 provider egress、撤销 credential 或保全证据。
- 需要读取最小 forensic metadata 以判断影响范围。
- 需要执行已批准的恢复、rotation、quarantine 或 status query。
### Break-glass 约束
- 绑定 incident、tenant/scope、purpose、命令 allowlist、TTL、双人审批或强认证。
- 默认 metadata-only、read-only、最小 provider/region/credential scope。
- 不允许借 break-glass 扩大 provider egress、下载完整 prompt 或读取无关租户。
- 每条命令有 command hash、actor、开始/结束、结果和 evidence ref。
- 事件结束自动 revoke，并审计所有访问、导出和未使用 grant。
### Privacy/Legal Coordination 触发
- data exposure、错误 region、regulated data、secret、provider retention/training 变化。
- remote object 无法删除、DSAR/删除传播不完整、legal hold 可能受影响。
- provider support、abuse review、人工内容审查或跨境数据路径未知。
- 通知、合同、监管、客户承诺或安全事件定义可能受影响。
### 分工
- Security 负责 containment、credential、egress、取证和攻击面。
- Privacy/Data Governance 负责 data inventory、lineage、purpose、retention、删除和 DSAR。
- Legal/Compliance 提供法律判断、通知与合同义务输入；不直接修改 runtime 事实。
- Incident Commander 统一节奏和决策记录。
## 生命周期与状态机
### Incident 生命周期
```text
SignalObserved
  -> Correlated
  -> CandidateCreated
  -> Acknowledged
  -> Declared
  -> Investigating
  -> ContainmentPlanned
  -> ContainmentApplied
  -> Contained
  -> Recovering
  -> CanaryVerified
  -> TrafficRestored
  -> Reconciliating
  -> Validated
  -> Communicated
  -> Closed
```
异常分支：
```text
任何活动状态 -> Escalated
任何活动状态 -> Suspended
任何活动状态 -> Reopened
ContainmentApplied -> PartialContainment
Reconciliating -> Unresolved
```
### Action 生命周期
```text
Proposed -> Approved -> Issued -> Applying -> Applied
Applying -> Partial | Failed
Applied -> Verified | RolledBack
```
### Surface 生命周期
```text
Active -> Suspected -> Degraded -> Quarantined -> Probed -> Canarying -> Active
Active -> Suspended -> Retired
```
### 状态不变量
- `Declared` 前必须存在最小 signal、scope、reason 和 owner。
- `Contained` 前不能声称所有外发已停止；必须有 action receipt 或明确失败。
- `TrafficRestored` 前必须有 canary 和 hard gate evidence。
- `Closed` 前必须完成 timeline、blast radius、reconciliation、postmortem owner 和 regression plan。
- `Reopened` 不覆盖原关闭事实，必须引用新 signal 和新 timeline。
- `Quarantined` surface 不得被 sticky、fallback、shadow 或 provider cache 复用。
## 端到端决策流程
### Receive/Normalize
1. 收集 Provider Runtime、Health、Routing、Security、Privacy、Quality、Billing、Tenant 和 Provider Communication signal。
2. 验证 event schema、source、timestamp、scope、surface、redaction 和 evidence ref。
3. 去重相同 event ID、request ID、provider receipt、detector window 和 root cause。
4. 关联 provider、api family、model、deployment、region、adapter、credential、route、tenant class 和版本。
5. 与 baseline、SLO、error budget、conformance、catalog freshness 比较。
### Classify/Assess
6. 判断普通 API error、业务 error、tool error、user cancellation、platform incident 或 provider incident candidate。
7. 选择 primary/secondary taxonomy。
8. 计算 severity、confidence、blast radius 和 data exposure potential。
9. 如果范围未知，按最保守安全上界建立临时 scope。
10. 分配 commander、lead、scribe、provider liaison 和 privacy/security reviewers。
### Contain
11. 选择最小有效 circuit/route/model/region/tenant/credential 隔离。
12. 停止 unsafe retry、fallback、hedge、shadow 和 canary amplification。
13. 需要时停止 provider egress、撤销 lease、rotation credential、quarantine remote object。
14. 暂停相关 run、worker、artifact transfer、memory write、export 或 background job。
15. 保全 event、audit、receipt、snapshot、artifact、usage 和 provider case evidence。
16. 发布脱敏状态更新和下一次更新承诺。
### Investigate/Communicate
17. 形成并行 hypotheses：provider outage、regional、adapter、schema、credential、policy、data exposure、billing、safety。
18. 用低敏感度 probe、fixture、record/replay、conformance、route comparison 和 status query 缩小范围。
19. 与 provider 沟通安全摘要、request IDs、时间窗和问题清单。
20. Privacy/Legal 判断通知、hold、DSAR、删除和合同路径。
21. 持续更新 timeline、blast radius、未知项和决策理由。
### Recover/Reconcile
22. 修复或切换已批准的 adapter、route、credential、config、schema 或 policy。
23. 运行 conformance、security、privacy、quality、usage、cost 和 canary gate。
24. 逐步恢复流量，按 tenant class、region、model、route 和 low-risk cohort 扩大。
25. 对 Attempt、ToolCall、Artifact、RemoteObject、Credential、Usage、Billing、Audit 和 Egress 做对账。
26. 处理 unknown outcome、删除、rotation、revoke、cache invalidation 和 residual risk。
### Close/Improve
27. 生成 postmortem、root cause、timeline、impact、cost、SLO 和 communication summary。
28. 新增 incident regression fixture、contract case、conformance gate、detector、runbook 和 dashboard。
29. 验证所有 action、owner、due date、expiry、rollback 和 evidence。
30. 关闭 incident 或保留明确 follow-up；不以“provider 恢复”替代本地治理完成。
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### Model/Provider Runtime
- Provider Runtime 产生 AttemptStarted、AttemptFailed、Usage、Finish、ProviderEvent、UnknownOutcome 和 RawResponseRef。
- Incident Controller 消费这些事实，但不改写 ModelResponse 或错误原文。
- `ProviderSurface`、RouteSnapshot、ContractSnapshot、CredentialLeaseRef、EgressSnapshot 和 AdapterAttestation 必须写入 Attempt。
- Incident quarantine 在 ModelRequest send boundary 被强制，不能只在 Router UI 中标记。
- provider metadata、safety、citation、grounding 和 usage 按 incident scope 做受控保存。
### Prompt
- Prompt 可以解释 degraded mode、provider unavailable、fallback restriction、safe text only、暂停工具或等待恢复。
- Prompt 不宣称 provider 已恢复，不解释未验证的 root cause，不授予 break-glass。
- Incident status 作为可信 Harness resource 注入，外部 provider text、工具结果和用户声称是数据。
- 事故期间 Prompt/Context 编译必须使用最新允许的 capabilities，但当前 run 仍引用 frozen snapshot；变更写入 ConfigChange/IncidentAction。
### Context
- ContextPlan 保存 selected、summarized、offloaded、dropped resources、view hash、purpose、sensitivity、provider target、region、contract 和 incident restriction。
- 发生 data exposure 或 region incident 时，Context Runtime 重新计算 egress view，不能继续使用旧 raw context。
- compaction 不能删除 IncidentSignal、UnknownOutcome、EgressDecision、CredentialRevoke、LegalHold 或 forensic refs。
- replay 只使用 recorded/sanitized context，不向真实 quarantined provider 发送敏感历史内容。
### Tool
- provider ToolCall 仍进入 ToolCallAssembler、schema/business validation、Policy、Approval、Sandbox 和 execution receipt。
- incident 期间可全局关闭工具、关闭特定 effect、限制 provider-side tools 或转 fake/dry-run。
- ToolResult、ArtifactRef 和 remote object 状态进入 blast radius 与 lineage；不能只看 provider response。
- 有副作用的 tool unknown outcome 不得因为 provider incident 自动 retry；先查询 receipt、幂等键和业务状态。
### State/Memory/Artifact/Event
- State 保存 IncidentRef、RouteQuarantine、FallbackRestriction、CredentialRevoke、EgressStop、Recovery、Postmortem 和 RegressionRef。
- Memory 默认不接收 incident 原始 payload、secret、完整 provider error 或法律资料；只写允许的结构化摘要。
- Artifact 保存 raw fixture、sanitized evidence、timeline、forensic bundle、provider case 和回归数据，独立 retention/ACL。
- Event Store 是 timeline、scope、action 和 recovery 的 source of truth；UI/Slack/指标只是投影。
- Session Replay 只重建状态和证据，不能重放真实 provider、Tool、Webhook、付款或删除副作用。
### Policy/Sandbox
- Policy 决定 provider/model/region/credential/egress/route 是否允许；Incident Response 可以产生更严格的 deny/quarantine obligation。
- Sandbox 在事故期间可切换 read-only、offline、no-network、fake provider 或 quarantine profile。
- break-glass 仍需 Policy、Approval、Sandbox Attestation 和 Audit；incident commander 不是万能权限。
- 事故解除必须重新生成 PolicySnapshot、EgressSnapshot、CredentialLease 和 RouteSnapshot。
### Harness
- Harness Bootstrap 装配 Signal Router、Incident Controller、Health、Routing、Contract、Security、Privacy、Evidence 和 Communications ports。
- RunSupervisor 监听 IncidentAction、CredentialRevoke、EgressStop、RouteQuarantine、PolicyChange 和 ProviderStatus。
- 高风险事件触发 structured cancellation 或 pause；Host disconnect 不等于 incident resolved。
- background worker、subagent、compaction、export、delete 和 recovery job 继承 incident scope，但不得扩大权限。
- terminal 前必须结算 Attempt、Tool、Usage、Artifact、Audit 和 Incident event；未结算则返回 structured diagnostics。
## 故障恢复与 Unknown Outcome
### Provider request unknown
1. 读取 request/attempt/transport/stream receipt。
2. 确认是否观察到 provider request ID、首帧、terminal 或 usage。
3. 查询 provider status/idempotency/remote object（若 contract 支持）。
4. 将结果分类为 `not_started`、`completed_known`、`failed_known`、`unknown`。
5. unknown 不盲重放；创建 RecoveryCandidate 和 incident timeline。
6. 新 Attempt 必须使用新的 Attempt ID、RouteSnapshot、ContractSnapshot、EgressSnapshot 和预算。
### Remote upload unknown
- 先按 remote ID、hash、size、expiry 查询。
- 已存在则补写本地 ProviderArtifactBinding；已失败才重传。
- 无法确认则 quarantine remote object 和本地 artifact view，停止复用。
- deletion unknown 不能标记 deleted；保留 limitation、owner 和 privacy/legal review。
### Billing/usage unknown
- provider usage 缺失时 provisional settlement，保留 observed token/bytes/latency。
- 账单未到达不等于零成本；report 标记 pending reconciliation。
- 不用 current PriceCatalog 覆盖历史价格。
- 对账差异使用 adjustment、variance 和 evidence，不删除历史 ledger。
### Control plane unavailable
- 已冻结的低风险 read-only run 可以到安全边界结束。
- 新的 confidential/secret/regulated egress、高风险 tool、provider upload、fallback、rotation 和删除默认暂停。
- 已发出的动作进入 unknown/recovery，不依赖内存状态猜测。
- 恢复后先重建 Incident、Route、Credential、Egress、Audit 和 queue projection，再开放新流量。
## 安全、隐私与多租户
### 数据最小化
incident 默认只保存：
- provider/api family/model/deployment/region class、错误分类、request/response hash、数量、时间、版本。
- request/response/stream/raw payload 使用受控 ArtifactRef、短 TTL、敏感度和 access scope。
- 完整 prompt、tool args、文件、secret、regulated 内容只有在明确 forensics purpose、hold、双人审批下收集。
- provider case 使用脱敏 request IDs、错误摘要和统计，不发送不必要用户内容。
### Tenant isolation
- Incident scope 可包含多个 tenant，但查询和导出必须按 tenant scope 和 purpose 重新授权。
- operator dashboard 使用 tenant class、hash、聚合和最小样本保护。
- 一个租户的 incident 不得暴露其他租户是否受影响，除非 communications/legal 已批准。
- route/circuit/credential quarantine 以 shared credential/route surface 为单位，不能错误污染无关租户。
- forensics bundle、regression fixture、provider case 和 postmortem 都有 retention、ACL 和 deletion path。
### Privacy incident coupling
以下必须同时进入 Privacy/Security Incident：
- 错误 region、错误 provider、错误 tenant、错误 remote object。
- secret/PII/regulated 数据进入 provider、trace、log、backup、support 或测试 fixture。
- provider retention/training/abuse review 事实变化。
- deletion、DSAR、remote delete、legal hold 或 egress stop 不完整。
### 供应链与 adapter
adapter、SDK、plugin、MCP、LSP、hook、schema projector 和 credential loader 的版本、digest、签名、依赖 lock、attestation 和 conformance 必须进入 scope；疑似被污染时可单独 quarantine，不得只重启 worker。
## 可观测性与审计
### Canonical Incident Events
```text
provider.signal.observed
provider.signal.correlated
provider.incident.candidate
provider.incident.declared
provider.incident.scope_changed
provider.incident.severity_changed
provider.incident.commander_assigned
provider.route.quarantined
provider.circuit.opened
provider.traffic.stopped
provider.fallback.restricted
provider.egress.stopped
provider.credential.revoked
provider.credential.rotated
provider.remote_object.quarantined
provider.evidence.collected
provider.timeline.updated
provider.case.opened
provider.status.published
provider.recovery.started
provider.canary.verified
provider.traffic.restored
provider.reconciliation.completed
provider.regression.added
provider.incident.closed
```
### Trace 层级
```text
session span
  -> run span
    -> attempt/provider span
      -> signal span
      -> correlation span
      -> containment action span
      -> credential/egress span
      -> evidence collection span
      -> recovery/reconciliation span
      -> regression/release span
```
### 必备字段
```text
incident_id
incident_status
severity
primary_taxonomy
scope_hash
blast_radius_hash
provider
api_family
model_class
 deployment_hash
region_class
route_snapshot_id
contract_snapshot_id
adapter_version
capability_version
credential_class
policy_version
egress_version
signal_kind
error_category
attempt_count
unknown_outcome_count
retry/fallback/hedge/shadow counts
containment_action_id
provider_case_id
recovery_plan_id
postmortem_id
```
不把 tenant ID、prompt、path、secret、原始 tool args 或 provider token 作为普通高基数 metric label。
### 指标
- signal ingest、correlation、candidate、declare latency。
- false positive、false negative、inconclusive 和 dedupe ratio。
- incident count by taxonomy/surface/region/adapter。
- MTTD、MTTA、MTTC、MTTR、reopen rate、containment partial rate。
- route/circuit/fallback/hedge/shadow stop 传播延迟。
- credential revoke、rotation、egress stop 和 remote object quarantine latency。
- blast radius bounded ratio、unknown resolution、reconciliation lag。
- provider case response latency、local/provider claim divergence。
- postmortem action overdue、regression gate coverage、repeat incident rate。
- SLO burn、error budget consumed、retry amplification、incident cost。
### Audit
Audit 必须回答：
- 谁在什么 incident scope 下基于什么 signal 宣布了什么 severity。
- 哪些 surface、tenant、region、route、credential、artifact 和 remote object 被隔离。
- 哪些 retry、fallback、hedge、shadow、canary 被停止或允许。
- 哪个 policy、contract、egress、credential、adapter、catalog 和 config version 生效。
- 谁执行了 break-glass、provider communication、rotation、recovery 和恢复流量。
- 哪些未知项、限制、法律/隐私判断和通知结论仍存在。
## 测试策略
### Testkit
```text
FakeProviderRuntime
FakeHealthPort
FakeRoutingPort
FakeContractRegistry
FakeCredentialBroker
FakeEgressEvaluator
FakeProviderCommunication
ScriptedProviderSignals
DeterministicClock
DeterministicIds
InMemoryEventStore
IncidentCommandRecorder
FakeCircuitBreaker
FakeQuotaPort
FakeRemoteObjectStatus
FakeBillingReceipt
ReplayRunner
CrashInjector
SideEffectRecorder
RedactionScanner
```
### 单元测试
- taxonomy、severity、confidence、blast radius 和 scope hash。
- signal dedupe、correlation window、baseline、version 和 unknown handling。
- circuit、quarantine、fallback restriction、traffic stop、egress stop、credential revoke/rotation。
- timeline ordering、causation、evidence hash、redaction 和 retention。
- recovery classification、receipt query、usage/billing reconciliation。
- incident state machine、action idempotency、break-glass expiry 和 dual control。
### Provider Contract/Conformance
每个受影响 Provider/API family 必须覆盖：
1. 文本同步成功。
2. stream 首帧前、中间、terminal 前断流。
3. 多工具交错 delta、未完成参数和 duplicate terminal。
4. strict/relaxed structured output。
5. safety/refusal/citation/grounding。
6. usage 缺失、usage drift、billing receipt variance。
7. 429、5xx、capacity、auth、region、schema、unknown event。
8. remote file upload/status/delete unknown。
9. credential rotation/revoke race。
10. route quarantine、fallback block、circuit recovery。
11. adapter version drift 与 rollback。
12. provider response 伪造 tenant、region、approval、policy、artifact owner。
### 场景测试
- 单 provider outage，不影响无关 provider/tenant。
- 单 region outage，只在同 jurisdiction candidate 中 fallback。
- capability drift 关闭 affected capability，不关闭全 provider。
- data exposure 触发 egress stop、credential revoke、forensics 和 privacy/legal review。
- schema drift 触发 adapter quarantine、fixture replay 和发布阻断。
- billing drift 保留 provisional cost，不错误放宽 hard cap。
- provider support claim 与本地 evidence 冲突时保持 restricted。
- incident 期间 host 断线，background recovery 仍有 scope、lease 和 audit。
### 故障注入
在以下边界注入 crash/timeout/duplicate/gap：
- signal ingest/correlation/declare。
- incident action planned/issued/applied/receipt。
- circuit open、route quarantine、traffic stop。
- credential revoke、rotation、cache invalidation。
- provider send/first event/terminal/usage。
- remote upload/status/delete。
- evidence collection、timeline append、audit append。
- recovery canary、traffic restore、reconciliation。
断言：不 fail-open、不跨 tenant、不重复敏感外发、不把 unknown 当 success、不丢 timeline/evidence、不让 quarantine route 被选中。
### Evaluation
Evaluation 必须同时断言：
- provider request count、attempt、retry、fallback、hedge、shadow。
- route/circuit/quarantine/fallback state。
- Context/Egress/Contract/Credential snapshots。
- event sequence、terminal、ToolCall/Result、usage/cost。
- side-effect count、remote object、deletion/rotation receipt。
- incident state、severity、blast radius、timeline 和 recovery。
- postmortem regression fixture 可阻断相同根因。
LLM judge 只能评价状态更新、解释和用户可读性，不能判断外发是否发生、凭据是否撤销、路由是否停止或副作用是否成功。
## 反模式
1. **把 500 加到 Slack 就算事故响应**：没有边界、关联、scope、containment、证据和恢复。
2. **所有 4xx/5xx 都 page**：把普通 invalid request、用户配置和真正 outage 混为一谈。
3. **只看 HTTP status**：遗漏 200 data exposure、schema drift、错误 region 和 billing 事故。
4. **一个全局 circuit**：单模型、单 region 或单租户故障熔断所有 provider。
5. **adapter 偷偷 fallback**：丢失 Attempt、RouteSnapshot、Contract、Usage 和审计。
6. **故障时关闭 DLP、audit、approval 或 sandbox**：把可用性恢复变成安全事故。
7. **用 provider status page 当恢复证明**：没有本地 conformance、canary、egress 和 reconciliation。
8. **把 provider safety 当本地 Policy**：绕过 Tool、Approval、Sandbox 和 Egress。
9. **只停止主流量**：shadow、hedge、canary、remote upload、background worker 继续外发。
10. **credential rotation 只改配置**：旧 lease、cache、worker 和 retry 仍在使用旧凭据。
11. **断线后盲目重传**：忽略 provider 已接受、remote object 或未知副作用。
12. **incident channel 复制完整 prompt/secret**：扩大传播范围并污染证据。
13. **用 dashboard 生成 timeline**：采样、延迟和投影不具备事实完整性。
14. **severity 只看错误率**：忽略 data sensitivity、blast radius、未知范围和法律影响。
15. **关闭 incident 就删除证据**：破坏 postmortem、DSAR、legal hold 和回归。
16. **修复只改 golden**：掩盖 schema、adapter、usage 或 event drift。
17. **把 unknown 当失败**：恢复时重复发送或错误计费。
18. **把 unknown 当成功**：向用户承诺已完成，造成重复副作用。
19. **忽略 billing/cost**：事故 retry、fallback、shadow 和 provider minimum charge 未计量。
20. **break-glass 无 TTL/双人/命令白名单**：事故期间扩大权限且无法审计。
21. **跨 tenant 做原始关联**：泄露租户存在性、路径、request 或错误内容。
22. **只做单元测试**：没有真实 Harness、State、Artifact、Policy、Provider 和恢复边界。
23. **postmortem 没有 owner/expiry**：行动项长期悬空，事故重复发生。
24. **恢复全量放流**：没有 canary、hard gate、分桶和自动 rollback。
25. **把普通 API error 改名 incident**：告警疲劳导致真正 provider incident 被忽略。
## 实施清单
### P0：事实与边界
- [ ] 定义 ProviderSurface、IncidentScope、BlastRadius、ProviderSignal、ProviderIncident。
- [ ] 区分普通 API error、业务 error、tool error、user cancel、platform incident 和 provider incident。
- [ ] 建立 taxonomy：outage、degraded、capability drift、data exposure、safety、regional、credential、billing、schema、adapter。
- [ ] 建立 signal schema、dedupe、correlation、baseline、confidence 和 unknown 处理。
- [ ] 建立 IncidentEvent、Timeline、EvidenceBundle、IncidentAction 和状态机。
### P1：Containment 与安全
- [ ] 按 provider/api family/model/deployment/region/route/tenant/credential 拆分 circuit 和 quarantine。
- [ ] 实现 traffic stop、route quarantine、fallback restriction、hedge/shadow/canary stop。
- [ ] 实现 credential lease revoke、rotation epoch、cache invalidation 和 worker 通知。
- [ ] 实现 provider egress stop、remote object quarantine、artifact quarantine 和 background job pause。
- [ ] 对 secret、regulated、错误 region、cross-tenant 和未知外发 fail-closed。
- [ ] 建立 break-glass 双人审批、TTL、命令白名单、自动 revoke 和 audit。
### P2：调查与恢复
- [ ] 建立 EvidenceBundle、ForensicBundle、timeline、hash、redaction、retention/incident hold。
- [ ] 建立 provider case、脱敏沟通、status query、provider claim 与本地 evidence 对比。
- [ ] 建立 unknown outcome、remote upload/status/delete、usage/billing reconciliation。
- [ ] 建立 low-risk probe、conformance、security/privacy、canary、traffic restore 和 rollback。
- [ ] 将 provider、route、credential、artifact、event、audit、billing 和 tenant scope 对账。
### P3：回归、SLO 与运营
- [ ] 建立 incident regression fixture、contract/conformance gate 和 schema drift gate。
- [ ] 连接 Provider SLI、SLO、error budget、alert、runbook、on-call 和 postmortem。
- [ ] 建立 MTTD/MTTC/MTTR、blast radius、unknown resolution、repeat incident 指标。
- [ ] 建立 tenant/operator/audit/status 三种脱敏视图。
- [ ] 建立定期 tabletop：provider outage、credential leak、wrong region、capability drift、billing drift。
- [ ] 所有 postmortem action 有 owner、due date、expiry、rollback 和验证 evidence。
### P4：治理与发布
- [ ] Provider/adapter/schema/projection/credential/config 变更必须引用 incident regression 和 conformance evidence。
- [ ] quarantine/revoke/restore 状态传播到 Catalog、Routing、Runtime、Harness、Worker 和 Dashboard。
- [ ] 恢复前后验证 privacy/legal、DSAR、retention、deletion、remote object 和 backup 影响。
- [ ] 对生产反馈进行脱敏、最小化、去重和 provenance 管理。
- [ ] 禁止以 Slack、最终文本、单个 200 或 dashboard 代替 durable incident fact。
## 五个参考项目的启发来源
### Pi
- headless agent loop、统一 Provider Event、session tree、checkpoint、compaction 和多 Host runtime 启发 incident facts 必须位于 Kernel 外、跨 CLI/TUI/RPC 共享，并能从 durable state 恢复。
- stream 事件、tool call/result 和 attempt 分层启发 provider incident 不能只按最终文本或 HTTP status 判断。
- session tree 和 branch 方向启发事故回放、timeline、恢复和 regression 应保留原始事实而创建新分支/新 Attempt。
### Grok Build
- actor、sampler、transport、permission、folder trust、sandbox、路径锁和独立 trace 启发 incident response 需要状态所有权、资源锁、权限与执行隔离分层。
- 并行工具和输出预算启发 blast radius、retry amplification、side-effect count 和 provider/tool 资源消耗应分别归因。
- fail-open 风险提醒 sandbox、credential、route 和 containment 失败必须有明确 quarantine/deny，而不是静默降级。
### OpenCode
- client/server、session/message/part、event bus、durable event/projector、snapshot/patch/revert 启发 timeline、evidence、multi-client status、replay 和恢复必须以 canonical event 为基础。
- permission、tool、provider 与 MCP/LSP 分离启发 incident action 不能由 Host/UI 或 provider response 私自执行。
- snapshot/patch/revert 方向启发配置、adapter、route 和 workspace 变更应可审计、可回滚但不删除历史事实。
### Claude Code
- permission modes、hooks、skills、subagents、memory、计划与任务工作流启发 incident response 必须覆盖 prompt/context/tool/state/approval/后台任务，而不只是 provider HTTP 层。
- human-in-the-loop、task progress 和用户交付启发 status update、approval、pause、resume 和 recovery 应独立于模型文本。
- 其辅助源码不是权威规范，故本设计坚持以本地 canonical contract、event、receipt、policy 和 evidence 为准。
### OpenClaw
- AgentHarness registry、agent-core、Gateway/channel、provider runtime、tool/sandbox/elevated 和后台任务启发 incident control 应作为 Harness 控制面跨 provider、host、channel 和 worker 传播。
- 多渠道和长生命周期运行启发 incident status、后台 job、credential lease、delivery 和 recovery 必须有 scope 与 cursor。
- 事务化插件注册启发 adapter/extension/route change 要有 candidate snapshot、冲突检查、提交和失败回滚。
## Definition of Done
- [ ] 能区分普通 API error、业务 error、tool error、用户取消、平台故障和 provider incident。
- [ ] taxonomy 覆盖 outage、degraded、capability drift、data exposure、safety、regional、credential、billing、schema、adapter。
- [ ] signal correlation 不依赖单一 500/Slack，且能计算 severity、blast radius、confidence 和 unknown。
- [ ] incident 可按 provider、api family、model、deployment、region、route、tenant、credential 和 adapter 隔离。
- [ ] traffic stop、quarantine、fallback restriction、credential revoke/rotation、egress stop 可在真实 send boundary 强制。
- [ ] evidence、timeline、audit、provider case、forensics、privacy/legal review 和 break-glass 可审计。
- [ ] recovery 具有 conformance、security/privacy、canary、reconciliation、usage/billing 和 remote object 验证。
- [ ] postmortem 会产生 regression fixture、contract/conformance gate、SLO/runbook/action owner。
- [ ] unknown outcome 不被伪装为失败或成功；不盲目重放可能成功的副作用请求。
- [ ] 事故系统与 Model/Prompt/Context/Tool/State/Policy/Harness、Artifact、Multi-tenant、Session Replay、Cost Governance 集成。
- [ ] 测试覆盖正常、边界、fault injection、跨租户、错误 region、secret、schema drift、provider outage、billing 和恢复。
- [ ] Provider Incident Response 的完成标准不是“告警已发出”，而是“影响已界定、传播已阻断、事实可证明、恢复已验证、回归已门禁”。
