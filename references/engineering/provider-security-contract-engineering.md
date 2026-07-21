# Provider Security Contract Engineering 细粒度工程设计

> 本文把 Provider Security Contract 定义为 Provider Runtime、Provider Routing、Privacy、Security Operations、Policy/Sandbox 与 Harness 之间的 provider-neutral 安全契约。
>
> 依据仅来自本地参考架构、Agent Harness、Prompt、Context、Tool、State/Memory、Permission/Sandbox、Subagent、Event/Observability、Evaluation、Provider Runtime、Provider Routing、Provider Runtime Conformance、Artifact、Multi-tenant、Host Adapter、Workspace Isolation、Production Operations、Security Operations、Privacy 与 Cost Governance 文档；不依赖 README，不新增网络搜索结论。
>
> **边界声明：** Provider Security Contract 不是 provider marketing checklist。它不是把“企业级、安全、隐私友好、合规”逐项打勾，而是把一次 Attempt 的身份、能力、数据、驻留、保留、训练、滥用、安全事件、工具、文件、外发、恢复和撤销约束编译成可验证、可拒绝、可审计的运行时事实。

## 目录

1. [目标与非目标](#目标与非目标)
2. [核心判断与职责边界](#核心判断与职责边界)
3. [术语与安全不变量](#术语与安全不变量)
4. [总体架构与包布局](#总体架构与包布局)
5. [Contract 组成与决策轴](#contract-组成与决策轴)
6. [核心数据模型与 TypeScript 接口](#核心数据模型与-typescript-接口)
7. [Capability 与 Trust Declaration](#capability-与-trust-declaration)
8. [Credential Scope 与身份绑定](#credential-scope-与身份绑定)
9. [Tenant、Region 与 Data Residency](#tenantregion-与-data-residency)
10. [Training、Retention 与 Abuse Policy](#trainingretention-与-abuse-policy)
11. [Content Safety、Refusal 与 Grounding Metadata](#content-safetyrefusal-与-grounding-metadata)
12. [Tool/Function Permission Contract](#toolfunction-permission-contract)
13. [File、Media 与 Remote Object Handling](#filemedia-与-remote-object-handling)
14. [Egress、Redaction 与 Data Minimization](#egressredaction-与-data-minimization)
15. [Provider Adapter Attestation](#provider-adapter-attestation)
16. [Contract Negotiation 与冲突解决](#contract-negotiation-与冲突解决)
17. [Versioning、Compatibility 与 Drift](#versioningcompatibility-与-drift)
18. [Fallback Safety 与 Route Interaction](#fallback-safety-与-route-interaction)
19. [生命周期与状态机](#生命周期与状态机)
20. [端到端决策流程](#端到端决策流程)
21. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
22. [故障恢复与安全降级](#故障恢复与安全降级)
23. [安全、隐私与多租户边界](#安全隐私与多租户边界)
24. [Audit、Conformance 与发布门禁](#auditconformance-与发布门禁)
25. [Incident、Revocation 与 Rotation](#incidentrevocation-与-rotation)
26. [可观测性与运营](#可观测性与运营)
27. [测试策略与 Evaluation](#测试策略与-evaluation)
28. [反模式](#反模式)
29. [实施清单](#实施清单)
30. [五个参考项目的启发来源](#五个参考项目的启发来源)

## 目标与非目标

### 目标

Provider Security Contract 必须能够：

- 描述 provider、api family、model、deployment、region、credential 与 adapter 的安全事实。
- 区分 provider 声明、平台配置、adapter 验证、conformance 证据和本次运行观测。
- 将 tenant、user、workspace、project、session、run、turn、attempt 绑定到 provider egress。
- 明确可以发送哪些数据 view、发送到哪个 jurisdiction、保存多久、是否训练或复用。
- 表达 content safety、refusal、grounding、citation、moderation、abuse response 和安全事件元数据。
- 表达 tool/function、文件、图片、音频、视频、文档和 provider-side object 的边界。
- 在能力、信任、凭据、驻留、保留、训练、DLP 或 attestation 不满足时安全拒绝或降级。
- 让 Routing、Runtime、Privacy、Policy、Artifact、State、Audit 和 Incident 使用同一份冻结快照。
- 通过 fixture、golden、录制回放、fault injection、conformance 和 scoped smoke 验证契约。
- 支持版本、兼容窗口、撤销、credential rotation、adapter quarantine 和安全事件传播。

### 非目标

本文不负责：

- 选择 primary provider；选择属于 Provider Routing。
- 解析具体 SDK、HTTP、SSE、云签名或原始 stream；这些属于 Provider Runtime。
- 代替 Policy/Sandbox 决定本地文件、网络、进程、secret 和工具真实边界。
- 代替法务解释法律条文、认证等级或合同义务。
- 通过一张供应商问卷证明调用安全。
- 把 marketing claim、trust center 标签、合规 logo 或白皮书当作运行时 allow 条件。
- 要求不同 provider 产生相同文本、token、拒答措辞或安全评分。
- 允许 adapter 自行改变 tenant、region、credential、retention、training 或 fallback。
- 把日志、trace 或 UI 文案当作安全审计事实。

### 质量公式

```text
Effective Provider Security
  = Contract Completeness
  × Declaration Trust
  × Egress Enforcement
  × Credential Scope
  × Adapter Attestation
  × Conformance Evidence
  × Revocation Readiness
```

## 核心判断与职责边界

### 核心判断

```text
Provider Security Contract describes what may happen.
Policy decides whether this run may use it.
Provider Runtime performs protocol translation.
Sandbox enforces local effects.
Harness freezes, supervises and recovers the decision.
Audit proves the decision without copying all payloads.
```

- capability 与 trust 是两个轴；支持工具不等于可信执行工具。
- provider 说“不训练”是待验证声明，不是跳过 egress、retention 和 DLP 的许可。
- provider safety response 是调用结果的一部分，本地 Policy 仍负责授权。
- adapter attestation 证明 adapter、配置、版本和环境绑定，不证明 provider 永远可靠。
- conformance 证明指定版本和 fixture 的语义，不证明未来 endpoint 不漂移。
- fallback、hedge、shadow、canary 和 retry 都是新的 Attempt，必须重新评估。

### 职责边界

| 组件 | 负责 | 不负责 |
|---|---|---|
| `ContractRegistry` | 合约注册、版本、状态、撤销 | 发送模型请求 |
| `DeclarationResolver` | 收集 capability、trust、data、safety 声明 | 盲信 marketing |
| `ContractEvaluator` | 比较需求、声明、证据、政策 | 执行工具 |
| `ProviderRuntime` | 协议映射、stream、usage、错误 | tenant 授权、业务审批 |
| `ProviderAdapter` | API family 适配和 raw metadata | 改写安全策略 |
| `ProviderRouting` | 候选、能力匹配、排序、fallback | 扩大 allowlist |
| `Privacy/Egress` | 分类、purpose、redaction、驻留 | 选择模型措辞 |
| `Policy/Sandbox` | visibility、call、approval、execution、egress 强制 | 解释合同全文 |
| `CredentialBroker` | scope、lease、轮换、撤销 | 将 secret 给模型 |
| `ArtifactStore` | 文件、视图、扫描、TTL、删除 | 放宽 provider egress |
| `State/EventStore` | durable facts、snapshot、replay、审计引用 | 默认保存所有 raw payload |
| `Harness` | 装配、冻结、监督、预算、取消、恢复 | 成为 provider policy 数据库 |
| `SecurityOperations` | incident、containment、revocation、rotation | 无审计手工改事实 |
| `Evaluation` | contract assertions、负向测试、回归、门禁 | 使用生产 secret |

### 强制关系

```text
Provider declaration -> evidence/attestation -> contract evaluation
-> policy/egress decision -> route/contract snapshot -> provider attempt
-> normalized events/receipt -> state/audit/evaluation
```

## 术语与安全不变量

### 术语

- `ProviderSecurityContract`：安全约束、声明、证据、版本和撤销状态的集合。
- `CapabilityDeclaration`：输入、输出、stream、tool、structured output、reasoning、citation、grounding、safety 和文件能力。
- `TrustDeclaration`：来源、签发者、验证级别、适用范围、有效期和限制。
- `CredentialScope`：credential 代表的 tenant、principal、operation、region、data class 和 expiry。
- `EgressProfile`：允许的字段、view、provider、region、retention 和 transformation。
- `SafetyMetadata`：拒答、安全类别、moderation、grounding、citation 和 provider policy signal。
- `AdapterAttestation`：adapter 构建、配置、contract、conformance 和 runtime 环境证明。
- `ContractSnapshot`：一次 run/attempt 使用的不可变安全快照。
- `ContractConflict`：tenant、workspace、provider、adapter、routing 或 artifact 约束冲突。
- `ContractReceipt`：请求、响应、远程对象、删除、撤销或 rotation 的核验回执。

### 安全不变量

1. tenant、workspace、session、run 由受信控制面产生，模型和 provider response 不能覆盖。
2. 每个 Attempt 必须引用一个 ContractSnapshot。
3. data class、purpose、region、provider、model、credential 或 retention 改变时必须重新评估。
4. `allow` 必须同时满足能力、信任、egress、credential、策略和证据有效期。
5. `ask` 只能请求具体动作授权，不能替代 provider 合同证据。
6. `unknown` 不等于 `allow`；secret、regulated、生产写和跨境外发默认 fail-closed。
7. provider safety filter 不能取消本地 DLP、scope、approval 和 sandbox。
8. fallback/retry/hedge/shadow/canary 都生成新 Attempt 和新计量事实。
9. 合约、声明、策略、attestation 和证据必须有版本、hash 和时间。
10. contract revoke 后新 Attempt 必须阻断；运行中的高风险动作只能到授权边界。
11. audit 保存决策和证据引用，不默认复制 secret、完整 prompt 和全部 provider payload。
12. provider-side remote object 是独立 inventory 对象，不能因本地删除就声称远端删除。

## 总体架构与包布局

### 逻辑拓扑

```text
Host/API -> Auth/TenantContext -> Harness Bootstrap
-> ContractRegistry/DeclarationResolver -> Privacy/Egress/Policy
-> Provider Routing -> ContractEvaluator -> Route/Contract Snapshot
-> Provider Runtime/Adapter -> Provider API/Remote Object
-> Canonical Events/Usage/Safety -> State/Event/Artifact/Audit
-> Security Operations/Evaluation/Host Delivery
```

### 控制面

保存 provider、api family、model、deployment 的合同版本、capability、trust、credential、region、retention、training、abuse、safety、conformance、attestation、revocation、rotation、fallback 和 evidence。

### 数据面

只使用冻结的 `ContextPlan`、`ToolsetSnapshot`、`EgressSnapshot`、`RouteSnapshot`、`ContractSnapshot`、`CredentialLeaseRef` 和 `AdapterAttestationRef`。

数据面不得在发送中隐式查询全局可变 policy 改写 payload；安全事件需要立即停止时，产生 revoke/change 事件并阻断后续动作。

### 推荐包布局

```text
packages/provider-security/
  contracts.ts registry.ts declarations.ts trust.ts capabilities.ts
  credentials.ts residency.ts retention.ts abuse.ts safety.ts tools.ts
  files.ts egress.ts attestation.ts negotiation.ts conflicts.ts
  fallback.ts snapshots.ts revocation.ts rotation.ts audit.ts
  conformance/ testkit/
```

依赖方向保持：

```text
Harness -> ProviderSecurity ports
Routing -> ContractEvaluator -> Catalog/Policy/Egress/Health
ProviderRuntime -> ContractSnapshot + ResolvedModel
Adapter -> Attestation port
State/Event/Audit -> canonical contracts
```

## Contract 组成与决策轴

### 四层身份

1. `ProviderProductContract`：provider 产品边界和服务对象。
2. `ApiFamilyContract`：协议族认证、请求、stream、文件和错误语义。
3. `DeploymentContract`：具体 endpoint、region、project/account、profile 和模型部署。
4. `RunUsageContract`：当前 tenant、purpose、data class、toolset、retention、预算和安全快照。

高层声明不能被低层“解释掉”；低层只能收紧或具体化。

### 每个决策轴

每个轴至少有 `requirement`、`declaration`、`evidence`、`freshness`、`decision`、`obligations` 和 `reasonCodes`。

### allow 的最小闭包

```text
identity verified + tenant scope matched + credential matched
+ capability satisfied + residency satisfied + purpose accepted
+ training/retention/abuse compatible + egress transformed
+ adapter attestation valid + conformance fresh + fallback safe
```

## 核心数据模型与 TypeScript 接口

```typescript
type ProviderSecurityContractId = string;
type ContractSnapshotId = string;
type DeclarationId = string;
type EvidenceId = string;
type AttestationId = string;
type CredentialLeaseId = string;
type ContractVersion = `${number}.${number}`;
type ContractStatus = "draft" | "proposed" | "verified" | "active"
  | "degraded" | "suspended" | "revoked" | "expired";
```

```typescript
interface ProviderSecurityContract {
  id: ProviderSecurityContractId;
  version: ContractVersion;
  status: ContractStatus;
  provider: ProviderRef;
  apiFamily: ApiFamilyRef;
  model?: ModelRef;
  deployment?: DeploymentRef;
  scope: ContractScope;
  capability: CapabilityDeclaration;
  trust: TrustDeclaration;
  credential: CredentialContract;
  residency: ResidencyContract;
  dataHandling: DataHandlingContract;
  safety: SafetyContract;
  tools: ToolSecurityContract;
  files: FileMediaSecurityContract;
  egress: ProviderEgressContract;
  attestation: AdapterAttestationPolicy;
  fallback: FallbackSecurityContract;
  evidence: ContractEvidence[];
  effectiveAt: string;
  expiresAt?: string;
  supersedes?: ProviderSecurityContractId;
  hash: string;
}
```

```typescript
interface ContractScope {
  providerId: string;
  apiFamilyId: string;
  modelId?: string;
  deploymentId?: string;
  regions: string[];
  jurisdictions?: string[];
  tenantClasses?: string[];
  dataClasses?: Sensitivity[];
  purposes?: ProcessingPurpose[];
}
interface DeclarationSource {
  kind: "provider_config" | "adapter_manifest" | "control_plane"
    | "conformance_fixture" | "recorded_observation"
    | "operator_attestation" | "incident_override";
  issuer: string;
  reference: string;
  capturedAt: string;
  expiresAt?: string;
  contentHash?: string;
  signatureRef?: string;
}
interface TrustDeclaration {
  level: "untrusted" | "observed" | "configured" | "attested" | "verified";
  source: DeclarationSource;
  issuerTrust: string;
  verificationMethod: string;
  limitations: string[];
}
```

```typescript
interface CapabilityDeclaration {
  inputModalities: ModalityCapability[];
  outputModalities: ModalityCapability[];
  streaming: StreamingCapability;
  tools: ToolCapability;
  structuredOutput: StructuredOutputCapability;
  reasoning?: ReasoningCapability;
  citations?: CitationCapability;
  grounding?: GroundingCapability;
  safetySignals: SafetySignalCapability;
  contextLimits: ContextLimitCapability;
  providerMetadata: MetadataCapability;
  unsupported: CapabilityLimitation[];
}
interface DataHandlingContract {
  allowedSensitivity: Sensitivity[];
  allowedPurposes: ProcessingPurpose[];
  minimization: MinimizationRequirement;
  training: TrainingPolicy;
  retention: RetentionPolicyDeclaration;
  abuseMonitoring: AbuseMonitoringPolicy;
  humanReview: HumanReviewPolicy;
  providerReuse: ProviderReusePolicy;
  deletion: RemoteDeletionPolicy;
}
```

```typescript
interface ContractSnapshot {
  id: ContractSnapshotId;
  tenantContextHash: string;
  scope: ScopeRef;
  provider: ProviderRef;
  apiFamily: ApiFamilyRef;
  resolvedModel: ResolvedModel;
  contractId: ProviderSecurityContractId;
  contractVersion: ContractVersion;
  policyVersion: string;
  egressSnapshotId: string;
  credentialLeaseId: CredentialLeaseId;
  adapterAttestationId: AttestationId;
  capabilityHash: string;
  declarationHash: string;
  evidenceRefs: EvidenceRef[];
  obligations: SecurityObligation[];
  createdAt: string;
  expiresAt: string;
  revokedAt?: string;
  hash: string;
}
```

```typescript
interface ContractRegistry {
  register(contract: ProviderSecurityContract): Promise<RegistrationReceipt>;
  get(ref: ContractRef): Promise<ProviderSecurityContract | undefined>;
  resolve(input: ContractResolutionInput): Promise<ContractResolution>;
  suspend(id: ProviderSecurityContractId, reason: string): Promise<void>;
  revoke(id: ProviderSecurityContractId, reason: string): Promise<RevocationRecord>;
}
interface ContractEvaluator {
  evaluate(input: ContractEvaluationInput): Promise<ContractEvaluationResult>;
  explain(snapshotId: ContractSnapshotId, audience: ExplanationAudience): Promise<ContractExplanation>;
  revalidate(snapshotId: ContractSnapshotId, reason: RevalidationReason): Promise<ContractEvaluationResult>;
}
```

```typescript
interface ContractEvaluationInput {
  resolution: ContractResolution;
  contextPlan: ContextPlan;
  toolset: ToolsetSnapshot;
  artifacts: ArtifactRef[];
  policy: PolicySnapshot;
  egress: EgressSnapshot;
  approval?: ApprovalDecision;
  now: string;
}
interface ContractEvaluationResult {
  decision: "allow" | "ask" | "deny" | "degrade" | "unknown";
  snapshot?: ContractSnapshot;
  obligations: SecurityObligation[];
  conflicts: ContractConflict[];
  missingEvidence: EvidenceRequirement[];
  reasonCodes: string[];
  diagnostics: Diagnostic[];
  auditRefs: AuditRef[];
}
```

```typescript
interface CredentialContract {
  credentialClass: string;
  allowedPrincipals: PrincipalRef[];
  allowedTenants: string[];
  allowedOperations: CredentialOperation[];
  allowedRegions: string[];
  allowedDataClasses: Sensitivity[];
  maxLeaseMs: number;
  rotationEpoch: string;
  revocationVersion: string;
  brokerRequired: boolean;
  directSecretExposure: "forbidden" | "sandbox_only" | "allowed";
}
interface SecurityObligation {
  id: string;
  kind: "redact" | "summarize" | "artifact_only" | "no_training"
    | "short_ttl" | "no_remote_file" | "no_tool_calls"
    | "approval_required" | "sandbox_profile" | "audit_required"
    | "no_retry" | "revalidate_before_send";
  parameters?: Record<string, unknown>;
  source: string;
  enforceAt: "compile" | "send" | "receive" | "execute" | "settle";
}
```

```typescript
interface ProviderAdapter {
  manifest(): AdapterManifest;
  attest(input: AttestationInput): Promise<AdapterAttestation>;
  compile(request: ProviderNeutralRequest, snapshot: ContractSnapshot): Promise<RawRequest>;
  stream(raw: RawRequest, signal: AbortSignal): AsyncIterable<ProviderEvent>;
  normalize(event: ProviderEvent, snapshot: ContractSnapshot): CanonicalModelEvent[];
  classifyError(error: unknown): ProviderErrorClassification;
  remoteObjects(): RemoteObjectPort | undefined;
}
interface RemoteObjectPort {
  upload(input: RemoteUploadInput): Promise<RemoteObjectReceipt>;
  inspect(ref: RemoteObjectRef): Promise<RemoteObjectState>;
  delete(ref: RemoteObjectRef, reason: string): Promise<RemoteDeletionReceipt>;
  revoke(ref: RemoteObjectRef, reason: string): Promise<void>;
}
```

## Capability 与 Trust Declaration

### capability 不是布尔值

至少表达：

- 单次或并行 tool call、call ID、参数增量和完整边界。
- tool schema 支持的 JSON Schema 子集和安全降级限制。
- structured output 是 strict、部分 strict、提示式还是不支持。
- 文件是 inline、URI、provider file object、batch input 还是不支持。
- 图片、音频、视频、文档的大小、编码、扫描和派生限制。
- stream 可否取消、usage 是否最终可见、是否可能重复 terminal frame。
- safety、citation、grounding、reasoning、trace 和 provider metadata 的可验证程度。
- context overflow、rate limit、abuse block、region block 和 policy error 分类。

### 声明可信度

```text
runtime observation > conformance evidence > signed adapter manifest
> control-plane configuration > provider declaration > marketing claim
```

最后一项不能单独产生 `allow`。

### capability 与 trust 的典型分离

- provider capability 很强，但 tenant credential scope 不满足。
- adapter 经过验证，但 deployment retention 或 region 未知。
- provider 声称支持 grounding，但 response 没有可验证来源。
- provider 支持文件上传，但 remote delete 不可核验。
- safety event 可解析，但人工 abuse review 不被 tenant 允许。

### 失效条件

provider、api family、model、deployment、region、endpoint、adapter、SDK、schema projector、normalizer、credential epoch、policy、purpose、consent、data class、workspace trust、egress、incident 或 conformance freshness 改变时，声明必须失效或降级。

### evidence 类型

- `CapabilityEvidence`：请求、响应、stream、错误和 finish 语义。
- `RetentionEvidence`：配置、provider receipt 或受控平台证明。
- `ResidencyEvidence`：deployment、region、catalog 和受控路由观察。
- `CredentialEvidence`：broker lease、scope、rotation epoch 和 audience。
- `SafetyEvidence`：拒答、moderation、grounding、citation 和 policy signal。
- `DeletionEvidence`：remote delete receipt、状态查询或 limitation。
- `AdapterEvidence`：构建 hash、依赖 lock、签名、测试和环境指纹。

## Credential Scope 与身份绑定

### 最小 scope

```text
principal + tenant + project/account + provider/api family
+ deployment/region + operation + data class + purpose + expiry
+ rotation epoch + revocation version
```

### broker 流程

```text
TenantContext -> contract credential requirements -> short-lived lease
-> bind lease to run/attempt/contract hash -> opaque adapter handle
-> no secret in Prompt/Context/Model/ToolResult -> settle or revoke
```

### allow 条件

- principal 来自受信 Host/Worker，不来自模型参数。
- tenant、workspace、run scope 与 lease 相交。
- operation、region、deployment、data class 和 purpose 被允许。
- lease 未过期，rotation epoch 和 revocation version 一致。
- adapter attestation 允许该 credential class。
- egress destination 与 lease destination 一致。
- break-glass 有独立 approval、expiry、双人审计和自动回收。

### 失败处理

- auth 失败：停止 Attempt，不回传 secret 或 provider 原文。
- scope mismatch：`deny`，对外使用稳定错误。
- lease 过期：重新 contract evaluation 和 broker，不静默重试。
- rotation：旧 lease draining/revoked，新 Attempt 使用新 epoch。
- broker 不可用：高风险/高敏感度 fail-closed；低风险只能沿已冻结边界结束。
- provider 返回 token/secret：扫描、隔离、脱敏和审计。

## Tenant、Region 与 Data Residency

### 硬约束

对 `confidential`、`secret`、`regulated` 数据，以下通常直接过滤：

- provider jurisdiction 不在 tenant allowlist。
- region/location 不满足 workspace 或组织策略。
- provider retention、remote object deletion 或 abuse review 未知。
- fallback 跨境且无独立 policy。
- adapter 无法证明实际 endpoint 与 declared region 一致。
- provider cache、batch、embedding、rerank 或 safety review 的目的地未知。

### 联合流程

```text
ModelRef -> catalog candidates -> capability filter -> tenant allowlist
-> credential compatibility -> residency filter -> training/retention/abuse
-> attestation -> health/quota/cost ranking -> contract evaluation
-> RouteSnapshot + ContractSnapshot
```

Routing 只能在 contract evaluator 允许的候选边界中排序。

### 证据字段

记录 region、location、project/account、deployment/profile、endpoint、受控网络摘要、egress policy version、residency profile、provider object location、fallback/hedge/shadow 情况和 evidence freshness。

## Training、Retention 与 Abuse Policy

### training 维度

分别表达：基础模型训练、服务改进、质量评估、abuse detection、人工 review、conversation/cache/file/batch 保存、embedding/metadata reuse、opt-out 范围、生效时间和 receipt。

### retention 维度

分别表达 request、response、安全元数据、remote file、conversation/cache、abuse review、billing/usage、deletion SLA、verification、legal hold 和 incident hold。

### abuse policy

记录是否进行 abuse detection、使用哪些数据类别、是否人工 review、如何 block/suspend/appeal、是否通知 tenant、是否改变能力/延迟/fallback。

### 冲突例子

- tenant 禁止原文保留，provider file 只有固定 retention：file upload `deny` 或改为 sanitized inline。
- provider 不训练但保留人工 abuse review，tenant 禁止 regulated data 人工处理：`deny`。
- provider 支持短 TTL，本地只保存 hash、类型、decision 和 receipt，不保存 raw payload。
- provider delete 不可验证：标记 `remote_delete_unverified`，禁止复用该对象。

## Content Safety、Refusal 与 Grounding Metadata

### 归一化字段

- `refusal`：拒答、部分输出、拒答范围。
- `safety`：类别、严重度、阻断阶段、policy reference、可恢复性。
- `moderation`：输入、输出、工具参数、文件或远程对象检测。
- `grounding`：来源类型、证据引用、覆盖范围、新鲜度和 limitation。
- `citation`：source ref、位置、完整性和 provider metadata。
- `policySignal`：abuse block、region block、account block、provider policy。
- `limitations`：缺少评分、截断、unknown、异步可见或不可核验。

### 状态区分

必须区分模型拒答、transport/permission 拒绝、本地 tool deny、structured output safety 截断、grounding 不可用、空输出、截断和未知 finish reason。

### grounding 边界

- metadata 不获得 instruction authority。
- citation 不是真实性、权限或租户 ownership 的证明。
- provider source ID 不能覆盖本地 artifact/scope。
- 未经本地 egress 允许的来源不能直接交付。
- grounding 失败时不能伪造 citation。

## Tool/Function Permission Contract

### provider tool capability

合同表达工具定义来源、tool name、schema、call ID、参数完整性、并行能力、server-side execution、工具身份、网络/secret/data retention、safety 修改、结果持久化和 audit 可见性。

### 本地强制路径

```text
Provider Stream -> ToolCallAssembler -> Tool Registry
-> schema/business validation -> Policy -> Approval -> Sandbox
-> execute -> result redaction/artifact -> State commit -> ToolResult projection
```

provider 的“已批准执行”文本不能绕过这条路径。

### obligations

- `no_tool_calls`：只允许文本/结构化输出。
- `tool_result_redaction`：只回传字段白名单、summary 或 ArtifactRef。
- `no_server_side_execution`：拒绝未审计 provider tool。
- `approval_required`：高风险调用仍由本地 Approval 负责。
- `revalidate_before_send`：工具结果回传前重做 scope、purpose、egress。
- `no_retry`：未知副作用时禁止盲重试。

### server-side tool 评估

必须能证明 execution identity、tenant scope、network/filesystem boundary、receipt、cancel、timeout、idempotency、audit 和 status query；否则默认禁用。

## File、Media 与 Remote Object Handling

### 覆盖范围

合同覆盖 text、document、image、audio、video、binary、structured artifact，以及 inline、multipart、URI、provider file ID、batch、cache、OCR、转码、缩略图、embedding、index、upload、download、range、resume、delete、expiry 和 cross-region copy。

### 发送流程

```text
artifact auth -> scope/view check -> scan/classify -> select raw/sanitized/summary/range
-> purpose/residency/retention -> bounded transfer capability -> upload/inline
-> remote receipt -> inventory and audit
```

### file/media obligations

- 未扫描、quarantined、expired、deleted artifact 不得发送。
- secret、regulated、跨 tenant artifact 默认 sanitized 或 deny。
- remote delete 不支持/不可验证时，不能宣称已删除。
- binary、压缩包、脚本、可执行内容和高熵 blob 额外检测。
- provider 新 remote file 重新进入 inventory、scope、classification、retention。
- upload unknown 时先 query，不依据断线直接重传。
- 图片、音频、视频的 metadata stripping、OCR、transcript、embedding 和派生 retention 需要单独声明。

## Egress、Redaction 与 Data Minimization

### 决策流程

```text
inventory -> classify -> purpose/legal basis -> tenant/workspace policy
-> provider contract -> region -> training/retention/abuse
-> view -> DLP/secret/PII scan -> redact/tokenize/summarize
-> byte/token budget -> capability -> send -> audit
```

### view

`full`、`redacted`、`tokenized`、`pseudonymized`、`summary`、`range`、`artifact_only` 和 `deny` 都是不同语义，不得只用一个 `redacted: boolean`。

### 重新检查

redaction、summary、schema projection、tool result、provider response 进入 State/Artifact/Trace/Host/Memory、fallback、retry、resume、replay 和 export 前都必须重新检查敏感度、scope、purpose、transform hash、contract hash 和 egress。

### DLP 失败

分类不确定、scanner timeout、redaction 失败或 token map scope 不明时，secret/regulated 默认 deny；低敏感度可退化为 summary/artifact_only。

## Provider Adapter Attestation

### 内容

包括 adapter name/version、source/build hash、依赖 lock hash、provider/api family/transport、schema projector/normalizer、endpoint/region/deployment、credential class、contract/conformance version、runtime/sandbox/network profile、key epoch、release ID、签名、有效期、撤销状态、生产/regulated/tool/file/fallback 限制。

### 不证明

attestation 不证明 provider 永远不训练、不保留、返回内容真实、工具已执行、远程对象已删除或 tenant policy/consent 已存在。

### 校验

```text
manifest -> signature/source -> build/dependency -> contract/conformance
-> endpoint/region/config -> expiry/revocation -> credential binding
-> persist attestation event
```

失败时，生产、secret、regulated、remote file 和高风险工具默认 deny；低风险 public/read-only 只能按 policy `degrade`。

## Contract Negotiation 与冲突解决

### 参与方

TenantPolicy、TaskRequirements、ContextPlan、ToolsetSnapshot、RoutingDecision、ProviderSecurityContract、CredentialContract、ExecutionPolicy 和 EgressSnapshot。

### 结果

- `exact`：全部满足。
- `degraded`：summary、redaction、no-tool、short TTL 或少模态满足。
- `ask`：具体处理或跨境目的需要确认。
- `deny`：不存在安全交集。
- `unknown`：证据不足，按敏感度和风险处理。

### 优先级

```text
security floor > tenant/org policy > privacy/residency
> workspace/project > session > run override > provider convenience
> cost/latency preference
```

deny 优先于 allow；具体规则只能收紧；transform 后回到 validation/egress/attestation；approval 不能补齐缺失 evidence；soft score 不能覆盖 hard deny。

### Conflict 数据

```typescript
interface ContractConflict {
  id: string;
  topic: string;
  higherSource: string;
  lowerSource: string;
  resolution: "higher_wins" | "merge" | "degrade" | "ask" | "deny" | "unknown";
  reason: string;
  evidenceRefs: EvidenceRef[];
}
```

## Versioning、Compatibility 与 Drift

### 版本轴

独立版本化 canonical contract schema、provider contract、adapter、capability、egress/privacy、credential、conformance fixture/golden、attestation 和 audit/event schema。

### 兼容级别

```text
major: 语义破坏或安全默认改变
minor: 新增可选 capability/metadata
patch: 修复解析、证据或诊断
revocation: 立即阻断新 Attempt
```

### drift

监控 capability probe、stream unknown event、retention/training/file API、endpoint/region、fixture/golden、usage/error/refusal、adapter hash、依赖和签名。

处理：记录 drift；标记 degraded/suspended；停止高敏感度/高风险 Attempt；启动 conformance、incident、route quarantine；新证据和发布门禁通过后恢复 active。

## Fallback Safety 与 Route Interaction

### 必须新建 Attempt

fallback 需要新 Attempt ID、ResolvedModel、RouteSnapshot、ContractSnapshot、credential lease、egress/residency/training/retention 检查、usage/cost/audit 归因和必要的 context/file projection。

### 硬约束

- 不跨未知 jurisdiction。
- 不关闭 DLP、redaction、approval、audit 或 residency。
- 不重放未知成功的写操作、文件上传或 server-side tool。
- shadow/canary 不发送完整敏感 payload，除非独立批准。
- hedge 不复制 confidential payload 到未批准 provider。
- fallback 不扩大 tool、file、media 或 context capability。

### 降级顺序

1. 同 provider/deployment 减少输出或关闭可选 metadata。
2. 同 jurisdiction 切换满足相同 contract 的 deployment。
3. 使用更低能力但更严格 egress 的 provider，并标记 degraded。
4. 转为 summary/artifact reference。
5. 安全拒答、等待人工或稍后重试。

## 生命周期与状态机

### Contract lifecycle

```text
Draft -> Proposed -> EvidenceCollecting -> ConformanceChecking
-> Attested -> Active -> Degraded -> Suspended -> Revoked -> Retired
```

- `Draft/Proposed` 不进入数据面。
- `EvidenceCollecting/ConformanceChecking` 只用于验证。
- `Attested` 已通过签名、版本和环境绑定。
- `Active` 可按 policy 生成 snapshot。
- `Degraded` 只允许指定低风险 obligations。
- `Suspended` 停止新 Attempt，保留调查。
- `Revoked` 立即阻断新使用，触发 rotation、quarantine 和 incident。
- `Retired` 不产生新 snapshot，保留历史审计和迁移信息。

### Attempt lifecycle

```text
Unresolved -> CandidateResolved -> ContractEvaluating -> SnapshotFrozen
-> CredentialLeased -> EgressCompiled -> Sending -> Receiving
-> SafetyEvaluated -> Settled -> Completed
```

失败分支：

```text
ContractEvaluating -> Denied | AwaitingApproval | Unknown
CredentialLeased -> LeaseFailed | Revoked
EgressCompiled -> RedactionFailed | ResidencyDenied
Sending -> TransportFailed | ProviderRejected | UnknownOutcome
Receiving -> SafetyBlocked | NormalizationFailed | Partial
```

### snapshot 不变量

hash 覆盖 contract、policy、egress、route、credential、attestation 和 obligations；snapshot 创建后不可被 response 修改；revalidation 只能生成新 snapshot/Attempt；过期、撤销或 scope mismatch 时执行器拒绝发送。

## 端到端决策流程

### Receive/Identity

1. Host Adapter 验证认证上下文。
2. Multi-tenant Runtime 生成 TenantContext。
3. Harness 解析 workspace/project trust 和 session scope。
4. 任务声明 purpose、data class、模态、工具和输出要求。
5. 读取 policy、egress、credential、catalog 和 contract 版本。

### Context/Data

6. Context Compiler 发现 ContextResource、ArtifactRef、Memory 和 runtime facts。
7. DataInventory 标记 source、scope、sensitivity、purpose、retention。
8. Egress 选择 full/redacted/summary/range/artifact_only/deny。
9. DLP、secret、PII、regulated 和恶意内容扫描。
10. 生成 ContextPlan 和 EgressSnapshot。

### Routing/Contract

11. Routing 生成满足任务能力的候选。
12. ContractEvaluator 过滤 credential、region、training、retention、abuse、safety、attestation。
13. 评分只能用于已通过 hard filter 的候选。
14. 生成 RouteSnapshot。
15. negotiation 产出 exact/degraded/ask/deny/unknown。

### Send/Receive

16. ContractSnapshot、CredentialLease 和 AdapterAttestation 冻结。
17. Provider Runtime 编译 message、tool schema、structured output 和 media。
18. 发送前执行 hash、region、credential、policy 和 DLP final check。
19. Stream Normalizer 产生 canonical events、SafetyUpdate、Citation、Grounding、Usage 和 terminal。
20. provider response 重新分类、校验和脱敏。
21. ToolCall 进入本地 Tool Runtime，不由 provider response 自动执行。
22. State/Event/Artifact/Audit 提交并结算 usage/cost。

### Stop/Delivery

23. 根据 refusal、safety、tool result、budget、cancel 或 final answer 停止。
24. 保存 provider metadata、contract evidence、receipt 的引用。
25. Host 仅投影获准的安全状态和交付 view。
26. conflict、drift、revocation、unknown 交付为可恢复状态，不伪造成功。

## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成

### Model Runtime

- `ModelRuntime` 接受 `ResolvedModel + ContractSnapshot`，不接受任意 provider 字符串。
- Adapter 只映射协议，不切换 tenant、region、credential 或 fallback。
- stream 保留 refusal、safety、citation、grounding、unknown event 和 raw metadata reference。
- usage/cost 按 Attempt 记录。
- error taxonomy 区分 auth、scope、region、capacity、policy、safety、overflow、transport 和 unknown。

### Prompt

- Prompt 解释 contract 的可见结论，例如本次只发送摘要、工具结果不会自动执行。
- Prompt 不承担 credential、egress、training、retention 或 tool authorization。
- PromptSection 带 source、trust、authority、sensitivity、contractSnapshotId 和 token estimate。
- provider-specific instruction 由受信 contract module 注入；检索内容没有 contract authority。
- refusal、grounding、citation 规则写入 output contract，最终状态以 canonical event 为准。

### Context

- Context Compiler 根据 EgressSnapshot 选择最小 work set。
- provider capability 限制影响 ContextPlan，不支持的模态不进入 prompt。
- cache key 包含 tenant、scope、policy、contract、capability 和 resource hash。
- compaction 不能拆散 tool call/result 对，也不能删除 contract change、policy deny、approval、remote object 和 safety event。
- memory recall 受 purpose、retention、tenant 和 egress 约束。

### Tool

- ToolsetSnapshot 使用 no-tool、schema projection、parallel 和 server-side obligations。
- provider ToolCall 仍需 registry、schema/business validation、Policy、Approval、Sandbox 和 idempotency。
- tool result 回 provider 前重做敏感度、redaction、artifact 和 contract revalidation。
- 无 execution receipt、scope、sandbox attestation 的 server-side tool 默认禁用。

### State/Memory

- State 保存 ContractSnapshotRef、Attempt、SafetyMetadata、EgressDecision、CredentialLeaseRef、RemoteObjectRef 和 revoke event。
- Transcript 不等于 provider message；保留应用事实与 provider projection 差异。
- Memory 默认不接收完整 provider response、safety payload 或 credential。
- delete/export 遍历 session、artifact、memory、event、trace、backup 和 remote object inventory。
- replay 使用原始 snapshot 只读重建，不向真实 provider 发送敏感 payload。

### Policy/Sandbox

- Policy 负责 visibility、call、approval、execution、egress 五层。
- contract allow 不取代本地工具授权。
- Sandbox 负责网络、文件、进程、secret 和 endpoint 边界。
- obligations 必须转为可执行限制，sandbox attestation 与 adapter attestation 分别记录。

### Harness

- Bootstrap 装配 contract registry、declaration、credential、policy、egress、routing 和 runtime。
- Run Supervisor 冻结 config/policy/route/contract/credential。
- Control Harness 将 expiry、revoke、budget、cancel、fallback 和 incident block 纳入终止条件。
- Event Router 输出 ContractNegotiated、Conflict、Egress、Attestation、Revoked、RemoteObject 和 Safety 事件。
- Host 只呈现脱敏 decision、warning、approval、safety 和恢复状态。

## 故障恢复与安全降级

### 故障分类

registry unavailable、evidence expired、attestation invalid、credential broker unavailable、DLP timeout、endpoint/region mismatch、remote upload unknown、provider safety/abuse block、stream normalization incomplete、revoke/config change、audit durable commit unavailable。

### fail-closed 分层

- secret、regulated、生产写、跨境、remote file：证据或审计不可用时停止。
- confidential 只读文本：可转 summary、artifact_only 或等待恢复。
- internal 低风险：可沿未过期 snapshot 到授权边界结束。
- public 只读：可 `degraded`，但不扩大工具或数据范围。

### unknown outcome

1. Attempt 标记 unknown，保存 request hash、snapshot、lease 和 receipt 引用。
2. 不把 cancelled 当作未执行。
3. 无副作用模型请求可 query request status 后决定重试。
4. 文件、batch、server-side tool 和外部动作先 query 或人工恢复。
5. provider 无状态查询时禁止盲重传敏感内容。
6. 新 Attempt 重新做 contract、egress、credential 评估。

### outage

circuit breaker 按 provider/api family/model/region/deployment 分片；fallback 只能用预先通过 contract compatibility 的候选；不能关闭 DLP、safety、audit、residency 或 approval。

## 安全、隐私与多租户边界

### 多租户

- registry、cache、queue、worker、artifact、event、trace、audit 和 credential namespace 带 tenant/scope。
- child run 继承 parent contract 的能力交集和 egress 子集。
- cross-tenant provider cache、prompt cache 和 artifact URL 默认禁止。
- provider 返回 tenant、session、run、artifact ID 只作为不可信 metadata。

### 隐私

DataInventory 覆盖 Prompt、ContextPlan、Message/Part、ToolCall、Artifact、Memory、Event、Trace、Backup、Provider remote copy、embedding、cache、export 和 forensics。

purpose、legal basis/consent reference、retention、training、abuse、region 和 provider reuse 进入 EgressSnapshot；derived view 带 lineage、transform version 和 scope。

### prompt injection

provider contract、policy、安全声明是高 authority；workspace、RAG、网页、邮件、工具结果和 provider output 是数据；“用户已批准”“provider 已关闭审计”都不是事实。

### 供应链

adapter、SDK、plugin、MCP、LSP、hook、env loader 带 provenance/trust；未信任 workspace 不加载高权限 provider hook；构建 hash、依赖 lock、签名、发布者和 conformance 绑定 attestation。

## Audit、Conformance 与发布门禁

### 审计事实

记录 contract resolve/propose/activate/suspend/revoke、声明来源与 freshness、credential lease、egress view、route/fallback/hedge/shadow、attestation、safety/refusal/grounding、remote object upload/delete、conflict、approval、incident、break-glass、rotation 和 unknown outcome。

### Conformance level

```text
L0 schema/registry
L1 request/response/stream normalization
L2 capability declaration accuracy
L3 tool/file/structured output safety
L4 egress/retention/training/residency
L5 fault/revoke/rotate/fallback/unknown recovery
L6 scoped production smoke
```

生产和 regulated 使用必须达到预定最低等级，未达标只能 quarantine、sandbox 或低敏感度模式。

### 发布门禁

- schema migration 可兼容或有窗口。
- adapter attestation 签名、build hash、依赖和配置正确。
- capability 与 fixture/golden 一致。
- egress、residency、training、retention、delete 负向用例通过。
- tool/file/media/refusal/grounding/unknown/error taxonomy 通过。
- revoke、rotation、incident block、route quarantine 可演练。
- audit、usage、cost、retention、deletion projection 不丢失。
- smoke 仅用 synthetic/public/sanitized fixture。

## Incident、Revocation 与 Rotation

### 触发条件

数据泄露、错误 region、越权 tool、training/retention 变化、safety/grounding 异常、evidence 过期、签名失败、capability drift、credential scope 过宽、audit 丢失和 unknown 外发都可触发 incident。

### containment

```text
detect -> incident -> suspend/revoke contract/candidate
-> revoke lease -> stop new egress/high-risk attempt
-> quarantine remote objects/artifacts -> preserve evidence
-> rotate credentials/keys -> assess propagation
-> delete/export where required -> recover with new snapshot
```

### revoke 语义

- contract revoke：阻止新 Attempt，保留历史事实。
- adapter revoke：阻止该 adapter 新发送/解析。
- credential revoke：停止 lease，启动替换。
- route revoke：移除候选，不改写完成 Attempt。
- remote object revoke：停止复用和交付，查询删除。

### rotation

新 key/credential epoch 不覆盖旧 audit；旧 lease draining；新 lease 验证 scope、attestation、conformance 和 smoke；失败进入 degraded/suspended，不使用全局高权限 credential。

## 可观测性与运营

### Canonical events

```text
ContractResolved DeclarationLoaded EvidenceChecked ContractNegotiationStarted
ContractNegotiated ContractConflictDetected ContractSnapshotFrozen
CredentialLeaseIssued EgressEvaluated RedactionApplied AdapterAttested
ProviderSafetyUpdated ProviderRefusal GroundingUpdated RemoteObjectCreated
RemoteDeletionAttempted ContractDriftDetected ProviderContractSuspended
ProviderContractRevoked CredentialRotated FallbackBlockedByContract
UnknownProviderOutcome
```

### 指标

allow/ask/degrade/deny/unknown；missing/expired evidence；capability mismatch；residency/training/retention conflict；lease failure/scope mismatch；rotation latency；revocation propagation；egress view distribution；DLP/redaction failure；refusal/safety/abuse/grounding；safe fallback；unknown recovery；attestation freshness；drift；remote delete success/unverified/orphan；audit latency/backlog。

### trace 与 SLO

trace 只使用 provider、api family、model class、region class、contract/policy version、decision code、sensitivity class 和 hash，不写完整 prompt、secret、原始 tool args 或 provider token。

SLO 分别度量 contract resolution、pre-send decision、safety/egress completeness、revocation propagation、audit settlement、drift detection、remote deletion verification 和高风险 fail-closed correctness。

### runbook

provider suspend/revoke、adapter attestation 失效、credential rotation、region error、remote upload unknown、safety/abuse incident、audit backlog、fallback 全部 deny、contract 恢复和逐步 canary 都必须有 runbook。

## 测试策略与 Evaluation

### 分层

- unit：merge、hash、scope、version、decision、conflict。
- component：declaration、credential、egress、attestation。
- adapter contract：request/response/stream、unknown event、usage、safety、refusal、grounding、error。
- integration：Harness、Routing、Runtime、Policy、Artifact、State、Audit。
- scenario：多租户、跨 region、fallback、tool、file、remote object、revoke、rotate、crash。
- online/shadow：只用 synthetic/public/sanitized fixture，禁用真实副作用。

### 正向用例

- 有效 contract 生成正确 snapshot。
- tool schema 投影后仍由本地 Tool Runtime 执行。
- safety/citation/grounding metadata 被保留。
- artifact summary/range/sanitized view 正确发送。
- fallback 保持 residency、training、retention policy。
- rotation 后新 Attempt 使用新 epoch。
- remote object 有状态查询和删除 receipt。

### 负向用例

- marketing claim 无 evidence。
- declaration 过期、attestation 签名错误。
- tenant 禁止 provider/region/retention/training。
- server-side tool 无 sandbox/receipt。
- schema projection 删除关键安全约束。
- provider response 伪造 tenant、approval、owner 或 policy。
- cross-tenant artifact/memory/cache/trace 串线。
- DLP secret、redaction failure、token map 泄漏。
- upload unknown、stream EOF、重复 terminal、未知 safety event。
- revoked contract 仍发送或 fallback。

### Fault injection

registry timeout、catalog stale、broker timeout、rotation race、revocation lag、DLP crash、artifact partial write、remote delete timeout、429/5xx、region mismatch、abuse block、partial safety、unknown frame、event reorder、worker crash after send/upload/before audit。

断言：不 fail-open、不泄露、不重复外发、不重复副作用；State/Event/Audit/Cost/Artifact 可恢复；Host 明确显示 denied/degraded/unknown。

### Oracle

确定性 oracle 检查 snapshot hash、scope、policy、egress、credential、attestation、event order、hard filter、provider request count、tool count、retry count、remote object、deletion、revocation、rotation 和 propagation。

LLM judge 只能评估安全解释、grounding 说明或替代方案可读性，不能判断权限、删除、驻留和副作用是否真实发生。

## 反模式

### Provider marketing checklist

症状：只勾选“有加密、合规、不训练”，没有版本、scope、region、receipt、TTL、freshness 和回归证据。

修复：声明必须绑定 evidence、适用范围、限制、决策和执行 obligation。

### 一个 `secure: true`

症状：用一个布尔值代表 capability、trust、egress、training、credential、safety 和 retention。

修复：拆成独立声明、hash、obligation 和失败路径。

### provider safety 代替本地授权

修复：provider safety 是 response metadata；Policy、Approval、Sandbox、State 和 Audit 仍由本地强制。

### adapter 偷换 policy

修复：region、tenant、credential、deployment、fallback 只能来自冻结 snapshot。

### 只看 model name

修复：contract identity 使用 Provider/ApiFamily/Model/Deployment/Region/Adapter 组合。

### 只存最终文本

修复：持久化 Attempt、contract、egress、credential、attestation、safety、usage 和 receipt 引用。

### 失败后盲目重传

修复：先 query unknown，必要时人工恢复，新 Attempt 重新评估。

### 本地删除等于远端删除

修复：remote object 独立 inventory，保留 receipt 或 unverified limitation。

### approval 补齐 contract evidence

修复：approval 只授权具体 action；证据缺失仍 deny/unknown。

### trace 存完整 payload

修复：使用 hash、类型、大小、ArtifactRef、redaction summary 和受控 forensics。

## 实施清单

### 基础契约

- [ ] 建立 ProviderSecurityContract、ContractSnapshot、CapabilityDeclaration、TrustDeclaration。
- [ ] 建立 ContractRegistry、版本、hash、状态、suspend、revoke。
- [ ] 为 Provider/ApiFamily/Model/Deployment/Region 建立稳定身份。
- [ ] 建立 CredentialContract、broker lease、rotation epoch、revocation version。
- [ ] 将 tenant、workspace、session、run、attempt 绑定 snapshot。
- [ ] 将 EgressSnapshot、PolicySnapshot、RouteSnapshot 和 attestation 接入 Attempt。

### 数据与工具

- [ ] 建立 DataInventory、Sensitivity、Purpose、Retention、lineage。
- [ ] 实现 full/redacted/tokenized/pseudonymized/summary/range/artifact_only/deny。
- [ ] 在 Prompt、Context、ToolResult、Artifact、remote upload 前加入 DLP/egress gate。
- [ ] 实现 tool schema projection、server-side tool deny、approval obligation。
- [ ] 建立 file/media MIME、扫描、remote object、TTL、delete 状态。
- [ ] 将 training、provider reuse、abuse、人审、retention 纳入 contract。

### Adapter 与 Routing

- [ ] 为每个 adapter 生成签名 manifest 和 attestation。
- [ ] 绑定 build hash、依赖、配置、endpoint、region、contract、conformance、有效期。
- [ ] contract evaluator 位于 routing hard filter 与 runtime 之间。
- [ ] fallback、hedge、shadow、canary、retry 使用独立 Attempt 和安全复评。
- [ ] 实现 conflict、degrade、ask、unknown、explainability。
- [ ] 建立 capability、schema、region、retention、training drift 检测。

### 恢复与运营

- [ ] 记录 contract、egress、credential、attestation、safety、remote object、revoke 事件。
- [ ] 实现 unknown outcome、status query、人工恢复和禁止盲重放。
- [ ] 建立 suspend/revoke、rotation、quarantine、incident runbook。
- [ ] 建立 audit、metrics、SLO、forensics、delete/export 证据。
- [ ] 对 secret、regulated、生产写和跨境外发 fail-closed。
- [ ] 建立 conformance、negative、fault injection、replay、release gate。

### 治理

- [ ] 指定 contract owner、security owner、privacy owner、runtime owner 和 on-call。
- [ ] 建立版本评审、兼容窗口、deprecation、撤销和变更审批。
- [ ] smoke 仅使用 synthetic/public/sanitized fixture。
- [ ] 定期对真实观测与声明 reconciliation。
- [ ] 将 incident postmortem 转为负向 fixture 和 policy rule。
- [ ] 新 provider/adapter 必须提交 conformance、attestation、fallback 和恢复证据。

## 五个参考项目的启发来源

### Pi（`earendil-works/pi`）

headless loop、统一 provider event、session tree、checkpoint 和 compaction 说明安全 contract 应位于 Kernel 外且可恢复；CLI/TUI/RPC 共用 runtime 说明同一 snapshot 要跨 Host 保持一致；执行隔离较弱提醒 provider contract 不能替代本地 sandbox。

### Grok Build（`xai-org/grok-build`）

actor、permission decision、并行工具、资源锁、folder trust 和 sandbox 说明 provider capability、tool permission、workspace trust、adapter attestation 和 execution attestation 必须分层；fail-open 风险提醒初始化失败要有明确 degraded/deny。

### OpenCode（`anomalyco/opencode`）

client/server、session/message/part、事件总线、durable projector、snapshot/patch/revert 和 MCP/LSP 说明 contract change、safety metadata、remote object、artifact view 和审计应走 canonical event 与不可变引用。

### Claude Code（`claude-code-best/claude-code`）

permission mode、hooks、subagents、skills、memory、MCP 和 approval 工作流说明 provider contract 必须与 Prompt、Tool、State、Subagent、Host 协作；非官方规范的限制提醒不能只凭产品宣传或单一实现推断能力。

### OpenClaw（`openclaw/openclaw`）

AgentHarness registry、agent-core、gateway、多渠道、provider runtime、tool/sandbox/elevated 分层和事务化插件注册说明 contract 是跨 channel/provider 的控制面；插件拥有进程权限的风险提醒 adapter、extension、credential 和 contract 变更需要撤销、隔离和可观察。

## 结语

完成标准不是“列出 provider 有哪些安全产品”，而是可以由 snapshot、event、receipt、oracle 和 runbook 回答：

```text
本次 Attempt 使用哪个版本化 contract？
发送了哪些最小化、脱敏后的数据？
credential、tenant、region、purpose、retention 是否匹配？
adapter/capability 是否有新鲜证据？
safety、tool、file、remote object、fallback 是否可审计？
drift、revocation、rotation、unknown 能否安全停止和恢复？
```

只有这些问题都能被工程事实回答，Provider Security Contract 才不是 provider marketing checklist。
