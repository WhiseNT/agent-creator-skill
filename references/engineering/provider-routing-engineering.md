# Provider Routing Engineering 细粒度工程设计
> 本文把 Provider Routing 设计为 Harness 中负责“选择与解释”的控制面组件。它沿用本地 `Provider Runtime Engineering`、`Multi-tenant Agent Engineering`、`Permission/Sandbox Engineering`、`Context Engineering`、`Event/Observability Engineering` 与 `Evaluation Engineering` 中的 `Provider`、`ApiFamily`、`Model`、`Deployment`、`ModelRef`、`ResolvedModel`、`ModelCapabilities`、`RoutingSnapshot`、`TenantContext`、`EgressSnapshot`、`Attempt`、`CircuitBreaker`、`UsageLedger` 和 durable/ephemeral event 术语。
>
> 依据仅来自当前目录已有参考架构和五个参考项目的本地源码调研归纳；不把 README 当作规范，不新增网络调研结论。
## 目录
1. [设计目标与非目标](#设计目标与非目标)
2. [术语与核心判断](#术语与核心判断)
3. [职责边界](#职责边界)
4. [总体架构与包布局](#总体架构与包布局)
5. [路由控制面与数据面](#路由控制面与数据面)
6. [核心数据模型](#核心数据模型)
7. [TypeScript 接口](#typescript-接口)
8. [Provider、ApiFamily、Model、Deployment 与 Catalog](#providerapifamilymodeldeployment-与-catalog)
9. [Capability Matching](#capability-matching)
10. [Tenant、Workspace 与 Policy 输入](#tenantworkspace-与-policy-输入)
11. [Region、Data Residency 与 Egress](#regiondata-residency-与-egress)
12. [候选集生成与过滤](#候选集生成与过滤)
13. [Latency、Cost、Quality 与 Fairness 路由](#latencycostquality-与-fairness-路由)
14. [Health、Readiness 与 Circuit Breaker](#healthreadiness-与-circuit-breaker)
15. [Rate Limit、Quota 与 Budget](#rate-limitquota-与-budget)
16. [Sticky Routing](#sticky-routing)
17. [Request Hedging](#request-hedging)
18. [Retry Budget 与 Attempt 语义](#retry-budget-与-attempt-语义)
19. [Fallback 与 Context Overflow](#fallback-与-context-overflow)
20. [Tool、Structured Output 与多模态兼容](#toolstructured-output-与多模态兼容)
21. [Shadow、Canary 与版本发布](#shadowcanary-与版本发布)
22. [Route Snapshot 与 Explainability](#route-snapshot-与-explainability)
23. [生命周期与状态机](#生命周期与状态机)
24. [端到端决策流程](#端到端决策流程)
25. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
26. [失败恢复与未知结果](#失败恢复与未知结果)
27. [安全、隐私与数据外发](#安全隐私与数据外发)
28. [可观测性与运营](#可观测性与运营)
29. [测试与 Evaluation 策略](#测试与-evaluation-策略)
30. [反模式](#反模式)
31. [实施清单](#实施清单)
32. [五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
Provider Routing 必须能够：
；从明确的 `ModelRef`、任务需求和 Harness 快照中解析可调用的 provider/API family/model/deployment。；在候选生成前区分基础模型能力、具体 deployment 能力、credential 能力、tenant policy、host 能力和 egress 能力。；对文本、工具调用、并行工具、structured output、reasoning、citation、grounding、安全事件及图片、音频、视频、文档等模态做显式 capability matching。；将 region、location、project/account、data residency、provider jurisdiction、retention 和 sensitivity 作为硬约束或可解释的软约束。；在健康、readiness、容量、限流、配额、延迟、成本、质量和公平之间做确定性、可审计的排序。；支持 primary、fallback、sticky、hedging、shadow 和 canary 等不同选择策略，但每个策略都必须产生 route snapshot 和 durable 变更事实。；将 transport retry、agent retry、fallback、hedged attempt、context compaction 和 tool retry 分开计量与控制。；在 context overflow、provider capability mismatch、region 不合规、credential 失效、quota 不足和 circuit open 时返回稳定错误或安全降级。；保留 provider metadata、raw request/response reference、request hash、catalog version、policy version、health evidence 和 usage/cost 归因。；通过 fake provider、recorded stream、fault injection、shadow replay、canary 监控和 side-effect oracle 进行评测。
### 非目标
Provider Routing 不负责：
；隐藏 tenant、workspace、组织或产品 policy；policy 必须由 Policy Engine 生成并由 Harness 注入。；代替 Policy/Sandbox 决定真实权限、审批、文件边界、网络边界、进程隔离或 secret 绑定。；在 provider adapter 内偷偷切换 provider、模型、deployment、region、credential 或 tenant。；选择 Prompt/Context 中的全部资源，或在 adapter 内随机删除上下文。；执行工具、验证工具业务参数、生成 approval 或修改业务状态。；把 provider safety filter 当成本地授权，把 OpenAI-compatible 当作完全相同的协议。；以单一总分抹平可靠性、成本、质量、数据驻留和安全差异。；让 shadow 流量执行真实副作用，或让 canary 绕过已有安全上限。；将 route snapshot、trace 或 metric 当作 session 的唯一 durable truth。
### 质量公式
```text
Routing Reliability = Candidate Correctness × Capability Accuracy × Policy Compliance × Egress Safety × Health Signal Quality × Retry/Fallback Safety × Explainability × Usage Attribution
```
任一乘项接近零，路由结果都可能在生产任务中失真。
## 术语与核心判断
### Provider-neutral 术语
；`Provider`：模型服务的产品或云平台边界。；`ApiFamily`：同一 provider 内的协议族，例如 Responses、Messages、Converse、Generate Content 或兼容协议。；`Model`：能力、版本、上下文和输出语义上的基础模型引用。；`Deployment`：具体可调用资源，可能是 deployment name、endpoint、profile、ARN、publisher model 或 inference profile。；`Catalog`：记录身份、能力、限制、区域、价格、版本、新鲜度和 conformance 的控制面。；`RouteCandidate`：已经通过硬约束、等待排序的可调用目标。；`RoutingDecision`：本次选择的 `ResolvedModel`、理由、约束和策略快照。；`Attempt`：某个 provider/model/deployment 下的一次模型采样尝试；fallback 和新的请求语义必须有新的 attempt。；`RouteSnapshot`：不可变的选择输入、候选摘要、过滤结果、评分、最终选择和版本引用。
### 核心判断
```text
Routing 负责选择。
Policy 负责决定是否允许选择。
Sandbox 负责限制真实执行边界。
Provider Runtime 负责按已冻结选择调用协议。
Harness 负责监督生命周期、预算、恢复和交付。
```
路由组件可以解释“为什么选择 A 而没有选择 B”，但不能把被 Policy 隐藏的 provider 重新暴露为候选。
## 职责边界
### Routing 负责
；接收经过认证、规范化和冻结的 `RoutingInput`。；解析 `ModelRef`、catalog record、deployment、region 和 credential compatibility。；计算模型需求与候选能力的匹配结果。；执行租户/工作区允许范围、数据驻留、egress、quota、health 和 circuit 输入的过滤。；计算 latency、cost、quality、fairness、stickiness 和风险调整后的排序。；选择 primary、fallback、hedge、shadow 或 canary route。；生成 `RouteSnapshot`、`RoutingDecision`、`RoutingExplanation` 和相关事件。；为 Harness 提供 retry budget、fallback compatibility 和 route recovery 建议。
### Routing 不负责
；修改 policy snapshot、扩大 provider allowlist 或覆盖 tenant context。；读取未经 Harness 认证的 tenant ID、workspace ID 或模型参数。；直接访问 session、memory、artifact 或业务数据库。；直接调用 provider SDK；具体调用由 Model Runtime/Adapter 完成。；判断工具动作是否允许或执行真实工具。；把软评分结果当作安全许可。
### 强制边界
```text
Tenant/Workspace Policy -> 允许的候选边界
Routing -> 候选解析、过滤、排序和选择
Provider Runtime -> 编译并发送已选择请求
Policy/Sandbox -> 强制数据和动作边界
Harness -> 记录、监督、恢复和交付
```
## 总体架构与包布局
```text
Host Request -> Harness TenantContext / PolicySnapshot / EgressSnapshot -> RoutingInput Normalizer -> Candidate Resolver -> Catalog + Capability Matcher -> Region / Residency / Credential Filter -> Quota / Rate Limit / Health Filter -> Latency / Cost / Quality Scorer -> Sticky / Hedging / Shadow / Canary Planner -> RoutingDecision + RouteSnapshot -> Provider Runtime ModelRequest -> Model Adapter / Transport
```
推荐包布局：
```text
packages/model-routing/ contracts.ts input-normalizer.ts candidate-resolver.ts catalog-view.ts capability-matcher.ts policy-boundary.ts residency-filter.ts quota-guard.ts health-filter.ts score.ts sticky.ts hedging.ts retry-budget.ts fallback.ts shadow-canary.ts snapshot.ts explain.ts planner.ts recovery.ts testkit/
```
依赖方向：
```text
Harness -> RoutingPort -> routing contracts
Routing -> CatalogPort / HealthPort / QuotaPort / PolicySnapshot / EgressSnapshot
Provider Runtime -> ResolvedModel + RouteSnapshot
Adapters -> protocol/transport contracts
Infrastructure -> catalog, health, quota, metrics and storage implementations
```
Routing 不应导入 TUI、HTTP client、SQLite schema 或具体 provider SDK 类型。
## 路由控制面与数据面
### 控制面
控制面保存或提供：
；provider、API family、model、deployment 的注册和版本。；catalog capability、limits、pricing、region availability 和 freshness。；tenant/workspace policy、egress、data residency、quota 和 fallback policy。；health、readiness、circuit state、capacity signal 和 quality profile。；sticky key policy、hedging policy、canary allocation、shadow rules。；route strategy、score weights、explainability schema 和配置版本。
控制面变化不应静默改变已运行的 attempt；运行中变化需要新的 route/config change entry。
### 数据面
数据面包含：
；一次请求的 `RoutingInput`、candidate IDs、过滤原因和评分。；`ResolvedModel`、credential lease reference、route snapshot 和 request hash。；provider request/stream、attempt、retry、fallback、hedge、usage 和 cost。；route decision event、health observation、quota reservation 和 delivery status。
数据面高频 stream 不应阻塞 control-plane durable snapshot；控制面 durable writer 失败时，Harness 必须阻止声称 route 已提交。
## 核心数据模型
### RoutingInput
```typescript
interface RoutingInput { requestId: string; runId: string; sessionId: string; turnId: string; attemptOrdinal: number; tenant: TenantRoutingContext; workspace?: WorkspaceRoutingContext; requestedModel?: ModelRef; apiFamilyPreference?: string[]; task: RoutingTaskRequirements; policy: RoutingPolicySnapshot; egress: EgressSnapshot; host: HostModelCapabilities; budget: RoutingBudget; history?: RoutingHistory; strategy?: RoutingStrategy;
}
```
### RoutingTaskRequirements
```typescript
interface RoutingTaskRequirements { inputModalities: InputModality[]; outputModalities: OutputModality[]; streaming: boolean; toolCalling: boolean; parallelToolCalls?: boolean; structuredOutput?: StructuredOutputRequirement; reasoning?: ReasoningRequirement; citations?: boolean; grounding?: boolean; contextTokens: number; expectedOutputTokens: number; toolCount: number; maxToolArgumentBytes?: number; qualityTier?: "economy" | "balanced" | "quality" | "critical"; latencyTargetMs?: number;
}
```
### Tenant 与 Workspace 输入
```typescript
interface TenantRoutingContext { tenantId: string; principalId: string; organizationId?: string; policyVersion: string; membershipVersion?: string; quotaScope: ScopeRef; credentialClass: string;
}
interface WorkspaceRoutingContext { workspaceId: string; projectId?: string; trust: ProjectTrustState; regionPreference?: string[]; dataClass: Sensitivity; configHash: string;
}
```
### Candidate
```typescript
interface RouteCandidate { id: string; provider: ProviderRef; apiFamily: ApiFamilyRef; model: CatalogModelRecord; deployment: DeploymentRef; capabilities: ModelCapabilities; limits: ModelLimits; region: RegionDescriptor; credentialCompatibility: CredentialCompatibility; health: HealthSnapshot; quota: CandidateQuotaState; quality: QualityProfile; pricing?: PricingProfile; freshness: CatalogFreshness; source: CandidateSource;
}
```
### Match 结果
```typescript
interface CapabilityMatch { compatible: boolean; required: CapabilityRequirement[]; satisfied: CapabilityMatchItem[]; missing: CapabilityMismatch[]; degraded: CapabilityDegradation[]; projection?: ProjectionCompatibility;
}
```
### RouteDecision
```typescript
interface RoutingDecision { decisionId: string; requestId: string; routeKind: "primary" | "fallback" | "hedge" | "shadow" | "canary"; selected: ResolvedModel; alternatives: RouteAlternative[]; reasonCodes: string[]; hardFilters: FilterResult[]; score: RouteScore; routeSnapshotId: string; policyVersion: string; catalogVersion: string; expiresAt?: string;
}
```
### RouteSnapshot
```typescript
interface RouteSnapshot { id: string; requestId: string; runId: string; sessionId: string; inputHash: string; tenantContextHash: string; policyVersion: string; egressPolicyVersion: string; catalogVersion: string; healthSnapshotVersion: string; quotaSnapshotVersion: string; strategy: RoutingStrategy; candidates: CandidateSnapshot[]; selectedCandidateId?: string; fallbackCandidateIds: string[]; sticky?: StickyRouteState; hedge?: HedgePlan; shadow?: ShadowPlan; canary?: CanaryAssignment; createdAt: string;
}
```
### 评分模型
```typescript
interface RouteScore { total: number; latency: number; cost: number; quality: number; reliability: number; fairness: number; residency: number; stickiness: number; penalties: ScorePenalty[]; weightsVersion: string;
}
```
## TypeScript 接口
### RoutingPort
```typescript
interface RoutingPort { resolve(input: RoutingInput): Promise<RoutingDecision>; planFallback(input: FallbackRoutingInput): Promise<RoutingDecision | undefined>; planHedge(input: HedgingInput): Promise<HedgePlan | undefined>; explain(snapshotId: string, audience: ExplanationAudience): Promise<RoutingExplanation>;
}
```
### CandidateResolver
```typescript
interface CandidateResolver { resolve(input: RoutingInput): Promise<RouteCandidate[]>; resolveExplicit(ref: ModelRef, context: ResolutionContext): Promise<RouteCandidate>;
}
```
### CatalogPort
```typescript
interface RoutingCatalogPort { resolve(ref: ModelRef, scope?: CatalogScope): Promise<CatalogModelRecord>; list(filter: CatalogFilter): Promise<CatalogModelRecord[]>; snapshot(): CatalogSnapshot; freshness(ref: ModelRef): Promise<CatalogFreshness>;
}
```
### CapabilityMatcher
```typescript
interface CapabilityMatcher { match(requirements: RoutingTaskRequirements, candidate: RouteCandidate): CapabilityMatch; explain(match: CapabilityMatch): CapabilityExplanation;
}
```
### HealthPort
```typescript
interface RoutingHealthPort { snapshot(key: HealthKey): Promise<HealthSnapshot>; record(observation: HealthObservation): Promise<void>; circuit(key: CircuitKey): Promise<CircuitState>;
}
```
### QuotaPort
```typescript
interface RoutingQuotaPort { reserve(input: RoutingQuotaReservation): Promise<QuotaLease>; settle(lease: QuotaLease, actual: RoutingUsage): Promise<void>; release(lease: QuotaLease, reason: string): Promise<void>;
}
```
### Scorer
```typescript
interface RouteScorer { score(candidate: RouteCandidate, input: RoutingInput, observations: ScoreObservations): RouteScore; rank(scored: ScoredCandidate[]): ScoredCandidate[];
}
```
### Policy 输入端口
```typescript
interface RoutingPolicyBoundary { allowedCandidates(input: RoutingInput): Promise<PolicyCandidateBoundary>; validateSelection(input: RoutingInput, decision: RoutingDecision): Promise<PolicySelectionCheck>;
}
```
该端口消费 immutable policy，而不是自己生成或放宽 policy。
## Provider、ApiFamily、Model、Deployment 与 Catalog
### 四层解析
```text
ModelRef -> provider/api family disambiguation -> catalog model record -> deployment resolution -> region/project/account resolution -> credential compatibility -> ResolvedModel
```
同一 `value` 在不同 API family 有不同含义时必须显式指定 provider 或 API family，不能依据名称猜测。
### Provider 记录
Provider record 至少包含：
；provider identity、kind、enabled、版本和可用 API family。；credential strategy、region/location 语义和原始 metadata namespace。；health probe 类型、transport 约束和默认错误分类。；不包含某个 tenant 的 allowlist；租户选择由 policy/routing 输入提供。
### ApiFamily 记录
ApiFamily record 至少包含：
；protocol、version、streaming mode 和 transport type。；message/content block 语义、tool result 顺序、structured output projection。；error/usage/finish reason 映射器版本。；provider-specific capability profile 和 conformance status。
### Model 记录
Model record 至少包含：
；基础模型身份、版本、生命周期和 catalog freshness。；input/output modalities、context window、max output、tool calling、structured output、reasoning、citation、grounding 和 safety events。；quality profile、已知限制、价格 profile 版本和可用区域。
### Deployment 记录
Deployment record 至少包含：
；resource ID、endpoint、region/location、project/account、API version。；deployment-specific capacity、quota、health、credential strategy 和 retention。；是否为 direct model、deployment、inference profile、endpoint、publisher model 或 ARN。
### Catalog 新鲜度
```typescript
interface CatalogFreshness { verifiedAt?: string; expiresAt?: string; status: "fresh" | "stale" | "unknown"; sourceVersion?: string; conformance: "passed" | "failed" | "unknown";
}
```
过期 catalog 可以用于诊断，但未知的 tool、strict structured output 或模态能力不能作为可用能力；价格过期只能返回 estimated cost。
## Capability Matching
### 能力合取
```text
effective capability = catalog capability ∩ deployment capability ∩ credential capability ∩ tenant policy ∩ workspace policy ∩ host capability ∩ egress policy ∩ current quota/health
```
Routing 计算候选的 catalog/deployment compatibility，并消费 Harness 注入的 tenant、host、egress 和 policy 结果；不能自己扩大后续能力。
### 硬能力
以下默认是硬约束：
；输入模态或输出模态不支持。；streaming 必需但候选不支持。；tool calling 或 strict structured output 必需但候选不支持。；context window 不足且不能通过 Context Runtime 安全压缩。；tool 数量、参数字节数、附件大小超过 deployment limit。；Host 无法交付必需的 streaming、approval 或 artifact capability。；egress、region、data residency 或 sensitivity 不满足 policy。
### 软能力
以下可以参与排序，但不能覆盖硬约束：
；reasoning event 是否用户可见。；citation/grounding 丰富度。；prompt caching 命中可能性。；quality tier、历史成功率和业务评测分。；latency、成本和容量稳定性。
### Projection compatibility
```typescript
interface ProjectionCompatibility { toolSchema: "native_strict" | "native_relaxed" | "unsafe" | "unsupported"; outputSchema: "native_strict" | "native_relaxed" | "prompt_only" | "unsupported"; multimodal: ProjectionStatus[]; droppedConstraints: string[]; projectionHash: string;
}
```
不可安全降级的 schema constraint 必须把候选标为不兼容，不应为了提高候选数量而删除 required 语义。
## Tenant、Workspace 与 Policy 输入
### Tenant Model Policy
```typescript
interface TenantModelPolicy { allowedProviders: string[]; allowedApiFamilies: string[]; allowedModelRefs: ModelRef[]; allowedDeployments?: string[]; allowedRegions: string[]; deniedRegions: string[]; requiredCapabilities: string[]; fallbackPolicy: FallbackPolicy; routingStrategy: RoutingStrategy; dataClassRules: DataClassEgressRule[]; maxCostPerRun?: Money; maxLatencyMs?: number;
}
```
### Workspace Policy
Workspace policy 可以收紧：
；允许的 provider/model/deployment 子集。；project trust、文件数据分类和 provider egress profile。；允许的 API family、工具能力和 context window。；任务模式对应的 cost、latency、quality 上限。
Workspace policy 不能放宽 tenant safety floor、denied region、secret/regulated egress 或 quota 上限。
### Routing 不隐藏 policy
错误流程：
```text
provider catalog -> routing silently drops policy-denied candidates -> explain says no candidate
```
正确流程：
```text
PolicySnapshot -> explicit candidate boundary with decision IDs -> Routing filters and ranks within boundary -> explanation distinguishes policy_denied from capability_mismatch
```
解释可以对用户隐藏敏感规则细节，但对 operator/audit 必须保留匹配 rule ID、版本和原因码。
## Region、Data Residency 与 Egress
### Egress 输入
```typescript
interface RoutingEgressConstraints { tenantId: string; allowedProviders: string[]; allowedRegions: string[]; deniedRegions: string[]; allowedDataClasses: Sensitivity[]; artifactOnlyClasses: Sensitivity[]; redactionProfile: string; retentionClass: string; policyVersion: string;
}
```
### 过滤顺序
```text
resource sensitivity + tenant/workspace policy + provider jurisdiction + deployment region/location + retention requirement + redaction/summary capability -> allow full | redact | summarize | artifact_only | deny
```
Routing 不执行 redaction；它只排除不能满足 egress 的候选，或选择 Harness 已经允许的 redaction profile。
### Fallback 约束
primary 故障后，fallback 必须重新检查：
；provider 和 API family allowlist。；region/location 和 data residency。；deployment retention 和 provider file semantics。；sensitivity ceiling、redaction 和 artifact-only 规则。；credential binding、quota 和成本上限。
不能因为 primary 不可用就跨区域或跨 provider 发送受限内容。
### 多模态 egress
图片、音频、视频、文档和远程 URL 需要额外检查：
；provider 是否支持对应 MIME/part。；URL 是否允许 provider 访问并通过 SSRF/redirect policy。；artifact owner、tenant、expiry 和 view 是否匹配。；base64、上传文件和 provider-side file reference 的 retention 是否符合 policy。
## 候选集生成与过滤
### 候选生成
```text
explicit ModelRef or tenant defaults -> expand provider/api family aliases -> resolve catalog records -> resolve deployments/regions -> attach credential compatibility -> attach health/quota/quality observations -> produce candidates
```
### 硬过滤顺序
1. ModelRef/provider/API family 解析。
2. tenant/workspace allowed boundary。
3. region/data residency/egress。
4. catalog freshness 和 conformance。
5. required capability matching。
6. deployment readiness 和 circuit state。
7. credential compatibility。
8. quota/rate limit reservation feasibility。
9. host delivery capability。
10. task-specific budget。
### FilterResult
```typescript
interface FilterResult { candidateId: string; stage: string; result: "kept" | "removed" | "degraded"; reasonCodes: string[]; diagnostic?: Diagnostic;
}
```
每一个 removed candidate 都应有稳定 reason code；诊断 payload 不能泄露候选的敏感 endpoint、credential 或其他租户信息。
### 无候选
无候选时按优先级返回：
；`routing_policy_denied`：策略没有允许的候选。；`routing_capability_mismatch`：能力要求无法满足。；`routing_residency_denied`：没有合规区域或外发路径。；`routing_health_unavailable`：候选均被健康/熔断排除。；`routing_quota_exhausted`：配额或预算不足。；`routing_catalog_stale`：能力事实无法可信判断。
不能把所有失败折叠为“模型不可用”。
## Latency、Cost、Quality 与 Fairness 路由
### 评分原则
评分只在硬过滤后执行：
```text
score = w_latency * normalized_latency + w_cost * normalized_cost + w_quality * quality_score + w_reliability * reliability_score + w_fairness * fairness_score + w_stickiness * stickiness_score - penalties
```
不同 quality tier 使用不同权重；权重和版本必须进入 `RouteScore.weightsVersion`。
### Latency
Latency 输入包括：
；queue wait、credential resolve、connect、TTFE、TTFT、first tool call。；stream duration、settlement、context compile 和 delivery 不应被误归为 provider latency。；p50/p95/p99、当前区域和 deployment 维度的历史样本。
没有足够样本时使用保守默认值并标记 `insufficient_observation`。
### Cost
Cost 输入包括：
；input/output/reasoning/cached tokens。；provider surcharge、远程 artifact、retry、fallback、compaction 和 shadow 成本。；pricing profile 版本和 estimated/reconciled 标记。
成本优化不能选择不满足 capability、policy 或质量底线的候选。
### Quality
Quality profile 可以来自既有 Evaluation 结果：
；task success、tool selection、structured output validity。；safety/policy compliance、context retention、citation/grounding。；provider/model/api family conformance 和 regression score。
Evaluation 分数是排序信号，不是授权；高分候选仍需 Policy/Sandbox。
### Fairness 与 noisy neighbor
公平性输入包括：
；tenant/user/workspace 当前 reservation、queue wait 和 provider quota share。；全局并发、per-tenant concurrency、weighted fair queue 和 starvation count。；共享 deployment 的热度和 retry amplification。
不得用 tenant ID 作为高基数 metric label；可以按受控 tenant 分区聚合。
## Health、Readiness 与 Circuit Breaker
### Health 维度
区分：
；liveness：adapter/transport 进程存活。；readiness：credential、endpoint、catalog 和基本调用可用。；capability readiness：目标模型支持本次请求所需能力。；quota health：429、capacity、预算和并发信号。；stream health：TTFE、EOF、sequence gap、incomplete tool call。；settlement health：usage、durable event、close 和 provider receipt。
### CircuitKey
```typescript
interface CircuitKey { provider: string; apiFamily: string; deployment: string; region: string; credentialClass: string;
}
```
必要时可以增加 tenant policy partition，但不应把所有租户共享为一个粗粒度 circuit，也不应为每个高基数 ID 创建不可运维的 circuit。
### Circuit 状态
```text
Closed -> Open on eligible consecutive/rolling failures -> HalfOpen after cooldown -> Closed on successful probe -> Open on failed probe
```
### 可熔断错误
；临时 transport、5xx、连接异常、连续 EOF 或严重 stream integrity failure。；明确 capacity failure，且有足够样本证明该 deployment 不健康。
### 不应熔断整个 provider 的错误
；schema/invalid request。；tenant policy deny、region deny、context overflow。；单个用户 credential 失效，除非 circuit key 明确绑定 credential class。；工具业务失败或模型输出业务校验失败。
### Health 采样
health observation 必须记录窗口、样本数、错误类别、延迟分位数和来源；不要从单个 429 直接推断 provider 永久不可用。
## Rate Limit、Quota 与 Budget
### 层级
```text
tenant quota -> user/workspace/project quota   -> session/run budget     -> attempt/provider/deployment reservation       -> turn/tool/context budget
```
### Reservation
```typescript
interface RoutingQuotaReservation { tenantId: string; scope: ScopeRef; candidateId: string; estimatedInputTokens: number; estimatedOutputTokens: number; estimatedCost?: Money; requestCount: number; hedgeSlots?: number; shadowSlots?: number; idempotencyKey: string;
}
```
动作前 reserve，事件后 settle；失败、取消、unknown 和 shadow 都必须结算或释放。
### 本地限流
本地 rate limit 先于 provider 请求，按 tenant/user/workspace/provider/deployment 分层；可以使用 token bucket、并发 semaphore 或等价端口。
### Retry 与 quota
每次 retry、fallback、hedge 都要预留额外 budget；没有足够 retry budget 时返回 `retry_budget_exhausted`，不能无限等待 provider 429。
### 超卖防护
并发 reservation 必须原子；shadow 和 hedge 默认使用低优先级、受限配额；一租户 burst 不能占满全局 provider connection、event queue 或 worker。
## Sticky Routing
### 用途
Sticky routing 用于：
；provider prompt cache 或 server-side conversation 的复用。；session/branch 的缓存局部性和一致的 provider metadata。；降低模型切换造成的行为漂移。
### StickyKey
```typescript
interface StickyKey { tenantId: string; workspaceId?: string; sessionId?: string; branchId?: string; taskClass?: string; capabilityFingerprint: string;
}
```
### Sticky 状态
```typescript
interface StickyRouteState { keyHash: string; candidateId: string; reason: "session_affinity" | "cache_affinity" | "conversation_state"; issuedAt: string; expiresAt?: string; invalidation: StickyInvalidation[];
}
```
### 失效条件
；provider/deployment health 或 circuit 不可用。；policy、egress、region、membership、credential 或 capability 变化。；model/toolset/context contract 变化导致 fingerprint 不同。；session branch 或 server-side conversation state 不再兼容。；sticky TTL 到期。
Sticky 不能绕过新 policy，也不能因为“保持粘性”继续使用不合规区域。
## Request Hedging
### 适用条件
Request hedging 只适合：
；只读、可安全重复的模型采样。；primary 超过历史 latency threshold 且仍有预算。；两个候选 capability、policy、egress 和 output contract 等价。
### 不适用条件
；provider-side 可能触发不可逆副作用的 hosted action。；不支持幂等或无法区分两个响应的 server-side conversation 写入。；已接近 tenant quota、cost 或 concurrency 上限。；会产生大量敏感数据外发或跨区域重复发送。
### HedgePlan
```typescript
interface HedgePlan { hedgeId: string; primaryAttemptId: string; secondaryCandidateId: string; trigger: "ttfe_timeout" | "latency_percentile" | "capacity_signal"; delayMs: number; maxParallel: 2; winnerRule: "first_valid_terminal" | "quality_then_latency"; cancelLoser: boolean; budgetReservationId: string;
}
```
### Winner 规则
；`first_valid_terminal` 只接受完整、未拒答、能力兼容、schema 可校验的结果。；`quality_then_latency` 需要等待有限窗口比较质量信号，不得把最终用户等待无限延长。；winner durable commit 后，loser 取消；loser 已产生的 usage/cost 和 unknown cancel 状态仍需记录。
## Retry Budget 与 Attempt 语义
### 四种重试
```text
Transport retry: 同一安全请求、同一 Attempt 内
Agent retry: 修改 context/generation/output contract，新的 Attempt
Fallback: 换 provider/model/deployment，新的 Attempt
Tool retry: 由 Tool Runtime 控制，不由 Routing 代替
```
### RetryBudget
```typescript
interface RetryBudget { maxTransportRetries: number; maxAgentRetries: number; maxFallbacks: number; maxHedges: number; maxElapsedMs: number; maxAdditionalCost?: Money; reserveTokens: number; consumed: RetryConsumption;
}
```
### Retry 决策
```typescript
interface RoutingRetryDecision { action: "retry_transport" | "retry_modified" | "fallback" | "hedge" | "wait" | "stop"; reasonCode: string; delayMs?: number; nextRoute?: RoutingDecision; budgetAfter: RetryBudget;
}
```
### Attempt 不变量
；fallback、modified request 和 hedge attempt 使用新的 attempt ID。；失败 attempt 的 usage、latency、cost 和 route snapshot 不能丢。；provider request ID 与 attempt ID 分开。；不能因为 UI 只看到最终答案而隐藏失败尝试。；已可能成功的 provider-side write 不得盲目重放。
## Fallback 与 Context Overflow
### Fallback 流程
```text
primary attempt failed -> classify normalized error -> verify retry budget -> load tenant/workspace fallback policy -> filter capability/region/egress/quota -> reserve quota -> create new route snapshot -> persist ModelChange/FallbackSelected -> create new Attempt -> invoke Provider Runtime
```
### Fallback 分类
；`retry_same`：安全 transport retry，仍在同一 attempt 内。；`retry_modified`：需要 Context/Prompt 或 generation 修改。；`fallback`：切换 route candidate。；`wait`：等待 rate limit/circuit cooldown，受 deadline 约束。；`stop`：不具备安全、预算或能力条件。
### Context Overflow
```text
local estimator overflow or provider context error -> persist AttemptFailed(context_overflow) -> preserve request/context/toolset hashes and usage -> ask Context Runtime for CompactionPlan -> verify tool call/result pairs and required state -> compile new ModelRequest -> route again with new context fingerprint -> create new Attempt
```
Routing 不随机删除历史、不切断 tool call/result 对、不把更小窗口 fallback 静默当作同等能力。
### Window 选择
候选必须满足：
```text
context window >= selected input context + expected output reserve + reasoning reserve + tool result reserve + safety margin
```
若只有更小窗口候选，必须由 Context/Harness 明确生成新 context hash，并把“压缩后路由”作为可解释变化。
## Tool、Structured Output 与多模态兼容
### Tool compatibility
路由需要检查：
；tool calling 是否支持。；parallel tool call 是否由 provider 支持；即使支持，并行执行仍由 Tool Scheduler 决定。；tool schema projection 是否安全。；最大 tool 数、参数字节、嵌套深度和名称限制。；Tool result status 是否能表达 denied、cancelled、unknown。；provider block/item 顺序是否能保留 call ID 和 result 顺序。
### Structured output
```typescript
interface StructuredOutputRequirement { schema: JsonSchema; strict: boolean; name?: string; validationVersion: string;
}
```
候选排序前判断 native strict、native relaxed、prompt-only 或 unsupported；strict 请求不得自动接受 prompt-only，除非产品策略明确允许并改变验收标准。
### 多模态
```typescript
interface ModalityCompatibility { kind: "image" | "audio" | "video" | "document"; input: "native" | "projected" | "unsupported"; output: "native" | "projected" | "unsupported"; maxBytes?: number; maxParts?: number; projectionHash?: string;
}
```
不支持的模态应返回 typed capability error；摘要降级由 Context Runtime 生成，Routing 只选择支持该 projection 的候选。
### Provider 差异
；OpenAI Responses、Chat Completions、Realtime 作为独立 API family。；Anthropic Messages 保留 content block、tool use/result 和 thinking 顺序。；Gemini 原生 `Content/Part` 与兼容端点分离。；Bedrock Converse、InvokeModel、profile/ARN 使用独立 deployment/API family。；Azure deployment name、endpoint、api version 单独解析。；Vertex publisher model、endpoint resource、project/location 和 Developer API 不能混用。
## Shadow、Canary 与版本发布
### Shadow
Shadow 只复制经过脱敏和最小化的请求：
```text
primary request executes -> sanitized fixture / recorded context -> shadow candidate with dry-run or fake tools -> compare route, events, final schema, latency and cost
```
Shadow candidate 不得执行真实工具、外部 webhook、邮件、部署或其他 side effect；provider egress 仍需重新评估。
### ShadowPlan
```typescript
interface ShadowPlan { shadowId: string; candidateId: string; sampleRate: number; inputProjection: "redacted" | "summary" | "artifact_ref"; toolMode: "disabled" | "fake" | "dry_run"; compare: string[]; retentionClass: string;
}
```
### Canary
Canary 需要：
；小流量、低风险任务和显式 tenant/workspace allowlist。；与 primary 相同或更严格的 policy、sandbox、egress 和 quota。；自动回滚条件：安全失败、schema 回归、unknown outcome、cost/latency 越界或 provider drift。；assignment、版本、分流 key 和回滚结果进入 route snapshot/audit。
### Route version
路由规则、权重、catalog、health classifier、quality profile、pricing profile 和 policy schema 都需要版本；运行中版本变化只影响新 attempt，除非显式重新路由并记录。
## Route Snapshot 与 Explainability
### Snapshot 必须回答
；输入请求要求了什么能力、模态、窗口、质量和延迟目标。；哪些 tenant/workspace/egress/policy 约束生效。；catalog、health、quota、pricing 和 scoring 版本是什么。；哪些候选被过滤，原因是什么。；最终选择和 fallback/hedge/canary/shadow 计划是什么。；发生了哪些 retry、route change、circuit 和 quota reservation。
### Explainability 接口
```typescript
interface RoutingExplanation { decisionId: string; audience: "user" | "operator" | "audit"; summary: string; selected: ExplanationCandidate; rejected: ExplanationRejectedCandidate[]; scoreBreakdown?: RouteScore; matchedPolicies: PolicyRuleRef[]; diagnostics: Diagnostic[]; redactionState: string;
}
```
### Audience 规则
；user：显示 provider/model/deployment 的必要摘要、区域/质量/延迟原因，不泄露敏感策略、credential 或其他候选的秘密。；operator：显示候选过滤、health、quota、版本和 score breakdown 的脱敏信息。；audit：保存完整 reason code、rule ID、snapshot hash、action correlation 和数据驻留结论。
### Explainability 不变量
解释必须由 snapshot 重建，不能由模型或 UI 自由生成；selected route 与执行的 `ResolvedModel`、request hash、policy version 和 egress snapshot 必须一致。
## 生命周期与状态机
### Route Request 状态机
```text
Received -> Normalized -> PolicyBoundaryLoaded -> CandidatesResolved -> CapabilityChecked -> ResidencyChecked -> HealthChecked -> QuotaReserved -> Scored -> Selected -> SnapshotCommitted -> HandedToModelRuntime -> Settled
任一活动状态 -> Failed
Selected -> Replanning
Replanning -> Selected | Failed
```
### Candidate 状态机
```text
Discovered -> CatalogResolved -> PolicyEligible -> CapabilityCompatible -> EgressCompatible -> HealthReady -> QuotaAvailable -> Scored -> Selected | Fallback | Shadow | Rejected | Expired
```
### Circuit 状态机
```text
Closed -> Open -> HalfOpen -> Closed                   -> Open
```
### Hedge 状态机
```text
Planned -> WaitingTrigger -> PrimaryRunning -> SecondaryStarted -> WinnerCommitted -> LoserCancelled -> Settled
```
### Route invariants
；`RouteSnapshot` 提交后不可变。；Policy、egress、catalog、health、quota 版本必须可追溯。；`Selected` 前必须完成 capability、residency、health 和 quota preflight。；Fallback/hedge 必须重新执行硬过滤。；Circuit open 不能通过 sticky 强行绕过。；取消后不再开始新的 hedge/fallback attempt。
## 端到端决策流程
1. Host/Harness 接收请求并认证 principal、tenant、workspace、session 和 run。
2. Harness 冻结 `TenantContext`、`PolicySnapshot`、`EgressSnapshot`、host capabilities 和 budget。
3. Routing Normalizer 校验 requested `ModelRef`、API family、task requirements、streaming、tools、modalities 和 output contract。
4. Candidate Resolver 从 tenant defaults、workspace defaults 或显式 ModelRef 解析 provider/API family/model/deployment。
5. Catalog View 加载能力、limits、pricing、region、freshness 和 conformance。
6. Policy Boundary 返回允许候选边界与 decision IDs；Routing 不自行修改。
7. Capability Matcher 过滤工具、structured output、窗口、模态和 provider metadata 需求。
8. Residency/Egress Filter 过滤 provider jurisdiction、region/location、sensitivity、artifact/file 和 retention 不兼容项。
9. Health/Circuit Filter 过滤不可用 deployment；区分 liveness、readiness、capacity 和 stream health。
10. Quota Guard 预留 token、cost、request、hedge/shadow slot 和并发。
11. Sticky Planner 尝试复用合法候选；失效时生成 diagnostic。
12. Scorer 根据 latency、cost、quality、reliability、fairness 和策略权重排序。
13. Hedging/Canary/Shadow Planner 生成受预算和 policy 限制的辅助计划。
14. 生成 `RouteSnapshot`、`RoutingDecision`、`RoutingExplanation`。
15. Durable commit route selection/model change 后，把 `ResolvedModel` 交给 Provider Runtime。
16. Provider Runtime 编译请求并发送；Routing 不进入 raw stream parser。
17. Attempt 结束后记录 usage、cost、health observation、quota settlement 和 result validity。
18. 失败时按 retry budget、error taxonomy 和 fallback policy 重新路由或停止。
19. Run terminal 前确保 route/attempt/usage/fallback durable settlement 完成。
### 关键决策表
| 情况 | Routing 决策 |
|---|---|
| ModelRef 无法解析 | 返回 `invalid_model_ref`，不猜测 |
| Provider 允许但 workspace 拒绝 | `policy_denied`，不暴露为可选候选 |
| Tool schema 无法安全投影 | capability mismatch，停止该候选 |
| context window 不足 | 交给 Context compaction，再新 Attempt |
| region 不合规 | residency deny，不跨区 fallback |
| circuit open | 排除对应 route，尝试合规替代 |
| quota 不足 | wait、降级或 stop，不能超卖 |
| primary 429 | transport/agent/fallback 按预算分类 |
| primary 结果 unknown | 不盲目 hedge/fallback 可能副作用请求 |
| Host 无多模态交付 | 排除需要该交付的候选 |
| sticky 候选不健康 | 失效 sticky，重新排序 |
| shadow 请求敏感 | redaction/artifact-only 或 deny |
| canary 安全指标越界 | 停止分流并回滚版本 |
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### 与 Model Runtime 集成
```text
RoutingDecision -> RouteSnapshot -> ResolvedModel + CredentialLeaseRef + EgressSnapshot -> ModelRequest -> Provider Adapter / Transport
```
Provider Runtime 只消费已解析、已冻结的 route；adapter 不调用 `RoutingPort`，不自行 fallback。
### 与 Prompt 集成
Prompt Compiler 消费 effective capabilities：
；只有候选支持 reasoning channel 才加入相关说明。；只有 structured output projection 可用才声明 schema 行为。；只有 tool calling 可用才描述 tool protocol。；没有模态或 host delivery capability 时删除相关指令。；Prompt 可以解释当前 provider/deployment/region 的可观察限制，但不能声称 policy 已允许未授权动作。
### 与 Context 集成
Context Compiler 在 routing 之前或与 routing 交替工作：
；使用 catalog limits 计算 usable input budget。；根据 egress、sensitivity、tenant policy 选择可发送资源。；生成 context hash、artifact projection、redaction profile 和 modality projection。；context overflow 时生成 CompactionPlan，路由使用新的 context fingerprint。
Routing 不负责选择历史、memory 或 artifact range；它只验证候选能承载 ContextPlan。
### 与 Tool 集成
```text
ActiveToolset -> ToolSchemaProjector(candidate capabilities) -> projected tool definitions -> ModelRequest -> normalized ToolCall -> Tool Runtime validation/policy/execute -> ToolResult -> provider result projection
```
Routing 验证 schema projection compatibility，但不做工具业务校验、授权或执行。
### 与 State/Memory 集成
State 至少保存：
；`RouteSelectedEntry`、`ModelChangeEntry`、`AttemptStartedEntry`、`AttemptFailedEntry`、`FallbackSelectedEntry`。；route snapshot ID/hash、catalog/health/quota/policy/egress versions。；sticky、hedge、shadow、canary assignment。；request/context/toolset/projection hashes。；usage/cost、retry budget、unknown outcome 和 recovery diagnostic。
Memory 不能决定 provider 授权；memory 只能作为 Context 候选，必须重新做 tenant/sensitivity/egress 过滤。
### 与 Policy 集成
Policy Engine 先决定：
；provider、API family、model、deployment、region 是否允许。；数据类、retention、credential、fallback 和 egress 限制。；quota、quality/latency 上限、shadow/canary 是否允许。
Routing 只能在 immutable policy boundary 内排序和选择。若 `validateSelection` 失败，必须回到候选过滤，而不是覆盖 policy。
### 与 Harness 集成
Harness 负责：
；bootstrap tenant/workspace/policy/egress/catalog/credential。；创建 run scope、budget tracker、quota lease 和 event router。；冻结 route/config snapshot，监督 retry/fallback/hedge/canary/shadow。；将 route/attempt/usage/failure 写入 durable state。；在崩溃后恢复 sticky、pending fallback、quota、unknown outcome 和 provider status。；在最终交付前等待 durable route settlement 与关键 projector。
### 与 Event/Observability 集成
```text
Routing Decision -> Harness Event -> State Entry / Projector -> Trace / Metric / Audit -> Host Explanation Projection
```
Host 可以展示简化 explanation，但不能自行计算候选、推断 fallback 或修改 route truth。
## 失败恢复与未知结果
### 错误分类
```text
routing_invalid_model_ref
routing_catalog_stale
routing_capability_mismatch
routing_policy_denied
routing_residency_denied
routing_credential_unavailable
routing_health_unavailable
routing_circuit_open
routing_quota_exhausted
routing_rate_limited
routing_retry_budget_exhausted
routing_context_overflow
routing_snapshot_conflict
routing_selection_expired
routing_provider_unknown_outcome
routing_canary_rollback
```
### 进程崩溃恢复
```text
load last checkpoint -> load RouteSnapshot and Attempt records -> verify tenant/policy/egress/catalog versions -> inspect provider request/response receipt -> query provider-side status if available -> classify completed/failed/unknown -> settle quota and usage -> invalidate unsafe sticky/hedge plan -> resume, fallback or require manual action
```
### Unknown outcome
；普通模型采样通常没有业务副作用，可按安全 retry policy 重试，但仍记录 unknown transport outcome。；provider-side batch/file/job 或 hosted action 先 query status。；可能触发外部副作用的请求不得自动 hedge 或 fallback 重放。；无法确认时写 `UnknownOutcomeEntry`，保留 request hash、route snapshot、credential class 和 external receipt reference。
### Route snapshot 过期
恢复时若 policy、egress、catalog、health、quota、credential 或 workspace trust 变化：
1. 标记旧 snapshot `expired`。
2. 不直接继续调用旧 deployment。
3. 重新构建 RoutingInput。
4. 重新执行 capability/residency/quota checks。
5. 创建新 route snapshot 和新 attempt。
### Circuit 恢复
half-open probe 必须：
；使用低成本、低风险、符合 policy 的 probe。；不发送不必要敏感上下文。；记录 probe route、结果和 cooldown。；probe 失败不触发无限 fallback 风暴。
## 安全、隐私与数据外发
### Trust Boundary
Provider Routing 涉及：
；Host/用户认证边界。；tenant/workspace policy 边界。；provider/API family/deployment 边界。；region/data residency 边界。；credential/secret 边界。；catalog/health/quality 外部事实边界。；shadow/canary 和观测数据边界。
### 不可信输入
以下不能直接影响授权：
；模型生成的 provider、model、deployment、region 或 tenant 参数。；workspace 文档、RAG、tool result、MCP 描述提出的路由要求。；provider metadata 声称的“已批准”“低成本”或“可安全外发”。；Host 控制事件提交的未经认证的 route override。
### Secret
；credential 只通过 `CredentialLease`、broker 或签名 transport 使用。；route snapshot 记录 credential class/reference hash，不记录明文 token。；provider endpoint、region 和 deployment 诊断按 sensitivity 脱敏。；shadow、trace、evaluation fixture 不复制 bearer token、API key、cookie 或 secret artifact。
### Redaction 与 Egress
```text
ContextResource sensitivity + tenant policy + provider jurisdiction/deployment + region/location + purpose/retention + redaction profile -> allow | redact | summarize | artifact_only | deny
```
Routing 不能把 `artifact_only` 当作“可以发送 raw artifact URL”；必须消费 EgressSnapshot 中的显式 view/reference 结果。
### 多租户
；RoutingInput 的 tenant context 必须来自认证，不得从模型参数读取。；candidate catalog、health、quota、cache 和 sticky state 必须带 tenant/scope boundary。；provider prompt cache、compiled context cache 和 route cache 默认禁止跨 tenant 共享。；operator explanation、diagnostic snapshot 和 replay 重新授权并审计。
### Fail-closed
以下情况默认拒绝或暂停：
；tenant、workspace、policy、egress 或 data class 无法解析。；credential scope 无法限定。；region/data residency 事实未知且策略要求强保证。；candidate capability 或 catalog freshness 不可信。；route snapshot 无法 durable commit。；shadow/canary 无法证明不会产生副作用。；quota reservation 不可验证或跨租户 owner 不匹配。
## 可观测性与运营
### Route Trace 层级
```text
session span -> run span   -> routing span     -> candidate resolution span     -> capability match span     -> policy/egress filter span     -> health/quota span     -> scoring span     -> snapshot commit span   -> attempt/model span     -> transport/normalize span   -> retry/fallback/hedge span   -> usage settlement span
```
### 必备字段
```text
trace_id
session_id
run_id
turn_id
attempt_id
request_id
route_decision_id
route_snapshot_id
provider/api_family/model/deployment hash
region/location
catalog_version
policy_version
egress_version
health_snapshot_version
quota_snapshot_version
capability fingerprint
context/toolset/projection hash
score weights version
sticky/hedge/shadow/canary IDs
retry/fallback count
usage/cost
latency breakdown
error category
redaction state
```
### 指标
；candidate count、hard filter count、no-candidate rate。；capability mismatch、policy deny、residency deny、catalog stale 比例。；selected route、fallback、retry、hedge、sticky hit/miss、shadow/canary exposure。；TTFE、TTFT、first tool call、stream、settlement 和 end-to-end latency。；provider 429、5xx、capacity、auth、overflow、unknown outcome。；route success、task success、tool/schema validity、quality score。；cost per run、cost per success、retry amplification、hedge waste、shadow cost。；quota reservation/settlement drift、circuit open duration、queue wait、starvation。
Metric label 使用 provider、api family、model class、region class、error category 等低基数维度；tenant/user/request/path 使用 trace 或受控分区聚合。
### Audit
Audit 需要回答：
；谁在什么 tenant/workspace/session/run 下请求了什么能力。；policy/egress/catalog/health/quota 哪些版本参与了决策。；哪些候选被过滤、最终选择谁、是否发生 fallback/hedge/canary/shadow。；请求发送到哪个 provider/region/deployment，数据是什么敏感度和 view。；是否发生 quota override、circuit probe、unknown outcome 或安全降级。
### Diagnostic Snapshot
```typescript
interface RoutingDiagnosticSnapshot { routeSnapshotId: string; runId: string; selected?: string; candidates: CandidateDiagnosticView[]; activeCircuit?: CircuitDiagnosticView[]; quota: QuotaDiagnosticView; policyVersion: string; egressVersion: string; retryBudget: RetryBudget; recentFailures: Diagnostic[]; redactionState: string;
}
```
默认 metadata-only、短 TTL、重新授权；不显示 secret、完整 prompt、原始 headers 或跨租户候选细节。
## 测试与 Evaluation 策略
### Testkit
```text
FakeCatalog
FakeRoutingPolicy
FakeEgressPolicy
FakeHealthPort
FakeCircuitBreaker
FakeQuotaPort
FakeCredentialCompatibility
DeterministicClock
DeterministicIds
ScriptedLatency
ScriptedUsage
ScriptedQualityProfile
RouteDecisionRecorder
CrashInjector
ReplayRunner
FakeModelProvider
SideEffectRecorder
```
### 单元测试
；ModelRef、ApiFamily、Deployment、region 和 project/account 解析。；capability intersection、schema projection、window/budget 计算。；policy boundary 不放宽、workspace 收紧、residency filter 和 egress decisions。；score normalization、weights version、tie-break 和 deterministic rank。；sticky key、TTL、失效和 policy change。；hedge trigger、winner/loser、budget reserve 和 cancellation。；retry budget、fallback classification、circuit transitions。；route snapshot hash、explanation redaction 和 version mismatch。
### Contract 测试
每个 provider/API family catalog profile 运行：
；普通文本、stream、tool call、多工具和 structured output。；多模态 projection、finish reason、safety/refusal、usage。；429/5xx/EOF/abort/context overflow/unknown event。；credential refresh、region/deployment resolution 和 capability mismatch。；raw fixture 脱敏、request hash、provider metadata 和 error taxonomy。
### Scenario 测试
至少覆盖：
1. 显式 ModelRef 成功解析。
2. tenant allowlist 拒绝 provider。
3. workspace 收紧 model/region。
4. strict structured output 只选择 strict candidate。
5. tool schema projection 不安全时拒绝候选。
6. image/document 不支持时 typed capability error。
7. primary 429 后有限 fallback。
8. circuit open 后不使用 sticky candidate。
9. quota reservation race 不超卖。
10. context overflow 后 compaction + new Attempt。
11. hedge 只用于安全采样并取消 loser。
12. shadow 使用 fake/dry-run tool，不产生真实 side effect。
13. canary 回滚条件触发。
14. route snapshot 版本变化后恢复重新路由。
15. unknown provider-side outcome 不盲目重放。
16. 多租户 cache 不命中、不串线。
17. region fallback 重新执行 residency policy。
18. host capability 不足时排除不兼容候选。
19. usage/cost 包含 retry/fallback/hedge/shadow。
20. explanation 对 user/operator/audit 的脱敏不同。
### Fault injection
在以下边界注入故障：
；catalog refresh 前后、catalog stale。；policy load、egress check、quota reserve、snapshot append。；credential resolve/refresh、connect、first event、stream EOF。；health observation、circuit transition、provider 429/5xx。；context compaction、hedge start、winner commit、loser cancel。；side effect unknown、host disconnect、process crash、projector lag。
### Evaluation 断言
每个 route scenario 至少同时断言：
；candidate filters 和 reason codes。；selected provider/model/deployment/region。；capability、policy、egress 和 quota 事实。；route snapshot/config/policy/catalog version。；attempt、retry、fallback、hedge 和 usage/cost。；final model/tool behavior、state entries 和 negative side effect。；recovery 后不重复不可逆副作用。
LLM judge 只能评估开放式最终解释或质量，不得判断 route 是否获准、quota 是否超卖、事件顺序或副作用是否发生。
### Shadow/Canary 评测
；Shadow 只使用脱敏 fixture、fake/dry-run tool、独立 quota 和独立 trace。；Canary 使用 hard safety assertions、schema/trajectory/state/side-effect oracle、自动回滚阈值。；provider/model/policy/catalog/weights/dataset 版本全部进入 baseline。；不能以 candidate 文本高分抵消未授权外发、secret、cross-tenant 或重复副作用。
## 反模式
1. Routing 在 adapter 内偷偷 fallback。
2. Routing 通过 prompt 或模型参数读取 tenant ID。
3. Routing 把 capability mismatch、policy deny 和 residency deny 混成一个错误。
4. 只按模型名称选择，不解析 deployment、region、API family。
5. 只使用 catalog 静态能力，不检查 deployment、host、egress 和 quota。
6. workspace 可以绕过 tenant provider allowlist 或 data residency。
7. sticky 路由绕过新 policy、circuit 或 credential 失效。
8. 对不可安全重复的请求启用 hedging。
9. hedge/fallback 没有额外 budget 和 usage 归因。
10. 429 后无限 retry 或创建 fallback 风暴。
11. context overflow 时 adapter 随机删除历史。
12. fallback 到更小窗口模型却不重建 context/hash。
13. provider safety filter 被当作本地 Policy。
14. shadow 调用真实工具或外部 webhook。
15. canary 分流放宽安全策略。
16. route snapshot 只保留最终选择，不保留被过滤候选和原因。
17. explanation 由模型生成，无法由 snapshot 重建。
18. circuit key 过粗造成全局雪崩，或过细导致无法运营。
19. 失败 attempt 的 usage/cost 被丢弃。
20. quota 在任务结束才结算，允许并发超卖。
21. provider/API family 共用最低公分母，丢失 block、reasoning、citation 和 safety metadata。
22. OpenAI-compatible 被当作完整兼容。
23. region fallback 不重新检查 egress。
24. 未知 provider-side outcome 自动 hedge 或重放。
25. 只测试最终文本，不测试 route snapshot、事件、状态和恢复。
## 实施清单
### 契约与候选
；[ ] 定义 `RoutingInput`、`RoutingTaskRequirements`、`RouteCandidate`、`RoutingDecision`。；[ ] 定义 ProviderRef、ApiFamilyRef、ModelRef、DeploymentRef 和 CatalogModelRecord。；[ ] 定义 `ModelCapabilities`、`ModelLimits`、`CapabilityMatch` 和 projection compatibility。；[ ] 实现 explicit ModelRef 与 tenant default 的解析规则。；[ ] 记录 catalog freshness、conformance、pricing 和 region provenance。
### Policy、Egress 与租户
；[ ] 定义 immutable `TenantModelPolicy`、`PolicyCandidateBoundary` 和 `EgressSnapshot`。；[ ] workspace 只能收紧 tenant policy。；[ ] provider、model、deployment、region、data residency 和 credential scope 在路由前过滤。；[ ] candidate remove/degrade 原因码稳定且可解释。；[ ] tenant、workspace、session、run、attempt scope 贯穿所有 port。
### 评分与可靠性
；[ ] 实现 latency、cost、quality、reliability、fairness score。；[ ] 记录 weights version、normalization 和 tie-break。；[ ] 实现 health/readiness/capability/quota/stream/settlement 维度。；[ ] 实现 circuit key、Closed/Open/HalfOpen 和 probe。；[ ] 实现 local rate limit、quota reservation/settlement/release。；[ ] 实现 retry budget、transport retry、agent retry、fallback 分离。
### Sticky、Hedge、Shadow、Canary
；[ ] 定义 sticky key、TTL、失效和重新验证。；[ ] 只为安全、可重复请求启用 hedging。；[ ] 记录 hedge winner/loser、cancel、usage 和额外成本。；[ ] Shadow 使用脱敏输入、fake/dry-run tool 和独立配额。；[ ] Canary 使用小流量、hard safety gate、自动回滚和审计。
### Snapshot 与解释
；[ ] 实现不可变 `RouteSnapshot`、input hash、candidate snapshot 和 selected/fallback IDs。；[ ] 保存 policy/catalog/health/quota/egress/config 版本。；[ ] 提供 user/operator/audit 三种 explanation。；[ ] Explanation 从 snapshot 重建，不由模型自由生成。；[ ] route selection、model change、fallback、circuit、quota 和 unknown outcome 写 durable entries。
### 集成与恢复
；[ ] 与 Model Runtime 的 `ResolvedModel`、CredentialLease、ModelRequest 集成。；[ ] 与 Prompt/Context 的 capability、budget、egress、compaction 和 projection 集成。；[ ] 与 Tool Runtime 的 schema projection、tool result order 和 status 集成。；[ ] 与 Policy/Sandbox 集成，明确 Routing 不替代真实权限。；[ ] 与 Harness 的 RunScope、BudgetTracker、EventRouter、Checkpoint 和 RecoveryCoordinator 集成。；[ ] 实现 route snapshot 过期、catalog stale、quota conflict、provider unknown outcome recovery。
### 测试与运营
；[ ] 建立 FakeCatalog、FakeHealth、FakeQuota、ScriptedLatency、DeterministicClock/IDs。；[ ] 建立每个 API family 的 provider conformance fixture。；[ ] 覆盖 stream、tool、structured output、多模态、429/5xx/EOF/abort/overflow。；[ ] 覆盖 residency、cross-tenant、cache、secret、shadow/canary 和 policy deny。；[ ] 覆盖 route snapshot replay、crash、unknown outcome、hedge cancel 和 fallback。；[ ] 建立 route/attempt/usage/cost/circuit/quota SLO 和 diagnostic snapshot。
## 五个参考项目的启发来源
### Pi
；headless agent loop、统一 provider event、EventStream 与最终结果并存，启发 Routing 只输出 provider-neutral decision，不把 Host 绑进 provider 协议。；session tree、steering/follow-up 和 compaction entry，启发 route/model change、attempt 和 context overflow 必须可恢复、可审计。；CLI/TUI/RPC 共用 runtime，启发 routing snapshot 和 ModelPort 应位于 Host 之下。
### Grok Build
；HTTP、协议转换、sampler 和 actor 分层，启发 candidate resolution、adapter、health 和 attempt 分离。；permission decision、folder trust、sandbox 和路径锁，启发 tenant/workspace policy、egress 和真实执行边界不能由 Routing 代替。；并行工具、路径级锁、输出限制和独立 trace，启发 hedge/parallel 预算、usage 归因和安全恢复。
### OpenCode
；provider、session、message/part、server/client 和 durable event/projector 分离，启发 RouteSnapshot、ModelChangeEntry、Attempt projector 和多客户端解释。；permission/tool/provider 模块分离，启发 Routing 负责选择，不负责隐藏 policy 或执行权限。；snapshot/patch/revert 方向启发 route/config 版本与恢复时的基线验证。
### Claude Code
；permission modes、hooks、skills、subagents、memory 和计划工作流，启发不同模式下 capability/context/policy 共同参与模型选择。；项目规则、auto memory、后台任务和子 Agent 方向，启发 workspace/tenant scope、最小上下文和子调用预算隔离。；公开能力与安全语义以现有本地文档中标注的官方资料为准，辅助源码不作为规范。
### OpenClaw
；AgentHarness registry、agent-core、provider runtime 和 Gateway/channel 分层，启发 Routing registry、runtime factory 与 Host 解耦。；tool、sandbox、elevated 的独立层次，启发路由选择、权限授权、执行隔离和高权限通道分离。；后台运行、memory flush、Gateway/channel session key 和事务化插件注册，启发 sticky/session routing、background recovery、scope isolation 和注册失败回滚。
本设计的实现审查应回到当前目录已有参考文档和其记录的源码范围；若新增 provider、API family、价格、区域、合规或路由算法，应补充一手证据、版本、迁移方案和契约测试。
